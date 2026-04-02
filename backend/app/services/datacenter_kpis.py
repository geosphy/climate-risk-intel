"""
Data Center Climate Risk KPI Engine.
Computes the 6 risk pillars specific to data center assets in Europe.
Maps to EU regulatory requirements: CSRD/ESRS E1, EU Taxonomy, 
EU Delegated Regulation 2024/1364 (WUE), DORA.
"""
import logging
from dataclasses import dataclass, field
from app.models.schemas import score_to_level

logger = logging.getLogger(__name__)


@dataclass
class ThermalRiskKPIs:
    """Thermal/Heat stress KPIs for data center cooling systems."""
    cooling_degree_days: float = 0.0          # CDD annual (base 18°C)
    days_above_35c: float = 0.0               # Days per year above 35°C
    days_above_40c: float = 0.0               # Days per year above 40°C (critical threshold)
    avg_summer_temp_c: float = 0.0            # Mean June-Aug temperature
    projected_temp_increase_2050: float = 0.0 # °C increase by 2050 vs baseline
    pue_impact_score: float = 0.0             # Estimated PUE degradation (0-1)
    cooling_cost_risk: str = "Low"            # Low/Medium/High/Extreme
    ashrae_class_risk: str = "A1"             # ASHRAE climate class at location
    score: float = 0.0
    level: str = "Low"
    confidence: str = "Medium"


@dataclass  
class WaterStressKPIs:
    """Water stress KPIs — mapped to EU Delegated Regulation 2024/1364."""
    water_stress_index: float = 0.0           # WRI Aqueduct 0-5 scale
    drought_frequency_per_decade: float = 0.0 # Historical drought events
    annual_precipitation_mm: float = 0.0      # Annual rainfall
    wue_target: float = 0.4                   # EU target L/kWh (Reg 2024/1364)
    wue_baseline_risk: str = "Compliant"      # Compliant/At Risk/Non-Compliant
    water_scarcity_2050: str = "Low"          # Projected scarcity by 2050
    score: float = 0.0
    level: str = "Low"
    confidence: str = "Medium"


@dataclass
class PowerGridKPIs:
    """Power grid resilience KPIs for data center continuity."""
    grid_reliability_score: float = 0.0       # 0-1 (1 = most reliable)
    renewable_energy_pct: float = 0.0         # % renewables in local grid
    grid_carbon_intensity_gco2_kwh: float = 0.0  # gCO2/kWh of local grid
    climate_outage_risk: str = "Low"          # Risk of climate-driven outages
    score: float = 0.0
    level: str = "Low"
    confidence: str = "Low"


@dataclass
class RegulatoryComplianceKPIs:
    """EU regulatory compliance KPIs for data center operators."""
    esrs_e1_physical_risk_score: float = 0.0  # 0-100 ESRS E1 exposure score
    eu_taxonomy_alignment: str = "Unknown"    # Aligned/Partially/Not Aligned
    csrd_materiality: str = "Material"        # Material/Potentially Material/Immaterial
    dora_ict_risk_flag: bool = False          # ICT continuity risk flag
    wue_regulation_exposure: str = "Low"      # Exposure to EU WUE regulation
    required_disclosures: list = field(default_factory=list)


@dataclass
class DataCenterRiskReport:
    """
    Complete climate risk profile for a data center asset.
    Structured for CSRD/ESRS E1, EU Taxonomy, and DORA reporting.
    """
    # Location
    address: str = ""
    canonical_address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    country: str = ""
    region: str = ""

    # 6 Risk Pillars
    thermal_risk: ThermalRiskKPIs = field(default_factory=ThermalRiskKPIs)
    flood_risk_score: float = 0.0
    flood_risk_level: str = "Low"
    flood_risk_details: dict = field(default_factory=dict)
    water_stress: WaterStressKPIs = field(default_factory=WaterStressKPIs)
    storm_risk_score: float = 0.0
    storm_risk_level: str = "Low"
    storm_risk_details: dict = field(default_factory=dict)
    power_grid: PowerGridKPIs = field(default_factory=PowerGridKPIs)
    regulatory: RegulatoryComplianceKPIs = field(default_factory=RegulatoryComplianceKPIs)

    # Overall
    overall_risk_score: float = 0.0
    overall_risk_level: str = "Low"

    # AI narrative
    ai_narrative: str = ""
    data_sources: list = field(default_factory=list)
    generated_at: str = ""


def compute_thermal_kpis(
    avg_max_temp: float,
    extreme_heat_days: float,
    temp_increase_2050: float,
    lat: float
) -> ThermalRiskKPIs:
    """
    Compute thermal stress KPIs for a data center at the given location.
    
    Critical thresholds for data centers:
    - ASHRAE A1 class: max 27°C inlet temp (typical EU DC)
    - Cooling failure risk: ambient >40°C
    - Economic impact: each 1°C above 20°C increases PUE by ~0.01
    """
    kpis = ThermalRiskKPIs()

    # Cooling Degree Days (base 18°C — EU standard)
    # Rough estimate from avg max temp
    kpis.avg_summer_temp_c = avg_max_temp
    kpis.cooling_degree_days = max(0, (avg_max_temp - 18) * 120)  # ~120 summer days
    kpis.days_above_35c = extreme_heat_days
    kpis.days_above_40c = max(0, extreme_heat_days * 0.1)  # ~10% of 35°C days reach 40°C
    kpis.projected_temp_increase_2050 = temp_increase_2050

    # PUE impact score — how much will cooling degrade
    # Rule of thumb: +1°C ambient → +0.01 PUE degradation
    pue_degradation = (max(0, avg_max_temp - 20) * 0.01) + (temp_increase_2050 * 0.01)
    kpis.pue_impact_score = min(pue_degradation / 0.3, 1.0)  # 0.3 PUE degradation = max risk

    # ASHRAE class risk
    if avg_max_temp >= 35:
        kpis.ashrae_class_risk = "A3/A4 required"
    elif avg_max_temp >= 30:
        kpis.ashrae_class_risk = "A2 required"
    else:
        kpis.ashrae_class_risk = "A1 suitable"

    # Cooling cost risk
    if extreme_heat_days >= 30 or avg_max_temp >= 35:
        kpis.cooling_cost_risk = "Extreme"
        kpis.score = 0.88
    elif extreme_heat_days >= 15 or avg_max_temp >= 30:
        kpis.cooling_cost_risk = "High"
        kpis.score = 0.68
    elif extreme_heat_days >= 5 or avg_max_temp >= 25:
        kpis.cooling_cost_risk = "Medium"
        kpis.score = 0.45
    else:
        kpis.cooling_cost_risk = "Low"
        kpis.score = 0.22

    # Climate projection adjustment
    kpis.score = min(kpis.score + (temp_increase_2050 * 0.06), 1.0)
    kpis.score = round(kpis.score, 3)
    kpis.level = score_to_level(kpis.score)
    kpis.confidence = "High"

    return kpis


def compute_water_stress_kpis(
    annual_precipitation_mm: float,
    drought_days: float,
    lat: float,
    lon: float
) -> WaterStressKPIs:
    """
    Compute water stress KPIs mapped to EU Delegated Regulation 2024/1364.
    EU WUE target: 0.4 L/kWh for new data centers in water-stressed areas.
    """
    kpis = WaterStressKPIs()
    kpis.annual_precipitation_mm = annual_precipitation_mm
    kpis.drought_frequency_per_decade = drought_days / 10

    # Water stress index (simplified WRI Aqueduct proxy)
    # Southern Europe / Mediterranean = higher water stress
    if lat <= 40 and lon >= -5:  # Southern Europe
        kpis.water_stress_index = 3.8
        kpis.water_scarcity_2050 = "High"
        kpis.score = 0.72
    elif lat <= 44:  # Central Mediterranean
        kpis.water_stress_index = 2.5
        kpis.water_scarcity_2050 = "Medium"
        kpis.score = 0.52
    elif lat <= 52:  # Central Europe
        kpis.water_stress_index = 1.8
        kpis.water_scarcity_2050 = "Low-Medium"
        kpis.score = 0.32
    else:  # Nordics — low water stress
        kpis.water_stress_index = 0.8
        kpis.water_scarcity_2050 = "Low"
        kpis.score = 0.15

    # WUE regulation exposure
    if kpis.water_stress_index >= 3.0:
        kpis.wue_baseline_risk = "Non-Compliant Risk"
        kpis.wue_regulation_exposure = "High"
    elif kpis.water_stress_index >= 2.0:
        kpis.wue_baseline_risk = "At Risk"
        kpis.wue_regulation_exposure = "Medium"
    else:
        kpis.wue_baseline_risk = "Likely Compliant"
        kpis.wue_regulation_exposure = "Low"

    # Adjust for precipitation
    if annual_precipitation_mm < 400:
        kpis.score = min(kpis.score + 0.15, 1.0)
    elif annual_precipitation_mm > 800:
        kpis.score = max(kpis.score - 0.08, 0.0)

    kpis.score = round(kpis.score, 3)
    kpis.level = score_to_level(kpis.score)
    kpis.confidence = "Medium"

    return kpis


def compute_power_grid_kpis(country_code: str, lat: float) -> PowerGridKPIs:
    """
    Compute power grid resilience KPIs.
    Based on known European grid reliability data and renewable energy mix.
    """
    kpis = PowerGridKPIs()

    # European grid reliability and renewables data (2024 values)
    GRID_DATA = {
        # country: (reliability_0_to_1, renewables_pct, carbon_intensity_gco2_kwh)
        "NO": (0.98, 98, 26),    # Norway — almost all hydro
        "SE": (0.97, 95, 13),    # Sweden — hydro + nuclear
        "FI": (0.96, 85, 72),    # Finland
        "AT": (0.95, 82, 132),   # Austria
        "DK": (0.96, 88, 134),   # Denmark — wind leader
        "CH": (0.99, 92, 28),    # Switzerland
        "DE": (0.97, 65, 380),   # Germany
        "NL": (0.97, 52, 295),   # Netherlands
        "FR": (0.96, 58, 56),    # France — nuclear-heavy
        "BE": (0.96, 42, 145),   # Belgium
        "IE": (0.94, 68, 310),   # Ireland
        "GB": (0.96, 58, 178),   # UK
        "ES": (0.95, 62, 163),   # Spain
        "PT": (0.94, 72, 174),   # Portugal
        "IT": (0.93, 48, 283),   # Italy
        "PL": (0.92, 35, 635),   # Poland — coal-heavy
        "CZ": (0.94, 22, 425),   # Czech Republic
        "HU": (0.93, 45, 238),   # Hungary
        "RO": (0.90, 55, 295),   # Romania
        "GR": (0.88, 48, 358),   # Greece
    }

    grid = GRID_DATA.get(country_code.upper(), (0.90, 40, 400))
    kpis.grid_reliability_score = grid[0]
    kpis.renewable_energy_pct = grid[1]
    kpis.grid_carbon_intensity_gco2_kwh = grid[2]

    # Climate outage risk — higher in storm-prone or extreme heat areas
    if lat <= 42:   # Southern Europe — heat-driven grid stress
        kpis.climate_outage_risk = "Medium"
        kpis.score = 1 - grid[0] + 0.10
    elif kpis.renewable_energy_pct < 30:  # Coal-heavy grids less resilient
        kpis.climate_outage_risk = "Medium"
        kpis.score = 1 - grid[0] + 0.05
    else:
        kpis.climate_outage_risk = "Low"
        kpis.score = 1 - grid[0]

    kpis.score = round(min(max(kpis.score, 0.05), 1.0), 3)
    kpis.level = score_to_level(kpis.score)
    kpis.confidence = "Medium"

    return kpis


def compute_regulatory_kpis(
    thermal: ThermalRiskKPIs,
    water: WaterStressKPIs,
    flood_score: float,
    storm_score: float,
    country_code: str
) -> RegulatoryComplianceKPIs:
    """
    Compute EU regulatory compliance KPIs for CSRD/ESRS E1, EU Taxonomy, DORA.
    """
    reg = RegulatoryComplianceKPIs()

    # ESRS E1 Physical Risk Score (0-100)
    # Weighted average of all physical hazards
    esrs_score = (
        thermal.score * 0.30 +
        flood_score * 0.25 +
        water.score * 0.20 +
        storm_score * 0.15 +
        (1 - 0.9) * 0.10  # power grid proxy
    ) * 100
    reg.esrs_e1_physical_risk_score = round(esrs_score, 1)

    # CSRD Materiality
    if esrs_score >= 60:
        reg.csrd_materiality = "Material — full ESRS E1 disclosure required"
    elif esrs_score >= 35:
        reg.csrd_materiality = "Potentially Material — assessment recommended"
    else:
        reg.csrd_materiality = "Lower materiality — monitor annually"

    # EU Taxonomy alignment
    if thermal.score <= 0.45 and flood_score <= 0.45 and water.score <= 0.35:
        reg.eu_taxonomy_alignment = "Likely Aligned"
    elif thermal.score >= 0.85 or flood_score >= 0.85:
        reg.eu_taxonomy_alignment = "Requires adaptation measures"
    else:
        reg.eu_taxonomy_alignment = "Partially Aligned — adaptation plan needed"

    # WUE Regulation Exposure
    reg.wue_regulation_exposure = water.wue_regulation_exposure

    # DORA ICT risk flag
    reg.dora_ict_flag = flood_score >= 0.65 or thermal.score >= 0.65

    # Required disclosures
    disclosures = ["CSRD/ESRS E1 Physical Risk Assessment"]
    if country_code.upper() in {"DE", "FR", "NL", "IT", "ES", "PL", "BE", "SE"}:
        disclosures.append("EU Taxonomy CapEx/OpEx KPI Reporting")
    if water.water_stress_index >= 2.0:
        disclosures.append("EU Delegated Regulation 2024/1364 (WUE Reporting)")
    if reg.dora_ict_flag:
        disclosures.append("DORA ICT Continuity Risk Documentation")
    reg.required_disclosures = disclosures

    return reg
