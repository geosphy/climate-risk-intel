"""
JRC Global Surface Water + European flood risk service.
Uses JRC WMS and Copernicus EFAS data for European flood zone assessment.
No API key required. Free public service from EU Joint Research Centre.
"""
import httpx
import logging
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

# JRC Global Surface Water WMS endpoint
JRC_WMS = "https://wms.jrc.ec.europa.eu/HydroSHEDS/wms"

# Global Flood Database via Copernicus (public)
COPERNICUS_FLOOD_WMS = "https://maps.disasters.copernicus.eu/arcgis/rest/services/Products/EFAS_European_Overview/MapServer"


async def get_flood_risk_europe(lat: float, lon: float) -> HazardScore:
    """
    Compute flood risk for European addresses using JRC Global Surface Water data.
    Falls back to geographic heuristics if WMS is unavailable.
    """
    try:
        # Query JRC WMS for flood occurrence at this location
        delta = 0.01
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": "occurrence",
            "QUERY_LAYERS": "occurrence",
            "CRS": "CRS:84",
            "BBOX": f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}",
            "WIDTH": "10",
            "HEIGHT": "10",
            "I": "5",
            "J": "5",
            "INFO_FORMAT": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(JRC_WMS, params=params)

        if response.status_code == 200:
            # Parse water occurrence percentage (0-100)
            try:
                data = response.json()
                features = data.get("features", [])
                if features:
                    occurrence = float(features[0].get("properties", {}).get("occurrence", 0))
                    return _score_from_jrc_occurrence(occurrence, lat, lon)
            except Exception:
                pass

        # Fallback to geographic heuristics
        return _geographic_flood_score_europe(lat, lon)

    except Exception as e:
        logger.warning(f"JRC flood service failed: {e}")
        return _geographic_flood_score_europe(lat, lon)


def _score_from_jrc_occurrence(occurrence: float, lat: float, lon: float) -> HazardScore:
    """Convert JRC water occurrence % to a flood risk score."""
    # occurrence = % of time water was detected 1984-2021
    if occurrence >= 75:
        score = 0.95   # Permanent water body — extreme risk
    elif occurrence >= 25:
        score = 0.82   # Seasonal flooding — high risk
    elif occurrence >= 5:
        score = 0.65   # Occasional flooding — high risk
    elif occurrence >= 1:
        score = 0.45   # Rare flooding — medium risk
    else:
        score = _geographic_flood_score_europe(lat, lon).score

    # River delta boost (Netherlands, Po Valley, Rhine delta)
    if _is_river_delta(lat, lon):
        score = min(score + 0.12, 1.0)

    return HazardScore(
        score=round(score, 3),
        level=score_to_level(score),
        confidence="High",
        details={
            "jrc_water_occurrence_pct": occurrence,
            "river_delta_zone": _is_river_delta(lat, lon),
            "source": "JRC Global Surface Water Explorer"
        }
    )


def _geographic_flood_score_europe(lat: float, lon: float) -> HazardScore:
    """
    Geographic heuristic flood scoring for Europe.
    Based on known high-risk zones: Netherlands, Po Valley, Rhine/Danube,
    UK flood plains, coastal areas.
    """
    score = 0.25  # European baseline
    zone_name = "Standard risk zone"

    # Netherlands / Low Countries — highest flood risk in Europe
    if 51 <= lat <= 53.5 and 3.5 <= lon <= 7:
        score = 0.88
        zone_name = "Netherlands/Low Countries (below sea level)"

    # Po Valley, Italy
    elif 44 <= lat <= 46 and 8 <= lon <= 13:
        score = 0.75
        zone_name = "Po Valley flood plain"

    # Rhine delta / Western Germany
    elif 50 <= lat <= 52 and 6 <= lon <= 9:
        score = 0.68
        zone_name = "Rhine/Ruhr flood zone"

    # Danube flood plains (Hungary, Romania, Serbia)
    elif 44 <= lat <= 48 and 18 <= lon <= 29:
        score = 0.65
        zone_name = "Danube flood plain"

    # UK flood plains (Thames, Severn, Trent)
    elif 51 <= lat <= 53 and -3 <= lon <= 1:
        score = 0.58
        zone_name = "UK river flood plain"

    # Coastal Europe — sea level rise risk
    elif _is_european_coast(lat, lon):
        score = 0.52
        zone_name = "European coastal zone"

    # Mediterranean coasts — flash flood risk
    elif 36 <= lat <= 44 and -5 <= lon <= 28:
        score = 0.42
        zone_name = "Mediterranean flash flood zone"

    return HazardScore(
        score=score,
        level=score_to_level(score),
        confidence="Medium",
        details={
            "zone": zone_name,
            "source": "Geographic flood risk heuristics (JRC data unavailable)"
        }
    )


def _is_river_delta(lat: float, lon: float) -> bool:
    """Check if location is in a major European river delta."""
    deltas = [
        (52.0, 4.5, 1.5),   # Rhine-Meuse delta (Netherlands)
        (45.0, 12.5, 1.0),  # Po delta (Italy)
        (45.2, 29.5, 1.5),  # Danube delta (Romania)
        (38.0, 21.5, 0.8),  # Acheloos delta (Greece)
    ]
    for dlat, dlon, radius in deltas:
        if abs(lat - dlat) <= radius and abs(lon - dlon) <= radius:
            return True
    return False


def _is_european_coast(lat: float, lon: float) -> bool:
    """Rough check if location is near a European coastline."""
    # Very simplified — checks proximity to known coastal bounds
    return (
        (35 <= lat <= 71) and (
            lon <= -5 or lon >= 25 or  # Atlantic / Eastern Europe coasts
            (lat >= 58) or              # Nordic coasts
            (lat <= 42 and lon >= 12)   # Adriatic / Aegean
        )
    )
