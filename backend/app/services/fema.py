"""
FEMA National Flood Hazard Layer service.
Retrieves flood zone classification for a given lat/lon.
No API key required. Public OpenFEMA service.
"""
import httpx
import logging
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

FEMA_NFHL_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)

# Flood zone to risk score mapping
ZONE_SCORES = {
    "VE": 1.0,   # Coastal high hazard with wave action
    "V":  0.95,
    "AE": 0.88,  # 1% annual chance, base flood elevation
    "A":  0.85,  # 1% annual chance, no BFE
    "AO": 0.75,  # River or stream flood hazard
    "AH": 0.72,  # Ponding flood hazard
    "AR": 0.60,  # Levee restoration zone
    "A99": 0.55,
    "X":  0.15,  # Minimal flood hazard (500-year flood)
    "D":  0.20,  # Undetermined risk
}

ZONE_DESCRIPTIONS = {
    "VE": "Coastal High Hazard Area (wave action)",
    "V":  "Coastal High Hazard Area",
    "AE": "Special Flood Hazard Area (detailed study)",
    "A":  "Special Flood Hazard Area (approximate)",
    "AO": "River/Stream Flood Hazard",
    "AH": "Ponding Flood Hazard",
    "AR": "Levee Restoration Zone",
    "A99": "Protected by levee (under construction)",
    "X":  "Minimal Flood Hazard",
    "D":  "Undetermined Risk Area",
}


async def get_flood_risk(lat: float, lon: float) -> HazardScore:
    """
    Query FEMA NFHL for flood zone at a given coordinate.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        HazardScore for flood risk
    """
    # Create a tiny bounding box (0.001 deg ≈ 100m)
    delta = 0.001
    geometry = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"

    params = {
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "false",
        "f": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(FEMA_NFHL_URL, params=params)
            response.raise_for_status()
            data = response.json()

        features = data.get("features", [])

        if not features:
            # No FEMA data — likely outside US or unmapped area
            return HazardScore(
                score=0.20,
                level="Low",
                confidence="Low",
                details={
                    "fema_zone": "Unknown",
                    "note": "No FEMA flood data available for this location"
                }
            )

        # Get the highest-risk zone from all overlapping features
        best_zone = "X"
        best_score = 0.0
        for feature in features:
            zone = feature.get("attributes", {}).get("FLD_ZONE", "X")
            zone_score = ZONE_SCORES.get(zone, 0.15)
            if zone_score > best_score:
                best_score = zone_score
                best_zone = zone

        return HazardScore(
            score=best_score,
            level=score_to_level(best_score),
            confidence="High",
            details={
                "fema_zone": best_zone,
                "fema_zone_description": ZONE_DESCRIPTIONS.get(best_zone, "Unknown"),
                "sfha": best_zone not in ("X", "D"),
                "source": "FEMA National Flood Hazard Layer"
            }
        )

    except Exception as e:
        logger.warning(f"FEMA service failed: {e}")
        return HazardScore(
            score=0.25,
            level="Low",
            confidence="Low",
            details={"error": "FEMA data temporarily unavailable", "note": str(e)}
        )
