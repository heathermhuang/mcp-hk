#!/usr/bin/env python3
"""Source-only host coordinator. No timer or credential is created by this file."""

from datetime import datetime, timedelta, timezone
import hashlib
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import urllib.error
import urllib.request

ROOT = Path("/srv/mcp-hk-curated/sfc")
CONFIG = Path("/etc/mcp-hk-curated/sfc-job.json")
ENV = "/etc/mcp-hk-curated/sfc.env"
BASE = "https://mcp.hk/__sfc-backup/"
MAX_DUMP = 64 * 1024**2
TABLES = (
    "migrations",
    "policies",
    "runs",
    "budgets",
    "holds",
    "attempts",
    "versions",
    "captures",
    "corporations",
    "pointer",
)


class JobError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise JobError("SFC_RECOVERY_REDIRECT_REJECTED")


def execute(argv, **kwargs):
    return subprocess.run(
        argv, check=True, timeout=kwargs.pop("timeout", 180), **kwargs
    )


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def occurrence(trigger, uptime, now):
    found = re.fullmatch(r"t ([0-9]+)", trigger)
    if (
        not found
        or not 0 < int(found[1]) <= uptime
        or uptime - int(found[1]) >= 60_000_000
    ):
        return "manual", now.isoformat()
    latest = now.replace(hour=6, minute=10, second=0, microsecond=0)
    if latest > now:
        latest -= timedelta(days=1)
    return "timer", latest.isoformat()


class Backend:
    def __init__(self, config):
        self.config = config
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect
        )

    def runner(self, *args, restored=None, artifact=None):
        command = [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--network",
            "curated_default",
            "--env-file",
            ENV,
        ]
        if restored:
            if not re.fullmatch(r"sfc_restore_[a-z0-9_]{8,64}", restored):
                raise JobError("SFC_RESTORE_DATABASE_INVALID")
            command += ["--env", "SFC_RESTORED_DATABASE=" + restored]
        if artifact:
            command += [
                "--mount",
                "type=bind,src="
                + str(artifact.resolve())
                + ",dst=/proof.dump,readonly",
            ]
        command += [
            "--entrypoint",
            "python",
            self.config["image"],
            "-m",
            "mcp_open_data_hk.curated.sfc",
            *args,
        ]
        p = subprocess.run(command, capture_output=True, text=True, timeout=660)
        if p.returncode:
            code = p.stderr.strip()
            raise JobError(
                code
                if re.fullmatch(r"SFC_[A-Z0-9_]{1,76}", code)
                else "SFC_SOURCE_COMMAND_FAILED"
            )
        try:
            return json.loads(p.stdout)
        except ValueError:
            raise JobError("SFC_SOURCE_RECEIPT_INVALID") from None

    def state(self):
        return self.runner("job-state", "--policy-sha256", self.config["policySha256"])

    def outcome(self, run, phase, state, **values):
        args = ["job-outcome", "--run", run, "--phase", phase, "--state", state]
        for key, flag in (("code", "--code"), ("artifact_sha256", "--artifact-sha256")):
            if values.get(key) is not None:
                args += [flag, values[key]]
        return self.runner(*args)

    def publish(self, version, previous):
        return self.runner(
            "publish", "--version", version, "--expected-version", previous or "NONE"
        )

    def collect(self, when, cohort, provenance, release):
        args = [
            "collect",
            "--policy-sha256",
            self.config["policySha256"],
            "--scheduled-for",
            when,
            "--provenance",
            provenance,
            "--source-release",
            release,
        ]
        for ce in cohort:
            args += ["--ce", ce]
        return self.runner(*args)

    def request(
        self, path, *, method="GET", body=None, length=None, sha=None, expires=None
    ):
        headers = {
            "Authorization": "Bearer " + self.config["token"],
            "Content-Type": "application/octet-stream",
            "User-Agent": "mcp.hk-sfc-recovery",
        }
        if length is not None:
            headers["Content-Length"] = str(length)
        if sha:
            headers["x-object-sha256"] = sha
        if expires:
            headers["x-source-expires-at"] = str(expires)
        return self.opener.open(
            urllib.request.Request(
                BASE + path, method=method, headers=headers, data=body
            ),
            timeout=45,
        )

    def check_storage(self):
        with self.request("capability") as response:
            capability = json.load(response)
        state = self.state()
        seconds = capability.get("configuredRetentionSeconds")
        if (
            capability.get("source") != "sfc_register"
            or capability.get("policySha256") != self.config["policySha256"]
            or seconds != self.config["qualifiedStorageMaximumSeconds"]
            or type(seconds) is not int
            or not 0 < seconds <= state["backupSeconds"]
        ):
            raise JobError("SFC_STORAGE_RETENTION_UNQUALIFIED")
        # No automatic deletion is authorized. Stop before copies could outlive
        # retained source facts; an exact retention reconciliation is separate.
        oldest = state.get("oldestVersionExpiresAt")
        if oldest and datetime.fromisoformat(oldest) <= datetime.now(
            timezone.utc
        ) + timedelta(seconds=seconds):
            raise JobError("SFC_RETENTION_RECONCILIATION_REQUIRED")
        return seconds

    def recover(self, version, stage):
        seconds = self.check_storage()
        if (
            sum(
                p.stat().st_size
                for p in ROOT.rglob("*")
                if p.is_file() and not p.is_symlink()
            )
            + 2 * MAX_DUMP
            > 512 * 1024**2
        ):
            raise JobError("SFC_LOCAL_RESERVE_EXHAUSTED")
        stamp = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + secrets.token_hex(4)
        )
        directory = ROOT / "backups" / stamp
        directory.mkdir(parents=True, mode=0o700)
        archive, downloaded = directory / "source.dump", directory / "retrieved.dump"
        with archive.open("xb") as stream:
            execute(
                [
                    "docker",
                    "exec",
                    "curated-postgres-1",
                    "pg_dump",
                    "-U",
                    "postgres",
                    "-d",
                    "curated",
                    "-Fc",
                    "-n",
                    "curated_sfc",
                    "--no-owner",
                    "--no-acl",
                ],
                stdout=stream,
            )
        size, sha = archive.stat().st_size, file_sha(archive)
        if not 0 < size <= MAX_DUMP:
            raise JobError("SFC_DUMP_SIZE_LIMIT")
        expires = int(
            (datetime.now(timezone.utc) + timedelta(seconds=seconds)).timestamp() * 1000
        )
        with (
            archive.open("rb") as stream,
            self.request(
                stamp + "/source.dump",
                method="PUT",
                body=stream,
                length=size,
                sha=sha,
                expires=expires,
            ) as response,
        ):
            stored = json.load(response)
        if stored.get("sha256") != sha or stored.get("bytes") != size:
            raise JobError("SFC_UPLOAD_UNCONFIRMED")
        with (
            self.request(stamp + "/source.dump") as response,
            downloaded.open("xb") as stream,
        ):
            if response.headers.get("x-object-sha256") != sha:
                raise JobError("SFC_RETRIEVED_HEADER_DIFFERS")
            count = 0
            for block in iter(lambda: response.read(1024 * 1024), b""):
                count += len(block)
                if count > size:
                    raise JobError("SFC_RETRIEVED_SIZE_DIFFERS")
                stream.write(block)
        if count != size or file_sha(downloaded) != sha:
            raise JobError("SFC_RETRIEVED_CHECKSUM_DIFFERS")
        name = "sfc_restore_" + stamp.lower().replace("-", "_")
        execute(
            ["docker", "exec", "curated-postgres-1", "createdb", "-U", "postgres", name]
        )
        try:
            with downloaded.open("rb") as stream:
                execute(
                    [
                        "docker",
                        "exec",
                        "-i",
                        "curated-postgres-1",
                        "pg_restore",
                        "-U",
                        "postgres",
                        "-d",
                        name,
                        "--no-owner",
                        "--no-acl",
                        "--single-transaction",
                        "--exit-on-error",
                    ],
                    stdin=stream,
                )
            # The child gets only its source writer, plus SELECT on this newly
            # created restore. Admin credentials/socket stay on the host.
            grants = "GRANT USAGE ON SCHEMA curated_sfc TO sfc_writer; GRANT SELECT ON ALL TABLES IN SCHEMA curated_sfc TO sfc_writer; GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO sfc_writer;"
            execute(
                [
                    "docker",
                    "exec",
                    "-i",
                    "curated-postgres-1",
                    "psql",
                    "-U",
                    "postgres",
                    "-d",
                    name,
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                input=grants,
                text=True,
                capture_output=True,
            )
            # Parent directory remains 0700. Only this mounted source artifact
            # becomes readable to the unprivileged verifier image.
            downloaded.chmod(0o444)
            try:
                proof = self.runner(
                    "qualify-restore",
                    "--version",
                    version,
                    "--artifact",
                    "/proof.dump",
                    "--sha256",
                    sha,
                    restored=name,
                    artifact=downloaded,
                )
            finally:
                downloaded.chmod(0o600)
            if stage == "accepted" and proof.get("acceptedPointerIncluded") is not True:
                raise JobError("SFC_ACCEPTED_RECOVERY_REQUIRED")
            try:
                with self.request("latest.json") as response:
                    previous = json.load(response).get("manifestSha256")
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                previous = None
            manifest = {
                "source": "sfc_register",
                "policySha256": self.config["policySha256"],
                "stamp": stamp,
                "stage": stage,
                "version": version,
                "expiresAt": expires,
                "dump": {"bytes": size, "sha256": sha},
                "restoreVerified": True,
                "acceptedPointerIncluded": proof["acceptedPointerIncluded"],
                "allTables": proof["tables"],
                "previousManifestSha256": previous,
            }
            body = (
                json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            manifest_sha = hashlib.sha256(body).hexdigest()
            with self.request(
                stamp + "/manifest.json",
                method="PUT",
                body=body,
                length=len(body),
                sha=manifest_sha,
                expires=expires,
            ) as response:
                saved = json.load(response)
            if (
                saved.get("sha256") != manifest_sha
                or not saved.get("stored")
                or stage == "accepted"
                and saved.get("recoveryAdvanced") is not True
            ):
                raise JobError("SFC_RECOVERY_MANIFEST_UNCONFIRMED")
            (directory / "receipt.json").write_text(
                json.dumps(
                    {
                        "manifest": manifest,
                        "proof": proof,
                        "manifestSha256": manifest_sha,
                    },
                    indent=2,
                )
                + "\n"
            )
            return proof
        finally:
            # Generated here, never the active database. Artifacts/receipts stay.
            execute(
                [
                    "docker",
                    "exec",
                    "curated-postgres-1",
                    "dropdb",
                    "-U",
                    "postgres",
                    name,
                ]
            )


def growth_gate(opener):
    request = urllib.request.Request(
        "https://mcp.hk/api/v1/companies/updates/status",
        headers={"User-Agent": "mcp.hk-sfc-recovery-gate"},
    )
    with opener.open(request, timeout=15) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise JobError("SFC_RECOVERY_GATE_UNAVAILABLE")
    value = json.loads(body)
    return {
        "qualified": value.get("data", {})
        .get("maintenance", {})
        .get("backfillRecoveryGateOpen")
        is True,
        "officialVersion": value.get("meta", {}).get("version"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Explicit operator qualification; never passed by the timer unit",
    )
    args = parser.parse_args()
    os.umask(0o077)
    if CONFIG.is_symlink() or CONFIG.stat().st_mode & 0o077:
        raise JobError("SFC_PRIVATE_CONFIG_REQUIRED")
    config = json.loads(CONFIG.read_text())
    if (
        not re.fullmatch(r"mcp-hk-curated:[a-f0-9]{40}", config.get("image", ""))
        or not re.fullmatch(r"[a-f0-9]{64}", config.get("policySha256", ""))
        or len(config.get("token", "")) < 32
        or not re.fullmatch(
            r"[a-f0-9]{64}", config.get("storageRetentionEvidenceSha256", "")
        )
        or type(config.get("qualifiedStorageMaximumSeconds")) is not int
        or config["qualifiedStorageMaximumSeconds"] < 1
    ):
        raise JobError("SFC_JOB_CONFIG_UNQUALIFIED")
    cohort = config.get("cohort", [])
    if (
        not 1 <= len(cohort) <= 25
        or len(set(cohort)) != len(cohort)
        or any(not re.fullmatch(r"[A-Z]{3}[0-9]{3}", ce) for ce in cohort)
    ):
        raise JobError("SFC_COHORT_UNQUALIFIED")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = (
        Path(__file__).resolve().parents[2]
        / "src/mcp_open_data_hk/curated/sfc/cycle.py"
    )
    spec = importlib.util.spec_from_file_location("sfc_host_cycle", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    backend = Backend(config)
    backend.check_storage()
    if args.manual:
        provenance, when = "manual", datetime.now(timezone.utc).isoformat()
    else:
        trigger = subprocess.check_output(
            [
                "busctl",
                "get-property",
                "org.freedesktop.systemd1",
                "/org/freedesktop/systemd1/unit/mcp_2dhk_2dsfc_2etimer",
                "org.freedesktop.systemd1.Timer",
                "LastTriggerUSecMonotonic",
            ],
            text=True,
        ).strip()
        provenance, when = occurrence(
            trigger,
            int(float(Path("/proc/uptime").read_text().split()[0]) * 1e6),
            datetime.now(timezone.utc),
        )
        if provenance != "timer":
            raise JobError("SFC_TIMER_PROVENANCE_UNAVAILABLE")
    result = module.run_cycle(
        backend,
        when,
        cohort,
        provenance=provenance,
        source_release=config["image"].split(":")[1],
        check_recovery=lambda: growth_gate(backend.opener),
    )
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        raise SystemExit(
            code if re.fullmatch(r"SFC_[A-Z0-9_]{1,76}", code) else "SFC_JOB_FAILED"
        ) from None
