"""Invented facts only. Never submit these fixtures to a provider or production."""

from mcp_open_data_hk.curated.racing.policy import FAMILIES, MODES, checksum
from mcp_open_data_hk.curated.racing.normalize import meeting, race

ROUTE = "https://racing.hkjc.com/en-us/local/information/localresults"


def source_policy():
    return {
        "schema": "racing-policy-v1",
        "source": "hkjc",
        "purpose": "read_only_racing_facts",
        "state": "active",
        "qualifiedAt": "2026-01-01T00:00:00Z",
        "recheckAt": "2099-01-01T00:00:00Z",
        "families": {
            family: {
                "modes": {mode: "allowed" for mode in MODES},
                "routes": [ROUTE],
                "fields": ["id", "name", "amount"],
                "evidenceRef": "SYNTHETIC TEST ONLY",
                "evidenceSha256": "a" * 64,
                "retentionSeconds": 172800,
                "rawRetentionSeconds": 172800,
                "minIntervalSeconds": 1,
            }
            for family in FAMILIES
        },
    }


def bundle(digest):
    mid, rid = meeting("2026-01-01", "HV"), race("2026-01-01", "HV", 1)
    families = ["races", "declared_runners", "results"]
    tables = {
        "captures": [
            {
                "capture_id": "c1",
                "family": "results",
                "canonical_location": ROUTE,
                "retrieved_at": "2026-10-25T00:00:00Z",
                "raw_sha256": "b" * 64,
                "transform_sha256": "c" * 64,
                "run_id": "synthetic",
                "policy_digest": digest,
                "source_timezone": "Asia/Hong_Kong",
                "source_date_precision": "day",
                "validation": {"valid": True},
            }
        ],
        "meetings": [
            {
                "meeting_id": mid,
                "season": "2025-2026",
                "local_date": "2026-01-01",
                "venue": "HV",
                "status": "completed",
                "capture_id": "c1",
            }
        ],
        "races": [
            {
                "race_id": rid,
                "meeting_id": mid,
                "race_number": 1,
                "distance_m": 1200,
                "surface": "TURF",
                "course": "A",
                "going": "GOOD",
                "class_raw": "4",
                "scheduled_raw": None,
                "actual_raw": None,
                "time_precision": "unknown",
                "status": "completed",
                "capture_id": "c1",
            }
        ],
        "participants": [],
        "runners": [],
        "results": [],
        "coverage": [],
    }
    for number, draw, placing, seconds in [
        ("01", "09", "1", "69.23"),
        ("02", "03", "WV", None),
    ]:
        horse = "hkjc:horse:HK_SYN_" + number
        tables["participants"].append(
            {
                "participant_id": horse,
                "kind": "horse",
                "source_id": "HK_SYN_" + number,
                "name_en": "Synthetic Horse " + number,
                "name_zh": "合成馬匹" + number,
                "capture_id": "c1",
            }
        )
        tables["runners"].append(
            {
                "race_id": rid,
                "participant_id": horse,
                "horse_number": number,
                "draw": draw,
                "weight_lb": "120",
                "claim_lb": "2",
                "status": "declared" if seconds else "withdrawn",
                "capture_id": "c1",
            }
        )
        tables["results"].append(
            {
                "fact_id": rid + ":" + horse,
                "revision": checksum([horse, placing]),
                "supersedes": None,
                "race_id": rid,
                "participant_id": horse,
                "placing_raw": placing,
                "placing": 1 if seconds else None,
                "status": "finished" if seconds else "withdrawn",
                "dead_heat": False,
                "margin_raw": None,
                "time_raw": "1:09.23" if seconds else None,
                "time_seconds": seconds,
                "time_precision": "centisecond" if seconds else None,
                "capture_id": "c1",
            }
        )
    for family in families:
        ids = (
            [rid]
            if family == "races"
            else [row["participant_id"] for row in tables["participants"]]
        )
        tables["coverage"].append(
            {
                "family": family,
                "group_id": mid if family == "races" else rid,
                "scope": "meeting" if family == "races" else "race",
                "expected_ids": ids,
                "observed_ids": ids,
                "complete": True,
                "proof": {"inventoryRef": "independent synthetic declarations"},
            }
        )
    return {
        "families": families,
        "inventoryRef": "independent synthetic inventory",
        "transformSha256": "c" * 64,
        "synthetic": True,
    }, tables
