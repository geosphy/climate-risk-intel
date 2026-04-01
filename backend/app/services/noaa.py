"""
NOAA climate data service.
Fetches historical temperature and wind/storm data for heat and storm risk scoring.

Two data paths:
  With NOAA_TOKEN  – NCEI CDO API v2 (fine-grained station + data queries)
  Without token    – NCEI Data Access API v1, no auth required:
      * normals-annualseasonal  → 30-yr average TMAX + hot-day counts
      * global-summary-of-year  → 10-yr annual TMAX + wind speed
  Station discovery (no-token path) uses the public GHCND station inventory,
  filtered to ~1 900 USW airport stations and cached in process memory.
"""
import asyncio
import io
import logging
import math
from typing import Optional

import httpx

from app.core.config import get_settings
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint constants
# ---------------------------------------------------------------------------

CDO_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2"
NCEI_V1  = "https://www.ncei.noaa.gov/access/services/data/v1"

GHCND_STATIONS_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"

# ---------------------------------------------------------------------------
# USW station index (cached once per process)
# ---------------------------------------------------------------------------

# Each entry: (station_id, latitude, longitude)
_Station = tuple[str, float, float]

_usw_station_cache: Optional[list[_Station]] = None
_cache_lock = asyncio.Lock()


async def _get_usw_stations(client: httpx.AsyncClient) -> list[_Station]:
    """
    Return a cached list of USW (US WBAN / airport) GHCND stations.

    Downloaded once from NCEI on first call, filtered from ~130 K entries to
    the ~1 900 USW stations (prefix "USW"), then held in process memory.
    """
    global _usw_station_cache
    async with _cache_lock:
        if _usw_station_cache is not None:
            return _usw_station_cache

        logger.info("Downloading GHCND station inventory (first call only)…")
        try:
            resp = await client.get(GHCND_STATIONS_URL, timeout=30.0)
            resp.raise_for_status()
            stations: list[_Station] = []
            for line in io.StringIO(resp.text):
                if not line.startswith("USW"):
                    continue
                try:
                    sid = line[:11].strip()
                    lat = float(line[12:20])
                    lon = float(line[21:30])
                    stations.append((sid, lat, lon))
                except ValueError:
                    continue
            _usw_station_cache = stations
            logger.info(f"Cached {len(stations)} USW stations from GHCND inventory")
        except Exception as exc:
            logger.warning(f"Could not download GHCND station inventory: {exc}")
            _usw_station_cache = []

    return _usw_station_cache


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6_371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _nearest_station(stations: list[_Station], lat: float, lon: float) -> Optional[str]:
    """Return the station ID closest to (lat, lon), or None if list is empty."""
    if not stations:
        return None
    return min(stations, key=lambda s: _haversine_km(lat, lon, s[1], s[2]))[0]


def _parse_ncei_ndjson(text: str) -> list[dict]:
    """
    Parse NCEI v1 responses, which are sometimes newline-delimited JSON
    (one object per line) rather than a plain JSON array.
    """
    import json
    text = text.strip()
    if not text:
        return []
    # Try as a regular JSON array first
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        pass
    # Fall back to NDJSON
    rows = []
    for line in text.splitlines():
        line = line.strip().strip(",")  # NCEI emits leading OR trailing commas
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


# ---------------------------------------------------------------------------
# Heat risk
# ---------------------------------------------------------------------------

async def get_heat_risk(lat: float, lon: float) -> HazardScore:
    """
    Compute extreme heat risk from NOAA historical temperature data.

    With NOAA_TOKEN : CDO API – finds nearest GHCND station and retrieves up
                      to 10 years of daily TMAX records.
    Without token   : NCEI v1 API – uses 30-year normals (1991-2020) for the
                      nearest USW airport station; falls back to 10-year GSOY
                      annual averages if normals are absent.

    Returns a HazardScore with score 0.0–1.0.
    """
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        if settings.noaa_token:
            return await _heat_via_cdo(client, lat, lon, settings.noaa_token)
        return await _heat_via_ncei_v1(client, lat, lon)


async def _heat_via_cdo(
    client: httpx.AsyncClient, lat: float, lon: float, token: str
) -> HazardScore:
    """CDO-based heat risk (requires NOAA_TOKEN)."""
    headers = {"token": token}
    try:
        # Find nearest station with TMAX data
        station_resp = await client.get(
            f"{CDO_BASE}/stations",
            headers=headers,
            params={
                "extent":      f"{lat - 1},{lon - 1},{lat + 1},{lon + 1}",
                "datasetid":   "GHCND",
                "datatypeid":  "TMAX",
                "limit":       1,
                "sortfield":   "datacoverage",
                "sortorder":   "desc",
            },
        )
        station_resp.raise_for_status()
        stations = station_resp.json().get("results", [])
        if not stations:
            return _fallback_heat_score(lat)

        station_id = stations[0]["id"]

        # Fetch last 10 years of daily max-temperature records
        data_resp = await client.get(
            f"{CDO_BASE}/data",
            headers=headers,
            params={
                "datasetid":  "GHCND",
                "stationid":  station_id,
                "datatypeid": "TMAX",
                "startdate":  "2015-01-01",
                "enddate":    "2024-12-31",
                "limit":      1000,
                "units":      "metric",
            },
        )
        data_resp.raise_for_status()
        records = data_resp.json().get("results", [])

        if not records:
            return _fallback_heat_score(lat)

        # GHCND CDO stores TMAX in tenths of °C
        temps_c = [r["value"] / 10 for r in records]
        avg_max_c = sum(temps_c) / len(temps_c)
        hot_days_per_yr = sum(1 for t in temps_c if t >= 35.0) / 10

        return _score_heat(avg_max_c, hot_days_per_yr, station_id, "NOAA CDO")

    except Exception as exc:
        logger.warning(f"NOAA CDO heat service failed: {exc}")
        return _fallback_heat_score(lat)


async def _heat_via_ncei_v1(
    client: httpx.AsyncClient, lat: float, lon: float
) -> HazardScore:
    """
    NCEI v1 heat risk (no token required).

    Primary: 30-yr climate normals (1991-2020) — ANN-TMAX-NORMAL + hot-day count.
    Fallback: 10-yr global-summary-of-year TMAX averages.
    """
    stations = await _get_usw_stations(client)
    station_id = _nearest_station(stations, lat, lon)
    if not station_id:
        return _fallback_heat_score(lat)

    try:
        # --- Primary: 30-yr normals ---
        normals_resp = await client.get(
            NCEI_V1,
            params={
                "dataset":              "normals-annualseasonal",
                "stations":             station_id,
                "dataTypes":            "ANN-TMAX-NORMAL,ANN-TMAX-AVGNDS-GRTH090,ANN-TMAX-AVGNDS-GRTH100",
                "startDate":            "1991-01-01",
                "endDate":              "2020-12-31",
                "format":               "json",
                "includeStationName":   "true",
                "includeStationLocation": "true",
            },
        )
        normals_resp.raise_for_status()
        normals = _parse_ncei_ndjson(normals_resp.text)

        if normals and normals[0].get("ANN-TMAX-NORMAL"):
            row = normals[0]
            # Normals are stored in tenths of °F
            avg_max_f  = float(row["ANN-TMAX-NORMAL"]) / 10
            avg_max_c  = (avg_max_f - 32) * 5 / 9
            # Days ≥ 90°F (32.2°C) per year; stored in tenths
            hot_90_days = float(row.get("ANN-TMAX-AVGNDS-GRTH090") or 0) / 10
            # Days ≥ 100°F (37.8°C) per year; stored in tenths
            hot_100_days = float(row.get("ANN-TMAX-AVGNDS-GRTH100") or 0) / 10
            station_name = row.get("NAME", station_id)

            # Combine 90°F+ and 100°F+ into an extreme-heat-days metric (≥ 35°C proxy)
            # 95°F = 35°C sits between 90 and 100; interpolate
            extreme_heat_days = hot_90_days * 0.4 + hot_100_days * 0.6

            return _score_heat(
                avg_max_c, extreme_heat_days, station_name,
                "NOAA Climate Normals 1991-2020"
            )

        # --- Fallback: 10-yr global summary of year ---
        gsoy_resp = await client.get(
            NCEI_V1,
            params={
                "dataset":   "global-summary-of-the-year",
                "stations":  station_id,
                "startDate": "2014-01-01",
                "endDate":   "2023-12-31",
                "dataTypes": "TMAX",
                "format":    "json",
            },
        )
        gsoy_resp.raise_for_status()
        gsoy_rows = _parse_ncei_ndjson(gsoy_resp.text)

        if not gsoy_rows:
            return _fallback_heat_score(lat)

        # GSOY TMAX is annual average of daily max temperatures in °C
        temps = [float(r["TMAX"]) for r in gsoy_rows if r.get("TMAX")]
        if not temps:
            return _fallback_heat_score(lat)

        avg_max_c = sum(temps) / len(temps)
        return _score_heat(avg_max_c, 0.0, station_id, "NOAA Global Summary of Year")

    except Exception as exc:
        logger.warning(f"NCEI v1 heat service failed: {exc}")
        return _fallback_heat_score(lat)


def _score_heat(
    avg_max_c: float,
    extreme_heat_days: float,
    station: str,
    source: str,
) -> HazardScore:
    """Convert raw temperature statistics to a HazardScore."""
    # Base score from average annual max temperature (CLAUDE.md thresholds)
    if avg_max_c >= 38:
        base = 0.90
    elif avg_max_c >= 33:
        base = 0.70
    elif avg_max_c >= 28:
        base = 0.50
    else:
        base = 0.20

    # Upward adjustment for extreme-heat-day frequency (up to +0.10)
    heat_day_adj = min(extreme_heat_days / 100, 0.10)
    score = round(min(base + heat_day_adj, 1.0), 3)

    return HazardScore(
        score=score,
        level=score_to_level(score),
        confidence="High",
        details={
            "avg_max_temp_c":         round(avg_max_c, 1),
            "extreme_heat_days_per_yr": round(extreme_heat_days, 1),
            "station":                station,
            "source":                 source,
        },
    )


# ---------------------------------------------------------------------------
# Storm risk
# ---------------------------------------------------------------------------

async def get_storm_risk(lat: float, lon: float) -> HazardScore:
    """
    Compute storm and wind risk from NOAA historical data.

    With NOAA_TOKEN : CDO API – daily average wind speed (AWND) from the
                      nearest GHCND station.
    Without token   : NCEI v1 GSOY AWND – 10-year annual average wind speed
                      from the nearest USW airport station.

    Hurricane-coast bonus applied for Gulf Coast / Atlantic Coast locations
    regardless of data source.

    Returns a HazardScore with score 0.0–1.0.
    """
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        if settings.noaa_token:
            return await _storm_via_cdo(client, lat, lon, settings.noaa_token)
        return await _storm_via_ncei_v1(client, lat, lon)


async def _storm_via_cdo(
    client: httpx.AsyncClient, lat: float, lon: float, token: str
) -> HazardScore:
    """CDO-based storm risk (requires NOAA_TOKEN)."""
    headers = {"token": token}
    try:
        station_resp = await client.get(
            f"{CDO_BASE}/stations",
            headers=headers,
            params={
                "extent":     f"{lat - 2},{lon - 2},{lat + 2},{lon + 2}",
                "datasetid":  "GHCND",
                "datatypeid": "AWND",
                "limit":      1,
                "sortfield":  "datacoverage",
                "sortorder":  "desc",
            },
        )
        station_resp.raise_for_status()
        stations = station_resp.json().get("results", [])
        if not stations:
            return _fallback_storm_score(lat, lon)

        station_id = stations[0]["id"]

        wind_resp = await client.get(
            f"{CDO_BASE}/data",
            headers=headers,
            params={
                "datasetid":  "GHCND",
                "stationid":  station_id,
                "datatypeid": "AWND",
                "startdate":  "2015-01-01",
                "enddate":    "2024-12-31",
                "limit":      1000,
                "units":      "metric",
            },
        )
        wind_resp.raise_for_status()
        records = wind_resp.json().get("results", [])

        if not records:
            return _fallback_storm_score(lat, lon)

        # GHCND CDO AWND is in tenths of m/s
        speeds = [r["value"] / 10 for r in records]
        avg_wind = sum(speeds) / len(speeds)
        severe_days_per_yr = sum(1 for w in speeds if w >= 17.2) / 10  # Beaufort 7+

        return _score_storm(avg_wind, severe_days_per_yr, lat, lon, station_id, "NOAA CDO")

    except Exception as exc:
        logger.warning(f"NOAA CDO storm service failed: {exc}")
        return _fallback_storm_score(lat, lon)


async def _storm_via_ncei_v1(
    client: httpx.AsyncClient, lat: float, lon: float
) -> HazardScore:
    """
    NCEI v1 storm risk (no token required).

    Uses 10-yr GSOY annual average wind speed (AWND) from the nearest USW station.
    AWND in GSOY is the mean of daily average wind speeds for the year, in m/s.
    """
    stations = await _get_usw_stations(client)
    station_id = _nearest_station(stations, lat, lon)
    if not station_id:
        return _fallback_storm_score(lat, lon)

    try:
        gsoy_resp = await client.get(
            NCEI_V1,
            params={
                "dataset":   "global-summary-of-the-year",
                "stations":  station_id,
                "startDate": "2014-01-01",
                "endDate":   "2023-12-31",
                "dataTypes": "AWND",
                "format":    "json",
            },
        )
        gsoy_resp.raise_for_status()
        rows = _parse_ncei_ndjson(gsoy_resp.text)

        if not rows:
            return _fallback_storm_score(lat, lon)

        speeds = [float(r["AWND"]) for r in rows if r.get("AWND")]
        if not speeds:
            return _fallback_storm_score(lat, lon)

        avg_wind = sum(speeds) / len(speeds)
        # GSOY AWND is an annual mean, so we can't derive per-day severe counts.
        # Use 0 for severe days; the avg_wind threshold drives the base score.
        return _score_storm(avg_wind, 0.0, lat, lon, station_id, "NOAA Global Summary of Year")

    except Exception as exc:
        logger.warning(f"NCEI v1 storm service failed: {exc}")
        return _fallback_storm_score(lat, lon)


def _score_storm(
    avg_wind_ms: float,
    severe_days_per_yr: float,
    lat: float,
    lon: float,
    station: str,
    source: str,
) -> HazardScore:
    """Convert wind statistics to a HazardScore (CLAUDE.md thresholds)."""
    if avg_wind_ms >= 8 or severe_days_per_yr >= 15:
        base = 0.80
    elif avg_wind_ms >= 5 or severe_days_per_yr >= 8:
        base = 0.60
    elif avg_wind_ms >= 3 or severe_days_per_yr >= 3:
        base = 0.40
    else:
        base = 0.20

    hurricane_coast = _is_hurricane_coast(lat, lon)
    if hurricane_coast:
        base = min(base + 0.15, 1.0)

    score = round(base, 3)
    return HazardScore(
        score=score,
        level=score_to_level(score),
        confidence="Medium",
        details={
            "avg_wind_speed_ms":      round(avg_wind_ms, 2),
            "severe_wind_days_per_yr": round(severe_days_per_yr, 1),
            "hurricane_coast":        hurricane_coast,
            "station":                station,
            "source":                 source,
        },
    )


# ---------------------------------------------------------------------------
# Geography helpers
# ---------------------------------------------------------------------------

def _is_hurricane_coast(lat: float, lon: float) -> bool:
    """Return True if the coordinate is in the US Gulf/Atlantic hurricane belt."""
    # Gulf Coast:     lat 25–31°N,  lon 97–80°W
    # Atlantic Coast: lat 25–35°N,  lon 80–75°W
    return (
        (25 <= lat <= 31 and -97 <= lon <= -80)
        or (25 <= lat <= 35 and -80 <= lon <= -75)
    )


# ---------------------------------------------------------------------------
# Fallbacks (no data available)
# ---------------------------------------------------------------------------

def _fallback_heat_score(lat: float) -> HazardScore:
    """Latitude-based estimate when all NOAA services fail."""
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
        details={"note": "Estimated from latitude — NOAA data unavailable"},
    )


def _fallback_storm_score(lat: float, lon: float) -> HazardScore:
    """Geography-based estimate when all NOAA services fail."""
    score = 0.55 if _is_hurricane_coast(lat, lon) else 0.30
    return HazardScore(
        score=score,
        level=score_to_level(score),
        confidence="Low",
        details={"note": "Estimated from geography — NOAA data unavailable"},
    )
