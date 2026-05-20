"""FastAPI application entry point.

Registers middleware, routers, and global exception handlers.
"""

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    """Wrap FastAPI/Starlette HTTPException into the error envelope format."""
    # Map known HTTP status codes to user-friendly codes and messages.
    code_map: dict[int, tuple[str, str]] = {
        404: ("TABLE_NOT_FOUND", "Table not found"),
        503: ("DATABASE_UNAVAILABLE", "Unable to connect to the database temporarily"),
    }
    code, user_message = code_map.get(
        exc.status_code, ("HTTP_ERROR", str(exc.detail))
    )

    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            user_message=user_message,
            technical_detail=str(exc.detail),
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

# Phase 2 routers (rules, results) are registered in later phases.
