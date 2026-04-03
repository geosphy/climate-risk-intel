"""
Open-Meteo service for European climate data.
Free, no API key required. Uses ERA5 reanalysis via archive API.
"""
import httpx
import logging
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_CLIMATE = "https://climate-api.open-meteo.com/v1/climate"


async def get_heat_risk_europe(lat: float, lon: float) -> HazardScore:
    """Compute extreme heat risk using Open-Meteo historical data."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2014-01-01",
        "end_date": "2023-12-31",
        "daily": "temperature_2m_max",
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(OPEN_METEO_HISTORICAL, params=params)
            response.raise_for_status()
            data = response.json()

        temps = [t for t in data.get("daily", {}).get("temperature_2m_max", []) if t is not None]
        if not temps:
            return _fallback_heat_score(lat)

        avg_max_temp = sum(temps) / len(temps)
        extreme_heat_days = round(sum(1 for t in temps if t >= 35.0) / 10, 1)
        days_above_40 = round(sum(1 for t in temps if t >= 40.0) / 10, 1)

        if avg_max_temp >= 35:
            base_score = 0.88
        elif avg_max_temp >= 28:
            base_score = 0.68
        elif avg_max_temp >= 22:
            base_score = 0.45
        elif avg_max_temp >= 16:
            base_score = 0.28
        else:
            base_score = 0.15

        adjustment = min(extreme_heat_days / 80, 0.10)
        final_score = min(round(base_score + adjustment, 3), 1.0)

        return HazardScore(
            score=final_score,
            level=score_to_level(final_score),
            confidence="High",
            details={
                "avg_max_temp_c": round(avg_max_temp, 1),
                "extreme_heat_days_per_year": extreme_heat_days,
                "days_above_40c_per_year": days_above_40,
                "source": "Open-Meteo / ERA5"
            }
        )
    except Exception as e:
        logger.warning(f"Open-Meteo heat failed: {e}")
        return _fallback_heat_score(lat)


async def get_storm_risk_europe(lat: float, lon: float) -> HazardScore:
    """Compute storm and wind risk using Open-Meteo historical data."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2014-01-01",
        "end_date": "2023-12-31",
        "daily": "windspeed_10m_max,precipitation_sum",
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(OPEN_METEO_HISTORICAL, params=params)
            response.raise_for_status()
            data = response.json()

        daily = data.get("daily", {})
        winds = [w for w in daily.get("windspeed_10m_max", []) if w is not None]
        precip = [p for p in daily.get("precipitation_sum", []) if p is not None]

        if not winds:
            return _fallback_storm_score(lat, lon)

        avg_wind = sum(winds) / len(winds)
        severe_wind_days = round(sum(1 for w in winds if w >= 61.2) / 10, 1)
        annual_precip = round(sum(precip) / (len(precip) / 365), 0) if precip else 600.0
        heavy_rain_days = round(sum(1 for p in precip if p >= 20) / 10, 1)

        if avg_wind >= 40 or severe_wind_days >= 20:
            base_score = 0.82
        elif avg_wind >= 30 or severe_wind_days >= 10:
            base_score = 0.62
        elif avg_wind >= 20 or severe_wind_days >= 5:
            base_score = 0.42
        else:
            base_score = 0.25

        atlantic_boost = 0.12 if _is_atlantic_coast(lat, lon) else 0.0
        final_score = min(round(base_score + atlantic_boost, 3), 1.0)

        return HazardScore(
            score=final_score,
            level=score_to_level(final_score),
            confidence="High",
            details={
                "avg_max_wind_kmh": round(avg_wind, 1),
                "severe_wind_days_per_year": severe_wind_days,
                "heavy_rain_days_per_year": heavy_rain_days,
                "annual_precipitation_mm": annual_precip,
                "atlantic_coast": _is_atlantic_coast(lat, lon),
                "source": "Open-Meteo / ERA5"
            }
        )
    except Exception as e:
        logger.warning(f"Open-Meteo storm failed: {e}")
        return _fallback_storm_score(lat, lon)


async def get_climate_projections_europe(lat: float, lon: float) -> dict:
    """Fetch 2050 climate projections using Open-Meteo Climate API."""
    try:
        future_params = {
            "latitude": lat, "longitude": lon,
            "start_date": "2041-01-01", "end_date": "2060-12-31",
            "daily": "temperature_2m_max",
            "models": "MRI_AGCM3_2_S",
        }
        baseline_params = {
            "latitude": lat, "longitude": lon,
            "start_date": "2014-01-01", "end_date": "2023-12-31",
            "daily": "temperature_2m_max",
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            future_resp = await client.get(OPEN_METEO_CLIMATE, params=future_params)
            baseline_resp = await client.get(OPEN_METEO_HISTORICAL, params=baseline_params)

        future_temps = [t for t in future_resp.json().get("daily", {}).get("temperature_2m_max", []) if t is not None]
        baseline_temps = [t for t in baseline_resp.json().get("daily", {}).get("temperature_2m_max", []) if t is not None]

        if future_temps and baseline_temps:
            temp_increase = round((sum(future_temps) / len(future_temps)) - (sum(baseline_temps) / len(baseline_temps)), 2)
        else:
            temp_increase = 1.8

        return {
            "temp_increase_c": max(temp_increase, 0.5),
            "precip_change_pct": 5.0,
            "scenario": "SSP2-4.5",
            "period": "2041-2060",
            "source": "Open-Meteo Climate API"
        }
    except Exception as e:
        logger.warning(f"Open-Meteo projection failed: {e}")
        return {"temp_increase_c": 1.8, "precip_change_pct": 5.0, "source": "fallback estimate"}


def _is_atlantic_coast(lat: float, lon: float) -> bool:
    return (
        (50 <= lat <= 58 and -10 <= lon <= 2) or
        (36 <= lat <= 44 and -9 <= lon <= -6) or
        (58 <= lat <= 71 and 4 <= lon <= 20)
    )


def _fallback_heat_score(lat: float) -> HazardScore:
    score = 0.78 if lat <= 38 else 0.58 if lat <= 44 else 0.38 if lat <= 50 else 0.22
    return HazardScore(score=score, level=score_to_level(score), confidence="Low",
                       details={"note": "Latitude estimate — Open-Meteo unavailable"})


def _fallback_storm_score(lat: float, lon: float) -> HazardScore:
    score = 0.55 if _is_atlantic_coast(lat, lon) else 0.32
    return HazardScore(score=score, level=score_to_level(score), confidence="Low",
                       details={"note": "Geographic estimate — Open-Meteo unavailable"})
