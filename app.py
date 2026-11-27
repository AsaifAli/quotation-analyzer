"""FastAPI service for the quotation intelligence engine."""

import asyncio
import hashlib
import json
import logging
import os
import tempfile

import requests
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, StreamingResponse

import config
from api_security import api_auth_error, require_api_auth
from api_rate_limit import RateLimitBackendUnavailable, rate_limiter
from llm_gateway_context import (
    get_llm_gateway_token,
    reset_llm_gateway_token,
    set_llm_gateway_token,
)
from modules.ai_agent import QuotationIntelligenceAgent
from modules.document_processor import DocumentProcessingLimitError


logger = logging.getLogger(__name__)


class _RequestBodyTooLarge(Exception):
    """Raised when a streamed request exceeds the configured body limit."""


class RequestBodySizeLimitMiddleware:
    """Bound upload request bodies even when Content-Length is absent.

    Only the two authenticated analysis endpoints are subject to this limit.
    The middleware counts chunks as the downstream multipart parser consumes
    them, so chunked requests cannot bypass the declared-length preflight.
    """

    PROTECTED_PATHS = {"/api/v1/analyses", "/api/v1/analyses/stream", "/analyze"}

    def __init__(self, app, *, max_bytes: int):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def _send_error(self, send, status_code: int, message: str) -> None:
        import json

        body = json.dumps({"detail": message}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })

    async def __call__(self, scope, receive, send):
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in self.PROTECTED_PATHS
        ):
            await self.app(scope, receive, send)
            return

        raw_headers = [
            (key.lower(), value)
            for key, value in scope.get("headers", [])
        ]
        content_lengths = [
            value
            for key, value in raw_headers
            if key == b"content-length"
        ]
        if len(content_lengths) > 1:
            await self._send_error(
                send,
                400,
                "Ambiguous Content-Length header.",
            )
            return

        content_length = content_lengths[0] if content_lengths else None
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except (TypeError, ValueError):
                await self._send_error(send, 400, "Invalid Content-Length header.")
                return
            if declared_length < 0:
                await self._send_error(send, 400, "Invalid Content-Length header.")
                return
            if declared_length > self.max_bytes:
                await self._send_error(send, 413, "Request body too large.")
                return

        received_bytes = 0
        response_started = False

        async def limited_receive():
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            # Multipart parsing happens before the analysis handler starts.
            # No response should have been started at this point.
            if not response_started:
                await self._send_error(send, 413, "Request body too large.")


app = FastAPI(
    title="Quotation Intelligence API",
    version="3.2.0",
    description=(
        "AI-assisted procurement quotation analysis "
        "with deterministic validation and scoring."
    ),
)

app.add_middleware(
    RequestBodySizeLimitMiddleware,
    max_bytes=config.MAX_TOTAL_UPLOAD_SIZE_MB * 1024 * 1024 + 2 * 1024 * 1024,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        item.strip()
        for item in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8501",
        ).split(",")
        if item.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_security_context(request, call_next):
    """Authenticate protected routes before FastAPI parses uploaded files."""

    protected_routes = {
        "/api/v1/analyses",
        "/api/v1/analyses/stream",
        "/analyze",
    }

    is_protected = (
        request.method == "POST"
        and request.url.path in protected_routes
    )

    if is_protected:
        client_ip = (
            request.client.host
            if request.client is not None
            else "unknown"
        )
        authorization = request.headers.get("Authorization")
        gateway_token = request.headers.get("X-LLM-Gateway-Token")
        try:
            ip_allowed, ip_retry_after = rate_limiter.check(
                f"ip:{client_ip}",
                limit=config.API_IP_RATE_LIMIT_PER_MINUTE,
            )
            if not ip_allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please retry later."},
                    headers={"Retry-After": str(ip_retry_after)},
                )

            error = api_auth_error(authorization, gateway_token)
            if error:
                status, detail = error
                headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
                return JSONResponse(
                    status_code=status,
                    content={"detail": detail},
                    headers=headers,
                )

            # A Gateway-authenticated BYOK request has no Authorization
            # header by design. Use a one-way digest of its project JWT so
            # sessions retain independent API quotas without storing tokens.
            quota_identity = (
                authorization
                if authorization
                else "gateway:" + hashlib.sha256(
                    (gateway_token or "").encode("utf-8")
                ).hexdigest()
            )
            token_fingerprint = hashlib.sha256(
                quota_identity.encode("utf-8")
            ).hexdigest()
            principal_allowed, principal_retry_after = rate_limiter.check(
                f"token:{token_fingerprint}",
                limit=config.API_RATE_LIMIT_PER_MINUTE,
            )
            if not principal_allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "API request limit reached. Please retry later."},
                    headers={"Retry-After": str(principal_retry_after)},
                )
        except RateLimitBackendUnavailable:
            logger.error("api_rate_limit_backend_unavailable")
            return JSONResponse(
                status_code=503,
                content={"detail": "API is temporarily unavailable."},
                headers={"Retry-After": "5"},
            )


    # Reset the gateway token even if request processing fails.
    token = set_llm_gateway_token(
        request.headers.get("X-LLM-Gateway-Token", "")
    )

    try:
        return await call_next(request)
    finally:
        reset_llm_gateway_token(token)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": config.LLM_PROVIDER,
    }


@app.get("/health/llm")
def llm_health():
    """Expose provider availability without exposing raw provider errors."""

    try:
        from modules.llm_provider import LLMProvider

        info = LLMProvider().health()

        available = (
            bool(info.get("available"))
            if isinstance(info, dict)
            else False
        )

        return {
            "available": available,
            "provider": config.LLM_PROVIDER,
        }

    except Exception:
        logger.exception("LLM health check failed")

        return {
            "available": False,
            "provider": config.LLM_PROVIDER,
        }


@app.get("/ready")
def ready():
    """Report readiness for direct-provider or per-client Gateway BYOK mode.

    A Gateway-backed service must not require a process-wide provider key:
    each authenticated client supplies its own short-lived Gateway session.
    Production readiness still requires the shared rate-limit backend because
    protected analysis requests fail closed when it is unavailable.
    """
    is_production = (
        os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}
        or os.getenv("RENDER", "").strip().lower() in {"1", "true"}
    )
    if is_production and (
        not os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
        or not os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    ):
        raise HTTPException(
            status_code=503,
            detail="Production rate limiting is not configured.",
        )

    gateway_url = config.LLM_GATEWAY_URL.strip().rstrip("/")
    if gateway_url:
        health_url = (
            f"{gateway_url}/health"
            if gateway_url.endswith("/v1")
            else f"{gateway_url}/v1/health"
        )
        try:
            response = requests.get(health_url, timeout=5)
            response.raise_for_status()
        except requests.RequestException:
            raise HTTPException(
                status_code=503,
                detail="Portfolio Gateway is unavailable.",
            ) from None
        return {
            "status": "ready",
            "provider": "gateway",
            "mode": "BYOK",
        }

    info = llm_health()
    if not info.get("available"):
        raise HTTPException(
            status_code=503,
            detail="LLM provider is not ready.",
        )

    return {"status": "ready", "provider": info.get("provider", config.LLM_PROVIDER)}


@app.post(
    "/api/v1/analyses",
    dependencies=[Depends(require_api_auth)],
)
async def analyze(
    files: list[UploadFile] = File(...),
    query: str = Form("Analyze quotations"),
    criteria: str = Form(""),
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="At least one quotation file is required.",
        )

    if len(files) > config.MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail="Too many files in one request.",
        )

    if len(query) + len(criteria) > config.MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=413,
            detail="Query and criteria exceed the configured length limit.",
        )

    paths = []
    names = []
    total_size = 0

    max_file_size = config.MAX_FILE_SIZE_MB * 1024 * 1024
    max_total_size = (
        config.MAX_TOTAL_UPLOAD_SIZE_MB * 1024 * 1024
    )

    try:
        for file in files:
            # Discard any client-supplied directory components.
            original_name = (
                (file.filename or "upload")
                .replace("\\", "/")
                .rsplit("/", 1)[-1]
            )

            ext = os.path.splitext(original_name)[1].lower()

            if ext not in config.SUPPORTED_FORMATS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {ext}",
                )

            # Reject oversized files before copying them.
            declared_size = getattr(file, "size", None)

            if declared_size is not None:
                if declared_size > max_file_size:
                    raise HTTPException(
                        status_code=413,
                        detail="An uploaded file exceeds the per-file size limit.",
                    )

                if total_size + declared_size > max_total_size:
                    raise HTTPException(
                        status_code=413,
                        detail="Total upload size limit exceeded.",
                    )

            fd, path = tempfile.mkstemp(suffix=ext)
            paths.append(path)

            file_size = 0

            # Copy in bounded chunks rather than reading the entire file
            # into application memory.
            with os.fdopen(fd, "wb") as output:
                while True:
                    chunk = await file.read(1024 * 1024)

                    if not chunk:
                        break

                    file_size += len(chunk)
                    total_size += len(chunk)

                    if file_size > max_file_size:
                        raise HTTPException(
                            status_code=413,
                            detail="An uploaded file exceeds the per-file size limit.",
                        )

                    if total_size > max_total_size:
                        raise HTTPException(
                            status_code=413,
                            detail="Total upload size limit exceeded.",
                        )

                    output.write(chunk)

            if file_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Uploaded files cannot be empty.",
                )

            names.append(original_name)

        criteria_list = [
            item.strip()
            for item in criteria.split(",")
            if item.strip()
        ] or config.DEFAULT_CRITERIA

        result = QuotationIntelligenceAgent().process_documents(
            paths,
            query=query,
            criteria=criteria_list,
        )

        result["uploaded_files"] = names

        return result

    except HTTPException:
        raise

    except DocumentProcessingLimitError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc

    except Exception:
        logger.exception("Quotation analysis failed")

        raise HTTPException(
            status_code=500,
            detail=(
                "Analysis failed. Please retry or contact the administrator."
            ),
        )

    finally:
        for file in files:
            try:
                await file.close()
            except Exception:
                logger.warning("Could not close an uploaded file.")

        for path in paths:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                logger.exception("Could not remove a temporary upload file.")


def _sse_frame(event_name: str, payload: dict) -> str:
    """Serialize one Server-Sent Event frame."""
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


@app.post(
    "/api/v1/analyses/stream",
    dependencies=[Depends(require_api_auth)],
)
async def analyze_stream(
    files: list[UploadFile] = File(...),
    query: str = Form("Analyze quotations"),
    criteria: str = Form(""),
):
    """Stream real processing stages while preserving the existing JSON API."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one quotation file is required.")
    if len(files) > config.MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail="Too many files in one request.")
    if len(query) + len(criteria) > config.MAX_QUERY_CHARS:
        raise HTTPException(status_code=413, detail="Query and criteria exceed the configured length limit.")

    paths = []
    names = []
    total_size = 0
    max_file_size = config.MAX_FILE_SIZE_MB * 1024 * 1024
    max_total_size = config.MAX_TOTAL_UPLOAD_SIZE_MB * 1024 * 1024

    try:
        for file in files:
            original_name = (
                (file.filename or "upload")
                .replace("\\", "/")
                .rsplit("/", 1)[-1]
            )
            extension = os.path.splitext(original_name)[1].lower()
            if extension not in config.SUPPORTED_FORMATS:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension}")

            declared_size = getattr(file, "size", None)
            if declared_size is not None and declared_size > max_file_size:
                raise HTTPException(status_code=413, detail="An uploaded file exceeds the per-file size limit.")
            if declared_size is not None and total_size + declared_size > max_total_size:
                raise HTTPException(status_code=413, detail="Total upload size limit exceeded.")

            fd, path = tempfile.mkstemp(suffix=extension)
            paths.append(path)
            file_size = 0
            with os.fdopen(fd, "wb") as output:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    total_size += len(chunk)
                    if file_size > max_file_size:
                        raise HTTPException(status_code=413, detail="An uploaded file exceeds the per-file size limit.")
                    if total_size > max_total_size:
                        raise HTTPException(status_code=413, detail="Total upload size limit exceeded.")
                    output.write(chunk)

            if file_size == 0:
                raise HTTPException(status_code=400, detail="Uploaded files cannot be empty.")
            names.append(original_name)
    except HTTPException:
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        for file in files:
            await file.close()
        raise
    except Exception:
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        for file in files:
            await file.close()
        raise HTTPException(status_code=500, detail="The quotation upload could not be prepared.") from None

    for file in files:
        await file.close()

    criteria_list = [
        item.strip() for item in criteria.split(",") if item.strip()
    ] or config.DEFAULT_CRITERIA

    # Capture the request-scoped Gateway session before the streaming response
    # outlives request middleware cleanup. The token is passed only server-side.
    gateway_token = get_llm_gateway_token()
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    loop = asyncio.get_running_loop()

    event_queue.put_nowait((
        "stage",
        {
            "sequence": 0,
            "stage": "ingest",
            "status": "completed",
            "message": "Quotation documents received and upload checks passed.",
            "occurred_at": None,
            "metrics": {"document_count": len(names), "total_bytes": total_size},
        },
    ))

    def publish_stage(event):
        try:
            loop.call_soon_threadsafe(event_queue.put_nowait, ("stage", event))
        except RuntimeError:
            # The browser may disconnect while the backend finishes safely.
            pass

    def run_analysis():
        try:
            agent = QuotationIntelligenceAgent(gateway_token=gateway_token)
            return agent.process_documents(
                paths,
                query=query,
                criteria=criteria_list,
                stage_callback=publish_stage,
            )
        finally:
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    logger.warning("Could not remove a temporary quotation upload.")
            try:
                loop.call_soon_threadsafe(event_queue.put_nowait, None)
            except RuntimeError:
                pass

    task = asyncio.create_task(asyncio.to_thread(run_analysis))

    # Retrieve a background exception even if the browser disconnects before
    # the stream consumer has a chance to await the processing task.
    def consume_task_exception(completed_task):
        if not completed_task.cancelled():
            completed_task.exception()

    task.add_done_callback(consume_task_exception)

    async def event_stream():
        yield ": QuoteSense processing stream connected\n\n"
        while True:
            try:
                queued = await asyncio.wait_for(event_queue.get(), timeout=15)
            except asyncio.TimeoutError:
                if task.done():
                    break
                yield ": keep-alive\n\n"
                continue
            if queued is None:
                break
            event_name, payload = queued
            yield _sse_frame(event_name, payload)

        try:
            result = await task
            result["uploaded_files"] = names
            yield _sse_frame("result", result)
        except DocumentProcessingLimitError as exc:
            yield _sse_frame("error", {"code": "DOCUMENT_LIMIT", "detail": str(exc)})
        except Exception:
            logger.exception("Streaming quotation analysis failed")
            yield _sse_frame(
                "error",
                {"code": "ANALYSIS_FAILED", "detail": "Analysis failed. Please retry or contact the administrator."},
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post(
    "/analyze",
    dependencies=[Depends(require_api_auth)],
)
async def legacy_analyze(
    file: UploadFile = File(...),
    query: str = Form("Analyze quotations"),
    criteria: str = Form(""),
):
    return await analyze(
        [file],
        query=query,
        criteria=criteria,
    )


@app.get("/")
def root():
    return {
        "service": "quotation-intelligence-api",
        "version": "3.2.0",
        "docs": "/docs",
        "health": "/health",
    }