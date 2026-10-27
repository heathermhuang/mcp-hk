"""Proof-bound SFC source cycle, independent of public output permission.

The host owns the source-wide file lock and supplies an actual offsite
upload/download/physical-restore context. The collector image receives neither
administrator credentials nor a Docker socket. Recovery adapters are trusted
operator code, never a URL or callback supplied through a public request.
"""

import json
import re
from datetime import datetime, timezone

import httpx

from .contracts import Rejected
from .public_register import Collector

RECOVERY_STATUS = "https://mcp.hk/api/v1/companies/updates/status"


def recovery_gate():
    """The existing recovery qualification must pass before new source growth."""
    body = bytearray()
    with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
        with client.stream("GET", RECOVERY_STATUS) as response:
            if response.status_code != 200:
                raise Rejected("SFC_RECOVERY_GATE_UNAVAILABLE")
            for block in response.iter_bytes(chunk_size=32768):
                if len(body) + len(block) > 1024 * 1024:
                    raise Rejected("SFC_RECOVERY_GATE_UNAVAILABLE")
                body.extend(block)
    try:
        value = json.loads(body)
        qualified = value["data"]["maintenance"]["backfillRecoveryGateOpen"]
        version = value["meta"]["version"]
        if qualified is not True or not re.fullmatch(r"official-[a-f0-9]{32}", version):
            raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise Rejected("SFC_RECOVERY_GATE_UNQUALIFIED") from exc
    return {
        "qualified": True,
        "officialVersion": version,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def run_cycle(
    state,
    policy_sha256,
    scheduled_for,
    cohort,
    recover,
    *,
    provenance="manual",
    source_release=None,
    collector=None,
    check_recovery=recovery_gate,
):
    """Use the same source cycle as the host with real State restore checks."""
    from .cycle import run_cycle as cycle, JobRejected

    with state.connection() as conn:
        policy = state.policy(conn, policy_sha256, "automation", "retention", "backup")

    class Backend:
        def state(self):
            return state.job_state(policy_sha256)

        def collect(self, when, cohort, provenance, source_release):
            return (collector or Collector(state, policy)).collect(
                when, cohort, provenance, source_release
            )

        def outcome(self, *args, **kwargs):
            return state.job_outcome(*args, **kwargs)

        def publish(self, *args):
            return state.publish(*args)

        def recover(self, version, stage):
            with recover(version, stage) as (restored, artifact, sha):
                return state.qualify_restore(version, restored, artifact, sha)

    try:
        return cycle(
            Backend(),
            scheduled_for,
            cohort,
            provenance=provenance,
            source_release=source_release,
            check_recovery=check_recovery,
        )
    except JobRejected as error:
        raise Rejected(str(error)) from error
