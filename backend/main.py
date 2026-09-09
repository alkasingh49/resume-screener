"""FastAPI application entrypoint.

Run with: uvicorn backend.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.v1.router import api_router
from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.db.session import init_db

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


def _validate_llm_config() -> None:
    """Warn early (once, at startup) if the configured provider's API key
    looks unset. Doesn't fail startup - JD/resume flows already degrade
    gracefully to a FAILED status with a clear error on a missing key - but
    a startup-log warning is much easier to notice than discovering it only
    when the first upload silently fails.
    """
    key_by_provider = {"gemini": settings.GOOGLE_API_KEY, "openai": settings.OPENAI_API_KEY}
    for label, provider in (
        ("LLM_PROVIDER", settings.LLM_PROVIDER),
        ("EMBEDDING_PROVIDER", settings.EMBEDDING_PROVIDER),
    ):
        if not key_by_provider.get(provider):
            logger.warning(
                "%s=%s but its API key is not set in .env - calls through it will fail until it is.",
                label,
                provider,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_data_dirs()
    init_db()
    _validate_llm_config()
    logger.info(
        "Startup complete | env=%s | llm_provider=%s | llm_model=%s",
        settings.APP_ENV,
        settings.LLM_PROVIDER,
        settings.LLM_MODEL,
    )
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort safety net for a genuinely unexpected bug - every known
    failure mode in the app (bad file, missing JD, LLM call failing, ...) is
    already caught and turned into a clean 4xx/5xx with a specific message
    at the route/service level; this only fires for the rest. Logs the full
    traceback server-side through the app's own logger and never leaks it
    to the client.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/")
def root() -> dict:
    """Root endpoint - points to the health check and API docs."""
    return {
        "app": settings.APP_NAME,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
