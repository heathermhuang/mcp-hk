"""Bounded source-scoped prefix reads using the existing text_pattern_ops indexes."""

PREFIX = "((r.name_key ~>=~ %s AND r.name_key ~<~ %s) OR (r.name2_key ~>=~ %s AND r.name2_key ~<~ %s))"
PUBLISHED_MEMBERS = (
    "SELECT source_key,capture_id FROM curated.official_members WHERE version=%s"
)
EFFECTIVE_MEMBERS = "SELECT source_key,capture_id FROM curated.official_staged UNION ALL SELECT m.source_key,m.capture_id FROM curated.official_members m JOIN curated.official_pointer p USING(version) WHERE NOT EXISTS(SELECT 1 FROM curated.official_staged s WHERE s.source_key=m.source_key)"


def prefix_rows(members=PUBLISHED_MEMBERS):
    # Both callers supply fixed internal membership SQL. No public SQL is accepted.
    # Select page identities before fetching JSON, without materializing every
    # prefix hit. Membership and the literal prefix still apply before LIMIT.
    return (
        "WITH members AS MATERIALIZED (" + members + "), "
        "selected AS (SELECT DISTINCT r.entity_id FROM curated.official_records r JOIN members m USING(capture_id) WHERE "
        + PREFIX
        + " AND r.entity_id>%s ORDER BY r.entity_id LIMIT %s) "
        "SELECT s.entity_id,chosen.record FROM selected s CROSS JOIN LATERAL ("
        "SELECT r.record FROM curated.official_records r JOIN members m USING(capture_id) WHERE r.entity_id=s.entity_id AND "
        + PREFIX
        + " ORDER BY r.record->>'coverageEnd' DESC NULLS LAST,r.fact_id LIMIT 1) chosen ORDER BY s.entity_id"
    )
