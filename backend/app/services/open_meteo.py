"""
Open-Meteo service for European climate data.
Provides historical weather and heat/storm risk for European addresses.
Free, no API key required. Covers all of Europe with ERA5/CERRA data.
Docs: https://open-meteo.com/en/docs/historical-weather-api
"""
import httpx
import logging
from datetime import datetime, timedelta
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_CLIMATE = "https://climate-api.open-meteo.com/v1/climate"


async def get_heat_risk_europe(lat: float, lon: float) -> HazardScore:
    """
    Compute extreme heat risk using Open-Meteo historical data for Europe.
    Uses ERA5 reanalysis — same underlying data as Copernicus CDS.
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2015-01-01",
        "end_date": "2024-12-31",
        "daily": "temperature_2m_max,temperature_2m_mean",
        "timezone": "Europe/London",
        "models": "ERA5",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(OPEN_METEO_HISTORICAL, params=params)
            response.raise_for_status()
            data = response.json()

        daily = data.get("daily", {})
        temps_max = [t for t in daily.get("temperature_2m_max", []) if t is not None]

        if not temps_max:
            return _fallback_heat_score_europe(lat)

        avg_max_temp = sum(temps_max) / len(temps_max)
        extreme_heat_days = sum(1 for t in temps_max if t >= 35.0) / 10  # per year

        # Mediterranean / Southern Europe scoring
        if avg_max_temp >= 35:
            base_score = 0.88
        elif avg_max_temp >= 30:
            base_score = 0.68
        elif avg_max_temp >= 25:
            base_score = 0.48
        elif avg_max_temp >= 20:
            base_score = 0.30
        else:
            base_score = 0.15

        # Adjust for extreme heat day frequency
        heat_adjustment = min(extreme_heat_days / 80, 0.10)
        final_score = min(base_score + heat_adjustment, 1.0)

        return HazardScore(
            score=round(final_score, 3),
            level=score_to_level(final_score),
            confidence="High",
            details={
                "avg_max_temp_c": round(avg_max_temp, 1),
                "extreme_heat_days_per_year": round(extreme_heat_days, 1),
                "data_model": "ERA5 Reanalysis",
                "source": "Open-Meteo / Copernicus ERA5"
            }
        )

    except Exception as e:
        logger.warning(f"Open-Meteo heat service failed: {e}")
        return _fallback_heat_score_europe(lat)


async def get_storm_risk_europe(lat: float, lon: float) -> HazardScore:
    """
    Compute storm and wind risk using Open-Meteo historical data for Europe.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2015-01-01",
        "end_date": "2024-12-31",
        "daily": "windspeed_10m_max,precipitation_sum",
        "timezone": "Europe/London",
        "models": "ERA5",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(OPEN_METEO_HISTORICAL, params=params)
            response.raise_for_status()
            data = response.json()

        daily = data.get("daily", {})
        wind_speeds = [w for w in daily.get("windspeed_10m_max", []) if w is not None]
        precip = [p for p in daily.get("precipitation_sum", []) if p is not None]

        if not wind_speeds:
            return _fallback_storm_score_europe(lat, lon)

        avg_wind = sum(wind_speeds) / len(wind_speeds)
        severe_wind_days = sum(1 for w in wind_speeds if w >= 61.2) / 10  # Beaufort 8+ per year
        heavy_rain_days = sum(1 for p in precip if p >= 20) / 10  # per year

        # Atlantic coast and Northern Europe are stormier
        atlantic_boost = 0.12 if _is_atlantic_coast(lat, lon) else 0.0
        alpine_boost = 0.08 if _is_alpine_region(lat, lon) else 0.0

        if avg_wind >= 40 or severe_wind_days >= 20:
            base_score = 0.82
        elif avg_wind >= 30 or severe_wind_days >= 10:
            base_score = 0.62
        elif avg_wind >= 20 or severe_wind_days >= 5:
            base_score = 0.42
        else:
            base_score = 0.22

        final_score = min(base_score + atlantic_boost + alpine_boost, 1.0)

        return HazardScore(
            score=round(final_score, 3),
            level=score_to_level(final_score),
            confidence="High",
            details={
                "avg_max_wind_kmh": round(avg_wind, 1),
                "severe_wind_days_per_year": round(severe_wind_days, 1),
                "heavy_rain_days_per_year": round(heavy_rain_days, 1),
                "atlantic_coast": _is_atlantic_coast(lat, lon),
                "source": "Open-Meteo / Copernicus ERA5"
            }
        )

    except Exception as e:
        logger.warning(f"Open-Meteo storm service failed: {e}")
        return _fallback_storm_score_europe(lat, lon)


async def get_climate_projections_europe(lat: float, lon: float) -> dict:
    """
    Fetch future climate projections for Europe using Open-Meteo Climate API.
    Uses CMIP6 ensemble data — same models as World Bank CCKP.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2041-01-01",
        "end_date": "2060-12-31",
        "models": "MRI_AGCM3_2_S",
        "daily": "temperature_2m_max,precipitation_sum",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(OPEN_METEO_CLIMATE, params=params)
            response.raise_for_status()
            data = response.json()

        daily = data.get("daily", {})
        future_temps = [t for t in daily.get("temperature_2m_max", []) if t is not None]

        if not future_temps:
            return {"temp_increase_c": 1.8, "precip_change_pct": 5.0, "source": "Open-Meteo Climate API (default)"}

        avg_future_temp = sum(future_temps) / len(future_temps)

        # Get baseline (2015-2024) for comparison
        baseline_params = {**params, "start_date": "2015-01-01", "end_date": "2024-12-31"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            baseline_resp = await client.get(OPEN_METEO_HISTORICAL, params={
                "latitude": lat, "longitude": lon,
                "start_date": "2015-01-01", "end_date": "2024-12-31",
                "daily": "temperature_2m_max", "timezone": "Europe/London", "models": "ERA5"
            })
            baseline_data = baseline_resp.json()

        baseline_temps = [t for t in baseline_data.get("daily", {}).get("temperature_2m_max", []) if t is not None]
        avg_baseline_temp = sum(baseline_temps) / len(baseline_temps) if baseline_temps else avg_future_temp - 1.5
        temp_increase = avg_future_temp - avg_baseline_temp

        return {
            "temp_increase_c": round(max(temp_increase, 0), 2),
            "precip_change_pct": 5.0,  # Default — ERA5 precip projections need separate call
            "scenario": "SSP2-4.5 equivalent",
            "period": "2041-2060",
            "source": "Open-Meteo Climate API / CMIP6"
        }

    except Exception as e:
        logger.warning(f"Open-Meteo climate projection failed: {e}")
        return {
            "temp_increase_c": 1.8,
            "precip_change_pct": 5.0,
            "source": "Open-Meteo Climate API (fallback estimate)"
        }


def _is_atlantic_coast(lat: float, lon: float) -> bool:
    """Check if location is on the Atlantic-facing European coast (high storm risk)."""
    # UK, Ireland, Western France, Portugal, Northern Spain, Norway
    return (
        (50 <= lat <= 58 and -10 <= lon <= 2) or   # UK / Ireland
        (36 <= lat <= 44 and -9 <= lon <= -6) or    # Portugal
        (43 <= lat <= 48 and -5 <= lon <= -1) or    # NW Spain / Biscay coast
        (58 <= lat <= 71 and 4 <= lon <= 20)         # Norway
    )


def _is_alpine_region(lat: float, lon: float) -> bool:
    """Check if location is in the Alpine region (high precipitation and storm risk)."""
    return 44 <= lat <= 48 and 6 <= lon <= 16


def _fallback_heat_score_europe(lat: float) -> HazardScore:
    """Latitude-based fallback for European heat risk."""
    if lat <= 38:    # Southern Spain, Sicily, Greece
        score = 0.78
    elif lat <= 44:  # Northern Spain, Southern France, Northern Italy
        score = 0.58
    elif lat <= 50:  # Central Europe — France, Germany, Poland
        score = 0.38
    elif lat <= 55:  # Northern Germany, Netherlands, Belgium, UK
        score = 0.25
    else:            # Scandinavia
        score = 0.15
    return HazardScore(
        score=score, level=score_to_level(score), confidence="Low",
        details={"note": "Latitude-based estimate — Open-Meteo data unavailable"}
    )


def _fallback_storm_score_europe(lat: float, lon: float) -> HazardScore:
    """Geographic fallback for European storm risk."""
    score = 0.55 if _is_atlantic_coast(lat, lon) else 0.30
    return HazardScore(
        score=score, level=score_to_level(score), confidence="Low",
        details={"note": "Geographic estimate — Open-Meteo data unavailable"}
    )
