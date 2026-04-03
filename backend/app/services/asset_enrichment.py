"""
Asset-level enrichment service.
Fetches location-specific physical characteristics that differentiate
individual data center assets within the same city.
Sources: Open-Meteo (elevation), OpenStreetMap Overpass (water/power proximity),
         JRC Surface Water (precise flood history at exact coordinates).
"""
import httpx
import math
import logging

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
JRC_WMS = "https://global-surface-water.appspot.com/mapPublish/mapserver/occurrence_3857/wms"


async def get_asset_level_factors(lat: float, lon: float) -> dict:
    """
    Fetch asset-specific physical factors for a precise lat/lon coordinate.
    Returns factors that differentiate individual assets within the same city.
    """
    import asyncio
    elevation_task = asyncio.create_task(get_elevation(lat, lon))
    water_task = asyncio.create_task(get_water_proximity(lat, lon))
    power_task = asyncio.create_task(get_power_infrastructure(lat, lon))
    uhi_task = asyncio.create_task(estimate_urban_heat_island(lat, lon))

    elevation, water, power, uhi = await asyncio.gather(
        elevation_task, water_task, power_task, uhi_task
    )

    return {
        "elevation_m": elevation,
        "water_proximity": water,
        "power_infrastructure": power,
        "urban_heat_island": uhi,
    }


async def get_elevation(lat: float, lon: float) -> float:
    """Get precise elevation at the asset location from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/elevation",
                params={"latitude": lat, "longitude": lon}
            )
            data = r.json()
            elevations = data.get("elevation", [0])
            return float(elevations[0]) if elevations else 0.0
    except Exception as e:
        logger.warning(f"Elevation fetch failed: {e}")
        return 0.0


async def get_water_proximity(lat: float, lon: float) -> dict:
    """
    Query OpenStreetMap for water bodies near the asset.
    Closer to water = higher flood risk modifier.
    Uses Overpass API — free, no key required.
    """
    try:
        # Search for water bodies within 500m radius
        query = f"""
        [out:json][timeout:10];
        (
          way["natural"="water"](around:500,{lat},{lon});
          way["waterway"~"river|stream|canal"](around:500,{lat},{lon});
          relation["natural"="water"](around:500,{lat},{lon});
        );
        out center;
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(OVERPASS_URL, data={"data": query})
            data = r.json()

        elements = data.get("elements", [])
        if not elements:
            return {"nearest_water_m": 999, "water_bodies": 0, "flood_modifier": 0.0}

        # Calculate distance to nearest water body
        min_dist = 999.0
        for el in elements:
            center = el.get("center", {})
            if center:
                dist = _haversine_m(lat, lon, center.get("lat", lat), center.get("lon", lon))
                min_dist = min(min_dist, dist)

        # Flood modifier based on distance to water
        if min_dist <= 50:
            modifier = 0.25
            risk_label = "Adjacent to water (<50m)"
        elif min_dist <= 150:
            modifier = 0.18
            risk_label = "Very close to water (<150m)"
        elif min_dist <= 300:
            modifier = 0.10
            risk_label = "Near water body (<300m)"
        elif min_dist <= 500:
            modifier = 0.05
            risk_label = "Water body within 500m"
        else:
            modifier = 0.0
            risk_label = "No water bodies within 500m"

        return {
            "nearest_water_m": round(min_dist),
            "water_bodies_count": len(elements),
            "flood_modifier": modifier,
            "risk_label": risk_label
        }
    except Exception as e:
        logger.warning(f"Water proximity fetch failed: {e}")
        return {"nearest_water_m": 999, "water_bodies": 0, "flood_modifier": 0.0}


async def get_power_infrastructure(lat: float, lon: float) -> dict:
    """
    Query OpenStreetMap for power substations and lines near the asset.
    Closer to substations = more reliable grid access.
    """
    try:
        query = f"""
        [out:json][timeout:10];
        (
          node["power"="substation"](around:2000,{lat},{lon});
          node["power"="transformer"](around:500,{lat},{lon});
        );
        out center;
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(OVERPASS_URL, data={"data": query})
            data = r.json()

        elements = data.get("elements", [])
        substations = [e for e in elements if e.get("tags", {}).get("power") == "substation"]
        transformers = [e for e in elements if e.get("tags", {}).get("power") == "transformer"]

        nearest_sub = 9999.0
        for el in substations:
            dist = _haversine_m(lat, lon, el.get("lat", lat), el.get("lon", lon))
            nearest_sub = min(nearest_sub, dist)

        # Grid reliability modifier
        if nearest_sub <= 200:
            grid_modifier = 0.10   # Very close to substation = better
            grid_label = "Substation within 200m"
        elif nearest_sub <= 500:
            grid_modifier = 0.05
            grid_label = "Substation within 500m"
        elif nearest_sub <= 2000:
            grid_modifier = 0.0
            grid_label = "Substation within 2km"
        else:
            grid_modifier = -0.05  # Far from substation = slight penalty
            grid_label = "No substation within 2km"

        return {
            "nearest_substation_m": round(nearest_sub) if nearest_sub < 9999 else None,
            "substations_nearby": len(substations),
            "transformers_nearby": len(transformers),
            "grid_reliability_modifier": grid_modifier,
            "grid_label": grid_label
        }
    except Exception as e:
        logger.warning(f"Power infrastructure fetch failed: {e}")
        return {"nearest_substation_m": None, "grid_reliability_modifier": 0.0}


async def estimate_urban_heat_island(lat: float, lon: float) -> dict:
    """
    Estimate Urban Heat Island effect using OpenStreetMap land use data.
    Dense urban areas are 1-3°C warmer than surrounding region.
    """
    try:
        query = f"""
        [out:json][timeout:10];
        (
          way["landuse"~"commercial|industrial|retail"](around:300,{lat},{lon});
          way["building"="yes"](around:200,{lat},{lon});
          way["landuse"="grass"](around:300,{lat},{lon});
          way["leisure"="park"](around:300,{lat},{lon});
        );
        out center;
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(OVERPASS_URL, data={"data": query})
            data = r.json()

        elements = data.get("elements", [])
        urban = sum(1 for e in elements
                   if e.get("tags", {}).get("landuse") in ("commercial", "industrial", "retail")
                   or e.get("tags", {}).get("building") == "yes")
        green = sum(1 for e in elements
                   if e.get("tags", {}).get("landuse") == "grass"
                   or e.get("tags", {}).get("leisure") == "park")

        urban_ratio = urban / max(urban + green, 1)

        if urban_ratio >= 0.8:
            uhi_delta = 2.5
            uhi_label = "Dense urban — high heat island effect"
        elif urban_ratio >= 0.5:
            uhi_delta = 1.5
            uhi_label = "Mixed urban — moderate heat island effect"
        elif urban_ratio >= 0.2:
            uhi_delta = 0.8
            uhi_label = "Suburban — low heat island effect"
        else:
            uhi_delta = 0.2
            uhi_label = "Green/rural area — minimal heat island effect"

        return {
            "uhi_temp_delta_c": uhi_delta,
            "urban_elements": urban,
            "green_elements": green,
            "uhi_label": uhi_label
        }
    except Exception as e:
        logger.warning(f"UHI estimation failed: {e}")
        return {"uhi_temp_delta_c": 1.0, "uhi_label": "Unknown land use"}


def apply_asset_level_adjustments(
    flood_score: float,
    thermal_score: float,
    grid_score: float,
    factors: dict
) -> tuple[float, float, float]:
    """
    Apply asset-level factors to adjust city-level risk scores.
    Returns (adjusted_flood, adjusted_thermal, adjusted_grid).
    """
    water = factors.get("water_proximity", {})
    uhi = factors.get("urban_heat_island", {})
    power = factors.get("power_infrastructure", {})
    elevation = factors.get("elevation_m", 10.0)

    # Flood: adjust for water proximity and elevation
    flood_modifier = water.get("flood_modifier", 0.0)
    # Low elevation = higher flood risk
    if elevation < 2:
        flood_modifier += 0.20
    elif elevation < 5:
        flood_modifier += 0.12
    elif elevation < 10:
        flood_modifier += 0.05
    elif elevation > 50:
        flood_modifier -= 0.08
    adjusted_flood = min(max(round(flood_score + flood_modifier, 3), 0.0), 1.0)

    # Thermal: adjust for Urban Heat Island
    uhi_delta = uhi.get("uhi_temp_delta_c", 1.0)
    thermal_modifier = uhi_delta * 0.03  # Each 1°C UHI = 0.03 score increase
    adjusted_thermal = min(max(round(thermal_score + thermal_modifier, 3), 0.0), 1.0)

    # Grid: adjust for substation proximity
    grid_modifier = power.get("grid_reliability_modifier", 0.0)
    adjusted_grid = min(max(round(grid_score - grid_modifier, 3), 0.05), 1.0)

    return adjusted_flood, adjusted_thermal, adjusted_grid


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in metres between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
