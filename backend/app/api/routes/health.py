"""Health check endpoint."""
from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.core.config import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Returns service health status and version info."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        services={
            "noaa": bool(settings.noaa_token),
            "anthropic": bool(settings.anthropic_api_key),
            "prithvi": settings.enable_prithvi,
            "climada": settings.enable_climada,
        }
    )
