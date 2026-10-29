"""Reproducible synthetic reader benchmark; not a production headroom proof."""

import asyncio
import json
import os
import sys
import time
import tempfile
import statistics
import resource
from pathlib import Path

if "--worker" in sys.argv:
    from mcp_open_data_hk.resources import Resources
    from mcp_open_data_hk.resource_formats import parse
    from mcp_open_data_hk.resource_stream import FileRows

    scenario = sys.argv[-1]
    n = 100000 if scenario in ("warm100k", "file100k", "filtered100k") else 10000
    wide = scenario == "nested_wide"
    rows = [
        {
            "id": str(i).zfill(8),
            "n": i,
            "text": "中文 source " + str(i),
            **(
                {
                    "nested": {"x": i, "f": 1.0},
                    **{f"field{k}": str(k) for k in range(50)},
                }
                if wide
                else {}
            ),
        }
        for i in range(n)
    ]
    body = json.dumps(rows, ensure_ascii=False).encode()
    started = time.perf_counter()
    parsed, schema = parse(body, "JSON")
    cold = time.perf_counter() - started
    engine = Resources.__new__(Resources)
    engine.active_scans = 0
    engine.scan_limit = 2
    engine.scan_seconds = 5
    scratch = tempfile.TemporaryDirectory(prefix="playground-benchmark-")
    path = Path(scratch.name)

    async def load(*args, **kwargs):
        def disk():
            import uuid

            item = path / (uuid.uuid4().hex + ".json")
            item.write_bytes(body)
            return FileRows(item, "JSON")

        data = await asyncio.to_thread(disk) if scenario == "file100k" else parsed
        return {}, {"rows": data, "schema": schema}, {"hash": "abc"}, False

    engine.load = load
    engine.envelope = lambda *args: {
        "schema": schema,
        "provenance": [
            {
                "sourceUrl": "https://example.gov.hk",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
            }
        ],
        "warnings": [],
    }
    candidate = os.environ.get("PLAYGROUND_CANDIDATE") == "1"

    async def main():
        timings = []
        cpu = []
        sizes = []
        for i in range(9):
            begin = time.perf_counter()
            ct = time.process_time()
            p = await engine.query(
                "r",
                fields=["id", "n", "text"],
                filters={"n": n - 1} if scenario == "filtered100k" else None,
                **({"presentation": True} if candidate else {}),
            )
            timings.append(time.perf_counter() - begin)
            cpu.append(time.process_time() - ct)
            sizes.append(len(json.dumps(p, ensure_ascii=False).encode()))
        ticks = []
        done = False

        async def maintenance():
            import sqlite3

            db = sqlite3.connect(":memory:")
            db.execute("create table checkpoint(n integer)")
            while not done:
                tick = time.perf_counter()
                await asyncio.sleep(0.005)
                db.execute("insert into checkpoint values (1)")
                ticks.append(time.perf_counter() - tick)
            db.close()

        beat = asyncio.create_task(maintenance())
        await asyncio.gather(
            engine.query(
                "r",
                fields=["id", "n"],
                filters={"n": n - 1} if scenario == "filtered100k" else None,
            ),
            engine.query(
                "r",
                fields=["id", "n"],
                filters={"n": n - 1} if scenario == "filtered100k" else None,
            ),
        )
        done = True
        await beat
        print(
            json.dumps(
                {
                    "scenario": scenario,
                    "n": n,
                    "samples": 9,
                    "python": sys.version.split()[0],
                    "inputBytes": len(body),
                    "fieldCount": len(rows[0]),
                    "coldParseMs": cold * 1000,
                    "medianMs": statistics.median(timings) * 1000,
                    "p95Ms": sorted(timings)[-1] * 1000,
                    "cpuMedianMs": statistics.median(cpu) * 1000,
                    "bytes": sizes[0],
                    "maxMaintenanceTickMs": max(ticks) * 1000,
                    "peakRssBytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    * (1 if sys.platform == "darwin" else 1024),
                    "timingsMs": [t * 1000 for t in timings],
                }
            )
        )

    asyncio.run(main())
    scratch.cleanup()
    sys.exit()
import subprocess
import argparse

parser = argparse.ArgumentParser(
    description="Interleaved local query/parse comparison; zero provider requests"
)
parser.add_argument("--baseline", type=Path, required=True)
parser.add_argument(
    "--candidate", type=Path, default=Path(__file__).resolve().parents[1]
)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--scenario",
    action="append",
    choices=["warm10k", "warm100k", "filtered100k", "nested_wide", "file100k"],
)
options = parser.parse_args()
options.output.parent.mkdir(parents=True, exist_ok=True)
results = []
for scenario in options.scenario or [
    "warm10k",
    "warm100k",
    "filtered100k",
    "nested_wide",
    "file100k",
]:
    for round in range(2):
        for label, folder in (
            [("baseline", options.baseline), ("candidate", options.candidate)]
            if round == 0
            else [("candidate", options.candidate), ("baseline", options.baseline)]
        ):
            env = {
                **os.environ,
                "PYTHONPATH": str(folder / "src"),
                "PLAYGROUND_CANDIDATE": "1" if label == "candidate" else "0",
            }
            p = subprocess.run(
                [sys.executable, __file__, "--worker", scenario],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            results.append({"variant": label, "round": round, **json.loads(p.stdout)})
            options.output.write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
