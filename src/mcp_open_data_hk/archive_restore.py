"""Restore only vetted literal projections into a dedicated, disconnected MySQL."""

import json
import os
import re
import secrets
import selectors
import subprocess
import tempfile
import time

from .archive_audit import (
    AuditError,
    GIB,
    atomic_json,
    disk_check,
    now,
    receipt,
    sha256,
)
from .archive_sql import (
    SELECTED,
    audit_ddl,
    preflight_columns,
    scan_dump,
    schema_inventory,
)

IMAGE = "mysql@sha256:598bf8b783dddc9070e9011aeb1eb5947f0bf7c4eda8ac510906556b8a2b6d0a"


def docker(*args, data=None, timeout=120):
    return subprocess.run(
        ["docker", *args], input=data, capture_output=True, timeout=timeout, check=True
    )


def isolation(workspace, container):
    info = json.loads(docker("inspect", container).stdout)[0]
    config = info["HostConfig"]
    mounts = info["Mounts"]
    if (
        info["Config"]["Image"] != IMAGE
        or config["NetworkMode"] != "none"
        or config.get("PortBindings")
        or config.get("Privileged")
        or not 0 < config["Memory"] <= 8 * GIB
        or not any(
            m["Source"] == str(workspace / "mysql")
            and m["Destination"] == "/var/lib/mysql"
            for m in mounts
        )
        or any(
            m.get("Type") == "bind" and m["Source"] != str(workspace / "mysql")
            for m in mounts
        )
    ):
        raise AuditError(
            "UNSAFE_DATABASE", "Database is not the isolated bounded audit container"
        )
    return {
        "image": IMAGE,
        "network": "none",
        "publishedPorts": [],
        "memoryBytes": config["Memory"],
        "containerId": info["Id"],
    }


def member_file(workspace, kind):
    acquisition = json.loads((workspace / "acquisition.json").read_text())
    inventory = json.loads((workspace / "archive-members.json").read_text())
    for path in workspace.glob("member-*.json"):
        proof = json.loads(path.read_text())
        if proof.get("member", "").startswith("enigma" + kind):
            expected = next(
                (m for m in inventory["members"] if m["path"] == proof["member"]), None
            )
            if (
                not re.fullmatch(r"member-[0-9a-f]{24}\.sql", proof.get("path", ""))
                or acquisition.get("status") != "verified"
                or proof.get("archiveSha256") != acquisition.get("sha256")
                or expected is None
                or expected["bytes"] != proof["bytes"]
            ):
                raise AuditError(
                    "UNVERIFIED_EXTRACTION",
                    "Member proof does not match the accepted source inventory",
                )
            data = workspace / proof["path"]
            if (
                data.is_symlink()
                or data.stat().st_size != proof["bytes"]
                or sha256(data) != proof["sha256"]
            ):
                raise AuditError(
                    "CHECKSUM_MISMATCH", "Extracted member changed before restore"
                )
            return data, proof
    raise AuditError(
        "MEMBER_NOT_EXTRACTED", "Extract the verified structure and data members first"
    )


def query(container, database, sql, root=False):
    auth = ["-uroot"] if root else ["--defaults-extra-file=/tmp/mcp-audit-client.cnf"]
    command = [
        "exec",
        "-i",
        container,
        "mysql",
        *auth,
        "--batch",
        "--raw",
        "--skip-column-names",
    ]
    if database:
        command.append(database)
    return docker(*command, data=sql.encode(), timeout=300).stdout.decode("utf-8")


def install_client_config(workspace, container):
    config = workspace / ".mysql-audit-client.cnf"
    if config.is_symlink() or config.stat().st_mode & 0o077:
        raise AuditError(
            "UNSAFE_CREDENTIAL_FILE", "Audit client credentials must remain owner-only"
        )
    docker(
        "exec",
        "-i",
        container,
        "sh",
        "-c",
        "umask 077; cat > /tmp/mcp-audit-client.cnf",
        data=config.read_bytes(),
    )


class DeadlineWriter:
    """Bound every pipe write, including when the database stops consuming."""

    def __init__(self, stream, deadline):
        self.fd, self.deadline = stream.fileno(), deadline
        os.set_blocking(self.fd, False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.fd, selectors.EVENT_WRITE)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.selector.close()

    def write(self, data):
        remaining = memoryview(data)
        while remaining:
            timeout = self.deadline - time.monotonic()
            if timeout <= 0:
                raise AuditError(
                    "RESTORE_TIMEOUT", "One-hour audit import bound reached"
                )
            if not self.selector.select(timeout=min(timeout, 5)):
                continue
            try:
                written = os.write(self.fd, remaining[:65536])
            except BlockingIOError:
                continue
            remaining = remaining[written:]


def loader_setup(database, password):
    # Database-level GRANT names are patterns in MySQL: escape underscores.
    grant_database = database.replace("_", "\\_")
    return (
        f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4;\n"
        "DROP USER IF EXISTS 'audit_loader'@'localhost';\n"
        f"CREATE USER 'audit_loader'@'localhost' IDENTIFIED BY '{password}';\n"
        f"GRANT SELECT,INSERT ON `{grant_database}`.* TO 'audit_loader'@'localhost';\n"
    )


def validate_loader_grants(database, grants, writing=False):
    grant_database = database.replace("_", "\\_")
    privileges = "SELECT, INSERT" if writing else "SELECT"
    expected = {
        "GRANT USAGE ON *.* TO `audit_loader`@`localhost`",
        f"GRANT {privileges} ON `{grant_database}`.* TO `audit_loader`@`localhost`",
    }
    if set(grants) != expected:
        raise AuditError(
            "UNSAFE_DATABASE", "Loader privileges exceed the current audit schema"
        )
    return grants


def restore(workspace, container, database):
    if not re.fullmatch(r"audit_[a-z0-9_]{1,50}", database):
        raise AuditError("UNSAFE_DATABASE", "Use a new audit_ database name")
    run_path = workspace / f"{database}-restore.json"
    if run_path.exists():
        raise AuditError(
            "RESTORE_ALREADY_ATTEMPTED",
            "Preserve the earlier attempt; inspect its receipt before choosing a new audit name",
        )
    started = time.monotonic()
    report = {
        "status": "running",
        "startedAt": now(),
        "database": database,
        "container": container,
    }
    atomic_json(run_path, report)
    process = None
    try:
        report["isolation"] = isolation(workspace, container)
        structure, structure_proof = member_file(workspace, "Structure")
        data, data_proof = member_file(workspace, "Data")
        report.update(
            sourceArchiveSha256=data_proof["archiveSha256"],
            structureSha256=structure_proof["sha256"],
            dataSha256=data_proof["sha256"],
        )
        schemas = schema_inventory(structure.read_text())
        ddl = audit_ddl(schemas)
        report["columnPreflight"] = preflight_columns(data, schemas)
        atomic_json(workspace / "source-schema.json", schemas)
        # No arbitrary password, identifier or original SQL enters setup DDL.
        password = secrets.token_hex(24)
        config = workspace / ".mysql-audit-client.cnf"
        config.write_text(
            f"[client]\nuser=audit_loader\npassword={password}\ndefault-character-set=utf8mb4\n"
        )
        os.chmod(config, 0o600)
        # Write inside the live mount namespace: archive-copy APIs can miss tmpfs.
        install_client_config(workspace, container)
        setup = loader_setup(database, password) + f"USE `{database}`;\n" + ddl
        query(container, None, setup, root=True)
        report["sourceTableCount"] = len(schemas)
        report["restoredTables"] = list(SELECTED)
        report["excludedSensitivePeopleFields"] = [
            c["name"]
            for c in schemas["people"]["columns"]
            if c["name"] not in SELECTED["people"]
        ]
        settings = query(
            container,
            database,
            "SELECT @@skip_networking,@@local_infile,@@event_scheduler,@@secure_file_priv;SHOW GRANTS;",
        )
        report["serverSettingsAndLoaderGrants"] = settings.splitlines()
        validate_loader_grants(database, settings.splitlines()[1:], writing=True)
        if not settings.startswith("1\t0\tOFF\t"):
            raise AuditError(
                "UNSAFE_DATABASE",
                "Server file/network/event settings disagree with audit policy",
            )
        disk_check(workspace, needed=data_proof["bytes"])
        atomic_json(run_path, report)
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "mysql",
                    "--defaults-extra-file=/tmp/mcp-audit-client.cnf",
                    "--binary-mode",
                    "--max-allowed-packet=16777216",
                    database,
                ],
                stdin=subprocess.PIPE,
                stdout=errors,
                stderr=errors,
            )
            sink = DeadlineWriter(process.stdin, started + 3600)

            def progress(table, byte_count, counts):
                if time.monotonic() - started > 3600:
                    raise AuditError(
                        "RESTORE_TIMEOUT", "One-hour audit import bound reached"
                    )
                disk_check(workspace)
                atomic_json(
                    workspace / "restore-progress.json",
                    {
                        "at": now(),
                        "table": table,
                        "sourceBytesScanned": byte_count,
                        "sourceRowsParsed": sum(c["rows"] for c in counts.values()),
                        "scope": "Submitted data, not confirmed committed counts",
                    },
                )

            with sink:
                sink.write(
                    b"SET NAMES utf8mb4; SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO';\n"
                )
                inventory = scan_dump(data, schemas, sink, progress)
            process.stdin.close()
            process.wait(timeout=max(0.01, min(300, started + 3600 - time.monotonic())))
            if process.returncode:
                raise AuditError(
                    "DATABASE_IMPORT_FAILED",
                    "Literal projection import failed; retain partial audit database",
                )
        grant_database = database.replace("_", "\\_")
        query(
            container,
            None,
            f"REVOKE INSERT ON `{grant_database}`.* FROM 'audit_loader'@'localhost';",
            root=True,
        )
        report["sourceInventory"] = inventory
        verified = {}
        for table in SELECTED:
            count = int(query(container, database, f"SELECT COUNT(*) FROM `{table}`;"))
            if count != inventory["tables"][table]["rows"]:
                raise AuditError(
                    "COUNT_MISMATCH", f"Committed row count differs for {table}"
                )
            columns = SELECTED[table] or [c["name"] for c in schemas[table]["columns"]]
            dates = [
                c["name"]
                for c in schemas[table]["columns"]
                if c["type"].split("(")[0] in {"date", "datetime", "timestamp"}
                and c["name"] in columns
            ]
            ranges = {}
            for column in dates:
                ranges[column] = (
                    query(
                        container,
                        database,
                        f"SELECT MIN(`{column}`),MAX(`{column}`),SUM(`{column}` IS NULL) FROM `{table}`;",
                    )
                    .strip()
                    .split("\t")
                )
            verified[table] = {"rows": count, "dateRanges": ranges, "columns": columns}
        report["restoredTableAudit"] = verified
        report["readOnlyGrants"] = validate_loader_grants(
            database, query(container, database, "SHOW GRANTS;").splitlines()
        )
        report["status"] = "restored"
        report["finishedAt"] = now()
        report["elapsedSeconds"] = round(time.monotonic() - started, 3)
        atomic_json(run_path, report)
        receipt(
            workspace,
            "restore",
            "verified",
            database=database,
            elapsedSeconds=report["elapsedSeconds"],
        )
        return report
    except BaseException as error:
        report.update(
            status="failed",
            code=getattr(error, "code", type(error).__name__),
            finishedAt=now(),
        )
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or b"").decode("utf-8", errors="replace")
            report["commandFailure"] = re.sub(r"[0-9a-f]{48}", "[redacted]", detail)[
                :1200
            ]
        atomic_json(run_path, report)
        receipt(workspace, "restore", "failed", database=database, code=report["code"])
        error.audit_recorded = True
        raise
    finally:
        if process is not None:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
