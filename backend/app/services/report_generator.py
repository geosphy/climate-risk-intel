"""
AI narrative generator for Data Center climate risk reports.
Generates CSRD/ESRS E1-aligned plain English risk summaries using Claude API.
"""
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def generate_dc_narrative(report) -> str:
    """Generate a data center-specific climate risk narrative."""
    settings = get_settings()

    if not settings.anthropic_api_key:
        return _fallback_dc_narrative(report)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        prompt = f"""You are a climate risk analyst writing an ESRS E1-aligned physical risk assessment 
for a data center asset. Write a concise 3-paragraph report.

DATA CENTER LOCATION: {report.canonical_address}
OVERALL RISK: {report.overall_risk_level} (score: {report.overall_risk_score:.2f}/1.0)

CLIMATE RISK PILLARS:
- Thermal/Heat Risk: {report.thermal_risk.level} — Avg summer temp: {report.thermal_risk.avg_summer_temp_c}°C, Days >35°C/yr: {report.thermal_risk.days_above_35c}, ASHRAE: {report.thermal_risk.ashrae_class_required}
- Flood Risk: {report.flood_risk.level} — Zone: {report.flood_risk.zone}
- Water Stress: {report.water_risk.level} — WRI Index: {report.water_risk.water_stress_index}/5, WUE status: {report.water_risk.wue_compliance_status}
- Storm/Wind Risk: {report.storm_risk.level}
- Power Grid: {report.power_grid_risk.level} — Renewables: {report.power_grid_risk.renewable_energy_pct}%, Carbon: {report.power_grid_risk.carbon_intensity_gco2_kwh} gCO2/kWh

EU REGULATORY STATUS:
- ESRS E1 Score: {report.regulatory_compliance.esrs_e1_physical_risk_score}/100
- CSRD Materiality: {report.regulatory_compliance.csrd_materiality}
- EU Taxonomy: {report.regulatory_compliance.eu_taxonomy_alignment}
- Required disclosures: {", ".join(report.regulatory_compliance.required_disclosures)}

Write exactly 3 paragraphs:
1. Physical risk summary: Key climate hazards and their operational implications for this data center.
2. EU regulatory exposure: CSRD/ESRS E1 materiality, EU Taxonomy alignment, and WUE regulation requirements.
3. Recommended actions: Specific adaptation and compliance measures the operator should prioritize.

Be specific, technical, and actionable. Use precise KPI values from the data above."""

        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()

    except Exception as e:
        logger.warning(f"DC narrative generation failed: {e}")
        return _fallback_dc_narrative(report)


def _fallback_dc_narrative(report) -> str:
    reg = report.regulatory_compliance
    return (
        f"This data center at {report.canonical_address} has been assessed with an overall "
        f"climate risk level of {report.overall_risk_level}. The primary physical hazards are "
        f"thermal stress ({report.thermal_risk.level}), flood risk ({report.flood_risk.level}), "
        f"and water stress ({report.water_risk.level}), which together impact cooling efficiency, "
        f"operational continuity, and water consumption compliance.\n\n"
        f"From an EU regulatory perspective, the ESRS E1 physical risk exposure score is "
        f"{reg.esrs_e1_physical_risk_score}/100, with a CSRD materiality assessment of "
        f"\"{reg.csrd_materiality}\". EU Taxonomy alignment is classified as "
        f"\"{reg.eu_taxonomy_alignment}\". The following disclosures are required: "
        f"{\', \'.join(reg.required_disclosures)}.\n\n"
        f"Recommended actions include conducting a detailed ESRS E1 physical risk scenario "
        f"analysis, implementing a water efficiency plan to meet the EU WUE target of 0.4 L/kWh, "
        f"and reviewing cooling system resilience for projected temperature increases by 2050. "
        f"A DORA ICT continuity review is {'recommended' if reg.dora_ict_risk_flag else 'not immediately required'} "
        f"based on current flood and thermal risk levels."
    )
