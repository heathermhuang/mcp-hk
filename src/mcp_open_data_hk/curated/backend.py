"""Optional private query service; the existing gateway does not depend on it."""

import hmac
import os
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from .read import Reader, ReadError
from .official_read import OfficialReader

STATUS = {
    "SFC_INVALID_CE": 400,
    "INVALID_QUERY": 400,
    "INVALID_LIMIT": 400,
    "INVALID_ID": 400,
    "INVALID_CURSOR": 400,
    "NOT_FOUND": 404,
    "VERSION_EXPIRED": 409,
    "AS_OF_UNSUPPORTED": 422,
    "QUERY_BUSY": 429,
    "QUERY_TIMEOUT": 504,
    "OUTPUT_LIMIT": 413,
    "PACK_UNAVAILABLE": 503,
    "UNSAFE_READER": 503,
}


def create_app(reader, token):
    if len(token) < 32:
        raise ValueError(
            "Use a dedicated backend bearer credential of at least 32 characters"
        )
    app = FastAPI(
        title="mcp.hk private curated read model",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    async def call(operation_fn, authorization, **kwargs):
        if not hmac.compare_digest(
            (authorization or "").encode(), ("Bearer " + token).encode()
        ):
            raise HTTPException(401, detail={"code": "UNAUTHORIZED"})
        try:
            return await run_in_threadpool(operation_fn, **kwargs)
        except ReadError as exc:
            headers = {"Retry-After": "1"} if exc.code == "QUERY_BUSY" else None
            raise HTTPException(
                STATUS.get(exc.code, 503),
                detail={"code": exc.code, "message": str(exc)},
                headers=headers,
            ) from exc
        except Exception as exc:
            # No DSNs, credentials, source values or caller terms in error bodies.
            raise HTTPException(503, detail={"code": "PACK_UNAVAILABLE"}) from exc

    from .sfc.read import SfcReader

    sfc = SfcReader(reader)

    @app.get("/v1/sfc/status")
    async def sfc_status(authorization: str | None = Header(None)):
        return await call(sfc.status, authorization)

    @app.get("/v1/sfc/corporations/{ce}")
    async def sfc_verify(
        ce: str,
        version: str | None = Query(None, max_length=100),
        authorization: str | None = Header(None),
    ):
        return await call(sfc.verify, authorization, ce=ce, version=version)

    from .webb_sdi_read import WebbSdiReader

    webb = WebbSdiReader(reader)

    @app.get("/v1/webb-sdi/status")
    async def webb_status(authorization: str | None = Header(None)):
        return await call(webb.status, authorization)

    @app.get("/v1/webb-sdi/issuers")
    async def webb_issuers(
        stockCode: str | None = None,
        q: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        version: str | None = None,
        authorization: str | None = Header(None),
    ):
        return await call(
            webb.query,
            authorization,
            operation="issuers",
            params=dict(
                stockCode=stockCode, q=q, limit=limit, cursor=cursor, version=version
            ),
        )

    @app.get("/v1/webb-sdi/disclosures")
    async def webb_disclosures(
        issuerId: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        version: str | None = None,
        authorization: str | None = Header(None),
    ):
        return await call(
            webb.query,
            authorization,
            operation="disclosures",
            params=dict(
                issuerId=issuerId,
                start=start,
                end=end,
                limit=limit,
                cursor=cursor,
                version=version,
            ),
        )

    @app.get("/v1/webb-sdi/disclosures/{filing_id}")
    async def webb_disclosure(
        filing_id: str, version: str, authorization: str | None = Header(None)
    ):
        return await call(
            webb.query,
            authorization,
            operation="disclosure",
            params=dict(filingId=filing_id, version=version),
        )

    from .hkex.read import HkexReader

    hkex = HkexReader(reader)

    @app.get("/v1/hkex/status")
    async def hkex_status(
        authorization: str | None = Header(None),
        mode: Literal["rest", "mcp", "browser"] = "rest",
    ):
        return await call(hkex.status, authorization, mode=mode)

    @app.get("/v1/hkex/issuers")
    async def hkex_issuers(
        stockCode: str | None = None,
        q: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        version: str | None = None,
        mode: Literal["rest", "mcp", "browser"] = "rest",
        authorization: str | None = Header(None),
    ):
        return await call(
            hkex.query,
            authorization,
            operation="issuers",
            params=dict(
                stockCode=stockCode, q=q, limit=limit, cursor=cursor, version=version
            ),
            mode=mode,
        )

    @app.get("/v1/hkex/disclosures")
    async def hkex_disclosures(
        issuerId: str,
        start: str,
        end: str,
        basis: Literal["filed", "published", "event"],
        channel: Literal["dion", "pre_dion"] = "dion",
        form: str | None = None,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = None,
        version: str | None = None,
        mode: Literal["rest", "mcp", "browser"] = "rest",
        authorization: str | None = Header(None),
    ):
        return await call(
            hkex.query,
            authorization,
            operation="disclosures",
            params=dict(
                issuerId=issuerId,
                start=start,
                end=end,
                basis=basis,
                channel=channel,
                form=form,
                limit=limit,
                cursor=cursor,
                version=version,
            ),
            mode=mode,
        )

    @app.get("/v1/hkex/disclosures/{filing_id}")
    async def hkex_disclosure(
        filing_id: str,
        version: str,
        mode: Literal["rest", "mcp", "browser"] = "rest",
        authorization: str | None = Header(None),
    ):
        return await call(
            hkex.query,
            authorization,
            operation="disclosure",
            params=dict(filingId=filing_id, version=version),
            mode=mode,
        )

    official = OfficialReader(reader)

    @app.get("/v1/official/status")
    async def official_status(authorization: str | None = Header(None)):
        return await call(official.status, authorization)

    @app.get("/v1/official/companies")
    async def official_search(
        groupBy: Literal["organisation"] | None = None,
        name: str | None = Query(None, max_length=200),
        namespace: str | None = Query(None, max_length=100),
        value: str | None = Query(None, max_length=200),
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=2048),
        authorization: str | None = Header(None),
    ):
        return await call(
            official.search,
            authorization,
            groupBy=groupBy,
            name=name,
            namespace=namespace,
            value=value,
            limit=limit,
            cursor=cursor,
        )

    @app.get("/v1/official/entities/{entity_id}")
    async def official_get(
        entity_id: str,
        version: str | None = Query(None, max_length=100),
        authorization: str | None = Header(None),
    ):
        return await call(
            official.get, authorization, entity_id=entity_id, version=version
        )

    @app.get("/v1/official/entities/{entity_id}/addresses")
    async def official_addresses(
        entity_id: str,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=2048),
        version: str | None = Query(None, max_length=100),
        asOf: str | None = Query(None, max_length=10),
        authorization: str | None = Header(None),
    ):
        return await call(
            official.address_history,
            authorization,
            entity_id=entity_id,
            limit=limit,
            cursor=cursor,
            version=version,
            asOf=asOf,
        )

    @app.get("/health")
    async def health(authorization: str | None = Header(None)):
        def check():
            with reader.request() as (_, release):
                return {
                    "capabilities": [
                        "company-search-groupBy-organisation-v1",
                        "webb-sdi-archive-v1",
                    ],
                    "status": "ready",
                    "version": release["version"],
                    "view": "archive",
                }

        return await call(check, authorization)

    @app.get("/v1/companies")
    async def search(
        groupBy: Literal["organisation"] | None = None,
        name: str | None = Query(None, max_length=200),
        namespace: str | None = Query(None, max_length=100),
        value: str | None = Query(None, max_length=200),
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=2048),
        authorization: str | None = Header(None),
    ):
        return await call(
            reader.search,
            authorization,
            groupBy=groupBy,
            name=name,
            namespace=namespace,
            value=value,
            limit=limit,
            cursor=cursor,
        )

    @app.get("/v1/entities/{entity_id}")
    async def get(
        entity_id: int,
        version: str | None = Query(None, max_length=100),
        authorization: str | None = Header(None),
    ):
        return await call(
            reader.get, authorization, entity_id=entity_id, version=version
        )

    @app.get("/v1/entities/{entity_id}/{family}")
    async def related(
        entity_id: int,
        family: str,
        limit: int = Query(20, ge=1, le=100),
        cursor: str | None = Query(None, max_length=2048),
        as_of: str | None = Query(None, alias="asOf", max_length=10),
        version: str | None = Query(None, max_length=100),
        authorization: str | None = Header(None),
    ):
        return await call(
            reader.related,
            authorization,
            entity_id=entity_id,
            family=family,
            limit=limit,
            cursor=cursor,
            as_of=as_of,
            version=version,
        )

    return app


def main():
    import uvicorn

    reader = Reader(
        os.environ["CURATED_DSN"], os.environ["CURATED_CURSOR_SECRET"].encode()
    )
    app = create_app(reader, os.environ["CURATED_BACKEND_TOKEN"])
    uvicorn.run(app, host="0.0.0.0", port=8081, access_log=False)
