"""
Climate risk assessment API endpoint.
Orchestrates all data services in parallel and returns a unified risk report.
Automatically routes to US (FEMA/NOAA) or European (JRC/Open-Meteo) data sources.
"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.models.schemas import RiskRequest, RiskReport, HazardScore, score_to_level
from app.services.geocoding import geocode_address
from app.services.geo_router import get_region, get_data_sources_for_region

# US data services
from app.services.fema import get_flood_risk
from app.services.noaa import get_heat_risk, get_storm_risk

# European data services
from app.services.europe_flood import get_flood_risk_europe
from app.services.open_meteo import (
    get_heat_risk_europe,
    get_storm_risk_europe,
    get_climate_projections_europe,
)

# Global services
from app.services.world_bank import (
    get_climate_projections,
    adjust_flood_score_for_climate,
    adjust_heat_score_for_climate,
)
from app.services.report_generator import generate_narrative

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/risk", response_model=RiskReport)
async def assess_climate_risk(request: RiskRequest) -> RiskReport:
    """
    Assess climate risk for a physical asset at the given address.
    Automatically uses US or European data sources based on location.
    """
    logger.info(f"Risk assessment requested for: {request.address}")

    # Step 1: Geocode the address
    try:
        geo = await geocode_address(request.address)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Could not locate address: {str(e)}")

    lat, lon = geo.latitude, geo.longitude
    region = get_region(geo.country_code)
    logger.info(f"Geocoded to: {lat}, {lon} — {geo.canonical_address} — Region: {region}")

    # Step 2: Fetch hazard data in parallel based on region
    if region == "EUROPE":
        flood_task = asyncio.create_task(get_flood_risk_europe(lat, lon))
        heat_task = asyncio.create_task(get_heat_risk_europe(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk_europe(lat, lon))
        projections_task = asyncio.create_task(get_climate_projections_europe(lat, lon))
    elif region == "US":
        flood_task = asyncio.create_task(get_flood_risk(lat, lon))
        heat_task = asyncio.create_task(get_heat_risk(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk(lat, lon))
        projections_task = asyncio.create_task(get_climate_projections(lat, lon))
    else:
        # Global fallback: Open-Meteo works worldwide, World Bank for projections
        flood_task = asyncio.create_task(get_flood_risk_europe(lat, lon))
        heat_task = asyncio.create_task(get_heat_risk_europe(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk_europe(lat, lon))
        projections_task = asyncio.create_task(get_climate_projections(lat, lon))

    flood_risk, heat_risk, storm_risk, projections = await asyncio.gather(
        flood_task, heat_task, storm_task, projections_task
    )

    # Step 3: Apply climate projection adjustments
    adjusted_flood_score = adjust_flood_score_for_climate(flood_risk.score, projections)
    if adjusted_flood_score != flood_risk.score:
        flood_risk = HazardScore(
            score=round(adjusted_flood_score, 3),
            level=score_to_level(adjusted_flood_score),
            confidence=flood_risk.confidence,
            details={**flood_risk.details, "climate_adjustment": round(adjusted_flood_score - flood_risk.score, 3)}
        )

    adjusted_heat_score = adjust_heat_score_for_climate(heat_risk.score, projections)
    if adjusted_heat_score != heat_risk.score:
        heat_risk = HazardScore(
            score=round(adjusted_heat_score, 3),
            level=score_to_level(adjusted_heat_score),
            confidence=heat_risk.confidence,
            details={**heat_risk.details, "climate_adjustment": round(adjusted_heat_score - heat_risk.score, 3)}
        )

    # Step 4: Compute overall risk score
    scores = [flood_risk.score, heat_risk.score, storm_risk.score]
    overall_score = round(max(scores) * 0.5 + (sum(scores) / len(scores)) * 0.5, 3)
    overall_risk = HazardScore(
        score=overall_score,
        level=score_to_level(overall_score),
        confidence="Medium",
        details={"region": region, "computation": "max*0.5 + mean*0.5"}
    )

    # Step 5: Assemble report
    data_sources = get_data_sources_for_region(region)
    partial_report = RiskReport(
        address=request.address,
        canonical_address=geo.canonical_address,
        latitude=lat,
        longitude=lon,
        flood_risk=flood_risk,
        heat_risk=heat_risk,
        storm_risk=storm_risk,
        overall_risk=overall_risk,
        data_sources=data_sources,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )

    # Step 6: Generate AI narrative
    partial_report.ai_narrative = await generate_narrative(partial_report)

    logger.info(
        f"Assessment complete [{region}] {geo.canonical_address}: "
        f"overall={overall_risk.level}, flood={flood_risk.level}, "
        f"heat={heat_risk.level}, storm={storm_risk.level}"
    )
    return partial_report
