"""
Asset-level enrichment service using OpenStreetMap Overpass API and Open-Meteo elevation.
"""
import httpx
import math
import logging
import urllib.parse

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


async def get_asset_level_factors(lat: float, lon: float) -> dict:
    import asyncio
    elevation_task = asyncio.create_task(get_elevation(lat, lon))
    water_task     = asyncio.create_task(get_water_proximity(lat, lon))
    power_task     = asyncio.create_task(get_power_infrastructure(lat, lon))
    uhi_task       = asyncio.create_task(estimate_urban_heat_island(lat, lon))

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
        return 10.0


async def _overpass_query(query: str) -> list:
    """Execute an Overpass API query and return elements. Uses POST with form data."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                OVERPASS_URL,
                content=query.encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"data": query}
            )
            if r.status_code != 200 or not r.text.strip():
                return []
            return r.json().get("elements", [])
    except Exception as e:
        logger.warning(f"Overpass query failed: {e}")
        return []


async def get_water_proximity(lat: float, lon: float) -> dict:
    """Find water bodies near the asset using Overpass API."""
    query = (
        f"[out:json][timeout:15];"
        f"("
        f'way["natural"="water"](around:600,{lat},{lon});'
        f'way["waterway"~"river|stream|canal"](around:600,{lat},{lon});'
        f");"
        f"out center;"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if r.status_code != 200 or not r.text.strip():
                return {"nearest_water_m": 999, "water_bodies": 0, "flood_modifier": 0.0, "risk_label": "No data"}
            elements = r.json().get("elements", [])

        if not elements:
            return {"nearest_water_m": 999, "water_bodies": 0, "flood_modifier": 0.0, "risk_label": "No water within 600m"}

        min_dist = 999.0
        for el in elements:
            c = el.get("center", {})
            if c:
                dist = _haversine_m(lat, lon, c.get("lat", lat), c.get("lon", lon))
                min_dist = min(min_dist, dist)

        if min_dist <= 50:
            modifier, label = 0.25, "Adjacent to water (<50m)"
        elif min_dist <= 150:
            modifier, label = 0.18, "Very close to water (<150m)"
        elif min_dist <= 300:
            modifier, label = 0.10, "Near water body (<300m)"
        elif min_dist <= 600:
            modifier, label = 0.05, "Water body within 600m"
        else:
            modifier, label = 0.0, "No water within 600m"

        return {
            "nearest_water_m": round(min_dist),
            "water_bodies_count": len(elements),
            "flood_modifier": modifier,
            "risk_label": label
        }
    except Exception as e:
        logger.warning(f"Water proximity fetch failed: {e}")
        return {"nearest_water_m": 999, "water_bodies": 0, "flood_modifier": 0.0, "risk_label": "Unavailable"}


async def get_power_infrastructure(lat: float, lon: float) -> dict:
    """Find power substations near the asset."""
    query = (
        f"[out:json][timeout:15];"
        f"("
        f'node["power"="substation"](around:2000,{lat},{lon});'
        f");"
        f"out;"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if r.status_code != 200 or not r.text.strip():
                return {"nearest_substation_m": None, "grid_reliability_modifier": 0.0, "grid_label": "No data"}
            elements = r.json().get("elements", [])

        if not elements:
            return {"nearest_substation_m": None, "grid_reliability_modifier": -0.03, "grid_label": "No substation within 2km"}

        min_dist = min(
            _haversine_m(lat, lon, el.get("lat", lat), el.get("lon", lon))
            for el in elements
        )

        if min_dist <= 200:
            modifier, label = 0.10, "Substation within 200m"
        elif min_dist <= 500:
            modifier, label = 0.05, "Substation within 500m"
        elif min_dist <= 1000:
            modifier, label = 0.02, "Substation within 1km"
        else:
            modifier, label = -0.03, "Substation 1-2km away"

        return {
            "nearest_substation_m": round(min_dist),
            "substations_nearby": len(elements),
            "grid_reliability_modifier": modifier,
            "grid_label": label
        }
    except Exception as e:
        logger.warning(f"Power infrastructure fetch failed: {e}")
        return {"nearest_substation_m": None, "grid_reliability_modifier": 0.0, "grid_label": "Unavailable"}


async def estimate_urban_heat_island(lat: float, lon: float) -> dict:
    """Estimate UHI effect from local land use."""
    query = (
        f"[out:json][timeout:15];"
        f"("
        f'way["landuse"~"commercial|industrial|retail"](around:400,{lat},{lon});'
        f'way["landuse"~"grass|forest|meadow"](around:400,{lat},{lon});'
        f'way["leisure"="park"](around:400,{lat},{lon});'
        f");"
        f"out center;"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if r.status_code != 200 or not r.text.strip():
                return {"uhi_temp_delta_c": 1.5, "uhi_label": "Default urban estimate"}
            elements = r.json().get("elements", [])

        urban = sum(1 for e in elements
                    if e.get("tags", {}).get("landuse") in ("commercial", "industrial", "retail"))
        green = sum(1 for e in elements
                    if e.get("tags", {}).get("landuse") in ("grass", "forest", "meadow")
                    or e.get("tags", {}).get("leisure") == "park")
        total = urban + green

        if total == 0:
            return {"uhi_temp_delta_c": 1.0, "uhi_label": "No land use data", "urban": 0, "green": 0}

        urban_ratio = urban / total
        if urban_ratio >= 0.8:
            delta, label = 2.5, "Dense urban — high UHI"
        elif urban_ratio >= 0.5:
            delta, label = 1.5, "Mixed urban — moderate UHI"
        elif urban_ratio >= 0.2:
            delta, label = 0.8, "Suburban — low UHI"
        else:
            delta, label = 0.2, "Green area — minimal UHI"

        return {"uhi_temp_delta_c": delta, "uhi_label": label, "urban": urban, "green": green}

    except Exception as e:
        logger.warning(f"UHI estimation failed: {e}")
        return {"uhi_temp_delta_c": 1.0, "uhi_label": "Unavailable"}


def apply_asset_level_adjustments(
    flood_score: float, thermal_score: float, grid_score: float, factors: dict
) -> tuple:
    water = factors.get("water_proximity", {})
    uhi   = factors.get("urban_heat_island", {})
    power = factors.get("power_infrastructure", {})
    elev  = factors.get("elevation_m", 10.0)

    # Flood: water proximity + elevation
    flood_mod = water.get("flood_modifier", 0.0)
    if elev < 2:    flood_mod += 0.20
    elif elev < 5:  flood_mod += 0.12
    elif elev < 10: flood_mod += 0.05
    elif elev > 50: flood_mod -= 0.08
    adj_flood = round(min(max(flood_score + flood_mod, 0.0), 1.0), 3)

    # Thermal: UHI
    uhi_delta = uhi.get("uhi_temp_delta_c", 1.0)
    thermal_mod = uhi_delta * 0.03
    adj_thermal = round(min(max(thermal_score + thermal_mod, 0.0), 1.0), 3)

    # Grid: substation proximity
    grid_mod = power.get("grid_reliability_modifier", 0.0)
    adj_grid = round(min(max(grid_score - grid_mod, 0.05), 1.0), 3)

    return adj_flood, adj_thermal, adj_grid


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2-lat1)/2)**2 +
         math.cos(phi1)*math.cos(phi2)*math.sin(math.radians(lon2-lon1)/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
