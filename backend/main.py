"""FastAPI entrypoint.

    uvicorn backend.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .routers import assessments, jds, resumes

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    if not settings.api_key:
        key = "GOOGLE_API_KEY" if settings.LLM_PROVIDER == "gemini" else "OPENAI_API_KEY"
        logger.warning("%s is not set in .env - every AI call will fail until it is.", key)
    logger.info("Ready | provider=%s | model=%s", settings.LLM_PROVIDER, settings.LLM_MODEL)
    yield


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jds.router, prefix="/api")
app.include_router(resumes.router, prefix="/api")
app.include_router(assessments.router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "api_key_set": bool(settings.api_key),
    }
