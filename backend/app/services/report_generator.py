"""
AI narrative report generator using the Claude API.
Converts structured risk scores into plain English risk reports.
Requires ANTHROPIC_API_KEY environment variable.
"""
import logging
from app.models.schemas import RiskReport
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def generate_narrative(report: RiskReport) -> str:
    """
    Generate an AI-written risk narrative using Claude.

    Args:
        report: Partially assembled RiskReport (without narrative)

    Returns:
        Plain English 3-paragraph risk narrative string
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI narrative")
        return _fallback_narrative(report)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        prompt = _build_prompt(report)

        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )

        return message.content[0].text.strip()

    except Exception as e:
        logger.warning(f"Claude API narrative generation failed: {e}")
        return _fallback_narrative(report)


def _build_prompt(report: RiskReport) -> str:
    """Build the Claude prompt from structured risk data."""
    flood = report.flood_risk
    heat = report.heat_risk
    storm = report.storm_risk
    overall = report.overall_risk

    fema_zone = flood.details.get("fema_zone", "Unknown")
    avg_temp = heat.details.get("avg_max_temp_c", "N/A")
    hurricane_coast = storm.details.get("hurricane_coast", False)

    return f"""You are a climate risk analyst writing a report for a property owner.
Write a concise 3-paragraph plain English climate risk assessment for this asset.

LOCATION: {report.canonical_address}
ASSET TYPE: Building

RISK SCORES:
- Overall Risk: {overall.level} (score: {overall.score:.2f})
- Flood & Sea Level Rise: {flood.level} (score: {flood.score:.2f}, FEMA Zone: {fema_zone})
- Extreme Heat: {heat.level} (score: {heat.score:.2f}, avg max temp: {avg_temp}°C)
- Storm & Wind: {storm.level} (score: {storm.score:.2f}, hurricane coast: {hurricane_coast})

Write exactly 3 paragraphs:
1. Overall risk summary (2-3 sentences): Summarize the overall climate risk profile of this asset.
2. Key hazard details (3-4 sentences): Describe the most significant hazards and their specific implications.
3. Recommended actions (2-3 sentences): Provide practical, actionable steps the asset owner can take.

Keep language clear and accessible. Avoid jargon. Be specific to this location. Do not use bullet points."""


def _fallback_narrative(report: RiskReport) -> str:
    """Generate a basic template narrative when AI is unavailable."""
    overall = report.overall_risk
    flood = report.flood_risk
    heat = report.heat_risk
    storm = report.storm_risk

    return (
        f"This property at {report.canonical_address} has been assessed with an overall "
        f"climate risk level of {overall.level}. The assessment is based on multiple data "
        f"sources including FEMA flood maps, NOAA historical climate records, and World Bank "
        f"climate projections.\n\n"
        f"The primary hazards identified are: Flood risk ({flood.level}), "
        f"Extreme heat risk ({heat.level}), and Storm and wind risk ({storm.level}). "
        f"These risks are expected to intensify over the coming decades due to climate change.\n\n"
        f"Asset owners should consult with local authorities about flood insurance requirements, "
        f"consider heat resilience upgrades, and review storm preparedness plans. "
        f"A professional climate risk assessment is recommended for detailed mitigation planning."
    )
