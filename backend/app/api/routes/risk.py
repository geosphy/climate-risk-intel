"""
Data Center Climate Risk Assessment Endpoint.
Computes 6 climate risk pillars specific to data center assets.
Routes to European data sources for EU addresses.
Outputs structured KPIs for CSRD/ESRS E1, EU Taxonomy, and DORA reporting.
"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    RiskRequest, DataCenterRiskReport,
    ThermalRisk, WaterRisk, FloodRisk, StormRisk, PowerGridRisk,
    RegulatoryCompliance, HealthResponse, score_to_level
)
from app.services.geocoding import geocode_address
from app.services.geo_router import get_region
from app.services.europe_flood import get_flood_risk_europe
from app.services.open_meteo import (
    get_heat_risk_europe, get_storm_risk_europe, get_climate_projections_europe
)
from app.services.fema import get_flood_risk
from app.services.noaa import get_heat_risk, get_storm_risk
from app.services.world_bank import get_climate_projections
from app.services.datacenter_kpis import (
    compute_thermal_kpis, compute_water_stress_kpis,
    compute_power_grid_kpis, compute_regulatory_kpis
)
from app.services.report_generator import generate_dc_narrative
from app.services.asset_enrichment import (
    get_asset_level_factors,
    apply_asset_level_adjustments,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/risk", response_model=DataCenterRiskReport)
async def assess_datacenter_risk(request: RiskRequest) -> DataCenterRiskReport:
    """
    Assess full climate risk profile for a data center asset.
    Returns 6 risk pillars with EU regulatory compliance KPIs.
    """
    logger.info(f"Data center risk assessment: {request.address}")

    # Geocode
    try:
        geo = await geocode_address(request.address)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Could not locate address: {str(e)}")

    lat, lon = geo.latitude, geo.longitude
    region = get_region(geo.country_code)
    logger.info(f"Location: {geo.canonical_address} | Region: {region}")

    # Fetch base climate data in parallel
    if region == "EUROPE":
        flood_task = asyncio.create_task(get_flood_risk_europe(lat, lon))
        heat_task = asyncio.create_task(get_heat_risk_europe(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk_europe(lat, lon))
        proj_task = asyncio.create_task(get_climate_projections_europe(lat, lon))
    else:
        flood_task = asyncio.create_task(get_flood_risk(lat, lon))
        heat_task = asyncio.create_task(get_heat_risk(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk(lat, lon))
        proj_task = asyncio.create_task(get_climate_projections(lat, lon))

    flood_base, heat_base, storm_base, projections = await asyncio.gather(
        flood_task, heat_task, storm_task, proj_task
    )

    # Fetch asset-level factors (elevation, water proximity, UHI, power grid)
    asset_factors = await get_asset_level_factors(lat, lon)
    logger.info(
        f"Asset factors: elevation={asset_factors.get('elevation_m')}m, "
        f"water={asset_factors.get('water_proximity', {}).get('nearest_water_m')}m, "
        f"UHI={asset_factors.get('urban_heat_island', {}).get('uhi_temp_delta_c')}C"
    )

    # Apply asset-level adjustments to city-level scores
    adj_flood, adj_thermal_score, adj_grid = apply_asset_level_adjustments(
        flood_base.score,
        heat_base.score,
        0.2,  # base grid score before country adjustment
        asset_factors,
    )

    # Extract raw values for DC KPI computation
    avg_max_temp = heat_base.details.get("avg_max_temp_c", 20.0)
    extreme_heat_days = heat_base.details.get("extreme_heat_days_per_year", 0.0)
    temp_increase_2050 = projections.get("temp_increase_c", 1.5)
    annual_precip = storm_base.details.get("annual_precipitation_mm",
                    600 if region == "EUROPE" else 1000)

    # Compute DC-specific KPIs
    # Apply Urban Heat Island delta to local temperature
    uhi = asset_factors.get("urban_heat_island", {})
    uhi_delta = uhi.get("uhi_temp_delta_c", 1.0)
    effective_temp = avg_max_temp + uhi_delta

    thermal_kpis = compute_thermal_kpis(effective_temp, extreme_heat_days, temp_increase_2050, lat)
    water_kpis = compute_water_stress_kpis(annual_precip, extreme_heat_days * 3, lat, lon)
    grid_kpis = compute_power_grid_kpis(geo.country_code, lat)
    # Apply substation proximity modifier
    power_infra = asset_factors.get("power_infrastructure", {})
    grid_kpis.score = min(max(
        round(grid_kpis.score - power_infra.get("grid_reliability_modifier", 0.0), 3), 0.05
    ), 1.0)
    grid_kpis.level = score_to_level(grid_kpis.score)
    reg_kpis = compute_regulatory_kpis(
        thermal_kpis, water_kpis, flood_base.score, storm_base.score, geo.country_code
    )

    # Build typed risk objects
    thermal_risk = ThermalRisk(
        score=thermal_kpis.score,
        level=thermal_kpis.level,
        cooling_degree_days=thermal_kpis.cooling_degree_days,
        days_above_35c=thermal_kpis.days_above_35c,
        days_above_40c=thermal_kpis.days_above_40c,
        avg_summer_temp_c=thermal_kpis.avg_summer_temp_c,
        projected_temp_increase_2050_c=thermal_kpis.projected_temp_increase_2050,
        pue_impact_score=thermal_kpis.pue_impact_score,
        ashrae_class_required=thermal_kpis.ashrae_class_risk,
        cooling_cost_risk=thermal_kpis.cooling_cost_risk,
        confidence=thermal_kpis.confidence,
    )

    water_risk = WaterRisk(
        score=water_kpis.score,
        level=water_kpis.level,
        water_stress_index=water_kpis.water_stress_index,
        annual_precipitation_mm=water_kpis.annual_precipitation_mm,
        wue_target_lkwh=water_kpis.wue_target,
        wue_compliance_status=water_kpis.wue_baseline_risk,
        water_scarcity_2050=water_kpis.water_scarcity_2050,
        regulation_exposure=water_kpis.wue_regulation_exposure,
        confidence=water_kpis.confidence,
    )

    # Merge asset-level water proximity into flood details
    flood_details = {**flood_base.details}
    water_prox = asset_factors.get("water_proximity", {})
    if water_prox.get("nearest_water_m"):
        flood_details["nearest_water_m"] = water_prox["nearest_water_m"]
        flood_details["water_risk_label"] = water_prox.get("risk_label", "")
        flood_details["elevation_m"] = asset_factors.get("elevation_m", "N/A")

    flood_risk = FloodRisk(
        score=adj_flood,
        level=score_to_level(adj_flood),
        zone=str(flood_base.details.get("fema_zone", flood_base.details.get("zone", "Unknown"))),
        details=flood_details,
        confidence=flood_base.confidence,
    )

    storm_risk = StormRisk(
        score=storm_base.score,
        level=storm_base.level,
        details=storm_base.details,
        confidence=storm_base.confidence,
    )

    power_infra = asset_factors.get("power_infrastructure", {})
    power_risk = PowerGridRisk(
        score=grid_kpis.score,
        level=grid_kpis.level,
        grid_reliability=grid_kpis.grid_reliability_score,
        renewable_energy_pct=grid_kpis.renewable_energy_pct,
        carbon_intensity_gco2_kwh=grid_kpis.grid_carbon_intensity_gco2_kwh,
        climate_outage_risk=grid_kpis.climate_outage_risk,
        confidence=grid_kpis.confidence,
    )

    regulatory = RegulatoryCompliance(
        esrs_e1_physical_risk_score=reg_kpis.esrs_e1_physical_risk_score,
        csrd_materiality=reg_kpis.csrd_materiality,
        eu_taxonomy_alignment=reg_kpis.eu_taxonomy_alignment,
        wue_regulation_exposure=reg_kpis.wue_regulation_exposure,
        dora_ict_risk_flag=reg_kpis.dora_ict_flag,
        required_disclosures=reg_kpis.required_disclosures,
    )

    # Overall score — weighted for DC priorities
    scores = {
        "thermal": (thermal_risk.score, 0.28),
        "flood":   (flood_risk.score,   0.22),
        "water":   (water_risk.score,   0.20),
        "storm":   (storm_risk.score,   0.15),
        "grid":    (power_risk.score,   0.15),
    }
    overall_score = round(sum(s * w for s, w in scores.values()), 3)
    overall_level = score_to_level(overall_score)

    # Data sources
    data_sources = ["OpenStreetMap Nominatim", "Open-Meteo / Copernicus ERA5",
                    "JRC Global Surface Water", "World Bank CCKP"]
    if region == "US":
        data_sources = ["OpenStreetMap Nominatim", "FEMA NFHL",
                        "NOAA Climate Data Online", "World Bank CCKP"]

    # Assemble report
    report = DataCenterRiskReport(
        address=request.address,
        canonical_address=geo.canonical_address,
        latitude=lat, longitude=lon,
        country_code=geo.country_code,
        thermal_risk=thermal_risk,
        flood_risk=flood_risk,
        water_risk=water_risk,
        storm_risk=storm_risk,
        power_grid_risk=power_risk,
        regulatory_compliance=regulatory,
        overall_risk_score=overall_score,
        overall_risk_level=overall_level,
        data_sources=data_sources,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )

    # Generate AI narrative
    report.ai_narrative = await generate_dc_narrative(report)

    logger.info(
        f"DC assessment complete [{geo.country_code}]: "
        f"overall={overall_level}, thermal={thermal_risk.level}, "
        f"flood={flood_risk.level}, water={water_risk.level}"
    )
    return report


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    from app.core.config import get_settings
    settings = get_settings()
    return HealthResponse(
        status="ok", version=settings.app_version,
        services={
            "noaa": bool(settings.noaa_token),
            "anthropic": bool(settings.anthropic_api_key),
            "open_meteo": True,
            "jrc_flood": True,
        }
    )
