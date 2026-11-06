"""Explicit native groups in three published Census16 nested XML archives."""

import hashlib
import io
import re
import stat
import zipfile

from defusedxml import ElementTree

from .contracts import DomainError
from .resource_formats import invalid, parse

SOURCES = {
    "hk-censtatd-census16bc-d521"
    + number: "https://www.censtatd.gov.hk/en/data/stat_report/product/D521"
    + number
    + "/att/D521"
    + number
    + "V2016XXXXV.zip"
    for number in ["1606", "1607", "1608"]
}
REVISION = "census16-nested-xml-1"
MAX_EXPANDED = 32_000_000
MAX_MEMBERS = 1000


def profile(resource):
    return (
        resource.get("format") == "XML"
        and resource.get("datasetId") in SOURCES
        and SOURCES[resource["datasetId"]] == resource.get("url")
    )


def selector(record_path):
    if not record_path:
        return "", ""
    match = re.fullmatch(
        r"file:([A-Za-z0-9_.()-]+\.[Zz][Ii][Pp])(?:/([A-Za-z_][A-Za-z0-9_.-]*))?",
        record_path,
    )
    if not match:
        raise DomainError(
            "INVALID_RECORD_PATH",
            "Select a published nested archive and native XML group",
            400,
        )
    return match[1], match[2] or ""


def validate(record_path, sheet="", layer=None):
    if sheet or layer is not None:
        raise DomainError(
            "INVALID_QUERY", "Nested XML archives have no workbook or map selector", 400
        )
    return selector(record_path)


def selected(resource, record_path):
    return profile(resource) and bool(record_path)


def members(archive):
    entries = archive.infolist()
    if not entries:
        invalid("Published archive has no file members")
    if len(entries) > MAX_MEMBERS:
        invalid("Nested archive member count exceeds its bound", "SOURCE_TOO_LARGE")
    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)):
        invalid("Duplicate archive member names")
    for entry in entries:
        if (
            entry.is_dir()
            or stat.S_IFMT(entry.external_attr >> 16) not in {0, stat.S_IFREG}
            or not re.fullmatch(r"[A-Za-z0-9_.()-]+", entry.filename)
            or entry.filename in {".", ".."}
        ):
            invalid("Unexpected archive member path")
        if entry.flag_bits & 1:
            invalid("Encrypted archive", "ACCESS_RESTRICTED")
    return entries


def bounded_read(archive, entry):
    if entry.file_size > MAX_EXPANDED:
        invalid("Archive expansion exceeds budget", "SOURCE_TOO_LARGE")
    with archive.open(entry) as stream:
        body = stream.read(MAX_EXPANDED + 1)
    if len(body) != entry.file_size or len(body) > MAX_EXPANDED:
        invalid("Archive size or expansion changed", "SOURCE_TOO_LARGE")
    return body


def complete_framing(body, archive):
    end = len(body) - len(archive.comment) - 22
    if (
        not body.startswith(b"PK\x03\x04")
        or end < 0
        or body[end : end + 4] != b"PK\x05\x06"
        or int.from_bytes(body[end + 20 : end + 22], "little") != len(archive.comment)
    ):
        invalid("Archive has an unexpected prefix or trailing data")


def index(body):
    result = {}
    expanded = count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as outer:
            complete_framing(body, outer)
            entries = members(outer)
            expanded += sum(x.file_size for x in entries)
            count += len(entries)
            if expanded > MAX_EXPANDED:
                invalid("Archive expansion exceeds budget", "SOURCE_TOO_LARGE")
            for entry in entries:
                if not entry.filename.lower().endswith(".zip"):
                    invalid("Expected a published inner ZIP table")
                nested = bounded_read(outer, entry)
                with zipfile.ZipFile(io.BytesIO(nested)) as inner:
                    complete_framing(nested, inner)
                    children = members(inner)
                    expanded += sum(x.file_size for x in children)
                    count += len(children)
                    if expanded > MAX_EXPANDED or count > MAX_MEMBERS:
                        invalid(
                            "Cumulative nested archive budget exceeded",
                            "SOURCE_TOO_LARGE",
                        )
                    xml = [
                        x.filename
                        for x in children
                        if x.filename.lower().endswith(".xml")
                    ]
                    xsd = [
                        x.filename
                        for x in children
                        if x.filename.lower().endswith(".xsd")
                    ]
                    if len(children) != 2 or len(xml) != 1 or len(xsd) != 1:
                        invalid(
                            "Expected one XML table and its XSD; deeper archives are not supported"
                        )
                result[entry.filename] = (nested, xml[0], xsd[0])
    except (zipfile.BadZipFile, EOFError, RuntimeError):
        invalid("Malformed nested archive")
    return result


def table(files, name):
    if name not in files:
        raise DomainError(
            "INVALID_RECORD_PATH",
            "The original archive does not contain that table",
            400,
        )
    nested, xml_name, xsd_name = files[name]
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        xml = bounded_read(inner, inner.getinfo(xml_name))
        xsd = bounded_read(inner, inner.getinfo(xsd_name))
    root = ElementTree.fromstring(xml)
    groups = list(dict.fromkeys(child.tag for child in root))
    if (
        root.tag != "root"
        or root.attrib
        or not groups
        or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", tag) for tag in groups)
    ):
        invalid("The native XML group layout changed")
    return xml, xsd, groups


def choices(body, record_path=""):
    name, path = selector(record_path)
    if path:
        raise DomainError(
            "INVALID_QUERY", "Use the selected XML group for records", 400
        )
    files = index(body)
    paths = (
        ["file:" + key for key in sorted(files)]
        if not name
        else ["file:" + name + "/" + group for group in table(files, name)[2]]
    )
    return {
        "selectionRequired": "recordPath",
        "recordCount": None,
        "structuredQueryable": False,
        "schema": {
            "format": "XML",
            "scope": "native_archive_group_choices_not_accepted_records",
            "availableRecordPaths": paths,
            "sourceContentHash": hashlib.sha256(body).hexdigest(),
        },
    }


def read(body, record_path="", sheet="", layer=None):
    name, path = validate(record_path, sheet, layer)
    if not name or not path:
        raise DomainError(
            "RECORD_PATH_REQUIRED", "Select a native archive member and XML group", 400
        )
    files = index(body)
    xml, xsd, groups = table(files, name)
    if path not in groups:
        raise DomainError("INVALID_RECORD_PATH", "Native XML group not found", 400)
    rows, schema = parse(xml, "XML", path)
    schema.update(
        sourceContract={"id": REVISION},
        observedSerialization="census16_two_layer_zip_xml",
        sourceArchiveMember=name,
        sourceXmlMember=files[name][1],
        sourceDictionaryMember=files[name][2],
        sourceXmlSha256=hashlib.sha256(xml).hexdigest(),
        sourceDictionarySha256=hashlib.sha256(xsd).hexdigest(),
        sourceContentHash=hashlib.sha256(body).hexdigest(),
        sourceResponseBytes=len(body),
        sourceFramingFullyConsumed=True,
        sourceArchiveValidationScope="Bounded archive directories and selected XML/XSD bytes; no record acceptance for unselected members.",
        unselectedArchiveMembers=[key for key in files if key != name],
        availableRecordPaths=["file:" + name + "/" + group for group in groups],
        scope="selected_native_xml_group",
        datasetCompleteness="Only this native XML group; other groups and dictionaries are not accepted record reads.",
        rowMeaning="Raw selected XML elements, not normalized statistical estimates or unique entities.",
        originalRepresentationEquivalence="unreviewed",
    )
    return rows, schema
