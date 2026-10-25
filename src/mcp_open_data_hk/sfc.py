"""Public SFC capability contract. No request can activate source access."""

from .contracts import DomainError, Envelope
from .curated.sfc.contracts import REGISTER_URL, LEGAL_URL, ce_reference, Rejected
from .curated.sfc.read import capability_status


def status():
    return Envelope(
        data=capability_status(),
        meta={
            "apiVersion": "v1",
            "snapshotIds": [],
            "version": None,
            "view": "sfc_capability_status",
        },
        provenance=[
            {
                "sourceId": "sfc_register",
                "sourceUrl": REGISTER_URL,
                "termsUrl": LEGAL_URL,
                "freshnessBasis": "no_qualified_observation",
                "currentVerification": False,
            }
        ],
        warnings=[
            {
                "code": "SFC_SOURCE_UNQUALIFIED",
                "message": "Fresh corporate verification requires qualified source access and output rights. Historical Webb licence records are separate.",
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


def register_http(app):
    @app.get("/api/v1/sfc/status")
    def sfc_status():
        return status()

    # Compatibility error routes deliberately absent from public discovery/schema.
    @app.get("/api/v1/sfc/corporations", include_in_schema=False)
    def sfc_search():
        return unavailable()

    @app.get("/api/v1/sfc/corporations/{ce}/history", include_in_schema=False)
    def sfc_history(ce: str):
        return unavailable(ce)

    @app.get("/api/v1/sfc/corporations/{ce}", include_in_schema=False)
    def sfc_verify(ce: str):
        return unavailable(ce)


def register_mcp(server):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_sfc_status() -> dict:
        """Read fresh SFC corporate verification capability and permission gates. Status only: no register collection, verification result, search, history or export is available. Webb licences remain a separate historical source."""
        return status()
