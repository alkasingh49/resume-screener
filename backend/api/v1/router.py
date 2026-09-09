"""Aggregates all v1 route modules."""

from fastapi import APIRouter

from backend.api.v1.routes import assessments, health, jd, resumes, screening

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(jd.router, tags=["job-descriptions"])
api_router.include_router(resumes.router, tags=["resumes"])
api_router.include_router(screening.router, tags=["screening"])
api_router.include_router(assessments.router, tags=["assessments"])
