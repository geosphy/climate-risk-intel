"""
Pydantic data models for ClimateRisk Intel — Data Center Edition.
Structured for CSRD/ESRS E1, EU Taxonomy, and DORA regulatory reporting.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class RiskRequest(BaseModel):
    address: str = Field(..., description="Data center address or coordinates")
    asset_type: Literal["data_center"] = Field(default="data_center")
    dc_tier: Optional[Literal["I", "II", "III", "IV"]] = Field(
        default=None, description="Uptime Institute Tier classification"
    )
    cooling_type: Optional[Literal["air", "liquid", "hybrid", "immersion"]] = Field(
        default="air", description="Primary cooling method"
    )


class ThermalRisk(BaseModel):
    score: float
    level: str
    cooling_degree_days: float = Field(description="Annual CDD base 18°C")
    days_above_35c: float = Field(description="Days per year above 35°C")
    days_above_40c: float = Field(description="Days per year above 40°C")
    avg_summer_temp_c: float
    projected_temp_increase_2050_c: float
    pue_impact_score: float = Field(description="Estimated PUE degradation risk 0-1")
    ashrae_class_required: str
    cooling_cost_risk: str
    confidence: str


class WaterRisk(BaseModel):
    score: float
    level: str
    water_stress_index: float = Field(description="WRI Aqueduct scale 0-5")
    annual_precipitation_mm: float
    wue_target_lkwh: float = Field(default=0.4, description="EU regulatory target L/kWh")
    wue_compliance_status: str
    water_scarcity_2050: str
    regulation_exposure: str = Field(description="EU Delegated Reg 2024/1364 exposure")
    confidence: str


class FloodRisk(BaseModel):
    score: float
    level: str
    zone: str
    details: dict
    confidence: str


class StormRisk(BaseModel):
    score: float
    level: str
    details: dict
    confidence: str


class PowerGridRisk(BaseModel):
    score: float
    level: str
    grid_reliability: float = Field(description="0-1 scale")
    renewable_energy_pct: float
    carbon_intensity_gco2_kwh: float
    climate_outage_risk: str
    confidence: str


class RegulatoryCompliance(BaseModel):
    esrs_e1_physical_risk_score: float = Field(description="0-100 ESRS E1 exposure score")
    csrd_materiality: str
    eu_taxonomy_alignment: str
    wue_regulation_exposure: str
    dora_ict_risk_flag: bool
    required_disclosures: list[str]


class DataCenterRiskReport(BaseModel):
    address: str
    canonical_address: str
    latitude: float
    longitude: float
    country_code: str = ""

    # 6 risk pillars
    thermal_risk: ThermalRisk
    flood_risk: FloodRisk
    water_risk: WaterRisk
    storm_risk: StormRisk
    power_grid_risk: PowerGridRisk
    regulatory_compliance: RegulatoryCompliance

    # Overall
    overall_risk_score: float
    overall_risk_level: str

    # AI narrative
    ai_narrative: str = ""
    data_sources: list[str] = []
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class HazardScore(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    level: Literal["Low", "Medium", "High", "Extreme"]
    confidence: Literal["Low", "Medium", "High"]
    details: dict = Field(default_factory=dict)


class GeocodeResult(BaseModel):
    latitude: float
    longitude: float
    canonical_address: str
    country_code: str = "EU"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    services: dict[str, bool]


def score_to_level(score: float) -> Literal["Low", "Medium", "High", "Extreme"]:
    if score >= 0.85: return "Extreme"
    elif score >= 0.65: return "High"
    elif score >= 0.45: return "Medium"
    else: return "Low"
