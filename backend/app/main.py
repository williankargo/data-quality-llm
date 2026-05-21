"""FastAPI application entry point.

Registers middleware, routers, and global exception handlers.
"""

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import CODE_MAP
from app.config import settings
from app.schemas.errors import ErrorDetail, ErrorEnvelope

app = FastAPI(
    title="Data Quality Assistant",
    description="AI-powered data quality rule management for domain experts.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handlers (D#10)
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap FastAPI/Starlette HTTPException into the error envelope format.

    When exc.detail is a known string code, that code is used directly so that
    multiple distinct 4xx/5xx errors sharing the same HTTP status can each carry
    their own machine-readable code.
    """
    # Maps detail string → (code, user_message).  All callers that raise a
    # domain-specific HTTPException must pass the code string as exc.detail.
    detail_str = str(exc.detail) if exc.detail is not None else ""
    if detail_str in CODE_MAP:
        code = detail_str
        _, user_message = CODE_MAP[detail_str]
    else:
        code = "HTTP_ERROR"
        user_message = detail_str

    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            user_message=user_message,
            technical_detail=detail_str,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected errors."""
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="INTERNAL_ERROR",
            user_message="An unexpected system error occurred. Please try again later.",
            technical_detail=traceback.format_exc(),
        )
    )
    return JSONResponse(status_code=500, content=envelope.model_dump())


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

# Health router (inline — keeps the entry point self-contained for Phase 1)
from fastapi import APIRouter  # noqa: E402

health_router = APIRouter()


@health_router.get("/health")
def health_check() -> dict:
    return {"status": "ok", "llm_model": settings.LLM_MODEL}


app.include_router(health_router)

# Phase 2: tables router
from app.api.tables import router as tables_router  # noqa: E402

app.include_router(tables_router)

from app.api.rules import router as rules_router  # noqa: E402

app.include_router(rules_router)

from app.api.results import router as results_router  # noqa: E402

app.include_router(results_router)
