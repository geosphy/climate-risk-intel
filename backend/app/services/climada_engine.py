"""
CLIMADA risk engine for flood and tropical cyclone hazard scoring adjustments.

Computes ±0.15 score adjustments on top of the FEMA/NOAA base scores using:
  - River flood:  CLIMADA data API (ISIMIP-based global river flood hazard)
  - Tropical cyclone: IBTrACS tracks + Holland H08 TropCyclone wind-field model

Both computations are CPU-bound and synchronous. All public functions are async
wrappers that delegate to a thread pool via asyncio.to_thread so the FastAPI
event loop is never blocked.

All failures (missing data, download errors, CLIMADA errors) return a neutral
adjustment of 0.0 with a details note, preserving the FEMA/NOAA base scores.
"""
import asyncio
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# Adjustment bounds — CLAUDE.md specifies ±0.15 for each CLIMADA source
_MAX_ADJ = 0.15
_MIN_ADJ = -0.15

# IBTrACS year range: 40 years gives statistically stable exceedance probabilities
# without using data from before modern satellite coverage (post-1980).
_TRACK_YEAR_RANGE = (1980, 2020)

# Return periods used for hazard intensity queries (years)
_RETURN_PERIODS = (10, 50, 100)

# Radius (decimal degrees ≈ 550 km) used to pre-filter IBTrACS tracks.
# Tracks outside this radius never produce significant wind at the centroid
# and can be skipped to save TropCyclone computation time.
_TRACK_FILTER_DEG = 5.0

# Timeout for CLIMADA thread-pool workers (seconds).
_TIMEOUT_S = 120.0


# ---------------------------------------------------------------------------
# Public async interface
# ---------------------------------------------------------------------------

async def get_flood_adjustment(lat: float, lon: float) -> tuple[float, dict]:
    """
    Compute a CLIMADA river-flood adjustment for a lat/lon point.

    Downloads and caches the ISIMIP river-flood hazard for the relevant
    country on first call. Subsequent calls use the cached HDF5 file.

    Returns
    -------
    (adjustment, details) where adjustment ∈ [-0.15, +0.15].
    """
    from app.core.config import get_settings
    if not get_settings().enable_climada:
        return 0.0, {"climada": "disabled (enable_climada=False)"}

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_flood_adj_sync, lat, lon),
            timeout=_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("CLIMADA flood computation timed out after %ss", _TIMEOUT_S)
        return 0.0, {"climada": "timeout"}
    except Exception as exc:
        logger.warning("CLIMADA flood engine failed: %s", exc)
        return 0.0, {"climada": f"error: {type(exc).__name__}"}


async def get_storm_adjustment(lat: float, lon: float) -> tuple[float, dict]:
    """
    Compute a CLIMADA tropical-cyclone wind adjustment for a lat/lon point.

    Downloads IBTrACS (≈150 MB, cached) and computes TC wind-field
    exceedance intensities at the point using the Holland H08 model.

    Returns
    -------
    (adjustment, details) where adjustment ∈ [-0.15, +0.15].
    """
    from app.core.config import get_settings
    if not get_settings().enable_climada:
        return 0.0, {"climada": "disabled (enable_climada=False)"}

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_storm_adj_sync, lat, lon),
            timeout=_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("CLIMADA storm computation timed out after %ss", _TIMEOUT_S)
        return 0.0, {"climada": "timeout"}
    except Exception as exc:
        logger.warning("CLIMADA storm engine failed: %s", exc)
        return 0.0, {"climada": f"error: {type(exc).__name__}"}


# ---------------------------------------------------------------------------
# Synchronous CLIMADA workers (run in thread pool)
# ---------------------------------------------------------------------------

def _flood_adj_sync(lat: float, lon: float) -> tuple[float, dict]:
    """
    Download and query CLIMADA river-flood hazard for the country at lat/lon.

    Uses the CLIMADA data API to fetch the ISIMIP 2b river flood hazard set
    for the relevant ISO-3 country, then picks the nearest centroid and reads
    flood-depth exceedance intensities at 10-, 50-, and 100-year return periods.

    Adjustment mapping (100-year flood depth in metres):
        > 2.0 m  → +0.15   (severe — much wetter than FEMA zone implies)
        1.0–2.0  → +0.10
        0.5–1.0  → +0.05
        0.1–0.5  → 0.00   (neutral)
        < 0.1    → -0.05   (drier — FEMA zone may overstate risk)
    """
    try:
        import numpy as np
        from climada.util.api_client import Client
        import reverse_geocoder
        import pycountry
    except ImportError as exc:
        logger.warning("CLIMADA flood: missing dependency (%s)", exc)
        return 0.0, {"climada": "dependency missing"}

    # Resolve country ISO-3 for the CLIMADA API query
    rg = reverse_geocoder.search([(lat, lon)], verbose=False)
    alpha2 = rg[0].get("cc", "US")
    country = pycountry.countries.get(alpha_2=alpha2)
    iso3 = country.alpha_3 if country else "USA"

    try:
        api = Client()
        flood_haz = api.get_hazard(
            "river_flood",
            properties={"country_iso3alpha": iso3},
        )
    except Exception as exc:
        logger.warning("CLIMADA flood API query failed for %s: %s", iso3, exc)
        return 0.0, {"climada": f"API error: {type(exc).__name__}", "country": iso3}

    # Find the centroid closest to the requested point
    dists = np.hypot(flood_haz.centroids.lat - lat, flood_haz.centroids.lon - lon)
    nearest_idx = int(np.argmin(dists))
    dist_deg = float(dists[nearest_idx])

    # If the nearest centroid is more than 1° away the hazard data is sparse
    # for this location — return neutral
    if dist_deg > 1.0:
        return 0.0, {
            "climada": "nearest centroid too distant",
            "dist_deg": round(dist_deg, 3),
            "country": iso3,
        }

    # Exceedance intensities: shape (len(return_periods), num_centroids)
    inten_stats = flood_haz.local_exceedance_inten(return_periods=list(_RETURN_PERIODS))
    depth_10yr  = float(inten_stats[0, nearest_idx])   # metres
    depth_50yr  = float(inten_stats[1, nearest_idx])
    depth_100yr = float(inten_stats[2, nearest_idx])

    adj = _depth_to_adjustment(depth_100yr)
    return adj, {
        "climada": "river_flood",
        "country": iso3,
        "flood_depth_10yr_m":  round(depth_10yr,  2),
        "flood_depth_50yr_m":  round(depth_50yr,  2),
        "flood_depth_100yr_m": round(depth_100yr, 2),
        "nearest_centroid_deg": round(dist_deg, 4),
        "adjustment": adj,
    }


def _storm_adj_sync(lat: float, lon: float) -> tuple[float, dict]:
    """
    Load IBTrACS tracks and compute TropCyclone wind-speed exceedance at lat/lon.

    Downloads IBTrACS.ALL on first call (~150 MB, cached in ~/climada/data).
    Uses the Holland H08 parametric model to compute 1-minute sustained wind
    speeds (m/s) at a single centroid, then derives exceedance intensities at
    10-, 50-, and 100-year return periods.

    Adjustment mapping (100-year wind speed in m/s):
        > 60 m/s  → +0.15   (Category 4–5 equivalent)
        50–60     → +0.12
        40–50     → +0.08
        30–40     → 0.00   (neutral)
        20–30     → -0.05
        < 20      → -0.10   (low TC exposure)
    """
    try:
        import numpy as np
        from climada.hazard.tc_tracks import TCTracks
        from climada.hazard import TropCyclone, Centroids
    except ImportError as exc:
        logger.warning("CLIMADA storm: missing dependency (%s)", exc)
        return 0.0, {"climada": "dependency missing"}

    basin = _basin_from_latlon(lat, lon)

    # Load IBTrACS tracks for the relevant basin
    logger.info(
        "Loading IBTrACS tracks for basin=%s, years=%s-%s (cached after first call)",
        basin, *_TRACK_YEAR_RANGE,
    )
    tracks = TCTracks.from_ibtracs_netcdf(
        basin=basin,
        year_range=_TRACK_YEAR_RANGE,
        estimate_missing=True,
    )

    if not tracks.data:
        logger.warning("IBTrACS returned no tracks for basin=%s", basin)
        return 0.0, {"climada": "no tracks", "basin": basin}

    # Pre-filter to tracks that ever pass within _TRACK_FILTER_DEG of the point.
    # This greatly reduces the TropCyclone computation time without changing the
    # exceedance statistics at the centroid.
    tracks = _filter_tracks_near_point(tracks, lat, lon, _TRACK_FILTER_DEG)
    n_nearby = len(tracks.data)
    logger.debug("Tracks within %.1f° of (%.4f, %.4f): %d", _TRACK_FILTER_DEG, lat, lon, n_nearby)

    if n_nearby == 0:
        # No TC has ever passed near this location — large negative adjustment
        return -0.10, {
            "climada": "tropical_cyclone",
            "basin": basin,
            "tracks_near_point": 0,
            "wind_speed_100yr_ms": 0.0,
            "adjustment": -0.10,
        }

    # Build single-centroid exposure at the requested point
    import numpy as np
    centroids = Centroids(
        lat=np.array([lat]),
        lon=np.array([lon]),
    )

    # Compute TC wind fields using the Holland H08 parametric model
    tc_haz = TropCyclone.from_tracks(
        tracks,
        centroids=centroids,
        model="H08",
        max_dist_eye_km=500,   # only compute for tracks that pass within 500 km
    )

    if tc_haz.intensity.nnz == 0:
        return -0.10, {
            "climada": "tropical_cyclone",
            "basin": basin,
            "tracks_near_point": n_nearby,
            "note": "no non-zero wind intensity at centroid",
            "adjustment": -0.10,
        }

    # Exceedance intensities: shape (len(return_periods), 1)
    inten_stats = tc_haz.local_exceedance_inten(return_periods=list(_RETURN_PERIODS))
    wind_10yr  = float(inten_stats[0, 0])   # m/s
    wind_50yr  = float(inten_stats[1, 0])
    wind_100yr = float(inten_stats[2, 0])

    adj = _wind_to_adjustment(wind_100yr)
    return adj, {
        "climada": "tropical_cyclone",
        "basin": basin,
        "tracks_near_point":  n_nearby,
        "wind_speed_10yr_ms":  round(wind_10yr,  1),
        "wind_speed_50yr_ms":  round(wind_50yr,  1),
        "wind_speed_100yr_ms": round(wind_100yr, 1),
        "adjustment": adj,
    }


# ---------------------------------------------------------------------------
# Adjustment mapping helpers
# ---------------------------------------------------------------------------

def _depth_to_adjustment(depth_100yr_m: float) -> float:
    """Map CLIMADA 100-year river flood depth (metres) → score adjustment."""
    if depth_100yr_m > 2.0:
        return 0.15
    elif depth_100yr_m > 1.0:
        return 0.10
    elif depth_100yr_m > 0.5:
        return 0.05
    elif depth_100yr_m > 0.1:
        return 0.00
    else:
        return -0.05


def _wind_to_adjustment(wind_100yr_ms: float) -> float:
    """Map CLIMADA 100-year TC wind speed (m/s) → score adjustment."""
    if wind_100yr_ms > 60:
        return 0.15
    elif wind_100yr_ms > 50:
        return 0.12
    elif wind_100yr_ms > 40:
        return 0.08
    elif wind_100yr_ms > 30:
        return 0.00
    elif wind_100yr_ms > 20:
        return -0.05
    else:
        return -0.10


# ---------------------------------------------------------------------------
# Geography helpers
# ---------------------------------------------------------------------------

def _basin_from_latlon(lat: float, lon: float) -> str:
    """
    Return the IBTrACS basin code for a lat/lon coordinate.

    Basin codes (IBTrACS convention):
        NA – North Atlantic          (default for US locations)
        EP – Eastern North Pacific
        WP – Western North Pacific
        NI – North Indian Ocean
        SI – South Indian Ocean
        SP – South Pacific
        SA – South Atlantic
    """
    if lat >= 0:
        if -100 <= lon <= 0:
            return "NA"
        if -180 <= lon < -100:
            return "EP"
        if 100 <= lon <= 180:
            return "WP"
        if 40 <= lon < 100:
            return "NI"
    else:
        if 20 <= lon <= 135:
            return "SI"
        if 135 < lon <= 180 or -180 <= lon < -70:
            return "SP"
        if -70 <= lon < 20:
            return "SA"
    return "NA"  # catch-all


def _filter_tracks_near_point(
    tracks: "TCTracks",
    lat: float,
    lon: float,
    radius_deg: float,
) -> "TCTracks":
    """
    Return a new TCTracks containing only tracks whose closest position
    to (lat, lon) is within radius_deg degrees (great-circle approximation).
    """
    import numpy as np
    from climada.hazard.tc_tracks import TCTracks as TC

    kept = []
    for track in tracks.data:
        t_lat = track.lat.values
        t_lon = track.lon.values
        # Wrap longitude difference to [-180, 180]
        dlon = ((t_lon - lon) + 180) % 360 - 180
        dlat = t_lat - lat
        min_dist = float(np.min(np.hypot(dlat, dlon)))
        if min_dist <= radius_deg:
            kept.append(track)

    result = TC()
    result.data = kept
    return result
