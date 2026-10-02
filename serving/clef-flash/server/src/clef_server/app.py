import asyncio
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)
from prometheus_client.exposition import generate_latest
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from clef_server.adapter import ClefAdapter, DecisionAdapter
from clef_server.schemas import SystemOneRequest

log = structlog.get_logger()
AdapterFactory = Callable[[], DecisionAdapter]
MAX_CONTENT_LENGTH = 13 * 1024 * 1024


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length", b"")
        if content_length.isdigit() and int(content_length) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413, content={"detail": "Request too large"}
        )
        await response(scope, receive, send)


def create_app(
    adapter_factory: AdapterFactory = ClefAdapter.from_environment,
    max_content_length: int = MAX_CONTENT_LENGTH,
) -> FastAPI:
    registry = CollectorRegistry()
    requests_total = Counter(
        "clef_requests_total",
        "SystemOne requests by outcome.",
        ["outcome"],
        registry=registry,
    )
    request_duration = Histogram(
        "clef_request_duration_seconds",
        "SystemOne request duration including queue wait.",
        buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
        registry=registry,
    )
    inference_duration = Histogram(
        "clef_inference_duration_seconds",
        "Model inference duration excluding queue wait.",
        buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
        registry=registry,
    )
    requests_in_flight = Gauge(
        "clef_requests_in_flight",
        "SystemOne requests currently in progress.",
        registry=registry,
    )
    model_ready = Gauge(
        "clef_model_ready",
        "Whether the CLEF model is ready for inference.",
        registry=registry,
    )
    model_load_duration = Gauge(
        "clef_model_load_duration_seconds",
        "Duration of the most recent model load attempt.",
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.adapter = None
        app.state.model_status = "loading"
        app.state.inference_lock = asyncio.Lock()

        async def load_adapter() -> None:
            log.info("model_loading_started", model="clef-flash")
            started = time.perf_counter()
            try:
                app.state.adapter = await run_in_threadpool(adapter_factory)
                app.state.model_status = "ready"
                model_ready.set(1)
                log.info("model_loading_completed", model="clef-flash")
            except Exception as error:  # noqa: BLE001 - readiness reports load failures
                app.state.model_status = "failed"
                model_ready.set(0)
                log.error(
                    "model_loading_failed",
                    model="clef-flash",
                    error_type=type(error).__name__,
                )
            finally:
                model_load_duration.set(time.perf_counter() - started)

        load_task = asyncio.create_task(load_adapter())
        yield
        if not load_task.done():
            load_task.cancel()
            with suppress(asyncio.CancelledError):
                await load_task

    app = FastAPI(title="CLEF-Flash SystemOne Server", lifespan=lifespan)

    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_content_length)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid SystemOne request"},
        )

    @app.get("/health/live")
    async def live(request: Request) -> JSONResponse:
        status = request.app.state.model_status
        if status == "failed":
            return JSONResponse(status_code=503, content={"status": status})
        return JSONResponse(content={"status": "live"})

    @app.get("/health/ready")
    async def ready(request: Request) -> JSONResponse:
        if request.app.state.adapter is None:
            return JSONResponse(
                status_code=503,
                content={"status": request.app.state.model_status},
            )
        return JSONResponse(content={"status": "ready"})

    @app.post("/v1/systemone")
    async def decide(payload: SystemOneRequest, request: Request) -> JSONResponse:
        started = time.perf_counter()
        requests_in_flight.inc()
        try:
            adapter = request.app.state.adapter
            if adapter is None:
                requests_total.labels(outcome="not_ready").inc()
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Model is not ready"},
                )

            async with request.app.state.inference_lock:
                inference_started = time.perf_counter()
                try:
                    result = await run_in_threadpool(
                        adapter.decide,
                        payload.model_dump(mode="json"),
                    )
                finally:
                    inference_duration.observe(time.perf_counter() - inference_started)
        except Exception as error:  # noqa: BLE001 - third-party inference boundary
            requests_total.labels(outcome="error").inc()
            log.error(
                "inference_failed",
                model=adapter.model_name,
                question_count=len(payload.questions),
                error_type=type(error).__name__,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Decision inference failed"},
            )
        finally:
            requests_in_flight.dec()
            request_duration.observe(time.perf_counter() - started)

        requests_total.labels(outcome="success").inc()
        log.info(
            "inference_completed",
            model=adapter.model_name,
            question_count=len(payload.questions),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return JSONResponse(content=result)

    return app


app = create_app()
