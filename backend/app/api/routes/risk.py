"""
Data Center Climate Risk Assessment Endpoint.
Computes 6 climate risk pillars with asset-level granularity.
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
from app.services.asset_enrichment import (
    get_asset_level_factors, apply_asset_level_adjustments
)
from app.services.report_generator import generate_dc_narrative

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/risk", response_model=DataCenterRiskReport)
async def assess_datacenter_risk(request: RiskRequest) -> DataCenterRiskReport:
    logger.info(f"DC risk assessment: {request.address}")

    # Step 1: Geocode
    try:
        geo = await geocode_address(request.address)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Could not locate address: {str(e)}")

    lat, lon = geo.latitude, geo.longitude
    region = get_region(geo.country_code)
    logger.info(f"Location: {geo.canonical_address} | {lat},{lon} | Region: {region}")

    # Step 2: Fetch city-level climate + asset-level factors in parallel
    if region == "EUROPE":
        flood_task = asyncio.create_task(get_flood_risk_europe(lat, lon))
        heat_task  = asyncio.create_task(get_heat_risk_europe(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk_europe(lat, lon))
        proj_task  = asyncio.create_task(get_climate_projections_europe(lat, lon))
    else:
        flood_task = asyncio.create_task(get_flood_risk(lat, lon))
        heat_task  = asyncio.create_task(get_heat_risk(lat, lon))
        storm_task = asyncio.create_task(get_storm_risk(lat, lon))
        proj_task  = asyncio.create_task(get_climate_projections(lat, lon))

    asset_task = asyncio.create_task(get_asset_level_factors(lat, lon))

    flood_base, heat_base, storm_base, projections, asset_factors = await asyncio.gather(
        flood_task, heat_task, storm_task, proj_task, asset_task
    )

    # Step 3: Log asset factors for debugging
    water_prox = asset_factors.get("water_proximity", {})
    uhi        = asset_factors.get("urban_heat_island", {})
    elev       = asset_factors.get("elevation_m", 10.0)
    power_infra = asset_factors.get("power_infrastructure", {})

    logger.info(
        f"Asset factors — elevation: {elev}m, "
        f"water: {water_prox.get('nearest_water_m')}m, "
        f"UHI: +{uhi.get('uhi_temp_delta_c')}C, "
        f"flood_modifier: +{water_prox.get('flood_modifier', 0)}"
    )

    # Step 4: Apply asset-level adjustments to city-level scores
    adj_flood_score, _, adj_grid_delta = apply_asset_level_adjustments(
        flood_base.score, heat_base.score, 0.0, asset_factors
    )

    # Step 5: Apply UHI to local effective temperature
    uhi_delta = uhi.get("uhi_temp_delta_c", 1.0)
    avg_max_temp     = heat_base.details.get("avg_max_temp_c", 20.0) + uhi_delta
    extreme_heat_days = heat_base.details.get("extreme_heat_days_per_year", 0.0)
    temp_increase_2050 = projections.get("temp_increase_c", 1.5)
    annual_precip    = storm_base.details.get("annual_precipitation_mm", 600.0)

    logger.info(
        f"Adjusted values — flood_score: {adj_flood_score} (base: {flood_base.score}), "
        f"effective_temp: {avg_max_temp}C (base: {heat_base.details.get('avg_max_temp_c')}C + UHI {uhi_delta}C)"
    )

    # Step 6: Compute DC-specific KPIs using adjusted values
    thermal_kpis = compute_thermal_kpis(avg_max_temp, extreme_heat_days, temp_increase_2050, lat)
    water_kpis   = compute_water_stress_kpis(annual_precip, extreme_heat_days * 3, lat, lon)
    grid_kpis    = compute_power_grid_kpis(geo.country_code, lat)

    # Apply substation proximity modifier to grid score
    grid_mod = power_infra.get("grid_reliability_modifier", 0.0)
    grid_kpis.score = round(min(max(grid_kpis.score - grid_mod, 0.05), 1.0), 3)
    grid_kpis.level = score_to_level(grid_kpis.score)

    reg_kpis = compute_regulatory_kpis(
        thermal_kpis, water_kpis, adj_flood_score, storm_base.score, geo.country_code
    )

    # Step 7: Build flood details with asset-level context
    flood_details = {**flood_base.details}
    flood_details["elevation_m"]       = elev
    flood_details["nearest_water_m"]   = water_prox.get("nearest_water_m", "N/A")
    flood_details["water_risk_label"]  = water_prox.get("risk_label", "No data")
    flood_details["flood_modifier_applied"] = water_prox.get("flood_modifier", 0.0)

    # Step 8: Assemble typed risk objects
    thermal_risk = ThermalRisk(
        score=thermal_kpis.score,
        level=thermal_kpis.level,
        cooling_degree_days=thermal_kpis.cooling_degree_days,
        days_above_35c=thermal_kpis.days_above_35c,
        days_above_40c=thermal_kpis.days_above_40c,
        avg_summer_temp_c=round(avg_max_temp, 1),
        projected_temp_increase_2050_c=temp_increase_2050,
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

    flood_risk = FloodRisk(
        score=adj_flood_score,
        level=score_to_level(adj_flood_score),
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
        dora_ict_risk_flag=reg_kpis.dora_ict_risk_flag,
        required_disclosures=reg_kpis.required_disclosures,
    )

    # Step 9: Overall score — weighted for DC priorities
    overall_score = round(
        thermal_risk.score  * 0.28 +
        flood_risk.score    * 0.22 +
        water_risk.score    * 0.20 +
        storm_risk.score    * 0.15 +
        power_risk.score    * 0.15,
        3
    )

    # Step 10: Assemble final report
    data_sources = (
        ["OpenStreetMap Nominatim", "Open-Meteo ERA5", "JRC Global Surface Water",
         "World Bank CCKP", "OSM Overpass (elevation/water/UHI)"]
        if region == "EUROPE"
        else ["OpenStreetMap Nominatim", "FEMA NFHL", "NOAA CDO", "World Bank CCKP"]
    )

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
        overall_risk_level=score_to_level(overall_score),
        data_sources=data_sources,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )

    report.ai_narrative = await generate_dc_narrative(report)
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
            "asset_enrichment": True,
        }
    )
