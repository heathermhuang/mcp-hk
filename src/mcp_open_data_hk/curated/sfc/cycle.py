"""Standard-library source-cycle control flow shared by host and local adapters."""

import re


class JobRejected(ValueError):
    pass


def safe_code(error):
    value = str(error)
    return value if re.fullmatch(r"SFC_[A-Z0-9_]{1,76}", value) else "SFC_JOB_FAILED"


def run_cycle(
    backend,
    scheduled_for,
    cohort,
    *,
    provenance="manual",
    source_release=None,
    check_recovery,
):
    """Collect once, verify a retrieved candidate, publish by CAS, recover accepted.

    The backend verifies a retrieved artifact against an independent physical
    restore. Its outcome recorder must validate the stored proof and pointer;
    an asserted success flag does not satisfy either source adapter.
    """
    current = backend.state()
    if current["acceptedRecoveryPending"]:
        retained = current["acceptedRecoveryPending"]
        version, run = retained["version"], retained["run_id"]
        backend.outcome(run, "accepted_backup", "pending")
        try:
            proof = backend.recover(version, "accepted")
            sha = proof["artifactSha256"]
            backend.outcome(run, "accepted_backup", "succeeded", artifact_sha256=sha)
        except Exception as error:
            backend.outcome(run, "accepted_backup", "failed", code=safe_code(error))
            raise
        return {
            "state": "accepted_recovery_verified",
            "version": version,
            "runId": run,
            "sourceReads": 0,
            "acceptedProof": proof,
            "publicModesGranted": False,
        }
    pending = current["pendingCandidate"]
    result = None
    if not pending:
        if provenance == "timer":
            witness = check_recovery()
            if (
                not isinstance(witness, dict)
                or witness.get("qualified") is not True
                or not re.fullmatch(
                    r"official-[a-f0-9]{32}", witness.get("officialVersion", "")
                )
            ):
                raise JobRejected("SFC_RECOVERY_GATE_UNQUALIFIED")
        elif provenance != "manual":
            raise JobRejected("SFC_JOB_PROVENANCE_INVALID")
        result = backend.collect(scheduled_for, cohort, provenance, source_release)
        if result["state"] == "already_processed":
            return {**result, "publicModesGranted": False}
        if result["state"] != "validated":
            raise JobRejected("SFC_COLLECTION_NOT_VALIDATED")
        version, run = result["version"], result["runId"]
    else:
        # A failed backup resumes retained facts, not the original provider read.
        if (
            not pending["base_qualified"]
            or pending["base_version"] != current["acceptedVersion"]
        ):
            raise JobRejected("SFC_CANDIDATE_BASE_CHANGED")
        version, run = pending["version"], pending["run_id"]
    backend.outcome(run, "collection", "succeeded")
    backend.outcome(run, "backup", "pending")
    try:
        candidate_proof = backend.recover(version, "candidate")
        sha = candidate_proof["artifactSha256"]
        backend.outcome(run, "backup", "succeeded", artifact_sha256=sha)
    except Exception as error:
        backend.outcome(run, "backup", "failed", code=safe_code(error))
        backend.outcome(run, "publication", "skipped", code="SFC_RESTORE_REQUIRED")
        raise
    backend.outcome(run, "publication", "pending")
    try:
        backend.publish(version, current["acceptedVersion"])
        backend.outcome(run, "publication", "succeeded")
    except Exception as error:
        backend.outcome(run, "publication", "failed", code=safe_code(error))
        raise
    backend.outcome(run, "accepted_backup", "pending")
    try:
        accepted_proof = backend.recover(version, "accepted")
        accepted_sha = accepted_proof["artifactSha256"]
        backend.outcome(
            run, "accepted_backup", "succeeded", artifact_sha256=accepted_sha
        )
    except Exception as error:
        backend.outcome(run, "accepted_backup", "failed", code=safe_code(error))
        raise
    return {
        "state": "accepted_and_recovery_verified",
        "version": version,
        "runId": run,
        "resumedCandidateWithoutSourceRead": result is None,
        "candidateProof": candidate_proof,
        "acceptedProof": accepted_proof,
        "publicModesGranted": False,
    }
