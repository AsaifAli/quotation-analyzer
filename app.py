"""FastAPI service for the quotation intelligence engine."""

import logging
import os
import tempfile

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

import config
from api_security import api_auth_error, require_api_auth
from llm_gateway_context import (
    reset_llm_gateway_token,
    set_llm_gateway_token,
)
from modules.ai_agent import QuotationIntelligenceAgent


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Quotation Intelligence API",
    version="3.2.0",
    description=(
        "AI-assisted procurement quotation analysis "
        "with deterministic validation and scoring."
    ),
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
        "/analyze",
    }

    is_protected = (
        request.method == "POST"
        and request.url.path in protected_routes
    )

    if is_protected:
        error = api_auth_error(
            request.headers.get("Authorization")
        )

        if error:
            status, detail = error
            headers = (
                {"WWW-Authenticate": "Bearer"}
                if status == 401
                else {}
            )

            return JSONResponse(
                status_code=status,
                content={"detail": detail},
                headers=headers,
            )

        # Account for multipart boundaries and form metadata.
        max_request_bytes = (
            config.MAX_TOTAL_UPLOAD_SIZE_MB * 1024 * 1024
            + 2 * 1024 * 1024
        )

        content_length = request.headers.get("content-length")

        if content_length:
            try:
                request_size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )

            if request_size < 0:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )

            if request_size > max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request size limit exceeded."},
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
    info = llm_health()

    if not info.get("available"):
        raise HTTPException(
            status_code=503,
            detail="LLM provider is not ready.",
        )

    return {"status": "ready"}


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