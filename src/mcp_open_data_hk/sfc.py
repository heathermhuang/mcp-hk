"""Public SFC capability contract. No request can activate source access."""

import asyncio
import re

import httpx

from .contracts import DomainError, Envelope
from .curated.sfc.contracts import REGISTER_URL, LEGAL_URL, ce_reference, Rejected
from .curated.sfc.read import capability_status
from .curated.sfc.policy import configured_policy
from .curated.sfc.contracts import Corporation


def status(payload=None):
    payload = payload or capability_status()
    version = payload.get("acceptedVersion")
    return Envelope(
        data=payload,
        meta={
            "apiVersion": "v1",
            "snapshotIds": [version] if version else [],
            "version": version,
            "view": "sfc_capability_status",
        },
        provenance=[
            {
                "sourceId": "sfc_register",
                "sourceUrl": REGISTER_URL,
                "termsUrl": LEGAL_URL,
                "freshnessBasis": payload.get(
                    "freshnessBasis", "no_qualified_observation"
                ),
                "currentVerification": False,
            }
        ],
        warnings=[
            {
                "code": payload.get("reasonCode") or "SFC_OBSERVED_SUBSET",
                "message": "Dated corporate verification is limited to the persisted cohort, available modes and retention state. Historical Webb licence records are separate.",
            }
        ],
    ).model_dump(mode="json")


def unavailable(ce=None):
    if ce is not None:
        try:
            ce_reference(ce)
        except Rejected as exc:
            raise DomainError(
                "SFC_INVALID_CE",
                "Use six ASCII characters: three letters and three digits",
                400,
            ) from exc
    raise DomainError(
        "SFC_SOURCE_UNQUALIFIED",
        "Fresh SFC corporate verification is not enabled; no status or revocation can be inferred",
        503,
    )


class Sfc:
    def __init__(self, companies, policy=None):
        self.backend = companies
        self.policy = policy or configured_policy()

    def enabled(self, mode):
        try:
            self.policy.require(mode, "retention")
            return self.backend.configured
        except Rejected:
            return False

    async def query(self, operation, ce=None, version=None, mode="rest"):
        if ce is not None:
            try:
                ce = ce_reference(ce)
            except Rejected as exc:
                raise DomainError(
                    "SFC_INVALID_CE", "Use a canonical six-character CE reference", 400
                ) from exc
        if operation not in {"status", "verify"}:
            raise DomainError("INVALID_QUERY", "Unsupported SFC operation", 400)
        if operation == "status" and not self.backend.configured:
            return status()
        if operation == "verify":
            if not ce or not self.enabled(mode):
                return unavailable(ce)
            if version is not None and not re.fullmatch(r"sfc-[a-f0-9]{32}", version):
                raise DomainError("INVALID_QUERY", "Use a returned SFC version", 400)
        path = (
            "/v1/sfc/status" if operation == "status" else "/v1/sfc/corporations/" + ce
        )
        params = (
            {}
            if operation == "status"
            else {"mode": mode, **({"version": version} if version else {})}
        )
        try:
            await asyncio.wait_for(self.backend.slots.acquire(), 0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY", "Shared query slots are busy", 429, retry_after=1
            ) from exc
        try:
            payload = await asyncio.wait_for(self.backend.fetch(path, params), 12)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise DomainError("QUERY_TIMEOUT", "SFC backend timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise DomainError(
                "PACK_UNAVAILABLE", "SFC backend unavailable", 503
            ) from exc
        finally:
            self.backend.slots.release()
        if operation == "status":
            if (
                not isinstance(payload, dict)
                or payload.get("sourceId") != "sfc_register"
                or not isinstance(payload.get("enabledModes"), list)
            ):
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "SFC status contract differs", 503
                )
            adopted_modes = [
                m
                for m in payload["enabledModes"]
                if m in {"rest", "mcp", "browser"} and self.enabled(m)
            ]
            if adopted_modes != payload["enabledModes"]:
                payload = dict(
                    payload,
                    enabledModes=adopted_modes,
                    state="gateway_policy_unavailable",
                    reasonCode="SFC_GATEWAY_POLICY_NOT_ADOPTED",
                )
            return status(payload)
        try:
            actual_version = payload["version"]
            record = Corporation.model_validate(payload["data"])
            if (
                not re.fullmatch(r"sfc-[a-f0-9]{32}", actual_version)
                or (version and actual_version != version)
                or record.ce != ce
                or payload["provenance"]["policySha256"] != self.policy.sha256
            ):
                raise ValueError("identity")
            self.policy.require(mode, "retention")
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "SFC accepted identity or policy differs", 503
            ) from exc
        return Envelope(
            data=record.model_dump(mode="json"),
            meta={
                "apiVersion": "v1",
                "snapshotIds": [actual_version],
                "version": actual_version,
                "view": "sfc_observation",
                "currentVerification": False,
            },
            provenance=[payload["provenance"]],
            warnings=[
                {
                    "code": "SFC_OBSERVED_SUBSET",
                    "message": "Dated corporate licence observations for the declared tracked cohort; unknown end dates do not establish current licensing or revocation.",
                }
            ],
        ).model_dump(mode="json")


def register_http(app, service):
    @app.get("/api/v1/sfc/status")
    async def sfc_status():
        return await service.sfc.query("status")

    @app.get("/api/v1/sfc/corporations", include_in_schema=False)
    def sfc_search():
        return unavailable()

    @app.get("/api/v1/sfc/corporations/{ce}/history", include_in_schema=False)
    def sfc_history(ce: str):
        return unavailable(ce)

    @app.get(
        "/api/v1/sfc/corporations/{ce}", include_in_schema=service.sfc.enabled("rest")
    )
    async def sfc_verify(ce: str, version: str | None = None):
        return await service.sfc.query("verify", ce=ce, version=version)


def register_mcp(server, current):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_sfc_status() -> dict:
        """Read persisted fresh SFC cohort, accepted version, mode gates, attempts and retention state. Starts no collection; Webb licences remain a separate archive."""
        return await current().sfc.query("status")

    if current().sfc.enabled("mcp"):

        @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
        async def hk_sfc_verify(ce: str, version: str | None = None) -> dict:
            """Read an exact corporate CE's dated official licence observation in the qualified tracked cohort. Missing end dates and negative matches never imply revocation. Starts no collection."""
            return await current().sfc.query(
                "verify", ce=ce, version=version, mode="mcp"
            )
