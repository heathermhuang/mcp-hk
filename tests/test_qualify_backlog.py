"""Qualification must not churn accepted selections past retention before querying."""

import argparse
from collections import OrderedDict
import gzip
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path


def test_queries_precede_variant_eviction_and_saved_receipts_are_reused(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "qualify_backlog",
        Path(__file__).parents[1] / "scripts" / "qualify_backlog.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = tmp_path / "manifest.json.gz"
    manifest.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "familyCandidates": [
                        {
                            "resourceId": "workbook",
                            "datasetId": "dataset",
                            "family": "workbook",
                            "lastStatus": "needs_selection",
                            "acceptedSameDatasetAlternatives": [],
                        }
                    ]
                }
            ).encode()
        )
    )
    cache = OrderedDict()
    cache_misses = []
    requests = []

    def request(req, timeout):
        args = json.loads(req.data)
        operation = req.full_url.rsplit("/", 1)[1]
        requests.append((operation, args.get("sheet")))
        if "sheet" not in args:
            value = {
                "selections": [
                    {
                        "argument": "sheet",
                        "options": [
                            {
                                "value": str(i),
                                "nextAction": {
                                    "arguments": {
                                        "resourceId": "workbook",
                                        "sheet": str(i),
                                    }
                                },
                            }
                            for i in range(52)
                        ],
                    }
                ]
            }
        elif operation == "schema":
            cache[args["sheet"]] = True
            while len(cache) > 50:
                cache.popitem(last=False)
            value = {"recordCount": 1, "schema": {"sourceResponseComplete": True}}
        else:
            if args["sheet"] not in cache:
                cache_misses.append(args["sheet"])
            value = {
                "data": {"items": [{"raw": args["sheet"]}]},
                "meta": {"total": 1},
                "schema": {"sourceResponseComplete": True},
            }
        response = io.BytesIO(json.dumps(value).encode())
        response.code = 200
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", request)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    args = argparse.Namespace(
        manifest=manifest,
        receipts=tmp_path / "receipts",
        family=None,
        read_options=True,
        requests=200,
    )
    module.main(args)
    assert len(requests) == 105
    assert not cache_misses
    receipts = list(args.receipts.glob("*-query.json.gz"))
    assert len(receipts) == 52
    assert all(json.load(gzip.open(p, "rt"))["httpStatus"] == 200 for p in receipts)
    requests.clear()
    args.requests = 1
    module.main(args)
    assert not requests


def test_query_leaf_proof_avoids_duplicate_materialization_and_replays_failures(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "qualify", Path(__file__).parents[1] / "scripts" / "qualify_backlog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = tmp_path / "manifest.json.gz"
    manifest.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "familyCandidates": [
                        {
                            "resourceId": "large-map",
                            "datasetId": "d",
                            "family": "arcgis",
                            "sourceUrl": "https://example.gov.hk/FeatureServer",
                            "lastStatus": "needs_selection",
                            "acceptedSameDatasetAlternatives": [],
                        }
                    ]
                }
            ).encode()
        )
    )
    calls = []
    materializations = []

    def request(req, timeout):
        q = json.loads(req.data)
        op = req.full_url.rsplit("/", 1)[1]
        calls.append((op, q))
        if "layer" not in q:
            value = {
                "selections": [
                    {
                        "argument": "layer",
                        "options": [
                            {
                                "value": i,
                                "nextAction": {
                                    "arguments": {"resourceId": "large-map", "layer": i}
                                },
                            }
                            for i in [0, 1]
                        ],
                    }
                ]
            }
            status = 200
        else:
            materializations.append(q["layer"])
            assert (
                op == "query"
            ), "An uncached selected schema would download the full layer again"
            if q["layer"] == 1:
                value = {"error": {"code": "ACCESS_RESTRICTED"}}
                status = 502
            else:
                value = {
                    "schema": {"sourceResponseComplete": True, "sourceMatched": 73058},
                    "meta": {"total": 73058},
                    "data": {"items": [{"nativeId": "0001"}]},
                }
                status = 200
        response = io.BytesIO(json.dumps(value).encode())
        response.code = status
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", request)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    args = argparse.Namespace(
        manifest=manifest,
        receipts=tmp_path / "receipts",
        family=None,
        read_options=True,
        requests=10,
        query_options=True,
    )
    module.main(args)
    assert len(calls) == 3 and materializations == [0, 1]
    assert not list(args.receipts.glob("*-schema.json.gz"))
    queries = [
        json.load(gzip.open(p, "rt")) for p in args.receipts.glob("*-query.json.gz")
    ]
    accepted = next(r for r in queries if r["httpStatus"] == 200)
    assert (
        accepted["operation"] == "query"
        and accepted["response"]["schema"]["sourceMatched"] == 73058
    )
    assert accepted["response"]["data"]["items"][0]["nativeId"] == "0001"
    calls.clear()
    args.query_options = False
    module.main(args)
    assert calls == [], "Legacy mode must reuse both query proof and a known denial"


def test_failure_context_retains_safe_headers_and_never_replays_the_failure(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "qualify_context", Path(__file__).parents[1] / "scripts" / "qualify_backlog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = tmp_path / "manifest.json.gz"
    manifest.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "familyCandidates": [
                        {
                            "resourceId": "r",
                            "datasetId": "d",
                            "family": "workbook",
                            "lastStatus": "needs_selection",
                            "acceptedSameDatasetAlternatives": [],
                        }
                    ]
                }
            ).encode()
        )
    )
    calls = []

    def request(req, timeout):
        calls.append(req.full_url)
        response = io.BytesIO(
            json.dumps({"error": {"code": "SERVICE_RECOVERING"}}).encode()
        )
        response.code = 503
        response.headers = Message()
        for name, value in {
            "CF-Ray": "synthetic-ray-SIN",
            "X-Request-ID": "synthetic-request",
            "X-Mcp-Release": "a" * 40,
            "Retry-After": "10",
            "Content-Type": "application/json",
            "Set-Cookie": "private-cookie",
            "Authorization": "Bearer private-auth",
            "Location": "https://private.invalid/?token=private-location",
        }.items():
            response.headers[name] = value
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", request)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    args = argparse.Namespace(
        manifest=manifest,
        receipts=tmp_path / "receipts",
        family=None,
        read_options=True,
        query_options=True,
        requests=1,
    )
    module.main(args)
    path = args.receipts / "r-options.json.gz"
    data = json.load(gzip.open(path, "rt"))
    assert (
        data["httpStatus"] == 503
        and data["response"]["error"]["code"] == "SERVICE_RECOVERING"
    )
    assert data["responseHeaders"] == {
        "cf-ray": "synthetic-ray-SIN",
        "x-request-id": "synthetic-request",
        "x-mcp-release": "a" * 40,
        "retry-after": "10",
        "content-type": "application/json",
    }
    assert "private-" not in json.dumps(data)
    before = path.read_bytes()
    module.main(args)
    assert len(calls) == 1 and path.read_bytes() == before


def test_response_context_omits_unbounded_and_control_character_values():
    spec = importlib.util.spec_from_file_location(
        "qualify_context_limits",
        Path(__file__).parents[1] / "scripts" / "qualify_backlog.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    response = argparse.Namespace(
        headers={"cf-ray": "x" * 257, "x-request-id": "a\r\nb"}
    )
    assert module.response_context(response) == {}


def test_native_xml_graph_discovers_files_before_queries_and_keeps_saved_failures(
    tmp_path, monkeypatch
):
    from mcp_open_data_hk import census_xml_archives

    spec = importlib.util.spec_from_file_location(
        "qualify_native_xml", Path(__file__).parents[1] / "scripts/qualify_backlog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    did, url = next(iter(census_xml_archives.SOURCES.items()))
    candidate = {
        "resourceId": "xml",
        "datasetId": did,
        "family": "xml",
        "format": "XML",
        "sourceUrl": url,
        "lastStatus": "unsupported",
        "acceptedSameDatasetAlternatives": [],
    }
    manifest = tmp_path / "manifest.json.gz"
    manifest.write_bytes(
        gzip.compress(json.dumps({"familyCandidates": [candidate]}).encode())
    )
    assert (
        module.candidates(
            {"familyCandidates": [{**candidate, "lastStatus": "restricted"}]}
        )
        == []
    )
    assert (
        module.candidates(
            {"familyCandidates": [{**candidate, "lastStatus": "unavailable"}]}
        )
        == []
    )
    requests = []

    def request(req, timeout):
        query = json.loads(req.data)
        operation = req.full_url.rsplit("/", 1)[1]
        path = query.get("recordPath", "")
        requests.append((operation, path))
        if not path:
            assert operation == "schema"
            paths = ["file:F101s.zip", "file:F102s.zip"]
        elif "/" not in path:
            assert operation == "schema"
            paths = [path + "/Observation", path + "/Class_code"]
        else:
            assert operation == "query" and query["requireFresh"] is True
            paths = None
        value = (
            {
                "selections": [
                    {
                        "argument": "recordPath",
                        "options": [
                            {
                                "value": p,
                                "nextAction": {
                                    "arguments": {"resourceId": "xml", "recordPath": p}
                                },
                            }
                            for p in paths
                        ],
                    }
                ]
            }
            if paths
            else {
                "schema": {"sourceResponseComplete": True},
                "meta": {"total": 1},
                "data": {"items": [{"raw": path}]},
            }
        )
        response = io.BytesIO(json.dumps(value).encode())
        response.code = 200
        if path == "file:F101s.zip/Class_code":
            response = io.BytesIO(
                json.dumps({"error": {"code": "SOURCE_UNAVAILABLE"}}).encode()
            )
            response.code = 502
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", request)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    args = argparse.Namespace(
        manifest=manifest,
        receipts=tmp_path / "receipts",
        family=None,
        read_options=True,
        query_options=True,
        requests=20,
    )
    module.main(args)
    assert len(requests) == 5
    assert sum(op == "query" for op, _ in requests) == 2
    assert not any(
        op == "query" and path.startswith("file:F102s.zip/") for op, path in requests
    )
    failures = [
        json.load(gzip.open(p, "rt")) for p in args.receipts.glob("*-query.json.gz")
    ]
    assert sum(x["httpStatus"] == 502 for x in failures) == 1
    requests.clear()
    module.main(args)
    assert not requests
