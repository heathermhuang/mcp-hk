"""Validated disk-backed CSV/JSON iterators: bounded memory, complete-file queries."""

import csv
import hashlib
import json
import codecs

import ijson
from ijson.common import ObjectBuilder

from .contracts import DomainError
from .resource_fields import add_nested, nested_schema
from .resource_formats import table, safe_json


class FileRows:
    def __init__(self, path, fmt, record_path=""):
        self.path = path
        self.fmt = fmt.upper()
        self.record_path = record_path
        self.count = 0
        with path.open("rb") as f:
            sample = f.read(65536)
        if self.fmt in {"API", "JSON", "GEOJSON"}:
            self.fmt = "GEOJSON" if self.fmt == "GEOJSON" else "JSON"
            if self.fmt == "GEOJSON":
                self.record_path = "features"
            elif not self.record_path and not sample.lstrip().startswith(b"["):
                raise DomainError(
                    "RECORD_PATH_REQUIRED",
                    "Select an array recordPath for this large JSON object",
                    400,
                )
            if any(
                p.isdigit() or "." in p or "~" in p for p in self.record_path.split("/")
            ):
                raise DomainError(
                    "INVALID_RECORD_PATH",
                    "Large JSON paths require object keys without dots or array indices",
                    400,
                )
        elif self.fmt == "CSV":
            self.encoding = (
                "utf-16"
                if sample.startswith((b"\xff\xfe", b"\xfe\xff"))
                else "utf-8-sig"
            )
            try:
                with path.open("r", encoding=self.encoding) as source:
                    while source.read(65536):
                        pass
            except UnicodeError:
                self.encoding = "big5hkscs"
            decoded = codecs.getincrementaldecoder(self.encoding)().decode(
                sample, final=False
            )
            if "\x00" in decoded or decoded.lstrip().lower().startswith(
                ("<html", "<!doctype")
            ):
                raise DomainError(
                    "INVALID_SOURCE", "Expected CSV, received binary/HTML", 422
                )
        else:
            raise DomainError(
                "UNSUPPORTED_FORMAT",
                "Large-file streaming supports CSV/JSON/GeoJSON",
                422,
            )
        self.schema = {
            "format": self.fmt,
            "recordPath": self.record_path or None,
            "streamed": True,
            "scope": "complete_streamed_file",
            "normalization": "Original source values and explicit positional header mappings; no inferred units/reference periods.",
        }
        if self.fmt == "CSV":
            self.schema["encoding"] = self.encoding
        stats = {}
        nested_stats = {}
        cells = 0
        records_digest = hashlib.sha256()
        for row in self:
            self.count += 1
            add_nested(nested_stats, row)
            cells += len(row)
            records_digest.update(
                json.dumps(
                    row, sort_keys=True, ensure_ascii=False, allow_nan=False
                ).encode()
                + b"\n"
            )
            if self.count > 1_000_000 or cells > 10_000_000:
                raise DomainError(
                    "SOURCE_TOO_LARGE", "Streamed row/cell budget exceeded", 422
                )
            for k, v in row.items():
                kind = (
                    "null"
                    if v is None
                    else (
                        "boolean"
                        if isinstance(v, bool)
                        else (
                            "number"
                            if isinstance(v, (int, float))
                            else (
                                "object"
                                if isinstance(v, dict)
                                else "array" if isinstance(v, list) else "string"
                            )
                        )
                    )
                )
                entry = stats.setdefault(k, {"types": set(), "present": 0})
                entry["types"].add(kind)
                entry["present"] += v is not None
            if len(stats) > 1000:
                raise DomainError(
                    "SOURCE_TOO_COMPLEX", "Streamed field budget exceeded", 422
                )
        self.schema["fields"] = [
            {
                "name": k,
                "types": sorted(
                    v["types"] | ({"null"} if v["present"] < self.count else set())
                ),
                "missingCount": self.count - v["present"],
                "unit": None,
            }
            for k, v in sorted(stats.items())
        ]
        self.schema["queryFields"] = nested_schema(nested_stats, self.count)
        digest = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                digest.update(chunk)
        self.digest = digest.hexdigest()
        self.records_digest = records_digest.hexdigest()
        self.schema["sourceContentHash"] = self.digest
        self.schema["versionScope"] = "selected_records"

    def __len__(self):
        return self.count

    def __iter__(self):
        if self.fmt == "CSV":
            with self.path.open("r", encoding=self.encoding, newline="") as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.reader(f, dialect, strict=True)
                header = next(reader, None)
                if header is None:
                    raise DomainError("INVALID_SOURCE", "Empty CSV source", 422)
                info = {}
                table([header], info)
                columns = [c["name"] for c in info["sourceColumns"]]
                self.schema.update(info)
                for values in reader:
                    if not any(values):
                        continue
                    if len(values) > 1000:
                        raise DomainError(
                            "SOURCE_TOO_COMPLEX", "CSV field budget exceeded", 422
                        )
                    while len(values) > len(columns):
                        field = "_column_" + str(len(columns) + 1)
                        while field in columns:
                            field = "_" + field
                        columns.append(field)
                        self.schema["sourceColumns"].append(
                            {
                                "name": field,
                                "sourceHeader": None,
                                "columnIndex": len(columns),
                            }
                        )
                    yield dict(zip(columns, values))
            return
        prefix = (
            self.record_path.replace("/", ".") + "." if self.record_path else ""
        ) + "item"
        array_prefix = prefix.removesuffix(".item") if "." in prefix else ""
        found = False
        builder = None
        record_depth = 0
        cost = 0
        stack = []
        with self.path.open("rb") as f:
            if f.read(3) != b"\xef\xbb\xbf":
                f.seek(0)
            for location, event, value in ijson.parse(f, use_float=True):
                if event in {"start_map", "start_array"}:
                    stack.append(set() if event == "start_map" else None)
                    if len(stack) > 30:
                        raise DomainError(
                            "SOURCE_TOO_COMPLEX", "JSON depth budget exceeded", 422
                        )
                elif event == "map_key":
                    if value in stack[-1]:
                        raise DomainError(
                            "INVALID_SOURCE", "Duplicate JSON object key", 422
                        )
                    stack[-1].add(value)
                    if len(stack[-1]) > 1000:
                        raise DomainError(
                            "SOURCE_TOO_COMPLEX", "JSON field budget exceeded", 422
                        )
                if location == array_prefix and event == "start_array":
                    found = True
                if builder is None and location == prefix:
                    if event in {"start_map", "start_array"}:
                        builder = ObjectBuilder()
                        record_depth = 0
                        cost = 0
                    elif event not in {"end_map", "end_array", "map_key"}:
                        yield {"value": value}
                        continue
                if builder is not None:
                    cost += len(value) if isinstance(value, str) else 16
                    if cost > 1_000_000:
                        raise DomainError(
                            "SOURCE_TOO_LARGE",
                            "Individual streamed record exceeds budget",
                            422,
                        )
                    builder.event(event, value)
                    if event in {"start_map", "start_array"}:
                        record_depth += 1
                    elif event in {"end_map", "end_array"}:
                        record_depth -= 1
                        if record_depth == 0:
                            row = builder.value
                            builder = None
                            yield safe_json(
                                row if isinstance(row, dict) else {"value": row}
                            )
                if event in {"end_map", "end_array"}:
                    stack.pop()
        if not found:
            raise DomainError(
                "INVALID_RECORD_PATH", "JSON path did not select a source array", 400
            )

    def close(self):
        if self.path is not None:
            path, self.path = self.path, None
            path.unlink(missing_ok=True)

    def __del__(self):
        self.close()
