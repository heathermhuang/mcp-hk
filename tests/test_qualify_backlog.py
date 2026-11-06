"""Qualification must not churn accepted selections past retention before querying."""

import argparse
from collections import OrderedDict
import gzip
import importlib.util
import io
import json
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
