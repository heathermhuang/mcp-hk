from datetime import datetime, timedelta, timezone
import io
import json
import zipfile

import pytest

from mcp_open_data_hk.curated.sfc.contracts import (
    Corporation,
    Rejected,
    digest,
    encoded,
)
from mcp_open_data_hk.curated.sfc.artifacts import build, deliver
from mcp_open_data_hk.curated.sfc.retention import capacity, expiry_proof, DOMAINS
from test_sfc import fake_policy, fake_fact


def artifact(tmp_path):
    base = fake_policy()
    policy = fake_policy(modes=dict(base.modes, export="allowed"))
    fact = Corporation.model_validate(fake_fact()).model_dump(mode="json")
    state = {
        "version": "sfc-" + "a" * 32,
        "policySha256": policy.sha256,
        "factsSha256": digest(encoded([fact])),
        "cohort": ["ZZZ001"],
        "acceptedAndRestored": True,
        "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    proof = build([fact], state, policy, tmp_path)
    return policy, state, proof


def test_prebuilt_export_preserves_all_facts_hashes_and_requires_current_modes(
    tmp_path,
):
    policy, state, proof = artifact(tmp_path)
    raw, actual = deliver(tmp_path, state["version"], lambda v: state, policy)
    assert proof == actual and proof["sha256"] == digest(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        facts = json.loads(z.read("records.json"))
        assert facts[0]["ce"] == "ZZZ001" and facts[0]["nameZhHant"] == "虛構測試法團"
        m = json.loads(z.read("manifest.json"))
        for name, item in m["files"].items():
            assert (
                digest(z.read(name)) == item["sha256"]
                and len(z.read(name)) == item["bytes"]
            )
    with pytest.raises(Rejected, match="MODE_UNQUALIFIED"):
        deliver(tmp_path, state["version"], lambda v: state, fake_policy())
    with pytest.raises(Rejected, match="VERSION_INVALID"):
        deliver(tmp_path, "../escape", lambda v: state, policy)
    changed = dict(state, factsSha256="0" * 64)
    with pytest.raises(Rejected, match="STATE_CHANGED"):
        deliver(tmp_path, state["version"], lambda v: changed, policy)
    archive = tmp_path / state["version"] / "corporations.zip"
    archive.write_bytes(b"corrupt")
    with pytest.raises(Rejected, match="HASH_MISMATCH"):
        deliver(tmp_path, state["version"], lambda v: state, policy)


def test_expired_artifact_and_concurrently_revoked_state_are_withheld(tmp_path):
    policy, state, _ = artifact(tmp_path)
    with pytest.raises(Rejected, match="STATE_UNQUALIFIED"):
        deliver(
            tmp_path,
            state["version"],
            lambda v: dict(state, expiresAt="2020-01-01T00:00:00+00:00"),
            policy,
        )
    states = iter([state, dict(state, acceptedAndRestored=False)])
    with pytest.raises(Rejected, match="STATE_CHANGED"):
        deliver(tmp_path, state["version"], lambda v: next(states), policy)


def test_shared_capacity_includes_existing_reservations_and_all_copy_peaks():
    kwargs = dict(
        free_bytes=40 * 1024**3,
        available_memory_bytes=2 * 1024**3,
        allocations={"hkex_daily": 3 * 1024**3},
        source_database_bytes=1024**2,
        source_local_bytes=0,
    )
    assert capacity(**kwargs)["diskQualified"]
    assert not capacity(**dict(kwargs, free_bytes=22 * 1024**3))["diskQualified"]
    with pytest.raises(Rejected, match="SHARED_ALLOCATION"):
        capacity(**dict(kwargs, allocations={}))


def test_physical_expiry_requires_exact_approved_canaries_and_observed_absence():
    policy = fake_policy()
    now = datetime.now(timezone.utc)
    inventory = {
        k: {
            "fabricatedCanary": True,
            "targetSha256": digest(k.encode()),
            "approvalSha256": "a" * 64,
            "createdAt": (now - timedelta(hours=2)).isoformat(),
            "physicalDeadline": (now - timedelta(hours=1)).isoformat(),
        }
        for k in DOMAINS
    }
    observed = {
        k: {
            "targetSha256": v["targetSha256"],
            "approvalSha256": "a" * 64,
            "physicalAbsenceVerified": True,
            "readDeniedOnly": False,
            "observedAbsentAt": (now - timedelta(minutes=90)).isoformat(),
        }
        for k, v in inventory.items()
    }
    assert expiry_proof(policy, inventory, observed)["syntheticMechanismProof"]
    observed["r2_immutable_copies"]["physicalAbsenceVerified"] = False
    with pytest.raises(Rejected, match="PHYSICAL_EXPIRY_UNQUALIFIED"):
        expiry_proof(policy, inventory, observed)
    with pytest.raises(Rejected, match="DOMAIN_INVENTORY"):
        expiry_proof(policy, {}, observed)


@pytest.mark.asyncio
async def test_public_prebuilt_delivery_checks_identity_limits_and_closed_defaults(
    monkeypatch,
):
    import hashlib
    import httpx
    from mcp_open_data_hk.companies import Companies
    from mcp_open_data_hk.sfc import Sfc
    from mcp_open_data_hk.contracts import DomainError

    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://archive.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "s" * 40)
    base = fake_policy()
    policy = fake_policy(modes=dict(base.modes, export="allowed"))
    raw = b"PKfabricated transport bytes"
    version = "sfc-" + "a" * 32

    def source(request):
        assert request.url.path == "/v1/sfc/exports/" + version
        return httpx.Response(
            200,
            content=raw,
            headers={
                "content-type": "application/zip",
                "x-content-sha256": hashlib.sha256(raw).hexdigest(),
                "x-sfc-version": version,
                "x-sfc-policy": policy.sha256,
            },
        )

    backend = Companies(transport=httpx.MockTransport(source))
    actual, sha = await Sfc(backend, policy).download(version)
    assert actual == raw and sha == hashlib.sha256(raw).hexdigest()
    with pytest.raises(DomainError, match="not enabled"):
        await Sfc(backend, base).download(version)
    backend.transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://other.test/"})
    )
    with pytest.raises(DomainError, match="No qualified"):
        await Sfc(backend, policy).download(version)
