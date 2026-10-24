"""Request-owned budgets, shared through async tasks and copied thread contexts.

Hosted readers have no direct egress: the sole internal HTTP gateway owns grants.
Outside hosted mode these same adapters enforce local operation limits.
"""

import asyncio
import contextvars
import os
import threading
import time
from contextlib import contextmanager

import httpx

from .contracts import DomainError

CALLS = 100
BYTES = 8_000_000
SECONDS = 30
CONCURRENCY = 2
GATEWAY = "http://mcp-egress"
current_budget = contextvars.ContextVar("upstream_budget", default=None)


class Budget:
    def __init__(
        self,
        grant="",
        calls=CALLS,
        size=BYTES,
        seconds=SECONDS,
        concurrency=CONCURRENCY,
    ):
        self.grant = grant
        self.max_calls, self.max_bytes = calls, size
        self.deadline = time.monotonic() + seconds
        self.calls = self.bytes = self.inflight = 0
        self.peak = 0
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(concurrency)

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise DomainError("UPSTREAM_DEADLINE", "Operation deadline exhausted", 504)
        return remaining

    def acquire(self):
        if not self.slots.acquire(timeout=self.remaining()):
            raise DomainError(
                "UPSTREAM_DEADLINE", "Operation concurrency wait expired", 504
            )
        try:
            with self.lock:
                self.remaining()
                if self.calls >= self.max_calls or self.bytes >= self.max_bytes:
                    raise DomainError(
                        "UPSTREAM_BUDGET", "Operation allocation exhausted", 429
                    )
                self.calls += 1
                self.inflight += 1
                self.peak = max(self.peak, self.inflight)
        except BaseException:
            self.slots.release()
            raise

    def retry(self):
        with self.lock:
            self.remaining()
            if self.calls >= self.max_calls or self.bytes >= self.max_bytes:
                raise DomainError(
                    "UPSTREAM_BUDGET", "Operation allocation exhausted", 429
                )
            self.calls += 1

    def charge(self, size):
        with self.lock:
            self.bytes += size
            self.remaining()
            if self.bytes > self.max_bytes:
                raise DomainError(
                    "UPSTREAM_BUDGET", "Decoded upstream byte allocation exhausted", 429
                )

    def release(self):
        with self.lock:
            self.inflight -= 1
        self.slots.release()


@contextmanager
def operation(budget=None):
    budget = budget or Budget()
    token = current_budget.set(budget)
    try:
        yield budget
    finally:
        budget.cancelled.set()
        current_budget.reset(token)


def get_budget():
    budget = current_budget.get()
    if budget is None:
        if os.environ.get("MCP_HK_EDGE_MODE") == "true":
            raise DomainError(
                "INVALID_OPERATION",
                "Hosted upstream operation requires an edge grant",
                403,
            )
        budget = Budget()
    return budget


def gateway_headers(budget, url):
    if not budget.grant:
        raise DomainError("INVALID_OPERATION", "Missing upstream grant", 403)
    return {"x-mcp-operation": budget.grant, "x-mcp-target": str(url)}


class BudgetStream(httpx.AsyncByteStream):
    def __init__(self, response, budget):
        self.response, self.budget = response, budget
        self.closed = False

    async def __aiter__(self):
        # Charge decoded bytes. The edge gateway returns identity encoding too.
        iterator = self.response.aiter_bytes().__aiter__()
        while True:
            try:
                chunk = await asyncio.wait_for(
                    iterator.__anext__(), self.budget.remaining()
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                raise DomainError(
                    "UPSTREAM_DEADLINE", "Operation body deadline exhausted", 504
                ) from None
            self.budget.charge(len(chunk))
            yield chunk

    async def aclose(self):
        if not self.closed:
            self.closed = True
            try:
                await self.response.aclose()
            finally:
                self.budget.release()


class BudgetTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport=None):
        self.inner = transport or httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request):
        budget = get_budget()
        # Do not abandon a queued thread that could later start an unowned request.
        while not budget.slots.acquire(blocking=False):
            budget.remaining()
            await asyncio.sleep(min(0.01, budget.remaining()))
        budget.slots.release()
        budget.acquire()
        try:
            request.extensions["timeout"] = {
                key: min(value or budget.remaining(), budget.remaining())
                for key, value in request.extensions.get("timeout", {}).items()
            }
            if os.environ.get("MCP_HK_EDGE_MODE") == "true":
                headers = dict(request.headers)
                headers.pop("host", None)
                headers.update(gateway_headers(budget, request.url))
                request = httpx.Request(
                    request.method,
                    GATEWAY + "/fetch",
                    headers=headers,
                    content=await request.aread(),
                    extensions=request.extensions,
                )
            response = await self.inner.handle_async_request(request)
            # The wrapper exposes decoded bytes, so remove encoding/length headers.
            headers = [
                (k, v)
                for k, v in response.headers.raw
                if k.lower() not in {b"content-encoding", b"content-length"}
            ]
            return httpx.Response(
                response.status_code,
                headers=headers,
                stream=BudgetStream(response, budget),
                extensions=response.extensions,
            )
        except BaseException:
            budget.release()
            raise

    async def aclose(self):
        await self.inner.aclose()


async def claim_grant(grant):
    # Fixed internal host, explicit environment distrust, bounded response and timeout.
    async with httpx.AsyncClient(
        trust_env=False, timeout=5, follow_redirects=False
    ) as client:
        async with client.stream(
            "POST", GATEWAY + "/claim", headers={"x-mcp-operation": grant}
        ) as response:
            if response.status_code != 204:
                raise DomainError(
                    "INVALID_OPERATION",
                    "Edge grant is missing, expired or already used",
                    403,
                )


class OperationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        edge = os.environ.get("MCP_HK_EDGE_MODE") == "true"
        headers = dict(scope.get("headers", []))
        # Health and private backup paths do not fetch public sources.
        governed = (
            scope["path"].startswith(("/mcp", "/api/"))
            or scope["path"] == "/__ops/refresh"
        )
        maintenance = scope["path"] == "/__ops/refresh"
        grant = headers.get(b"x-mcp-operation", b"").decode("ascii", errors="ignore")
        budget = (
            Budget(grant, calls=2000, size=1_000_000_000, seconds=900, concurrency=6)
            if maintenance
            else Budget(grant)
        )
        started = False

        async def tracked(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        with operation(budget):
            try:
                if edge and governed:
                    # Check the static controller credential before spending a grant.
                    from .operations import authorized

                    if not authorized(
                        "Bearer " + headers.get(b"x-mcp-edge-token", b"").decode()
                    ):
                        raise DomainError("INVALID_EDGE", "Invalid controller", 403)
                    await claim_grant(grant)
                await asyncio.wait_for(
                    self.app(scope, receive, tracked), budget.remaining()
                )
            except (DomainError, asyncio.TimeoutError) as exc:
                if started:
                    raise
                code = exc.code if isinstance(exc, DomainError) else "UPSTREAM_DEADLINE"
                status = exc.status if isinstance(exc, DomainError) else 504
                await JSONResponse({"error": {"code": code}}, status_code=status)(
                    scope, receive, send
                )


from fastmcp.server.middleware import Middleware


class ToolBudgetMiddleware(Middleware):
    async def on_call_tool(self, context, call_next):
        # HTTP already owns the operation; stdio gets one budget per tool call.
        if current_budget.get() is not None:
            return await call_next(context)
        with operation() as budget:
            return await asyncio.wait_for(call_next(context), budget.remaining())
