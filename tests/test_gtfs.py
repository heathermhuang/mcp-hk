"""GTFS is UTF-8 CSV, including recognised TXT members of a bounded archive."""

import io
import zipfile

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.resource_stream import FileRows


def test_plain_gtfs_keeps_ids_and_schedule_times_as_source_strings():
    rows, schema = parse(
        "stop_id,stop_name,arrival_time\n001042,蘭桂坊,25:01:00\n".encode(), "GTFS"
    )
    assert rows == [
        {"stop_id": "001042", "stop_name": "蘭桂坊", "arrival_time": "25:01:00"}
    ]
    assert schema["sourceFormat"] == "GTFS"
    assert schema["transportReference"] == {
        "kind": "published_timetable",
        "realtime": False,
    }
    with pytest.raises(DomainError, match="UNSUPPORTED_ENCODING"):
        parse("stop_id,stop_name\n1,蘭桂坊\n".encode("big5"), "GTFS")


def test_gtfs_archive_retains_member_provenance_and_unread_files():
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr("feed/stops.txt", "stop_id,stop_name\n001042,Lan Kwai Fong\n")
        archive.writestr("feed/routes.txt", "route_id,route_short_name\n001,12\n")
        archive.writestr("readme.txt", "This is not a table")
    rows, schema = parse(body.getvalue(), "GTFS")
    assert {r["_sourceArchiveMember"] for r in rows} == {
        "feed/stops.txt",
        "feed/routes.txt",
    }
    assert schema["unreadMembers"] == ["readme.txt"]
    assert schema["transportReference"]["realtime"] is False
    with pytest.raises(DomainError, match="UNSUPPORTED_FORMAT"):
        parse(body.getvalue(), "ZIP")


def test_streamed_gtfs_uses_the_same_utf8_table_contract(tmp_path):
    path = tmp_path / "stops.txt"
    path.write_bytes("stop_id,stop_name\n001042,蘭桂坊\n".encode())
    rows = FileRows(path, "GTFS")
    assert list(rows) == [{"stop_id": "001042", "stop_name": "蘭桂坊"}]
    assert rows.schema["sourceFormat"] == "GTFS"
    assert rows.schema["transportReference"]["realtime"] is False
    rows.close()
    path.write_bytes("stop_id,stop_name\n1,蘭桂坊\n".encode("utf-16"))
    with pytest.raises(DomainError, match="UNSUPPORTED_ENCODING"):
        FileRows(path, "GTFS")
