"""
ClimateRisk Intel — FastAPI Application Entry Point
Registers routes, configures CORS, and sets up logging.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes import risk, health, simulate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI-Native Climate Risk Intelligence API. "
        "Enter any address to receive flood, heat, and storm risk scores."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(risk.router, prefix="/api", tags=["Risk Assessment"])
app.include_router(simulate.router, prefix="/api", tags=["Stochastic Simulation"])


@app.on_event("startup")
async def startup_event():
    logger.info(f"🌍 {settings.app_name} v{settings.app_version} starting up")
    logger.info(f"NOAA token: {'✓' if settings.noaa_token else '✗ (add NOAA_TOKEN to .env)'}")
    logger.info(f"Anthropic: {'✓' if settings.anthropic_api_key else '✗ (add ANTHROPIC_API_KEY to .env)'}")
