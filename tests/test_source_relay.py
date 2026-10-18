import socket

import pytest

from mcp_open_data_hk import resource_fetch
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.source_relay import TARGETS, relay_request


def configure(monkeypatch):
    monkeypatch.setenv("MCP_HK_BOOTSTRAP_URL", "https://mcp.hk/__ops/snapshot")
    monkeypatch.setenv("MCP_HK_OPS_TOKEN", "private-token")


def test_relay_is_exact_and_never_routes_credentials_to_an_untrusted_destination(
    monkeypatch,
):
    configure(monkeypatch)
    url = TARGETS["8e4b55c8803277a7e109d007bfac4d98"]
    request, headers = relay_request(url)
    assert (
        request
        == "https://mcp.hk/__ops/source-relay?resourceId=8e4b55c8803277a7e109d007bfac4d98"
    )
    assert headers == {"Authorization": "Bearer private-token"}
    assert relay_request(url + "?unapproved=1") is None
    assert relay_request(url, payload=b"{}") is None
    assert relay_request(url, {"Authorization": "caller-credential"}) is None
    assert relay_request(url, {"Cookie": "caller-cookie"}) is None
    monkeypatch.setenv(
        "MCP_HK_BOOTSTRAP_URL", "https://mcp.hk.evil.example/__ops/snapshot"
    )
    assert relay_request(url) is None


def test_reader_uses_own_relay_only_and_preserves_original_provenance(monkeypatch):
    configure(monkeypatch)
    requests = []
    dns = []
    url = TARGETS["8e4b55c8803277a7e109d007bfac4d98"]

    def public(host, port):
        dns.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", port))]

    class Response:
        status = 200
        body = b'[{"actual":1}]'

        def getheaders(self):
            return [("X-Mcp-Source-Transport", "approved-worker-relay")]

        def read1(self, size):
            value, self.body = self.body, b""
            return value

    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "mcp.hk"

        def request(self, method, path, body, headers):
            requests.append((method, path, headers))

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(resource_fetch, "public_addresses", public)
    monkeypatch.setattr(resource_fetch, "PinnedHTTPS", Connection)
    body, headers, final, status = resource_fetch.fetch_sync(url)
    assert body == b'[{"actual":1}]' and final == url and status == 200
    assert dns == ["xpms.hyd.gov.hk"]
    assert requests[0][2]["Authorization"] == "Bearer private-token"
    assert headers["_mcp_source_transport"] == "approved-worker-relay"


def test_relay_retains_original_private_address_rejection(monkeypatch):
    configure(monkeypatch)

    def reject(*args):
        raise DomainError("UNSAFE_SOURCE", "Nonpublic address")

    monkeypatch.setattr(resource_fetch, "public_addresses", reject)
    with pytest.raises(DomainError, match="UNSAFE_SOURCE"):
        resource_fetch.fetch_sync(TARGETS["8e4b55c8803277a7e109d007bfac4d98"])


def test_rss_rejects_html_errors_and_exposes_its_flexible_syntax_contract():
    with pytest.raises(DomainError):
        parse(b"<html><head><title>Access denied</title></head></html>", "RSS")
    rows, schema = parse(
        b"<rss version='2.0'><channel><title>Actual feed</title><item><title>Record</title></item></channel></rss>",
        "RSS",
    )
    assert rows and schema["readerContract"] == "rss-feed-root-1"
    assert "not a count of all catalogue books" in schema["rowMeaning"]
    _, atom = parse(
        b"<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Actual</title></entry></feed>",
        "RSS",
    )
    assert atom["readerContract"] == "rss-feed-root-1"
