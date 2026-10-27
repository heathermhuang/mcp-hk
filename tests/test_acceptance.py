"""Acceptance evidence survives interruption and cannot mix versions or page scope."""

import csv
import io
import json
import zipfile

import pytest

from mcp_open_data_hk.curated.acceptance import (
    Journal,
    company_plan,
    verify_company_record,
    verify_page_zip,
    sha,
)
from mcp_open_data_hk.curated.official_acceptance import reconcile
from test_official_acceptance import inventory


def test_plan_requires_exact_accepted_cohort_and_never_promotes_staged():
    baseline, rows = inventory()
    version = "official-" + "a" * 32
    for row in rows:
        row["sampleRecord"] = {"fact_id": row["sourceKey"], "identifier": "05243897"}
    cohort = reconcile(baseline, rows, version)
    plan = company_plan(cohort)
    assert len(plan["cases"]) == 188
    assert sum(len(c["steps"]) for c in plan["cases"]) == 1128
    rows[-1]["publishedCaptureId"] = "prior"
    with pytest.raises(ValueError, match="FULL_ACCEPTED"):
        company_plan(reconcile(baseline, rows, version))
    cohort["cases"][0]["version"] = "official-" + "b" * 32
    with pytest.raises(ValueError, match="ACCEPTED_EVIDENCE"):
        company_plan(cohort)


def test_bounded_serialized_resume_never_repeats_settled_or_failed_steps(tmp_path):
    plan = {"version": "v1", "cases": [{"id": "one", "steps": ["rest", "mcp"]}]}
    path = tmp_path / "progress.sqlite3"
    journal = Journal(path, plan)
    calls = []

    def check(case, step, version):
        calls.append((case["id"], step, version))
        artifact = tmp_path / (step + ".json")
        artifact.write_text('{"actual":true}')
        return [artifact]

    assert journal.run(check, limit=1)["completedSteps"] == 1
    journal = Journal(path, plan)
    assert journal.run(check)["completedSteps"] == 1
    assert journal.run(check)["completedSteps"] == 0
    assert journal.summary()["allRequiredStepsPassed"]
    assert len(calls) == 2
    with pytest.raises(ValueError, match="PLAN_CHANGED"):
        Journal(path, dict(plan, version="v2"))
    with journal.owner():
        with pytest.raises(ValueError, match="OWNER_BUSY"):
            Journal(path, plan).run(check)


def test_interrupted_and_failed_checks_remain_visible_without_automatic_retry(tmp_path):
    plan = {"version": "v", "cases": [{"id": "a", "steps": ["rest", "mcp"]}]}
    journal = Journal(tmp_path / "unknown.sqlite3", plan)
    with journal.connect() as db:
        db.execute(
            "INSERT INTO attempts(case_id,step,state) VALUES('a','rest','unknown')"
        )
    calls = []

    def fail(*args):
        calls.append(args)
        raise ValueError("changed source failure")

    with pytest.raises(ValueError, match="changed source failure"):
        journal.run(fail)
    assert journal.run(fail)["completedSteps"] == 0
    assert len(calls) == 1
    assert journal.summary()["states"] == {"failed": 1, "unknown": 1}
    assert not journal.summary()["allRequiredStepsPassed"]


def test_full_fact_and_lineage_comparison_includes_string_identity():
    row = {
        "fact_id": "f",
        "identifier": {"namespace": "cr:local:brn", "value": "05243897"},
    }
    case = {"expected": row}
    response = {
        "meta": {"version": "v1", "view": "latest_observed"},
        "data": {"observations": [row]},
    }
    assert verify_company_record(response, case, "v1")
    with pytest.raises(ValueError, match="VERSION_MISMATCH"):
        verify_company_record(response, case, "v2")
    response["data"]["observations"] = [dict(row, identifier={"value": 5243897})]
    with pytest.raises(ValueError, match="FACT_OR_LINEAGE"):
        verify_company_record(response, case, "v1")


def package(rows, *, mutate=None):
    """Fabricated package with independently declared expected records."""
    envelope = {
        "data": {"items": rows},
        "meta": {
            "version": "v1",
            "view": "latest_observed",
            "nextCursor": "signed-page-2",
        },
        "provenance": [{"sourceId": "cr"}],
        "warnings": [],
    }
    columns = list(rows[0])
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            [
                (
                    json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (dict, list))
                    else (
                        "'" + v
                        if isinstance(v, str) and v.startswith(("0", "="))
                        else v
                    )
                )
                for v in row.values()
            ]
        )
    files = {
        "records.json": json.dumps(rows, ensure_ascii=False).encode(),
        "records.csv": stream.getvalue().encode("utf-8-sig"),
        "schema.json": json.dumps(
            {
                "columns": [
                    {
                        "name": c,
                        "jsonTypes": [
                            (
                                "object"
                                if isinstance(rows[0][c], dict)
                                else (
                                    "array"
                                    if isinstance(rows[0][c], list)
                                    else "string"
                                )
                            )
                        ],
                    }
                    for c in columns
                ],
                "csv": {
                    "encoding": "UTF-8 with BOM",
                    "null": "empty cell",
                    "nestedValues": "JSON text",
                    "spreadsheetTextEscape": "apostrophe prefix",
                },
            }
        ).encode(),
        "provenance.json": json.dumps(
            {k: envelope[k] for k in ["meta", "provenance", "warnings"]}
        ).encode(),
        "NOTICE.txt": b"Source: Companies Registry. Dated observations only.",
    }
    manifest = {
        "version": "v1",
        "view": "latest_observed",
        "scope": "this_page",
        "currentVerification": False,
        "rowCount": len(rows),
        "selection": {"cursor": "signed-page-1"},
        "files": [
            {"file": k, "bytes": len(v), "sha256": sha(v)} for k, v in files.items()
        ],
    }
    if mutate:
        mutate(files, manifest)
    files["manifest.json"] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return out.getvalue(), envelope, {"cursor": "signed-page-1"}


def test_actual_package_verifier_checks_every_nested_csv_value_and_page_hash():
    rows = [
        {
            "identifier": {"value": "05243897", "namespace": "cr:local:brn"},
            "value": "05243897",
            "name": "=香港",
            "events": [{"date": "2026-10-05"}],
        }
    ] * 2
    raw, envelope, selection = package(rows)
    proof = verify_page_zip(raw, envelope, selection)
    assert proof["rows"] == 2 and proof["zipSha256"] == sha(raw)
    with pytest.raises(ValueError, match="PAGE_MISMATCH"):
        verify_page_zip(raw, envelope, {"cursor": "another-page"})
    raw, envelope, selection = package(
        rows,
        mutate=lambda f, m: f.update(
            {"records.csv": f["records.csv"].replace(b"05243897", b"5243897")}
        ),
    )
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        verify_page_zip(raw, envelope, selection)


def test_rehashed_logically_corrupt_csv_still_fails():
    def corrupt(files, manifest):
        files["records.csv"] = files["records.csv"].replace(b"05243897", b"5243897")
        for member in manifest["files"]:
            member.update(
                bytes=len(files[member["file"]]), sha256=sha(files[member["file"]])
            )

    raw, envelope, selection = package([{"value": "05243897"}], mutate=corrupt)
    with pytest.raises(ValueError, match="CSV_VALUE"):
        verify_page_zip(raw, envelope, selection)


def test_reviewed_correction_reopens_only_failed_step_and_preserves_prior_attempt(
    tmp_path,
):
    journal = Journal(
        tmp_path / "review.sqlite3",
        {"version": "v", "cases": [{"id": "a", "steps": ["rest"]}]},
    )
    with journal.connect() as db:
        db.execute(
            "INSERT INTO attempts(case_id,step,state) VALUES('a','rest','failed')"
        )
    with pytest.raises(ValueError, match="REVIEW_REQUIRED"):
        journal.reopen("a", "rest", {})
    journal.reopen(
        "a",
        "rest",
        {
            "reason": "deployed correction",
            "correctedRelease": "a" * 40,
            "evidenceSha256": "b" * 64,
        },
    )
    artifact = tmp_path / "actual.json"
    artifact.write_text("{}")
    journal.run(lambda *a: [artifact])
    assert journal.summary()["allRequiredStepsPassed"]
    with journal.connect() as db:
        assert [r[0] for r in db.execute("select state from attempts order by id")] == [
            "failed",
            "ready",
            "passed",
        ]


def test_coordinator_runs_successive_batches_in_one_bounded_wake_without_models(
    tmp_path,
):
    from mcp_open_data_hk.curated.company_suite import run

    plan = {
        "version": "v",
        "cases": [{"id": str(n), "steps": ["rest", "mcp"]} for n in range(12)],
    }
    journal = Journal(tmp_path / "suite.sqlite3", plan)
    artifact = tmp_path / "receipt.json"
    artifact.write_text("{}")
    calls = []

    def verify(case, step, version):
        calls.append((case["id"], step, version))
        return [artifact]

    assert run(journal, verify, seconds=10)["allRequiredStepsPassed"]
    assert len(calls) == 24
    assert (
        run(journal, verify, seconds=10)["allRequiredStepsPassed"] and len(calls) == 24
    )
