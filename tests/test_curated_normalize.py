import datetime as dt

import pytest

from mcp_open_data_hk.curated import normalize as n
from mcp_open_data_hk.curated.read import ReadError, Reader, prefix_end
from mcp_open_data_hk.curated.schema import schema_name


def test_identity_not_name_or_numeric_register_coercion():
    row = {
        "PersonID": 9,
        "Name1": "ＦＯＯ",
        "cName": "香港公司",
        "incID": "0000123",
        "Domicile": 1,
    }
    ids = list(n.identifiers(row, "organisation"))
    assert (9, "webb:incorporation:1", "0000123", "incID") in ids
    assert all("brn" not in item[1] for item in ids)
    names = list(n.names(row, "organisation"))
    assert names[0][3:5] == ("ＦＯＯ", "foo")
    assert names[1][3:5] == ("香港公司", "香港公司")
    assert names[0][1] == names[1][1] == 9
    assert list(n.names(dict(row, PersonID=10), "organisation"))[0][1] == 10


def test_partial_invalid_and_unknown_dates_are_preserved():
    assert n.bound(None) == (None, None, "unknown")
    assert n.bound("0000-00-00") == ("0000-00-00", None, "invalid")
    assert n.bound("2020-01-01", 1) == ("2020-01-01", dt.date(2020, 1, 1), "year")
    assert n.bound("2020-01-01", 3)[2] == "unknown"
    assert n.bound("2020-01-31", 5)[2] == "month_end"
    row = {
        "ID1": 4,
        "personID": 9,
        "oldName": "Old",
        "dateChanged": "2020-01-01",
        "dateAcc": 1,
    }
    fact = list(n.old_names(row))[0]
    assert fact[6:9] == ("2020-01-01", dt.date(2020, 1, 1), "year")
    assert len(fact) == 10  # No invented effective-from date.


def test_scope_is_explicit_and_offshore_issuers_survive():
    assert n.scope({"PersonID": 5, "Domicile": 2, "orgType": 7}, {5}, set()) == [
        "hk_listed_issuer"
    ]
    assert n.scope({"PersonID": 6, "Domicile": 2, "orgType": 27}, set(), set()) == [
        "registered_non_hk"
    ]
    assert n.scope({"PersonID": 7, "Domicile": 2, "orgType": 7}, set(), set()) == []


def test_cursor_tampering_filters_expiry_and_schema_grammar(monkeypatch):
    reader = Reader("unused", b"x" * 32)
    payload = {
        "op": "search",
        "filters": {"q": "香港"},
        "expires": 9999999999,
        "version": "v1",
        "last": 1,
    }
    token = reader.seal(payload)
    assert reader.unseal(token, "search", {"q": "香港"}) == payload
    for bad, operation, filters in [
        (token[:-3] + "AAA", "search", {"q": "香港"}),
        (token, "officers", {"q": "香港"}),
        (token, "search", {"q": "other"}),
    ]:
        with pytest.raises(ReadError, match="does not match"):
            reader.unseal(bad, operation, filters)
    monkeypatch.setattr("time.time", lambda: 10000000000)
    with pytest.raises(ReadError, match="expired"):
        reader.unseal(token, "search", {"q": "香港"})
    with pytest.raises(ValueError):
        schema_name('v1"; DROP SCHEMA public')
    assert prefix_end("a\U0010ffff") == "b"
    assert prefix_end("香港") > "香港\U0010ffff"


@pytest.mark.parametrize("query", ["a", " " * 4, "a" * 201, "ab\x00", "ab\ud800"])
def test_invalid_prefix_is_rejected_before_database_access(query):
    with pytest.raises(ReadError):
        Reader("unused", b"x" * 32).search(name=query)


def test_legacy_gateway_does_not_import_optional_driver():
    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import mcp_open_data_hk.api; assert not any(k == 'psycopg' or k.startswith('psycopg.') for k in sys.modules)",
        ],
        check=True,
        capture_output=True,
    )


def test_changed_or_empty_source_census_is_rejected(tmp_path, monkeypatch):
    import json
    from mcp_open_data_hk.archive_sql import SELECTED
    from mcp_open_data_hk.curated.source import ARCHIVE_SHA256, Source

    restored = {
        "status": "restored",
        "sourceArchiveSha256": ARCHIVE_SHA256,
        "restoredTableAudit": {t: {"rows": 1} for t in SELECTED},
    }
    (tmp_path / "audit_fixture-restore.json").write_text(json.dumps(restored))
    (tmp_path / "archive-audit.json").write_text(
        json.dumps({"status": "source_fidelity_verified"})
    )
    (tmp_path / "acquisition.json").write_text(json.dumps({"sha256": ARCHIVE_SHA256}))
    monkeypatch.setattr("mcp_open_data_hk.curated.source.isolation", lambda *a: None)
    monkeypatch.setattr(
        "mcp_open_data_hk.curated.source.install_client_config", lambda *a: None
    )
    monkeypatch.setattr(
        "mcp_open_data_hk.curated.source.query",
        lambda *a: "\n".join(json.dumps([t, 0]) for t in SELECTED),
    )
    with pytest.raises(ValueError, match="census differs"):
        Source(tmp_path, "owned-fixture", "audit_fixture")
