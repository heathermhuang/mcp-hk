"""Synthetic literal fixtures test the importer; real-data receipts are separate."""

import hashlib
import json

import pytest

from mcp_open_data_hk.curated.webb_sdi_source import ARCHIVE_SHA, extract


def fixture_source(root):
    root.mkdir()
    columns = {
        "sdi": [
            "ID",
            "form",
            "filing",
            "name1",
            "name2",
            "cName",
            "stockCode",
            "stockName",
            "relDate",
            "awDate",
            "issueID",
            "dir",
            "longShs1",
            "longStk1",
            "shortShs1",
            "shortStk1",
            "longShs2",
            "longStk2",
            "shortShs2",
            "shortStk2",
            "shsOut",
            "signDate",
            "curr",
            "hiPrice",
            "avPrice",
            "avCon",
            "conCode",
            "serNo",
            "serNoAmend",
            "serNoSuper",
            "modified",
            "ccc",
        ],
        "sdicap": ["sdiID", "capID", "posType", "shares"],
        "sdievent": [
            "sdiID",
            "posType",
            "reason",
            "capBefore",
            "capAfter",
            "shsInv",
            "probReason",
        ],
        "sdireason": ["ID", "rsnSht", "rsnLng"],
        "capacity": ["ID", "capShort", "capLong"],
        "currencies": ["ID", "currency", "HKEXcurr"],
        "issue": ["ID1", "issuer", "SEHKID", "typeID", "userID"],
    }
    row = {key: None for key in columns["sdi"]}
    row.update(
        ID=1,
        form=3,
        name1="Synthetic name",
        stockCode="00005",
        stockName="Synthetic issuer",
        relDate="2000-01-01",
        awDate=None,
        issueID=10,
        longShs1="9007199254740993.00000001",
        signDate="2025-01-01",
        serNo="TEST_001",
        modified="2025-01-02 00:00:00",
        ccc="EXCLUDED",
    )

    def literal(v, k):
        if v is None:
            return "NULL"
        if isinstance(v, int) or k == "longShs1":
            return str(v)
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"

    records = {
        "sdi": [row[k] for k in columns["sdi"]],
        "sdicap": [1, 1, 1, 10],
        "sdievent": [1, 1, 1, None, 1, 10, None],
        "sdireason": [1, "TEST", "Synthetic reason"],
        "capacity": [1, "TEST", "Synthetic capacity"],
        "currencies": [1, "HKD", "HKD"],
        "issue": [10, 100, 1, 1, 999],
    }
    schema = {
        t: {
            "columns": [
                {"name": k, "type": "double" if k == "longShs1" else "varchar(255)"}
                for k in keys
            ],
            "primaryKey": [],
        }
        for t, keys in columns.items()
    }
    body = "".join(
        "INSERT INTO `"
        + t
        + "` VALUES ("
        + ",".join(literal(v, k) for k, v in zip(columns[t], values))
        + ");\n"
        for t, values in records.items()
    ).encode()
    member = root / "data.sql"
    member.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    (root / "source-schema.json").write_text(json.dumps(schema))
    (root / "archive-audit.json").write_text(
        json.dumps({"status": "source_fidelity_verified", "sourceDataSha256": sha})
    )
    (root / "acquisition.json").write_text(json.dumps({"sha256": ARCHIVE_SHA}))
    (root / "webb-site-NOTICE.txt").write_text("Synthetic Webb attribution notice")
    census = root / "census.json"
    census.write_text(
        json.dumps(
            {
                "archiveSha256": ARCHIVE_SHA,
                "sourceTableRows": {t: {"rows": 1} for t in columns},
            }
        )
    )
    return member, sha, census


def test_scoped_literal_projection_preserves_precision_dates_and_identity(tmp_path):
    workspace = tmp_path / "source"
    member, sha, census = fixture_source(workspace)
    output = tmp_path / "projection"
    manifest = extract(
        workspace, output, data_path=member, expected_sha=sha, census=census
    )
    row = json.loads((output / "sdi.ndjson").read_text())
    assert row["longShs1"] == "9007199254740993.00000001"
    assert row["stockCode"] == "00005" and row["awDate"] is None
    assert "ccc" not in row
    assert "userID" not in json.loads((output / "issue.ndjson").read_text())
    assert manifest["forms"] == {"3": 1}
    assert manifest["dateRanges"]["relDate"] == ("2000-01-01", "2000-01-01")
    assert manifest["orphanCapacityParentIds"] == 0
    with pytest.raises(FileExistsError):
        extract(workspace, output, data_path=member, expected_sha=sha, census=census)


def test_tampered_source_cannot_create_accepted_manifest(tmp_path):
    workspace = tmp_path / "source"
    member, sha, census = fixture_source(workspace)
    member.write_bytes(member.read_bytes() + b"-- changed source bytes\n")
    with pytest.raises(ValueError, match="CHECKSUM"):
        extract(
            workspace,
            tmp_path / "failed",
            data_path=member,
            expected_sha=sha,
            census=census,
        )
    assert (tmp_path / "failed/FAILED.json").exists()
    assert not (tmp_path / "failed/manifest.json").exists()


def test_wrong_census_is_rejected_after_complete_parse(tmp_path):
    workspace = tmp_path / "source"
    member, sha, census = fixture_source(workspace)
    counted = json.loads(census.read_text())
    counted["sourceTableRows"]["sdi"]["rows"] = 2
    census.write_text(json.dumps(counted))
    with pytest.raises(ValueError, match="CENSUS_MISMATCH"):
        extract(
            workspace,
            tmp_path / "failed",
            data_path=member,
            expected_sha=sha,
            census=census,
        )


def test_archive_queries_validate_source_identity_and_bounded_event_dates():
    from pydantic import ValidationError
    from mcp_open_data_hk.webb_sdi import DisclosureQuery, IssuerQuery

    assert IssuerQuery(stockCode="5").stockCode == "5"
    assert (
        DisclosureQuery(
            issuerId="webb:person:100", start="2000-01-01", end="2000-02-01"
        ).end
        == "2000-02-01"
    )
    for args in (
        {"q": "x"},
        {"stockCode": "000005"},
        {"q": "foo", "stockCode": "5"},
        {"q": "foo", "limit": 101},
    ):
        with pytest.raises(ValidationError):
            IssuerQuery(**args)
    for args in (
        {"start": "2000-01-01"},
        {"start": "2000-01-01", "end": "2000-02-02"},
        {"start": "invalid", "end": "2000-01-02"},
    ):
        with pytest.raises(ValidationError):
            DisclosureQuery(issuerId="100", **args)


def test_unpublished_archive_has_no_data_tools_or_openapi_queries(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    monkeypatch.delenv("MCP_HK_WEBB_SDI_ENABLED", raising=False)
    app = create_app(Service(Store(tmp_path / "gateway.sqlite3")))
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/hkex/archive/status").json()["state"] == "not_published"
        )
        assert (
            "/api/v1/hkex/archive/issuers"
            not in client.get("/openapi.json").json()["paths"]
        )
        assert client.get("/api/v1/hkex/archive/issuers?stockCode=5").status_code == 503
        assert "Webb" in client.get("/api/v1/hkex/archive/notice").text
