"""Validate independently declared coverage and typed facts before staging any bytes."""

from .normalize import meeting, participant, placing, elapsed
from .policy import FAMILIES, RacingRejected, location, utc


def validate_bundle(manifest, tables):
    families = manifest.get("families", [])
    if (
        not families
        or len(set(families)) != len(families)
        or set(families) - set(FAMILIES)
    ):
        raise RacingRejected("INVALID_BUNDLE_FAMILIES")
    captures = {row["capture_id"]: row for row in tables.get("captures", [])}
    if len(captures) != len(tables.get("captures", [])) or not captures:
        raise RacingRejected("CAPTURE_LINEAGE_REQUIRED")
    for row in captures.values():
        location(row["canonical_location"])
        utc(row["retrieved_at"])
        if row["family"] not in families or not row["validation"].get("valid"):
            raise RacingRejected("CAPTURE_VALIDATION_REQUIRED")
    for table, rows in tables.items():
        if table not in {"coverage", "captures"}:
            for row in rows:
                if row.get("capture_id") not in captures:
                    raise RacingRejected("CAPTURE_LINEAGE_REQUIRED")
    meetings = {row["meeting_id"]: row for row in tables.get("meetings", [])}
    for row in meetings.values():
        if row["meeting_id"] != meeting(row["local_date"], row["venue"]):
            raise RacingRejected("MEETING_IDENTITY_MISMATCH")
    races = {row["race_id"]: row for row in tables.get("races", [])}
    for row in races.values():
        if (
            row["meeting_id"] not in meetings
            or row["race_id"] != row["meeting_id"] + f':{row["race_number"]:02d}'
        ):
            raise RacingRejected("RACE_IDENTITY_MISMATCH")
    for row in tables.get("participants", []):
        if row["participant_id"] != participant(row["kind"], row["source_id"]):
            raise RacingRejected("PARTICIPANT_IDENTITY_MISMATCH")
    seen = set()
    for row in tables.get("results", []):
        if row["fact_id"] in seen:
            raise RacingRejected("MULTIPLE_SELECTED_REVISIONS")
        seen.add(row["fact_id"])
        outcome = placing(row["placing_raw"])
        if any(
            row[key] != outcome[field]
            for key, field in (
                ("placing", "placing"),
                ("status", "status"),
                ("dead_heat", "deadHeat"),
            )
        ):
            raise RacingRejected("RESULT_SEMANTIC_MISMATCH")
        seconds = elapsed(row["time_raw"])
        if (
            row["time_seconds"] != seconds
            or outcome["status"] != "finished"
            and seconds is not None
        ):
            raise RacingRejected("RESULT_TIME_MISMATCH")
    coverage = tables.get("coverage", [])
    if set(row["family"] for row in coverage) != set(families):
        raise RacingRejected("FAMILY_COVERAGE_REQUIRED")
    for row in coverage:
        expected, observed = row["expected_ids"], row["observed_ids"]
        if (
            not row["complete"]
            or len(set(expected)) != len(expected)
            or len(set(observed)) != len(observed)
            or set(expected) != set(observed)
            or not row["proof"].get("inventoryRef")
        ):
            raise RacingRejected("INCOMPLETE_BUNDLE")
        # Expected inventory must be reconciled against actual facts, not parser counts.
        table_key = {
            "races": ("races", "race_id"),
            "declared_runners": ("runners", "participant_id"),
            "results": ("results", "participant_id"),
            "profiles": ("participants", "participant_id"),
        }.get(row["family"])
        if table_key:
            table, key = table_key
            if row["scope"] == "season":
                actual = {
                    fact["meeting_id"]
                    for fact in tables.get("meetings", [])
                    if fact["season"] == row["group_id"]
                }
            elif table == "races":
                actual = {
                    fact[key]
                    for fact in tables.get(table, [])
                    if fact["meeting_id"] == row["group_id"]
                }
            else:
                actual = {
                    fact[key]
                    for fact in tables.get(table, [])
                    if row["family"] == "profiles" or fact["race_id"] == row["group_id"]
                }
            if actual != set(expected):
                raise RacingRejected("INVENTORY_FACT_MISMATCH")
    return True
