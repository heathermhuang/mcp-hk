"""Review-only physical-expiry/capacity proofs. This module never deletes data."""

from datetime import datetime, timezone

from .contracts import Rejected, digest, encoded

DOMAINS = (
    "database_facts_and_captures",
    "source_local_dumps",
    "independently_downloaded_dumps",
    "fact_bearing_receipts",
    "r2_immutable_copies",
    "r2_latest_reference",
    "failed_and_interrupted_copies",
    "prebuilt_exports",
)


def capacity(
    *,
    free_bytes,
    available_memory_bytes,
    allocations,
    source_database_bytes,
    source_local_bytes,
    export_bytes=0,
):
    values = (
        free_bytes,
        available_memory_bytes,
        source_database_bytes,
        source_local_bytes,
        export_bytes,
    )
    if any(type(v) is not int or v < 0 for v in values) or any(
        type(v) is not int or v < 0 for v in allocations.values()
    ):
        raise Rejected("SFC_CAPACITY_MEASUREMENT_REQUIRED")
    # Existing allocations include HKEX's 3 GiB reservation. Never spend it twice.
    if allocations.get("hkex_daily", 0) < 3 * 1024**3:
        raise Rejected("SFC_SHARED_ALLOCATION_REQUIRED")
    dump = 64 * 1024**2
    source_peak = (
        source_database_bytes * 4 + 3 * dump + source_local_bytes + 2 * export_bytes
    )
    return {
        "sharedAllocations": allocations,
        "sourcePeakBytes": source_peak,
        "freeBytes": free_bytes,
        "minimumFreeReserveBytes": 20 * 1024**3,
        "sourceLocalWithin512MiB": source_local_bytes + 2 * dump + export_bytes
        <= 512 * 1024**2,
        "diskQualified": free_bytes - sum(allocations.values()) - source_peak
        >= 20 * 1024**3,
        "memoryQualified": available_memory_bytes >= 1024**3,
        "measured": True,
    }


def expiry_proof(policy, inventory, observations, *, now=None):
    """Require actual physical-absence observations for every named canary target.

    Read denial, TTL metadata, response expiry, a planned lifecycle or a promise to
    delete is not physical absence. Only fabricated approved canaries belong here.
    A canary proof qualifies the tested mechanism/configuration, never actual data.
    """
    now = now or datetime.now(timezone.utc)
    policy.require("retention", "backup", now=now)
    if set(inventory) != set(DOMAINS) or set(observations) != set(DOMAINS):
        raise Rejected("SFC_EXPIRY_DOMAIN_INVENTORY_REQUIRED")
    checked = {}
    for domain in DOMAINS:
        target, receipt = inventory[domain], observations[domain]
        try:
            created = datetime.fromisoformat(target["createdAt"])
            deadline = datetime.fromisoformat(target["physicalDeadline"])
            absent = datetime.fromisoformat(receipt["observedAbsentAt"])
            if any(t.tzinfo is None for t in (created, deadline, absent)):
                raise ValueError()
            if (
                target.get("fabricatedCanary") is not True
                or target["targetSha256"] != receipt["targetSha256"]
                or target.get("approvalSha256") != receipt.get("approvalSha256")
                or len(target.get("approvalSha256", "")) != 64
                or receipt.get("physicalAbsenceVerified") is not True
                or receipt.get("readDeniedOnly") is not False
                or not created < absent <= deadline <= now
                or (deadline - created).total_seconds() > policy.backupSeconds
            ):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise Rejected("SFC_PHYSICAL_EXPIRY_UNQUALIFIED") from None
        checked[domain] = receipt
    return {
        "policySha256": policy.sha256,
        "inventorySha256": digest(encoded(inventory)),
        "observationsSha256": digest(encoded(checked)),
        "checkedAt": now.isoformat(),
        "testedDomains": list(DOMAINS),
        "syntheticMechanismProof": True,
        "realSourceDataExpired": False,
        "newSourcePermissionGranted": False,
    }
