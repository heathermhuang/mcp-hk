"""Explicit file choices from independently inspected publisher index pages."""

import asyncio
import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .contracts import DomainError

PAGES = {
    "https://www.census2021.gov.hk/" + lang + "/district_profiles.html"
    for lang in ["en", "tc", "sc"]
}
FILE = re.compile(r"[A-Za-z0-9_-]+_21C\.(?:xlsx|zip)\Z")
RECYCLING = "https://www.wastereduction.gov.hk/zh-hk/resources-centre/recyclable-collection-points-dataset"
RECYCLING_FILE = re.compile(r"wasteless[0-9]{6}\.csv\Z")


def profile(url):
    return url in PAGES or url == RECYCLING


def rules(url):
    if url in PAGES:
        return "www.census2021.gov.hk", "/doc/", FILE, "XML"
    if url == RECYCLING:
        return (
            "www.wastereduction.gov.hk",
            "/sites/default/files/",
            RECYCLING_FILE,
            "CSV",
        )
    raise DomainError(
        "UNSUPPORTED_FORMAT", "No published-file contract for this page", 422
    )


def selected(url, record_path):
    return profile(url) and record_path.startswith("file:")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and dict(attrs).get("href"):
            self.urls.append(dict(attrs)["href"])


def discover(url, body):
    host, prefix, pattern, _ = rules(url)
    parser = Links()
    parser.feed(body.decode("utf-8-sig"))
    files = {}
    for href in parser.urls:
        target = urlsplit(urljoin(url, href))
        name = target.path.removeprefix(prefix)
        if (
            target.scheme == "https"
            and target.netloc == host
            and target.path == prefix + name
            and pattern.fullmatch(name)
            and not target.query
            and not target.fragment
        ):
            files["file:" + name] = {
                "url": target.geturl(),
                "format": name.rsplit(".", 1)[1].upper(),
                "name": name,
            }
    if not files or len(files) > 100:
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED",
            "Published file list is absent or exceeds its bound",
            422,
        )
    return files


async def index(url, fetch):
    body, _, _, _ = await fetch(url)
    files = await asyncio.to_thread(discover, url, body)
    return files, hashlib.sha256(body).hexdigest()


async def schema(url, fetch):
    files, digest = await index(url, fetch)
    return {
        "selectionRequired": "recordPath",
        "recordCount": None,
        "structuredQueryable": False,
        "sourceInterface": {
            "kind": "published_file_index",
            "sourcePageSha256": digest,
            "advertisedCatalogueFormat": rules(url)[3],
            "originalRepresentationEquivalence": "unreviewed",
        },
        "schema": {
            "format": "HTML",
            "scope": "published_file_choices_not_accepted_records",
            "availableRecordPaths": [
                {"id": key, "name": value["name"]}
                for key, value in sorted(files.items())
            ],
        },
    }


async def request(url, record_path, fetch):
    files, digest = await index(url, fetch)
    if not record_path:
        raise DomainError(
            "RECORD_PATH_REQUIRED", "Select a file published by this source page", 400
        )
    if record_path not in files:
        raise DomainError(
            "INVALID_RECORD_PATH",
            "The source page does not publish that file choice",
            400,
        )
    file = files[record_path]
    return (
        file["url"],
        file["format"],
        {
            "publishedFile": {
                "selection": record_path,
                "sourcePageUrl": url,
                "sourcePageSha256": digest,
                "publishedUrl": file["url"],
            },
            "advertisedCatalogueFormat": rules(url)[3],
            "originalRepresentationEquivalence": "unreviewed",
            "rowMeaning": (
                "Original published rows; collection-point identity, coordinates and current service status remain unreviewed."
                if url == RECYCLING
                else "Raw parsed table/grid rows, including secondary headers or notes; not district/entity counts or qualified statistical observations."
            ),
        },
    )
