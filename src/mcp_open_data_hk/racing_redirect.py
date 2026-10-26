"""Reconcile only a recorded, twice-observed public archive redirect.

The original charge, error and both inspections survive. This is routing
qualification, never a successful results read or a parser-failure override.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from .curated.racing.policy import RacingRejected, canonical
from .curated.racing.public_results import archive_redirect


def reconcile_archive_redirect(store, attempt):
    if (
        type(attempt) is not int
        or attempt < 1
        or os.environ.get("MCP_HK_EDGE_MODE") != "true"
    ):
        raise RacingRejected("RACING_REDIRECT_DURABLE_PROOF_REQUIRED")
    key = "qualified-archive-redirect:" + str(attempt)
    with store.collector_lock():
        with store.connect() as db:
            old = db.execute(
                "SELECT a.*,r.remote_id FROM racing_attempts a JOIN racing_remote_requests r ON r.local_id=a.id WHERE a.id=?",
                (attempt,),
            ).fetchone()
            if old and old["state"] == "reviewed_redirect":
                saved = db.execute(
                    "SELECT value FROM racing_control WHERE key=?", (key,)
                ).fetchone()
                if saved:
                    return json.loads(saved[0])
            if (
                not old
                or old["state"] != "held"
                or old["error"] != "DEVELOPMENT_HTTP_302"
            ):
                raise RacingRejected("RACING_REDIRECT_NOT_ELIGIBLE")
            if db.execute(
                "SELECT 1 FROM racing_attempts WHERE state IN ('reserved','held','unknown') AND id<>?",
                (attempt,),
            ).fetchone():
                raise RacingRejected("RACING_REDIRECT_OTHER_UNRESOLVED")
            observations = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT payload FROM racing_redirect_inspections WHERE original_attempt=? ORDER BY inspection_attempt",
                    (attempt,),
                )
            ]
            source = urlsplit(old["url"])
            query = {k.lower(): v[0] for k, v in parse_qs(source.query).items()}
            relative = (
                source.path.replace("/localresults", "/archive/localresults")
                + "?"
                + urlencode(query, safe="/")
            )
            target = archive_redirect(old["url"], relative)
            location_hash = hashlib.sha256(relative.encode()).hexdigest()
            proofs = {}
            for observation in observations:
                if (
                    observation.get("state") == "received"
                    and observation.get("responseStatus") == 302
                    and observation.get("settlementConfirmed") is True
                    and observation.get("accountingState") == "settled"
                    and observation.get("truncated") is False
                    and observation.get("locationSha256") == location_hash
                ):
                    proofs[observation.get("inspectionKind", "location")] = observation
            if set(proofs) != {"location", "routing_shape"}:
                raise RacingRejected("RACING_REDIRECT_HASH_PROOF_REQUIRED")
            proof = proofs["routing_shape"]
            shape = proof.get("locationShape", {})
            if (
                shape.get("sameProviderHost") is not True
                or shape.get("credentialsInAuthority") is not False
                or shape.get("scheme") != "https"
            ):
                raise RacingRejected("RACING_REDIRECT_SHAPE_PROOF_REQUIRED")
            remote = db.execute(
                "SELECT r.remote_id,a.state,a.error FROM racing_remote_requests r JOIN racing_attempts a ON a.id=r.local_id WHERE r.local_id=?",
                (proof["inspectionAttempt"],),
            ).fetchone()
            if (
                not remote
                or remote["state"] != "success"
                or remote["error"] != "REDIRECT_INSPECTION_COMPLETE"
            ):
                raise RacingRejected("RACING_REDIRECT_SETTLEMENT_REQUIRED")
            evidence = {
                "originalAttempt": attempt,
                "originalState": old["state"],
                "originalError": old["error"],
                "originalChargedBytes": old["bytes"],
                "originalRemoteId": old["remote_id"],
                "locationSha256": location_hash,
                "target": target,
                "inspections": proofs,
            }
            evidence_sha = hashlib.sha256(canonical(evidence)).hexdigest()
        try:
            result = store.admission(
                {
                    "action": "review_archive_redirect",
                    "id": old["remote_id"],
                    "inspectionId": remote["remote_id"],
                    "evidenceSha256": evidence_sha,
                }
            )
        except (OSError, ValueError) as exc:
            raise RacingRejected("RACING_REDIRECT_REVIEW_UNCONFIRMED") from exc
        if result.get("reviewed") is not True:
            raise RacingRejected("RACING_REDIRECT_REVIEW_UNCONFIRMED")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE racing_attempts SET state='reviewed_redirect' WHERE id=? AND state='held' AND error=? AND bytes=?",
                (attempt, old["error"], old["bytes"]),
            ).rowcount
            if changed != 1:
                raise RacingRejected("RACING_REDIRECT_STATE_CHANGED")
            payload = {
                "kind": "qualified_archive_redirect",
                "target": target,
                "locationSha256": location_hash,
            }
            db.execute(
                "INSERT OR REPLACE INTO racing_pages VALUES(?,?,?,?,?)",
                (
                    old["url"],
                    proof["observedAt"],
                    proof["bodySha256"],
                    proof["bytes"],
                    canonical(payload).decode(),
                ),
            )
            same = db.execute(
                "UPDATE racing_queue SET state='partial',error=NULL WHERE day=? AND venue=? AND state='held' AND error='DEVELOPMENT_HTTP_302'",
                (query["racedate"].replace("/", "-"), query["racecourse"]),
            ).rowcount
            blocked = db.execute(
                "UPDATE racing_queue SET state='partial',error=NULL WHERE state='held' AND error='DEVELOPMENT_SOURCE_HELD'"
            ).rowcount
            db.execute("DELETE FROM racing_control WHERE key='remote-hold'")
            receipt = dict(
                evidence,
                evidenceSha256=evidence_sha,
                reviewedAt=datetime.now(timezone.utc).isoformat(),
                relatedQueueResumed=same,
                globalHoldOnlyQueueResumed=blocked,
                providerRequests=0,
                targetResultsVerified=False,
            )
            db.execute(
                "INSERT INTO racing_control VALUES(?,?)",
                (key, canonical(receipt).decode()),
            )
        return receipt
