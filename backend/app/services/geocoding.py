"""
Geocoding service using OpenStreetMap Nominatim.
Converts addresses and zip codes to lat/lon coordinates.
No API key required. Rate limit: 1 req/sec.
"""
import httpx
import asyncio
import logging
from app.models.schemas import GeocodeResult

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "ClimateRiskIntel/1.0 (open-source climate risk platform)"
}


async def geocode_address(address: str) -> GeocodeResult:
    """
    Convert an address or zip code to latitude/longitude.

    Args:
        address: Street address, city/state, or zip code

    Returns:
        GeocodeResult with lat, lon, and canonical address

    Raises:
        ValueError: If address cannot be geocoded
    """
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }

    # Nominatim requires 1 second between requests
    await asyncio.sleep(1)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(NOMINATIM_URL, params=params, headers=HEADERS)
        response.raise_for_status()
        results = response.json()

    if not results:
        raise ValueError(f"Could not geocode address: {address}")

    result = results[0]
    address_data = result.get("address", {})
    country_code = address_data.get("country_code", "us").upper()

    return GeocodeResult(
        latitude=float(result["lat"]),
        longitude=float(result["lon"]),
        canonical_address=result["display_name"],
        country_code=country_code,
    )
