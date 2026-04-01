"""
Integration tests for the /api/risk endpoint.
Uses httpx AsyncClient and respx for mocking external APIs.
Test address: Houston, TX 77002 (high flood + storm risk city)
"""
import pytest
import respx
import httpx
from httpx import AsyncClient
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


HOUSTON_TX = "Houston, TX 77002"

# --- Mock responses ---

NOMINATIM_MOCK = [
    {
        "lat": "29.7604",
        "lon": "-95.3698",
        "display_name": "Houston, Harris County, Texas, United States",
        "address": {"country_code": "us"}
    }
]

FEMA_MOCK = {
    "features": [
        {"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T"}}
    ]
}


@pytest.mark.anyio
@respx.mock
async def test_risk_endpoint_returns_report():
    """Test that /api/risk returns a valid RiskReport for Houston TX."""
    # Mock Nominatim
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=NOMINATIM_MOCK)
    )

    # Mock FEMA
    respx.get("https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query").mock(
        return_value=httpx.Response(200, json=FEMA_MOCK)
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/risk",
            json={"address": HOUSTON_TX, "asset_type": "building"}
        )

    assert response.status_code == 200
    data = response.json()

    # Check all required fields are present
    assert data["address"] == HOUSTON_TX
    assert data["latitude"] == pytest.approx(29.7604, abs=0.01)
    assert data["longitude"] == pytest.approx(-95.3698, abs=0.01)

    # Check risk scores are within valid range
    for hazard in ["flood_risk", "heat_risk", "storm_risk", "overall_risk"]:
        assert hazard in data
        assert 0.0 <= data[hazard]["score"] <= 1.0
        assert data[hazard]["level"] in ["Low", "Medium", "High", "Extreme"]

    # Houston should have high flood risk (AE zone)
    assert data["flood_risk"]["score"] >= 0.70
    assert data["flood_risk"]["details"]["fema_zone"] == "AE"

    # Check data sources are listed
    assert len(data["data_sources"]) > 0


@pytest.mark.anyio
async def test_health_endpoint():
    """Test that /api/health returns 200."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_invalid_address_returns_422():
    """Test that an unresolvable address returns a 422 error."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/risk",
            json={"address": "XYZXYZXYZ_NOT_A_REAL_PLACE_12345"}
        )
    # Should return 422 Unprocessable Entity
    assert response.status_code == 422
