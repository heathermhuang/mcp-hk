"""Version-isolated typed schemas. Schema names are derived, never caller SQL."""

import hashlib
import re

TABLES = {
    "entities": "entity_id kind scope domicile org_type name1 name2 chinese_name inc_raw inc_date inc_precision dissolved_raw dissolved_date dissolved_precision dissolution_mode source_modified incorporation_checked sfc_checked".split(),
    "entity_identifiers": "entity_id namespace value source_column".split(),
    "entity_names": "fact_id entity_id language display_name search_key name_kind until_raw until_date until_precision source_modified".split(),
    "officer_appointments": "source_id company_id officer_id role_id start_raw start_date start_precision end_raw end_date end_precision joined_year source_code source_modified".split(),
    "licences": "source_id company_id registered_institution activity_id start_raw start_date start_precision end_raw end_date end_precision source_modified".split(),
    "licence_relationships": "source_id company_id person_id role_code activity_id start_raw start_date start_precision end_raw end_date end_precision source_modified".split(),
    "source_references": "family code label".split(),
}


def schema_name(version):
    if not isinstance(version, str) or not re.fullmatch(
        r"[a-zA-Z0-9._-]{1,100}", version
    ):
        raise ValueError("Invalid dataset version")
    return "curated_" + hashlib.sha256(version.encode()).hexdigest()[:24]


META = """
CREATE SCHEMA IF NOT EXISTS curated;
CREATE TABLE IF NOT EXISTS curated.dataset_versions (
 version text PRIMARY KEY, schema_name text UNIQUE NOT NULL,
 state text NOT NULL CHECK(state IN ('staging','validated','published')),
 manifest jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 validated_at timestamptz, restore_proof jsonb
);
CREATE TABLE IF NOT EXISTS curated.published_releases (
 pack text PRIMARY KEY, version text NOT NULL REFERENCES curated.dataset_versions(version),
 published_at timestamptz NOT NULL DEFAULT now()
);
"""

DDL = """
CREATE TABLE entities (
 entity_id bigint PRIMARY KEY, kind text NOT NULL CHECK(kind IN ('organisation','person')),
 scope text[] NOT NULL, domicile integer, org_type integer,
 name1 text NOT NULL, name2 text, chinese_name text,
 inc_raw text, inc_date date, inc_precision text NOT NULL,
 dissolved_raw text, dissolved_date date, dissolved_precision text NOT NULL,
 dissolution_mode integer, source_modified text, incorporation_checked text, sfc_checked text
);
CREATE TABLE entity_identifiers (
 entity_id bigint NOT NULL REFERENCES entities, namespace text NOT NULL,
 value text NOT NULL, source_column text NOT NULL,
 PRIMARY KEY(entity_id, namespace, value)
);
CREATE TABLE entity_names (
 fact_id text PRIMARY KEY, entity_id bigint NOT NULL REFERENCES entities,
 language text NOT NULL, display_name text NOT NULL, search_key text COLLATE "C" NOT NULL,
 name_kind text NOT NULL, until_raw text, until_date date,
 until_precision text NOT NULL, source_modified text
);
CREATE TABLE officer_appointments (
 source_id bigint PRIMARY KEY, company_id bigint NOT NULL REFERENCES entities,
 officer_id bigint NOT NULL REFERENCES entities, role_id integer NOT NULL,
 start_raw text, start_date date, start_precision text NOT NULL,
 end_raw text, end_date date, end_precision text NOT NULL,
 joined_year integer, source_code integer, source_modified text
);
CREATE TABLE licences (
 source_id bigint PRIMARY KEY, company_id bigint NOT NULL REFERENCES entities,
 registered_institution integer NOT NULL, activity_id integer NOT NULL,
 start_raw text, start_date date, start_precision text NOT NULL,
 end_raw text, end_date date, end_precision text NOT NULL, source_modified text
);
CREATE TABLE licence_relationships (
 source_id bigint PRIMARY KEY, company_id bigint NOT NULL REFERENCES entities,
 person_id bigint NOT NULL REFERENCES entities, role_code integer NOT NULL,
 activity_id integer NOT NULL,
 start_raw text, start_date date, start_precision text NOT NULL,
 end_raw text, end_date date, end_precision text NOT NULL, source_modified text
);
CREATE TABLE source_references (family text, code integer, label text, PRIMARY KEY(family,code));
"""

INDEXES = """
CREATE INDEX names_prefix ON entity_names(search_key, entity_id, fact_id);
CREATE INDEX names_entity ON entity_names(entity_id, fact_id);
CREATE INDEX identifiers_lookup ON entity_identifiers(namespace, value, entity_id);
CREATE INDEX officers_company ON officer_appointments(company_id, source_id);
CREATE INDEX officers_person ON officer_appointments(officer_id, source_id);
CREATE INDEX licences_company ON licences(company_id, source_id);
CREATE INDEX licence_relationships_company ON licence_relationships(company_id, source_id);
CREATE INDEX licence_relationships_person ON licence_relationships(person_id, source_id);
"""
