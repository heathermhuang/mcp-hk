"""Bounded public-source downloads with DNS-pinned connections and redirect checks."""

import asyncio
import gzip
import http.client
import os
import tempfile
import threading
from pathlib import Path
import ipaddress
import socket
import ssl
import time
import zlib

import certifi
from urllib.parse import quote, urljoin, urlsplit

from .contracts import DomainError
from .upstream_budget import get_budget, gateway_headers, GATEWAY
from .source_relay import relay_request

MAX_BYTES = 8_000_000


def validate_url(url):
    try:
        p = urlsplit(url)
        if (
            p.scheme not in {"http", "https"}
            or not p.hostname
            or p.username is not None
            or p.password is not None
            or p.port not in {None, 80, 443}
            or p.fragment
            or any(c in url for c in "\r\n\\")
        ):
            raise ValueError()
        return p
    except ValueError:
        raise DomainError(
            "UNSAFE_SOURCE", "Source URL is not a public HTTP endpoint", 422
        ) from None


def public_addresses(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if (
        not addresses
        or len(addresses) > 16
        or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    ):
        raise DomainError(
            "UNSAFE_SOURCE", "Source resolves to a non-public network", 422
        )
    return addresses


class PinnedHTTP(http.client.HTTPConnection):
    def connect(self):
        # Validate ALL answers, then connect to one of exactly those addresses.
        addresses = public_addresses(self.host, self.port)
        last = None
        for family, kind, proto, _, addr in addresses:
            budget = get_budget()
            remaining = budget.remaining()
            conn = socket.socket(family, kind, proto)
            conn.settimeout(
                min(self.timeout, remaining)
                if isinstance(self.timeout, (int, float))
                else remaining
            )
            try:
                conn.connect(addr)
                self.sock = conn
                return
            except OSError as exc:
                conn.close()
                last = exc
        raise last or OSError("No source address")


class PinnedHTTPS(PinnedHTTP):
    default_port = 443

    def connect(self):
        super().connect()
        self.sock = ssl.create_default_context(cafile=certifi.where()).wrap_socket(
            self.sock, server_hostname=self.host
        )


def fetch_sync(
    url, headers=None, maximum=MAX_BYTES, destination=None, payload=None, deadline=30
):
    started = time.monotonic()
    budget = get_budget()
    budget.acquire()
    try:
        return _fetch_attempts(
            url, headers, maximum, destination, payload, deadline, started, budget
        )
    finally:
        budget.release()


def _fetch_attempts(
    url, headers, maximum, destination, payload, deadline, started, budget
):
    identity_retry = False
    for attempt in range(4):
        if attempt:
            # Each redirect/retry is a new charged upstream attempt.
            budget.retry()
        budget.remaining()
        original = validate_url(url)
        hosted = os.environ.get("MCP_HK_EDGE_MODE") == "true"
        relay = None if hosted else relay_request(url, headers, payload)
        if relay:
            # The approved source is public too. Never turn this into a route
            # around the reader's private-address rejection.
            public_addresses(original.hostname, original.port or 443)
        p = validate_url(relay[0] if relay else url)
        if hosted:
            gateway = validate_url(GATEWAY)
            connection = http.client.HTTPConnection(
                gateway.hostname, timeout=min(10, budget.remaining())
            )
        else:
            connection = (PinnedHTTPS if p.scheme == "https" else PinnedHTTP)(
                p.hostname, port=p.port, timeout=min(10, budget.remaining())
            )
        output = None
        try:
            connection.request(
                "POST" if payload is not None else "GET",
                (
                    "/fetch"
                    if hosted
                    else quote(p.path or "/", safe="/%:@!$&'()*+,;=-._~")
                    + (
                        "?" + quote(p.query, safe="=&;%:+,/?@!$'()*-._~")
                        if p.query
                        else ""
                    )
                ),
                body=payload,
                headers={
                    "User-Agent": "mcp.hk-resources/0.4 (+https://mcp.hk)",
                    "Accept-Encoding": "identity" if identity_retry else "gzip",
                    **(headers or {}),
                    **(relay[1] if relay else {}),
                    **(gateway_headers(budget, url) if hosted else {}),
                },
            )
            if getattr(connection, "sock", None):
                connection.sock.settimeout(min(10, budget.remaining()))
            response = connection.getresponse()
            meta = {k.lower(): v for k, v in response.getheaders()}
            if hosted and response.status in {403, 429, 504}:
                raise DomainError(
                    "UPSTREAM_BUDGET",
                    "Edge upstream allocation denied",
                    response.status,
                )
            if relay and meta.get("x-mcp-source-transport") != "approved-worker-relay":
                raise DomainError(
                    "SOURCE_UNAVAILABLE", "Approved source relay was unavailable", 502
                )
            meta["_mcp_source_transport"] = (
                "edge-governed"
                if hosted
                else "approved-worker-relay" if relay else "direct"
            )
            if response.status in {301, 302, 303, 307, 308}:
                if relay:
                    raise DomainError(
                        "UNSAFE_SOURCE", "Source relay redirect rejected", 422
                    )
                if payload is not None:
                    raise DomainError(
                        "UNSAFE_SOURCE", "Transport POST redirects are not allowed", 422
                    )
                redirect_url = urljoin(url, meta.get("location", ""))
                validate_url(redirect_url)
                if p.scheme == "https" and urlsplit(redirect_url).scheme != "https":
                    raise DomainError("UNSAFE_SOURCE", "HTTPS downgrade rejected", 422)
                url = redirect_url
                continue
            if response.status == 304:
                return b"", meta, url, 304
            if response.status != 200:
                code = (
                    "ACCESS_RESTRICTED"
                    if response.status in {401, 403}
                    else (
                        "SOURCE_NOT_FOUND"
                        if response.status == 404
                        else "SOURCE_HTTP_ERROR"
                    )
                )
                raise DomainError(code, f"Source returned HTTP {response.status}", 502)
            if int(meta.get("content-length", "0")) > maximum:
                raise DomainError(
                    "SOURCE_TOO_LARGE", "Source exceeds download budget", 422
                )
            body = bytearray()
            length = 0
            if destination:
                output = Path(destination).open("wb")
            decoder = (
                zlib.decompressobj(16 + zlib.MAX_WBITS)
                if meta.get("content-encoding") == "gzip"
                else None
            )
            while True:
                if getattr(connection, "sock", None):
                    connection.sock.settimeout(min(10, budget.remaining()))
                budget.remaining()
                chunk = response.read1(65536)
                if not chunk:
                    break
                if time.monotonic() - started > deadline:
                    raise DomainError(
                        "SOURCE_TIMEOUT", "Source exceeded download deadline", 504
                    )
                if decoder:
                    chunk = decoder.decompress(chunk, maximum + 1 - length)
                budget.charge(len(chunk))
                length += len(chunk)
                if output:
                    output.write(chunk)
                else:
                    body.extend(chunk)
                if length > maximum or (decoder and decoder.unconsumed_tail):
                    raise DomainError(
                        "SOURCE_TOO_LARGE",
                        "Decoded source exceeds download budget",
                        422,
                    )
            # Some public APIs (observed HKSTP, 2026-10-18) advertise a successful
            # empty response only when gzip is requested. Retry the identical GET
            # once without compression; keep all URL, size and time guards.
            if (
                not length
                and not identity_retry
                and payload is None
                and not any(k.lower() == "accept-encoding" for k in (headers or {}))
            ):
                identity_retry = True
                continue
            if decoder and (not decoder.eof or decoder.unused_data):
                raise DomainError(
                    "INVALID_SOURCE",
                    "Incomplete or concatenated compressed response",
                    422,
                )
            return Path(destination) if destination else bytes(body), meta, url, 200
        finally:
            if output:
                output.close()
            connection.close()
    raise DomainError("SOURCE_REDIRECT_LIMIT", "Source redirected too many times", 422)


async def fetch(url, headers=None, maximum=MAX_BYTES, payload=None):
    try:
        return await asyncio.to_thread(
            fetch_sync, url, headers, maximum, payload=payload
        )
    except DomainError:
        raise
    except (
        OSError,
        ValueError,
        http.client.HTTPException,
        gzip.BadGzipFile,
        zlib.error,
    ) as exc:
        raise source_failure(exc) from None


def source_failure(exc):
    if isinstance(exc, ssl.SSLCertVerificationError):
        message = "Source TLS certificate could not be verified"
    elif isinstance(exc, ssl.SSLError):
        message = "Source TLS negotiation failed"
    elif isinstance(exc, socket.gaierror):
        message = "Source DNS lookup failed"
    elif isinstance(exc, TimeoutError):
        message = "Source connection timed out"
    else:
        message = "Source download failed"
    return DomainError("SOURCE_UNAVAILABLE", message, 502)


async def fetch_file(url, maximum=128_000_000):
    fd, name = tempfile.mkstemp(prefix="mcp-hk-resource-", suffix=".source")
    os.close(fd)
    path = Path(name)
    cancelled = threading.Event()

    def download():
        try:
            return fetch_sync(url, None, maximum, path, deadline=60)
        finally:
            if cancelled.is_set():
                path.unlink(missing_ok=True)

    try:
        return await asyncio.to_thread(download)
    except BaseException as exc:
        cancelled.set()
        path.unlink(missing_ok=True)
        if not isinstance(exc, Exception):
            raise
        if isinstance(exc, DomainError):
            raise
        raise source_failure(exc) from None
