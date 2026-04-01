"""
NOAA Climate Data Online (CDO) service.
Fetches historical temperature and storm event data.
Requires NOAA_TOKEN environment variable.
Free token at: https://www.ncdc.noaa.gov/cdo-web/token
"""
import httpx
import logging
from app.models.schemas import HazardScore, score_to_level
from app.core.config import get_settings

logger = logging.getLogger(__name__)

NOAA_CDO_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2"


async def get_heat_risk(lat: float, lon: float) -> HazardScore:
    """
    Compute extreme heat risk from NOAA historical temperature data.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        HazardScore for extreme heat risk
    """
    settings = get_settings()

    if not settings.noaa_token:
        logger.warning("NOAA_TOKEN not set — using fallback heat score")
        return _fallback_heat_score(lat)

    headers = {"token": settings.noaa_token}

    try:
        # Find nearest NOAA station
        async with httpx.AsyncClient(timeout=15.0) as client:
            station_resp = await client.get(
                f"{NOAA_CDO_BASE}/stations",
                headers=headers,
                params={
                    "extent": f"{lat-1},{lon-1},{lat+1},{lon+1}",
                    "datasetid": "GHCND",
                    "datatypeid": "TMAX",
                    "limit": 1,
                    "sortfield": "datacoverage",
                    "sortorder": "desc",
                }
            )
            station_resp.raise_for_status()
            stations = station_resp.json().get("results", [])

            if not stations:
                return _fallback_heat_score(lat)

            station_id = stations[0]["id"]

            # Fetch last 10 years of max temperature data
            data_resp = await client.get(
                f"{NOAA_CDO_BASE}/data",
                headers=headers,
                params={
                    "datasetid": "GHCND",
                    "stationid": station_id,
                    "datatypeid": "TMAX",
                    "startdate": "2015-01-01",
                    "enddate": "2024-12-31",
                    "limit": 1000,
                    "units": "metric",
                }
            )
            data_resp.raise_for_status()
            records = data_resp.json().get("results", [])

        if not records:
            return _fallback_heat_score(lat)

        # Analyze temperature data
        temps_c = [r["value"] / 10 for r in records]  # NOAA stores in tenths of °C
        avg_max_temp = sum(temps_c) / len(temps_c)
        extreme_heat_days = sum(1 for t in temps_c if t >= 35.0) / 10  # per year

        # Score based on avg max temp
        if avg_max_temp >= 38:
            base_score = 0.90
        elif avg_max_temp >= 33:
            base_score = 0.70
        elif avg_max_temp >= 28:
            base_score = 0.50
        else:
            base_score = 0.20

        # Adjust for number of extreme heat days
        heat_day_adjustment = min(extreme_heat_days / 100, 0.10)
        final_score = min(base_score + heat_day_adjustment, 1.0)

        return HazardScore(
            score=round(final_score, 3),
            level=score_to_level(final_score),
            confidence="High",
            details={
                "avg_max_temp_c": round(avg_max_temp, 1),
                "extreme_heat_days_per_year": round(extreme_heat_days, 1),
                "station_id": station_id,
                "source": "NOAA Climate Data Online"
            }
        )

    except Exception as e:
        logger.warning(f"NOAA heat service failed: {e}")
        return _fallback_heat_score(lat)


async def get_storm_risk(lat: float, lon: float) -> HazardScore:
    """
    Compute storm risk from NOAA historical storm event data.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        HazardScore for storm and wind risk
    """
    settings = get_settings()

    if not settings.noaa_token:
        return _fallback_storm_score(lat, lon)

    headers = {"token": settings.noaa_token}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Find nearest station for precipitation/wind data
            station_resp = await client.get(
                f"{NOAA_CDO_BASE}/stations",
                headers=headers,
                params={
                    "extent": f"{lat-2},{lon-2},{lat+2},{lon+2}",
                    "datasetid": "GHCND",
                    "datatypeid": "AWND",  # Average wind speed
                    "limit": 1,
                    "sortfield": "datacoverage",
                    "sortorder": "desc",
                }
            )
            station_resp.raise_for_status()
            stations = station_resp.json().get("results", [])

            if not stations:
                return _fallback_storm_score(lat, lon)

            station_id = stations[0]["id"]

            # Fetch wind data
            wind_resp = await client.get(
                f"{NOAA_CDO_BASE}/data",
                headers=headers,
                params={
                    "datasetid": "GHCND",
                    "stationid": station_id,
                    "datatypeid": "AWND",
                    "startdate": "2015-01-01",
                    "enddate": "2024-12-31",
                    "limit": 1000,
                    "units": "metric",
                }
            )
            wind_resp.raise_for_status()
            records = wind_resp.json().get("results", [])

        if not records:
            return _fallback_storm_score(lat, lon)

        wind_speeds = [r["value"] / 10 for r in records]  # tenths of m/s
        avg_wind = sum(wind_speeds) / len(wind_speeds)
        severe_wind_days = sum(1 for w in wind_speeds if w >= 17.2) / 10  # per year (Beaufort 7+)

        if avg_wind >= 8 or severe_wind_days >= 15:
            base_score = 0.80
        elif avg_wind >= 5 or severe_wind_days >= 8:
            base_score = 0.60
        elif avg_wind >= 3 or severe_wind_days >= 3:
            base_score = 0.40
        else:
            base_score = 0.20

        # Gulf/Atlantic coast boost for hurricane risk
        if _is_hurricane_coast(lat, lon):
            base_score = min(base_score + 0.15, 1.0)

        return HazardScore(
            score=round(base_score, 3),
            level=score_to_level(base_score),
            confidence="Medium",
            details={
                "avg_wind_speed_ms": round(avg_wind, 1),
                "severe_wind_days_per_year": round(severe_wind_days, 1),
                "hurricane_coast": _is_hurricane_coast(lat, lon),
                "source": "NOAA Climate Data Online"
            }
        )

    except Exception as e:
        logger.warning(f"NOAA storm service failed: {e}")
        return _fallback_storm_score(lat, lon)


def _is_hurricane_coast(lat: float, lon: float) -> bool:
    """Check if location is in the US Gulf/Atlantic hurricane-prone coastal zone."""
    # Gulf Coast: lat 25-31, lon -97 to -80
    # Atlantic Coast: lat 25-35, lon -80 to -75
    return (
        (25 <= lat <= 31 and -97 <= lon <= -80) or
        (25 <= lat <= 35 and -80 <= lon <= -75)
    )


def _fallback_heat_score(lat: float) -> HazardScore:
    """Latitude-based fallback when NOAA data is unavailable."""
    # Rough heat risk by latitude (lower lat = hotter in US)
    if lat <= 30:
        score = 0.70
    elif lat <= 35:
        score = 0.50
    elif lat <= 40:
        score = 0.35
    else:
        score = 0.20
    return HazardScore(
        score=score,
        level=score_to_level(score),
        confidence="Low",
        details={"note": "Estimated from latitude — add NOAA_TOKEN for precise data"}
    )


def _fallback_storm_score(lat: float, lon: float) -> HazardScore:
    """Geographic fallback when NOAA data is unavailable."""
    score = 0.55 if _is_hurricane_coast(lat, lon) else 0.30
    return HazardScore(
        score=score,
        level=score_to_level(score),
        confidence="Low",
        details={"note": "Estimated from geography — add NOAA_TOKEN for precise data"}
    )
