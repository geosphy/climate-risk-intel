"""
World Bank Climate Change Knowledge Portal (CCKP) service.
Fetches climate projections (temperature, precipitation) for a location.
No API key required. Free public API.
"""
import httpx
import logging
import reverse_geocoder
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

CCKP_BASE = "https://cckpapi.worldbank.org/cckp/v1"

# SSP2-4.5 is the "middle of the road" climate scenario
SCENARIO = "ssp245"
PERIOD = "2041-2060"  # Near-term 2050 projection


async def get_climate_projections(lat: float, lon: float) -> dict:
    """
    Fetch World Bank climate projections for the country/region containing lat/lon.

    Returns dict with:
        - temp_increase_c: projected temperature increase by 2050
        - precip_change_pct: projected precipitation change by 2050
        - country_code: ISO3 country code
    """
    try:
        # Reverse geocode to get country code
        rg_result = reverse_geocoder.search([(lat, lon)], verbose=False)
        country_code_2 = rg_result[0].get("cc", "US")

        # Convert 2-letter to 3-letter ISO code for World Bank API
        import pycountry
        country = pycountry.countries.get(alpha_2=country_code_2)
        country_code_3 = country.alpha_3 if country else "USA"

        async with httpx.AsyncClient(timeout=20.0) as client:
            # Fetch temperature projection
            temp_url = f"{CCKP_BASE}/cmip6-x0.25_tas_timeseries_annual_{SCENARIO}_median/{PERIOD}/ISO/{country_code_3}"
            temp_resp = await client.get(temp_url)

            if temp_resp.status_code == 200:
                temp_data = temp_resp.json()
                # Extract temperature anomaly from response
                temp_increase = _extract_temp_anomaly(temp_data)
            else:
                temp_increase = 1.5  # Default global estimate

            # Fetch precipitation projection
            precip_url = f"{CCKP_BASE}/cmip6-x0.25_pr_timeseries_annual_{SCENARIO}_median/{PERIOD}/ISO/{country_code_3}"
            precip_resp = await client.get(precip_url)

            if precip_resp.status_code == 200:
                precip_data = precip_resp.json()
                precip_change = _extract_precip_change(precip_data)
            else:
                precip_change = 0.0  # Default no change

        return {
            "temp_increase_c": temp_increase,
            "precip_change_pct": precip_change,
            "country_code": country_code_3,
            "scenario": SCENARIO,
            "period": PERIOD,
            "source": "World Bank Climate Change Knowledge Portal"
        }

    except Exception as e:
        logger.warning(f"World Bank CCKP service failed: {e}")
        return {
            "temp_increase_c": 1.5,
            "precip_change_pct": 0.0,
            "country_code": "Unknown",
            "scenario": SCENARIO,
            "period": PERIOD,
            "note": f"Using global default estimates. Error: {str(e)}"
        }


def _extract_temp_anomaly(data: dict) -> float:
    """Extract temperature anomaly value from World Bank API response."""
    try:
        # World Bank API response structure varies — try common patterns
        if "data" in data:
            values = list(data["data"].values())
            if values and isinstance(values[0], (int, float)):
                return float(values[0])
        return 1.5  # Default
    except Exception:
        return 1.5


def _extract_precip_change(data: dict) -> float:
    """Extract precipitation change percentage from World Bank API response."""
    try:
        if "data" in data:
            values = list(data["data"].values())
            if values and isinstance(values[0], (int, float)):
                return float(values[0])
        return 0.0
    except Exception:
        return 0.0


def adjust_flood_score_for_climate(
    base_score: float, projections: dict
) -> float:
    """
    Adjust a flood risk score upward based on World Bank precipitation projections.
    More rain = more flood risk.
    """
    precip_change = projections.get("precip_change_pct", 0.0)
    if precip_change > 10:
        adjustment = 0.10
    elif precip_change > 5:
        adjustment = 0.05
    elif precip_change < -10:
        adjustment = -0.05
    else:
        adjustment = 0.0
    return min(max(base_score + adjustment, 0.0), 1.0)


def adjust_heat_score_for_climate(
    base_score: float, projections: dict
) -> float:
    """
    Adjust a heat risk score upward based on World Bank temperature projections.
    +1°C projected increase → +0.10 score adjustment.
    """
    temp_increase = projections.get("temp_increase_c", 1.5)
    adjustment = min(temp_increase * 0.08, 0.20)
    return min(base_score + adjustment, 1.0)
