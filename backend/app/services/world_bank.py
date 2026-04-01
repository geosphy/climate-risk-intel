"""
World Bank Climate Change Knowledge Portal (CCKP) service.
Fetches climate projections (temperature, precipitation) for a location.
No API key required. Free public API.

Endpoint format (11 underscore-separated segments):
  /cckp/v1/{collection}_{type}_{variable}_{product}_{aggregation}_{period}
           _{percentile}_{scenario}_{model}_{model-calc}_{statistic}/{ISO3}

Temperature anomaly = SSP2-4.5 2040-2059 climatology minus 1995-2014 historical baseline.
Precipitation change = (future - historical) / historical * 100.
"""
import httpx
import logging
import reverse_geocoder
import pycountry
from typing import Optional

logger = logging.getLogger(__name__)

CCKP_BASE = "https://cckpapi.worldbank.org/cckp/v1"

# SSP2-4.5 "middle of the road" scenario, near-term 2050 window
_FUTURE   = "cmip6-x0.25_climatology_tas,pr_climatology_annual_2040-2059_median_ssp245_ensemble_all_mean"
_BASELINE = "cmip6-x0.25_climatology_tas,pr_climatology_annual_1995-2014_median_historical_ensemble_all_mean"


def _lat_lon_to_iso3(lat: float, lon: float) -> str:
    """Reverse-geocode lat/lon to an ISO-3166-1 alpha-3 country code."""
    rg = reverse_geocoder.search([(lat, lon)], verbose=False)
    alpha2 = rg[0].get("cc", "US")
    country = pycountry.countries.get(alpha_2=alpha2)
    return country.alpha_3 if country else "USA"


def _extract_value(data: dict | list, variable: str, iso3: str) -> Optional[float]:
    """
    Pull the single scalar value out of the CCKP response data block.

    Response shape:
        {"tas": {"USA": {"2040-07": 12.03}}, "pr": {"USA": {"2040-07": 851.71}}}

    Returns None when the variable or country is absent, or when data is an
    empty list (CCKP sends [] for unknown country codes).
    """
    if not isinstance(data, dict):
        return None
    var_block = data.get(variable)
    if not isinstance(var_block, dict):
        return None
    country_block = var_block.get(iso3)
    if not isinstance(country_block, dict) or not country_block:
        return None
    # There is exactly one period key; grab its value.
    return float(next(iter(country_block.values())))


async def get_climate_projections(lat: float, lon: float) -> dict:
    """
    Fetch World Bank CCKP SSP2-4.5 climate projections for the country at lat/lon.

    Makes two parallel requests:
      1. Future climatology  (SSP2-4.5, 2040-2059)
      2. Historical baseline (1995-2014)

    Returns a dict with:
        temp_increase_c    – projected warming by 2050 (°C above 1995-2014 mean)
        precip_change_pct  – projected precipitation change (%)
        future_tas_c       – absolute future temperature (°C)
        future_pr_mm       – absolute future precipitation (mm/yr)
        country_code       – ISO-3166-1 alpha-3 code used
        scenario           – "ssp245"
        period             – "2040-2059"
        source             – attribution string
    """
    iso3 = _lat_lon_to_iso3(lat, lon)

    future_url   = f"{CCKP_BASE}/{_FUTURE}/{iso3}"
    baseline_url = f"{CCKP_BASE}/{_BASELINE}/{iso3}"
    params = {"_format": "json"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            future_resp, baseline_resp = await _gather(
                client.get(future_url,   params=params),
                client.get(baseline_url, params=params),
            )

        future_data   = future_resp.json().get("data",   [])
        baseline_data = baseline_resp.json().get("data", [])

        future_tas   = _extract_value(future_data,   "tas", iso3)
        future_pr    = _extract_value(future_data,   "pr",  iso3)
        baseline_tas = _extract_value(baseline_data, "tas", iso3)
        baseline_pr  = _extract_value(baseline_data, "pr",  iso3)

        if future_tas is not None and baseline_tas is not None:
            temp_increase = round(future_tas - baseline_tas, 2)
        else:
            logger.warning(f"CCKP: missing temperature data for {iso3}, using default")
            temp_increase = 1.5

        if future_pr is not None and baseline_pr is not None and baseline_pr > 0:
            precip_change = round((future_pr - baseline_pr) / baseline_pr * 100, 1)
        else:
            logger.warning(f"CCKP: missing precipitation data for {iso3}, using default")
            precip_change = 0.0

        return {
            "temp_increase_c":   temp_increase,
            "precip_change_pct": precip_change,
            "future_tas_c":      future_tas,
            "future_pr_mm":      future_pr,
            "country_code":      iso3,
            "scenario":          "ssp245",
            "period":            "2040-2059",
            "source":            "World Bank Climate Change Knowledge Portal",
        }

    except Exception as e:
        logger.warning(f"World Bank CCKP service failed: {e}")
        return {
            "temp_increase_c":   1.5,
            "precip_change_pct": 0.0,
            "future_tas_c":      None,
            "future_pr_mm":      None,
            "country_code":      iso3,
            "scenario":          "ssp245",
            "period":            "2040-2059",
            "source":            "World Bank Climate Change Knowledge Portal",
            "note":              f"Using global defaults. Error: {e}",
        }


async def _gather(*coros):
    """Await multiple coroutines concurrently (thin wrapper to keep code readable)."""
    import asyncio
    return await asyncio.gather(*coros)


# ---------------------------------------------------------------------------
# Score adjustment helpers (called by the risk router)
# ---------------------------------------------------------------------------

def adjust_flood_score_for_climate(base_score: float, projections: dict) -> float:
    """
    Nudge flood risk upward when CCKP projects increased precipitation.
    More rain → more runoff → higher flood probability.
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
    return round(min(max(base_score + adjustment, 0.0), 1.0), 3)


def adjust_heat_score_for_climate(base_score: float, projections: dict) -> float:
    """
    Nudge heat risk upward based on projected temperature increase.
    Each +1 °C of warming adds ~0.08 to the score (capped at +0.20).
    """
    temp_increase = projections.get("temp_increase_c", 1.5)
    adjustment = min(temp_increase * 0.08, 0.20)
    return round(min(base_score + adjustment, 1.0), 3)
