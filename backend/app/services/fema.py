"""
FEMA National Flood Hazard Layer (NFHL) service.
Retrieves flood zone classification for a given lat/lon.
No API key required. Uses the public ArcGIS REST endpoint.

Primary source:   FEMA NFHL ArcGIS REST service (hazards.fema.gov)
Fallback source:  Esri-hosted NFHL copy on ArcGIS Online (always reachable)

Both return the same NFHL field schema (FLD_ZONE, ZONE_SUBTY, SFHA_TF).
"""
import httpx
import logging
from app.models.schemas import HazardScore, score_to_level

logger = logging.getLogger(__name__)

# Official FEMA NFHL — authoritative, most up-to-date, but occasionally unreachable
# due to FEMA infrastructure maintenance or network-level TLS restrictions.
FEMA_NFHL_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)

# Esri-hosted mirror of the NFHL — slightly less current but always available.
# Hosted on ArcGIS Online Living Atlas; updated periodically from FEMA source data.
ESRI_NFHL_URL = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services"
    "/USA_Flood_Hazard_Reduced_Set_gdb/FeatureServer/0/query"
)

# ±0.005° ≈ 500 m — large enough to catch zone polygon edges at the point,
# small enough to stay within the local flood zone.
_BBOX_DELTA = 0.005

# ---------------------------------------------------------------------------
# Flood zone risk scores
# ---------------------------------------------------------------------------

ZONE_SCORES: dict[str, float] = {
    "VE":  1.00,  # Coastal high hazard with wave action (>3 ft)
    "V":   0.95,  # Coastal high hazard
    "AE":  0.88,  # Special flood hazard (detailed study, base flood elevation known)
    "A":   0.85,  # Special flood hazard (approximate, no BFE)
    "AO":  0.75,  # River/stream flood hazard (shallow, 1–3 ft avg depth)
    "AH":  0.72,  # Ponding flood hazard (shallow, avg depth ≤ 3 ft)
    "AR":  0.60,  # Levee restoration zone (temporary designation)
    "A99": 0.55,  # Protected by levee under construction
    "X":   0.15,  # Minimal flood hazard (0.2% annual chance — 500-yr flood)
    "D":   0.20,  # Undetermined risk (no study performed)
}

ZONE_DESCRIPTIONS: dict[str, str] = {
    "VE":  "Coastal High Hazard Area (wave action > 3 ft)",
    "V":   "Coastal High Hazard Area",
    "AE":  "Special Flood Hazard Area — detailed study (BFE known)",
    "A":   "Special Flood Hazard Area — approximate",
    "AO":  "River/Stream Flood Hazard (shallow, avg 1–3 ft depth)",
    "AH":  "Ponding Flood Hazard (shallow, avg ≤ 3 ft depth)",
    "AR":  "Levee Restoration Zone",
    "A99": "Protected by Levee Under Construction",
    "X":   "Minimal Flood Hazard (0.2% annual chance)",
    "D":   "Undetermined Risk Area (no FEMA study performed)",
}

# Zones that place a property inside the Special Flood Hazard Area (SFHA),
# triggering mandatory flood insurance for federally-backed mortgages.
_SFHA_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}


def _build_params(lat: float, lon: float) -> dict:
    """Build the shared ArcGIS query parameters for a bounding-box spatial query."""
    bbox = (
        f"{lon - _BBOX_DELTA},{lat - _BBOX_DELTA},"
        f"{lon + _BBOX_DELTA},{lat + _BBOX_DELTA}"
    )
    return {
        "geometry":     bbox,
        "geometryType": "esriGeometryEnvelope",
        "inSR":         "4326",   # declare input as WGS-84 lat/lon
        "spatialRel":   "esriSpatialRelIntersects",
        "outFields":    "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "false",
        "f":            "json",
    }


def _parse_features(features: list, source_label: str) -> HazardScore:
    """
    Select the highest-risk flood zone from a list of ArcGIS feature records
    and return a scored HazardScore.
    """
    best_zone  = "X"
    best_score = ZONE_SCORES["X"]
    best_subty = ""

    for feature in features:
        attrs = feature.get("attributes", {})
        zone  = (attrs.get("FLD_ZONE") or "X").strip().upper()
        score = ZONE_SCORES.get(zone, ZONE_SCORES["X"])
        if score > best_score:
            best_score = score
            best_zone  = zone
            best_subty = attrs.get("ZONE_SUBTY") or ""

    return HazardScore(
        score=best_score,
        level=score_to_level(best_score),
        confidence="High",
        details={
            "fema_zone":             best_zone,
            "fema_zone_description": ZONE_DESCRIPTIONS.get(best_zone, "Unknown"),
            "zone_subtype":          best_subty,
            "sfha":                  best_zone in _SFHA_ZONES,
            "zones_found":           len(features),
            "source":                source_label,
        },
    )


async def get_flood_risk(lat: float, lon: float) -> HazardScore:
    """
    Query the FEMA NFHL for the flood zone at a given coordinate.

    Tries the official FEMA ArcGIS service first; falls back to the
    Esri-hosted NFHL mirror on failure or timeout.

    Returns a HazardScore with score 0.0–1.0, risk level, and FEMA zone details.
    """
    params = _build_params(lat, lon)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # --- Primary: official FEMA endpoint ---
        try:
            response = await client.get(FEMA_NFHL_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise ValueError(f"FEMA API error: {data['error']}")

            features = data.get("features", [])
            logger.debug(
                f"FEMA NFHL returned {len(features)} features for ({lat:.4f}, {lon:.4f})"
            )
            return _parse_features(features, "FEMA National Flood Hazard Layer")

        except Exception as primary_exc:
            logger.warning(
                f"FEMA NFHL primary endpoint unavailable ({type(primary_exc).__name__}); "
                f"falling back to Esri-hosted NFHL"
            )

        # --- Fallback: Esri-hosted NFHL mirror ---
        try:
            response = await client.get(ESRI_NFHL_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                raise ValueError(f"Esri NFHL API error: {data['error']}")

            features = data.get("features", [])
            logger.debug(
                f"Esri NFHL fallback returned {len(features)} features for ({lat:.4f}, {lon:.4f})"
            )
            return _parse_features(features, "FEMA NFHL via Esri ArcGIS Online")

        except Exception as fallback_exc:
            logger.warning(f"Esri NFHL fallback also failed: {fallback_exc}")

    # Both sources failed — return a conservative low-confidence default
    return HazardScore(
        score=0.25,
        level="Low",
        confidence="Low",
        details={
            "fema_zone":  "Unknown",
            "sfha":       False,
            "note":       "Flood data temporarily unavailable from both FEMA and Esri sources",
        },
    )
