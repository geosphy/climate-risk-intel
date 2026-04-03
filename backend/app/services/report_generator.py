"""
AI narrative generator for Data Center climate risk reports.
"""
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def generate_dc_narrative(report) -> str:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return _fallback_dc_narrative(report)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        disclosures = ", ".join(report.regulatory_compliance.required_disclosures)
        prompt = (
            "You are a climate risk analyst writing an ESRS E1 physical risk assessment "
            "for a data center. Write a concise 3-paragraph report covering: "
            "1) Physical risk summary for " + report.canonical_address + " "
            "Overall risk: " + report.overall_risk_level + ". "
            "Thermal: " + report.thermal_risk.level + ", "
            "Flood: " + report.flood_risk.level + ", "
            "Water: " + report.water_risk.level + ", "
            "Storm: " + report.storm_risk.level + ". "
            "ESRS E1 score: " + str(report.regulatory_compliance.esrs_e1_physical_risk_score) + "/100. "
            "EU Taxonomy: " + report.regulatory_compliance.eu_taxonomy_alignment + ". "
            "Required disclosures: " + disclosures + ". "
            "2) EU regulatory exposure. "
            "3) Recommended adaptation actions."
        )
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.warning("DC narrative generation failed: " + str(e))
        return _fallback_dc_narrative(report)


def _fallback_dc_narrative(report) -> str:
    reg = report.regulatory_compliance
    disclosures = ", ".join(reg.required_disclosures)
    dora_note = "recommended" if reg.dora_ict_risk_flag else "not immediately required"
    para1 = (
        "This data center at " + report.canonical_address + " has an overall climate risk level of "
        + report.overall_risk_level + ". The primary physical hazards are thermal stress ("
        + report.thermal_risk.level + "), flood risk (" + report.flood_risk.level
        + "), and water stress (" + report.water_risk.level + ")."
    )
    para2 = (
        "From an EU regulatory perspective, the ESRS E1 score is "
        + str(reg.esrs_e1_physical_risk_score) + "/100. CSRD materiality: "
        + reg.csrd_materiality + ". EU Taxonomy: " + reg.eu_taxonomy_alignment
        + ". Required disclosures: " + disclosures + "."
    )
    para3 = (
        "Recommended actions include a detailed ESRS E1 physical risk scenario analysis, "
        "implementing a water efficiency plan targeting the EU WUE of 0.4 L/kWh, "
        "and reviewing cooling resilience for 2050 temperature projections. "
        "A DORA ICT continuity review is " + dora_note + "."
    )
    return para1 + chr(10) + chr(10) + para2 + chr(10) + chr(10) + para3