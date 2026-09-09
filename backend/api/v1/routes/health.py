"""Liveness/readiness check for the API."""

from fastapi import APIRouter, Depends

from backend.core.config import Settings, get_settings

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    """Basic health check used by the frontend shell and deploy checks."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }
