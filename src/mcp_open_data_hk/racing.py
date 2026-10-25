"""Public racing gate shared by REST, MCP and browser. Never initiates source reads."""

from .contracts import DomainError, Envelope
from .curated.racing.policy import FAMILIES

# A code-reviewed source qualification release is required before exposing facts.
# Runtime flags, caller parameters and synthetic imports cannot bypass this gate.
LIVE_QUALIFIED = False


def status():
    return Envelope(
        data={
            "source": "hkjc",
            "state": "source_permission_required",
            "liveQualified": LIVE_QUALIFIED,
            "acceptedVersion": None,
            "coverage": {"meeting": None, "season": None, "history": None},
            "seriesStart": None,
            "measuredCadenceSeconds": None,
            "scheduled": False,
            "families": [
                {"id": family, "state": "unqualified", "enabled": False}
                for family in FAMILIES
            ],
            "modes": {
                mode: "unqualified"
                for mode in (
                    "collection",
                    "cache",
                    "history",
                    "rest",
                    "mcp",
                    "browser",
                    "links",
                    "export",
                    "schedule",
                )
            },
        },
        meta={"pack": "hkjc_racing", "version": None, "sourceQualified": False},
        provenance=[
            {
                "sourceId": "hkjc",
                "qualificationChecked": "2026-10-25",
                "sourceUrl": "https://www.hkjc.com/en-us/disclaimer",
                "freshnessBasis": "no_accepted_source_observation",
            }
        ],
        warnings=[
            {
                "code": "SOURCE_PERMISSION_REQUIRED",
                "message": "No racing facts are published. Route-specific collection, retention and output rights remain unqualified.",
            }
        ],
    ).model_dump()


def unavailable():
    raise DomainError(
        "RACING_SOURCE_UNQUALIFIED",
        "Racing collection and public data modes await source qualification",
        503,
    )


def register_tools(server):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_racing_status() -> dict:
        """Read racing permission/coverage gates. No accepted racing dataset or live odds; no source request is made."""
        return status()
