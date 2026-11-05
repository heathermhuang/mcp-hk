"""Plan every frozen resource from a read-only accepted checkpoint, without source IO.

This classifies the next work, not acceptance, current source availability or
semantic equivalence. Native catalogue identifiers are followed only when explicit.
"""

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

from mcp_open_data_hk.capabilities import unpack
from mcp_open_data_hk.census_reports import location
from mcp_open_data_hk.transport import profile


def report_identity(url):
    query = parse_qs(urlsplit(url).query)
    if set(query) - {"ecode", "download_excel", "download_csv", "download_xml"}:
        return None
    return location(url)


def triage(database, frozen, census_tasks):
    database = Path(database).resolve()
    wal = Path(str(database) + "-wal")
    before = database.stat()
    if wal.exists() and wal.stat().st_size:
        raise ValueError("Use a closed isolated checkpoint without a live WAL")
    memberships = defaultdict(list)
    for candidate in frozen["familyCandidates"]:
        memberships[candidate["resourceId"]].append(
            {
                "kind": "family_candidate",
                "datasetId": candidate["datasetId"],
                "family": candidate["family"],
                "status": candidate["lastStatus"],
                "reason": candidate["lastReason"],
                "sourceUrlSha256": hashlib.sha256(
                    candidate["sourceUrl"].encode()
                ).hexdigest(),
            }
        )
    for group in frozen["residualUncoveredGroups"]:
        for rid in group["resourceIds"]:
            memberships[rid].append(
                {
                    "kind": "residual_group",
                    **{
                        k: group[k] for k in ("datasetId", "family", "status", "reason")
                    },
                }
            )
    report_tasks = defaultdict(list)
    for candidate in frozen["familyCandidates"]:
        identity = report_identity(candidate["sourceUrl"])
        if identity and candidate["family"] == "workbook":
            report_tasks[identity].append(candidate["resourceId"])
    census_links = {
        c["resourceId"]: c
        for c in census_tasks["candidates"]
        if c["acceptedEquivalentAdapterSelections"]
    }
    database_hash = hashlib.sha256()
    with Path(database).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            database_hash.update(chunk)
    plans = []
    with sqlite3.connect(
        Path(database).resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        generation = db.execute("SELECT generation FROM inventory_head").fetchone()[0]
        dataset_ids = {
            r[0]
            for r in db.execute(
                "SELECT id FROM inventory_datasets WHERE generation=?", (generation,)
            )
        }
        accepted = dict(
            db.execute(
                "SELECT dataset,count(*) FROM inventory_resources r JOIN resource_checks c "
                "ON c.id=r.id WHERE r.generation=? AND c.status='queryable' GROUP BY dataset",
                (generation,),
            )
        )
        variants = defaultdict(dict)
        for row in db.execute(
            "SELECT resource,status,count(*) FROM resource_variants GROUP BY resource,status"
        ):
            variants[row[0]][row[1]] = row[2]
        for rid, origins in sorted(memberships.items()):
            row = db.execute(
                "SELECT dataset,payload FROM inventory_resources WHERE generation=? AND id=?",
                (generation, rid),
            ).fetchone()
            item = {"resourceId": rid, "frozenMemberships": origins}
            if row is None:
                item.update(
                    state="inventory_reference_missing",
                    nextAction="reconcile_exact_identifier_without_inventing_a_replacement",
                )
                plans.append(item)
                continue
            assert all(o["datasetId"] == row["dataset"] for o in origins)
            resource = unpack(row["payload"])
            url = resource["url"]
            parts, query = urlsplit(url), parse_qs(urlsplit(url).query)
            check = db.execute(
                "SELECT status,reason,checked,validated FROM resource_checks WHERE id=?",
                (rid,),
            ).fetchone()
            check = dict(check) if check else {}
            item.update(
                datasetId=row["dataset"],
                format=resource.get("format"),
                sourceHost=parts.hostname,
                sourceQueryParameterNames=sorted(query),
                sourceUrlSha256=hashlib.sha256(url.encode()).hexdigest(),
                checkpointCheck=check,
                checkpointVariantStatusCounts=variants[rid],
                latestCheckIsWholeResourceCoverage=False,
                datasetHasAcceptedRepresentation=bool(accepted.get(row["dataset"])),
                recordAcceptanceChanged=False,
                semanticApprovalGenerated=False,
            )
            native = query.get("datasetId", [])
            changed_url = any(
                o.get("sourceUrlSha256")
                and o["sourceUrlSha256"] != item["sourceUrlSha256"]
                for o in origins
            )
            item["sourceUrlChangedSinceFreeze"] = changed_url
            if changed_url:
                item.update(
                    state="source_url_drift_requires_reconciliation",
                    nextAction="retain_both_source_versions_and_reconcile_scope_before_qualification",
                )
            elif (
                parts.hostname == "portal.csdi.gov.hk"
                and parts.path.rstrip("/") == "/geoportal"
                and len(native) == 1
                and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", native[0])
            ):
                target = "csdi:" + native[0]
                item.update(
                    state=(
                        "explicit_catalogue_link"
                        if target in dataset_ids
                        else "catalogue_link_target_missing"
                    ),
                    nativeDatasetId=target,
                    nativeDatasetPresent=target in dataset_ids,
                    nativeAcceptedRepresentations=accepted.get(target, 0),
                    nextAction=(
                        "inspect_exact_native_resources_then_verify_requested_scope"
                        if target in dataset_ids
                        else "reconcile_exact_native_reference_before_requesting_records"
                    ),
                )
            elif report_identity(url) in report_tasks:
                item.update(
                    state="existing_report_adapter_task_link",
                    reportIdentity=list(report_identity(url)),
                    primaryResourceIds=sorted(report_tasks[report_identity(url)]),
                    nextAction="qualify_explicit_series_in_saved_primary_graph",
                    originalDownloadFileEquivalence="not_established",
                )
            elif rid in census_links:
                item.update(
                    state="dated_accepted_api_task_link",
                    taskEvidenceCheckpoint=census_tasks["checkpoint"],
                    adapterIdentity=census_links[rid]["adapterIdentity"],
                    acceptedAdapterAlternatives=census_links[rid][
                        "acceptedEquivalentAdapterSelections"
                    ],
                    nextAction="revalidate_only_requested_scope_or_freshness_no_workbook_equivalence_claim",
                    originalDownloadFileEquivalence="not_established",
                )
            elif check.get("reason") == "ACCESS_RESTRICTED":
                item.update(
                    state="dated_source_access_hold",
                    nextAction="retain_exact_denial_until_source_or_access_evidence_changes",
                )
            elif check.get("status") == "capacity_limited":
                item.update(
                    state="internal_capacity_hold",
                    nextAction="retain_exact_bound_and_scope_without_raising_limits",
                )
            elif resource.get("format") in {"WMS", "WMTS"}:
                item.update(
                    state="non_record_map_representation",
                    nextAction="find_official_feature_scope_for_a_record_task_no_raster_infrastructure",
                )
            elif profile(resource):
                item.update(
                    state="existing_explicit_transport_contract",
                    requiredParameters=profile(resource).required,
                    nextAction="qualify_explicit_native_route_or_stop_no_default_service_type",
                )
            elif check.get("status") in {"queryable", "document"}:
                item.update(
                    state="accepted_scope_requires_remaining_choice_review",
                    nextAction="inspect_exact_accepted_scope_and_pending_choices_no_whole_dataset_inference",
                )
            elif check.get("status") == "needs_selection":
                item.update(
                    state="explicit_selection_pending",
                    nextAction="discover_published_choices_then_qualify_exact_selected_scope",
                )
            elif check.get("reason") in {
                "SOURCE_PARSE_ERROR",
                "SOURCE_SCHEMA_CHANGED",
                "SCHEMA_DRIFT",
            }:
                item.update(
                    state="reader_investigation_pending",
                    nextAction="inspect_exact_failure_and_minimal_source_fixture_before_fixing",
                )
            elif check.get("status") == "unavailable":
                item.update(
                    state="dated_failure_cause_unresolved",
                    nextAction="distinguish_upstream_failure_from_adapter_error_no_blind_retry",
                )
            else:
                item.update(
                    state="representation_task_triage_pending",
                    nextAction="establish_uncovered_task_and_contract_before_new_infrastructure",
                )
            plans.append(item)
    after = database.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or (
        wal.exists() and wal.stat().st_size
    ):
        raise ValueError("Checkpoint changed during planning")
    assert len(plans) == len(memberships)
    return {
        "scope": "Exact resource work plan only; dated checks, discovery links and matching adapter tasks are not record/semantic acceptance or current upstream verification.",
        "inputDatabaseSha256": database_hash.hexdigest(),
        "checkpointGeneration": generation,
        "frozenGeneration": frozen["generation"],
        "familyCandidateCount": len(frozen["familyCandidates"]),
        "residualGroupCount": len(frozen["residualUncoveredGroups"]),
        "uniquePlannedResources": len(plans),
        "counts": dict(sorted(Counter(p["state"] for p in plans).items())),
        "providerRequests": 0,
        "statusWrites": 0,
        "plans": plans,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("census_tasks", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = triage(
        args.database,
        json.load(gzip.open(args.candidates, "rt")),
        json.load(gzip.open(args.census_tasks, "rt")),
    )
    data = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    args.output.write_bytes(
        gzip.compress(data, mtime=0) if args.output.suffix == ".gz" else data
    )
    print(json.dumps({k: v for k, v in result.items() if k != "plans"}))
