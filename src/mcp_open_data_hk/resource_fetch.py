"""Bounded public-source downloads with DNS-pinned connections and redirect checks."""

import asyncio
import gzip
import http.client
import ipaddress
import socket
import ssl
import time
import zlib
from urllib.parse import urljoin, urlsplit

from .contracts import DomainError

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
    if not addresses or any(
        not ipaddress.ip_address(a[4][0]).is_global for a in addresses
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
            conn = socket.socket(family, kind, proto)
            conn.settimeout(self.timeout)
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
        self.sock = ssl.create_default_context().wrap_socket(
            self.sock, server_hostname=self.host
        )


def fetch_sync(url, headers=None, maximum=MAX_BYTES):
    started = time.monotonic()
    for _ in range(4):
        p = validate_url(url)
        connection = (PinnedHTTPS if p.scheme == "https" else PinnedHTTP)(
            p.hostname, port=p.port, timeout=10
        )
        try:
            connection.request(
                "GET",
                p.path + ("?" + p.query if p.query else ""),
                headers={
                    "User-Agent": "mcp.hk-resources/0.4 (+https://mcp.hk)",
                    "Accept-Encoding": "gzip",
                    **(headers or {}),
                },
            )
            response = connection.getresponse()
            meta = {k.lower(): v for k, v in response.getheaders()}
            if response.status in {301, 302, 303, 307, 308}:
                destination = urljoin(url, meta.get("location", ""))
                validate_url(destination)
                if p.scheme == "https" and urlsplit(destination).scheme != "https":
                    raise DomainError("UNSAFE_SOURCE", "HTTPS downgrade rejected", 422)
                url = destination
                continue
            if response.status == 304:
                return b"", meta, url, 304
            if response.status != 200:
                code = (
                    "ACCESS_RESTRICTED"
                    if response.status in {401, 403}
                    else "SOURCE_HTTP_ERROR"
                )
                raise DomainError(code, f"Source returned HTTP {response.status}", 502)
            if int(meta.get("content-length", "0")) > maximum:
                raise DomainError(
                    "SOURCE_TOO_LARGE", "Source exceeds download budget", 422
                )
            body = bytearray()
            decoder = (
                zlib.decompressobj(16 + zlib.MAX_WBITS)
                if meta.get("content-encoding") == "gzip"
                else None
            )
            while chunk := response.read1(65536):
                if time.monotonic() - started > 30:
                    raise DomainError(
                        "SOURCE_TIMEOUT", "Source exceeded download deadline", 504
                    )
                if decoder:
                    chunk = decoder.decompress(chunk, maximum + 1 - len(body))
                body.extend(chunk)
                if len(body) > maximum or (decoder and decoder.unconsumed_tail):
                    raise DomainError(
                        "SOURCE_TOO_LARGE",
                        "Decoded source exceeds download budget",
                        422,
                    )
            if decoder and (not decoder.eof or decoder.unused_data):
                raise DomainError(
                    "INVALID_SOURCE",
                    "Incomplete or concatenated compressed response",
                    422,
                )
            return bytes(body), meta, url, 200
        finally:
            connection.close()
    raise DomainError("SOURCE_REDIRECT_LIMIT", "Source redirected too many times", 422)


async def fetch(url, headers=None, maximum=MAX_BYTES):
    try:
        return await asyncio.to_thread(fetch_sync, url, headers, maximum)
    except DomainError:
        raise
    except (
        OSError,
        ValueError,
        http.client.HTTPException,
        gzip.BadGzipFile,
        zlib.error,
    ):
        raise DomainError("SOURCE_UNAVAILABLE", "Source download failed", 502) from None
