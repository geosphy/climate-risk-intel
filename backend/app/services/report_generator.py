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

    Uses the async Anthropic client so the FastAPI event loop is never blocked.
    Falls back to a template-based narrative if the API key is absent or the
    call fails.

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
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        message = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=600,
            messages=[{"role": "user", "content": _build_prompt(report)}],
        )

        return message.content[0].text.strip()

    except Exception as e:
        logger.warning(f"Claude API narrative generation failed: {e}")
        return _fallback_narrative(report)


def _build_prompt(report: RiskReport) -> str:
    """Build the Claude prompt from structured risk data."""
    flood  = report.flood_risk
    heat   = report.heat_risk
    storm  = report.storm_risk
    overall = report.overall_risk

    fema_zone       = flood.details.get("fema_zone", "Unknown")
    fema_zone_desc  = flood.details.get("fema_zone_description", "")
    sfha            = flood.details.get("sfha", False)

    avg_max_temp_c      = heat.details.get("avg_max_temp_c", "N/A")
    extreme_heat_days   = heat.details.get("extreme_heat_days_per_yr", "N/A")

    avg_wind_ms         = storm.details.get("avg_wind_speed_ms", "N/A")
    hurricane_coast     = storm.details.get("hurricane_coast", False)
    severe_wind_days    = storm.details.get("severe_wind_days_per_yr", "N/A")

    sfha_note = "Yes — mandatory flood insurance zone" if sfha else "No"

    return f"""You are a climate risk analyst writing a report for a property owner.
Write a concise 3-paragraph plain English climate risk assessment for this asset.

LOCATION: {report.canonical_address}
ASSET TYPE: Building

RISK SCORES (0.0 = no risk, 1.0 = extreme risk):
- Overall Risk:         {overall.level} ({overall.score:.2f})
- Flood & Sea Level:    {flood.level} ({flood.score:.2f})
    FEMA Zone:          {fema_zone} — {fema_zone_desc}
    In SFHA:            {sfha_note}
- Extreme Heat:         {heat.level} ({heat.score:.2f})
    Avg annual max temp: {avg_max_temp_c}°C
    Extreme-heat days/yr (≥35°C): {extreme_heat_days}
- Storm & Wind:         {storm.level} ({storm.score:.2f})
    Avg wind speed:     {avg_wind_ms} m/s
    Severe wind days/yr: {severe_wind_days}
    Hurricane coast:    {hurricane_coast}

Write exactly 3 paragraphs:
1. Overall risk summary (2-3 sentences): Summarise the overall climate risk profile of this asset.
2. Key hazard details (3-4 sentences): Describe the most significant hazards and their specific implications for the property.
3. Recommended actions (2-3 sentences): Provide practical, actionable steps the asset owner can take to reduce risk and improve resilience.

Keep language clear and accessible to a non-expert reader. Avoid jargon. Be specific to this location. Do not use bullet points or headers."""


def _fallback_narrative(report: RiskReport) -> str:
    """Generate a basic template narrative when the Claude API is unavailable."""
    overall = report.overall_risk
    flood   = report.flood_risk
    heat    = report.heat_risk
    storm   = report.storm_risk

    fema_zone = flood.details.get("fema_zone", "Unknown")
    sfha      = flood.details.get("sfha", False)
    sfha_note = " This property falls within FEMA's Special Flood Hazard Area, meaning federally-backed mortgages require flood insurance." if sfha else ""

    return (
        f"This property at {report.canonical_address} has been assessed with an overall "
        f"climate risk level of {overall.level} (score: {overall.score:.2f}). "
        f"The assessment draws on FEMA flood maps, NOAA historical climate records, and "
        f"World Bank SSP2-4.5 climate projections for 2040–2059.\n\n"
        f"The three primary hazards are: flood risk ({flood.level}, FEMA Zone {fema_zone}){sfha_note}, "
        f"extreme heat risk ({heat.level}), and storm and wind risk ({storm.level}). "
        f"Climate change is expected to intensify all three hazards over the coming decades, "
        f"increasing both the frequency and severity of extreme events at this location.\n\n"
        f"Asset owners should review flood insurance requirements with their lender or insurer, "
        f"consider heat-resilience upgrades such as improved insulation and cooling systems, "
        f"and ensure the building envelope meets current wind-resistance standards. "
        f"A professional climate risk assessment is recommended for detailed, site-specific mitigation planning."
    )
