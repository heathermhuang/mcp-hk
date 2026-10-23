"""Bounded read-only streaming of the already verified, isolated source database."""

import json
import os
import re
import selectors
import subprocess
import tempfile
import time

from ..archive_audit import AuditError, disk_check
from ..archive_restore import install_client_config, isolation, query
from ..archive_sql import SELECTED


ARCHIVE_SHA256 = "9c2c42ae5e762d34b60954f43b37199b92b546033e229a292ed08b76323f6de2"


class Source:
    def __init__(self, workspace, container, database):
        if not re.fullmatch(r"audit_[a-z0-9_]{1,50}", database):
            raise ValueError("Use a recorded audit database")
        restored = json.loads((workspace / f"{database}-restore.json").read_text())
        audit = json.loads((workspace / "archive-audit.json").read_text())
        acquisition = json.loads((workspace / "acquisition.json").read_text())
        if (
            restored.get("status") != "restored"
            or audit.get("status") != "source_fidelity_verified"
            or restored["sourceArchiveSha256"] != acquisition["sha256"]
        ):
            raise ValueError("Source has not passed archive qualification")
        if acquisition["sha256"] != ARCHIVE_SHA256:
            raise ValueError(
                "This transform is qualified only for the original enigma251227 bytes"
            )
        isolation(workspace, container)
        install_client_config(workspace, container)
        census_sql = (
            "SET SESSION TRANSACTION READ ONLY; SET SESSION max_execution_time=120000; "
            + "".join(
                f"SELECT JSON_ARRAY('{table}',COUNT(*)) FROM `{table}`;"
                for table in SELECTED
            )
        )
        current_counts = dict(
            json.loads(line)
            for line in query(container, database, census_sql).splitlines()
        )
        expected_counts = {
            table: restored["restoredTableAudit"][table]["rows"] for table in SELECTED
        }
        if current_counts != expected_counts:
            raise ValueError(
                "Source database row census differs from the verified restore"
            )
        self.workspace, self.container, self.database = workspace, container, database
        self.manifest = {
            "archiveSha256": acquisition["sha256"],
            "sourceDataSha256": restored["dataSha256"],
            "sourceStructureSha256": restored["structureSha256"],
            "sourceRelease": "enigma251227",
            "attribution": "David Webb / Webb-site, original Enigma release",
            "notice": "webb-site-NOTICE.txt",
            "licence": "CC-BY; retain the original release notice",
            "view": "archive",
            "observedAt": None,
            "coverage": "Source observations vary by record; not a current register",
        }

    def rows(self, table, columns, where="1"):
        if table not in SELECTED or any(
            not re.fullmatch(r"[A-Za-z0-9_]+", c) for c in columns
        ):
            raise ValueError("Unsupported source projection")
        expressions = [
            f"CAST(`{c}` AS UNSIGNED)" if c in {"ri", "SFCri"} else f"`{c}`"
            for c in columns
        ]
        sql = (
            "SET SESSION TRANSACTION READ ONLY; SET SESSION max_execution_time=1200000; "
            f"SELECT JSON_ARRAY({','.join(expressions)}) FROM `{table}` WHERE {where};"
        )
        command = [
            "docker",
            "exec",
            "-i",
            self.container,
            "mysql",
            "--defaults-extra-file=/tmp/mcp-audit-client.cnf",
            "--batch",
            "--raw",
            "--skip-column-names",
            self.database,
        ]
        deadline = time.monotonic() + 1800
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors
            )
            try:
                process.stdin.write(sql.encode())
                process.stdin.close()
                buffer = b""
                streamed = 0
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Source stream exceeded 30 minutes")
                        if not selector.select(
                            timeout=min(5, max(0, deadline - time.monotonic()))
                        ):
                            continue
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            break
                        buffer += chunk
                        if len(buffer) > 2 * 1024 * 1024:
                            raise ValueError(
                                "Source row exceeds the bounded JSON record size"
                            )
                        lines = buffer.split(b"\n")
                        buffer = lines.pop()
                        for line in lines:
                            if line:
                                streamed += 1
                                if streamed % 100000 == 0:
                                    self.check_disk()
                                yield dict(zip(columns, json.loads(line), strict=True))
                if buffer or process.wait(timeout=10):
                    raise AuditError(
                        "SOURCE_QUERY_FAILED",
                        "Source stream was incomplete; no empty fallback",
                    )
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                process.stdout.close()

    def check_disk(self):
        disk_check(self.workspace)
