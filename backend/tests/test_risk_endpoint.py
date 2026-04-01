"""
Integration tests for the /api/risk endpoint, FEMA flood zone service,
NOAA heat/storm services, and World Bank CCKP service.
Uses httpx AsyncClient and respx for mocking external APIs.
Test address: Houston, TX 77002 (high flood + storm risk city)
"""
import re
import pytest
import respx
import httpx
from httpx import AsyncClient
from app.main import app
from app.services.fema import (
    FEMA_NFHL_URL,
    ESRI_NFHL_URL,
    ZONE_SCORES,
    _parse_features,
    _build_params,
)
from app.services.noaa import (
    GHCND_STATIONS_URL,
    NCEI_V1,
    _haversine_km,
    _nearest_station,
    _is_hurricane_coast,
    _parse_ncei_ndjson,
    _score_heat,
    _score_storm,
)
from app.services.world_bank import (
    _FUTURE,
    _BASELINE,
    CCKP_BASE,
    _extract_value,
    adjust_flood_score_for_climate,
    adjust_heat_score_for_climate,
)

# Exact CCKP URLs used by the service for USA (Houston resolves to USA)
_CCKP_FUTURE_URL   = f"{CCKP_BASE}/{_FUTURE}/USA"
_CCKP_BASELINE_URL = f"{CCKP_BASE}/{_BASELINE}/USA"


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
        "address": {"country_code": "us"},
    }
]

FEMA_MOCK_AE = {
    "features": [
        {"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": "1% Annual Chance Flood Hazard", "SFHA_TF": "T"}}
    ]
}
FEMA_MOCK_VE = {
    "features": [
        {"attributes": {"FLD_ZONE": "VE", "ZONE_SUBTY": "Coastal High Hazard", "SFHA_TF": "T"}},
        {"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T"}},
    ]
}
FEMA_MOCK_X = {"features": [
    {"attributes": {"FLD_ZONE": "X", "ZONE_SUBTY": "0.2 Percent Annual Chance", "SFHA_TF": "F"}}
]}
FEMA_MOCK_EMPTY = {"features": []}
# Keep old name as alias for the main endpoint test
FEMA_MOCK = FEMA_MOCK_AE

CCKP_FUTURE_MOCK = {
    "metadata": {"apiVersion": "v1", "status": "success", "messages": []},
    "data": {
        "tas": {"USA": {"2040-07": 12.03}},
        "pr":  {"USA": {"2040-07": 851.71}},
    },
}

CCKP_BASELINE_MOCK = {
    "metadata": {"apiVersion": "v1", "status": "success", "messages": []},
    "data": {
        "tas": {"USA": {"1995-07": 10.23}},
        "pr":  {"USA": {"1995-07": 810.93}},
    },
}

CCKP_EMPTY_MOCK = {
    "metadata": {"apiVersion": "v1", "status": "success", "messages": []},
    "data": [],
}


# ---------------------------------------------------------------------------
# /api/risk endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@respx.mock
async def test_risk_endpoint_returns_report():
    """Test that /api/risk returns a valid RiskReport for Houston TX."""
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=NOMINATIM_MOCK)
    )
    respx.get("https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query").mock(
        return_value=httpx.Response(200, json=FEMA_MOCK)
    )
    # Mock CCKP future + baseline endpoints (exact URLs, query params ignored)
    respx.get(re.compile(r".*2040-2059.*")).mock(
        return_value=httpx.Response(200, json=CCKP_FUTURE_MOCK)
    )
    respx.get(re.compile(r".*1995-2014.*")).mock(
        return_value=httpx.Response(200, json=CCKP_BASELINE_MOCK)
    )
    # NOAA stations — return empty so the service falls back gracefully
    respx.get(re.compile(r".*ncei\.noaa\.gov.*")).mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/risk",
            json={"address": HOUSTON_TX, "asset_type": "building"},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["address"] == HOUSTON_TX
    assert data["latitude"] == pytest.approx(29.7604, abs=0.01)
    assert data["longitude"] == pytest.approx(-95.3698, abs=0.01)

    for hazard in ["flood_risk", "heat_risk", "storm_risk", "overall_risk"]:
        assert hazard in data
        assert 0.0 <= data[hazard]["score"] <= 1.0
        assert data[hazard]["level"] in ["Low", "Medium", "High", "Extreme"]

    # Houston should have high flood risk (FEMA AE zone)
    assert data["flood_risk"]["score"] >= 0.70
    assert data["flood_risk"]["details"]["fema_zone"] == "AE"

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
            json={"address": "XYZXYZXYZ_NOT_A_REAL_PLACE_12345"},
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# World Bank CCKP unit tests
# ---------------------------------------------------------------------------

class TestExtractValue:
    def test_happy_path(self):
        data = {"tas": {"USA": {"2040-07": 12.03}}}
        assert _extract_value(data, "tas", "USA") == pytest.approx(12.03)

    def test_missing_variable(self):
        data = {"pr": {"USA": {"2040-07": 851.71}}}
        assert _extract_value(data, "tas", "USA") is None

    def test_missing_country(self):
        data = {"tas": {"GBR": {"2040-07": 9.50}}}
        assert _extract_value(data, "tas", "USA") is None

    def test_empty_list_response(self):
        """CCKP returns [] (not {}) for unknown country codes."""
        assert _extract_value([], "tas", "XXX") is None

    def test_empty_dict_response(self):
        assert _extract_value({}, "tas", "USA") is None


class TestScoreAdjustments:
    def test_flood_increases_on_heavy_rain(self):
        proj = {"precip_change_pct": 15.0}
        assert adjust_flood_score_for_climate(0.50, proj) == pytest.approx(0.60)

    def test_flood_increases_on_moderate_rain(self):
        proj = {"precip_change_pct": 7.0}
        assert adjust_flood_score_for_climate(0.50, proj) == pytest.approx(0.55)

    def test_flood_decreases_on_drying(self):
        proj = {"precip_change_pct": -15.0}
        assert adjust_flood_score_for_climate(0.50, proj) == pytest.approx(0.45)

    def test_flood_unchanged_on_small_change(self):
        proj = {"precip_change_pct": 3.0}
        assert adjust_flood_score_for_climate(0.50, proj) == pytest.approx(0.50)

    def test_flood_capped_at_1(self):
        proj = {"precip_change_pct": 20.0}
        assert adjust_flood_score_for_climate(0.95, proj) == pytest.approx(1.0)

    def test_heat_increases_with_warming(self):
        proj = {"temp_increase_c": 2.0}
        assert adjust_heat_score_for_climate(0.50, proj) == pytest.approx(0.66)

    def test_heat_adjustment_capped_at_plus_20(self):
        # 10 °C * 0.08 = 0.80, but cap is 0.20
        proj = {"temp_increase_c": 10.0}
        assert adjust_heat_score_for_climate(0.50, proj) == pytest.approx(0.70)

    def test_heat_capped_at_1(self):
        proj = {"temp_increase_c": 3.0}
        assert adjust_heat_score_for_climate(0.90, proj) == pytest.approx(1.0)

    def test_default_used_when_key_missing(self):
        # No temp_increase_c key → default 1.5 °C → +0.12
        assert adjust_heat_score_for_climate(0.50, {}) == pytest.approx(0.62)


@pytest.mark.anyio
@respx.mock
async def test_world_bank_projections_usa():
    """Test get_climate_projections returns correct anomaly for USA."""
    from app.services.world_bank import get_climate_projections

    respx.get(re.compile(r".*2040-2059.*")).mock(
        return_value=httpx.Response(200, json=CCKP_FUTURE_MOCK)
    )
    respx.get(re.compile(r".*1995-2014.*")).mock(
        return_value=httpx.Response(200, json=CCKP_BASELINE_MOCK)
    )

    result = await get_climate_projections(29.7604, -95.3698)

    assert result["country_code"] == "USA"
    assert result["temp_increase_c"] == pytest.approx(1.8, abs=0.05)   # 12.03 - 10.23
    assert result["precip_change_pct"] == pytest.approx(5.0, abs=0.5)  # (851.71-810.93)/810.93*100
    assert result["scenario"] == "ssp245"
    assert result["source"] == "World Bank Climate Change Knowledge Portal"


@pytest.mark.anyio
@respx.mock
async def test_world_bank_falls_back_on_empty_data():
    """CCKP returns [] for unknown ISO3 codes — service should use defaults."""
    from app.services.world_bank import get_climate_projections

    respx.get(re.compile(r".*cckpapi\.worldbank\.org.*")).mock(
        return_value=httpx.Response(200, json=CCKP_EMPTY_MOCK)
    )

    # Use coordinates that map to a real country (USA) but mock returns empty data
    result = await get_climate_projections(29.7604, -95.3698)

    assert result["temp_increase_c"] == pytest.approx(1.5)
    assert result["precip_change_pct"] == pytest.approx(0.0)


@pytest.mark.anyio
@respx.mock
async def test_world_bank_falls_back_on_http_error():
    """Network failure should return safe defaults, not raise."""
    from app.services.world_bank import get_climate_projections

    respx.get(re.compile(r".*cckpapi\.worldbank\.org.*")).mock(
        return_value=httpx.Response(500)
    )

    result = await get_climate_projections(29.7604, -95.3698)

    assert result["temp_increase_c"] == pytest.approx(1.5)
    assert "note" in result


# ---------------------------------------------------------------------------
# FEMA flood zone service unit tests
# ---------------------------------------------------------------------------

class TestParseFeatures:
    """Unit tests for the _parse_features helper — no HTTP needed."""

    def test_ae_zone_returns_high_score(self):
        result = _parse_features(FEMA_MOCK_AE["features"], "test")
        assert result.score == pytest.approx(ZONE_SCORES["AE"])
        assert result.details["fema_zone"] == "AE"
        assert result.details["sfha"] is True
        assert result.details["zones_found"] == 1

    def test_ve_zone_wins_over_ae(self):
        """When multiple zones overlap, the highest-risk one should win."""
        result = _parse_features(FEMA_MOCK_VE["features"], "test")
        assert result.score == pytest.approx(ZONE_SCORES["VE"])
        assert result.details["fema_zone"] == "VE"
        assert result.details["sfha"] is True

    def test_x_zone_returns_low_score(self):
        result = _parse_features(FEMA_MOCK_X["features"], "test")
        assert result.score == pytest.approx(ZONE_SCORES["X"])
        assert result.details["fema_zone"] == "X"
        assert result.details["sfha"] is False

    def test_empty_features_defaults_to_x(self):
        """No features → treat as Zone X (minimal risk, no FEMA polygon present)."""
        result = _parse_features([], "test")
        assert result.score == pytest.approx(ZONE_SCORES["X"])
        assert result.details["fema_zone"] == "X"

    def test_source_label_is_propagated(self):
        result = _parse_features(FEMA_MOCK_AE["features"], "FEMA NFHL")
        assert result.details["source"] == "FEMA NFHL"

    def test_zone_subtype_is_included(self):
        result = _parse_features(FEMA_MOCK_AE["features"], "test")
        assert result.details["zone_subtype"] == "1% Annual Chance Flood Hazard"


class TestBuildParams:
    """Unit tests for the query parameter builder."""

    def test_bbox_uses_correct_delta(self):
        params = _build_params(29.7604, -95.3698)
        parts = params["geometry"].split(",")
        lon_min, lat_min, lon_max, lat_max = (float(p) for p in parts)
        assert lon_min == pytest.approx(-95.3698 - 0.005)
        assert lat_min == pytest.approx(29.7604  - 0.005)
        assert lon_max == pytest.approx(-95.3698 + 0.005)
        assert lat_max == pytest.approx(29.7604  + 0.005)

    def test_insr_is_4326(self):
        assert _build_params(0, 0)["inSR"] == "4326"

    def test_required_outfields_present(self):
        params = _build_params(0, 0)
        for field in ("FLD_ZONE", "ZONE_SUBTY", "SFHA_TF"):
            assert field in params["outFields"]


@pytest.mark.anyio
@respx.mock
async def test_fema_primary_endpoint_used_first():
    """Service should call the official FEMA endpoint first."""
    from app.services.fema import get_flood_risk

    respx.get(FEMA_NFHL_URL).mock(
        return_value=httpx.Response(200, json=FEMA_MOCK_AE)
    )

    result = await get_flood_risk(29.7604, -95.3698)

    assert result.score == pytest.approx(ZONE_SCORES["AE"])
    assert result.details["source"] == "FEMA National Flood Hazard Layer"


@pytest.mark.anyio
@respx.mock
async def test_fema_falls_back_to_esri_on_primary_failure():
    """When the FEMA endpoint fails, the Esri-hosted mirror should be used."""
    from app.services.fema import get_flood_risk

    respx.get(FEMA_NFHL_URL).mock(side_effect=httpx.ConnectError("FEMA unreachable"))
    respx.get(ESRI_NFHL_URL).mock(
        return_value=httpx.Response(200, json=FEMA_MOCK_AE)
    )

    result = await get_flood_risk(29.7604, -95.3698)

    assert result.score == pytest.approx(ZONE_SCORES["AE"])
    assert result.details["source"] == "FEMA NFHL via Esri ArcGIS Online"


@pytest.mark.anyio
@respx.mock
async def test_fema_returns_safe_default_when_both_sources_fail():
    """When both endpoints fail, service returns a low-confidence default score."""
    from app.services.fema import get_flood_risk

    respx.get(FEMA_NFHL_URL).mock(side_effect=httpx.ConnectError("unreachable"))
    respx.get(ESRI_NFHL_URL).mock(side_effect=httpx.ConnectError("unreachable"))

    result = await get_flood_risk(29.7604, -95.3698)

    assert result.confidence == "Low"
    assert result.details["fema_zone"] == "Unknown"


@pytest.mark.anyio
@respx.mock
async def test_fema_galveston_ve_zone():
    """Galveston coastal location should return a VE (extreme) flood zone score."""
    from app.services.fema import get_flood_risk

    respx.get(FEMA_NFHL_URL).mock(
        return_value=httpx.Response(200, json=FEMA_MOCK_VE)
    )

    result = await get_flood_risk(29.2975, -94.7977)

    assert result.score == pytest.approx(ZONE_SCORES["VE"])
    assert result.level == "Extreme"
    assert result.details["sfha"] is True


# ---------------------------------------------------------------------------
# NOAA service unit tests
# ---------------------------------------------------------------------------

# --- Fixture data ---

# Minimal GHCND station inventory (USW prefix, fixed-width format matching the real file)
_GHCND_STATION_LINES = (
    "USW00012918  29.6381  -95.2819   13.4    HOUSTON WILLIAM P HOBBY AP\n"
    "USW00012960  29.9844  -95.3608   29.0    HOUSTON INTERCONTINENTAL AP\n"
    "USW00094728  40.7794  -73.9692   42.7    NEW YORK CENTRAL PARK\n"
    "USW00012839  25.7959  -80.2867    2.4    MIAMI INTERNATIONAL AP\n"
)

_NORMALS_HOUSTON = (
    '[{"ANN-TMAX-NORMAL":"790","STATION":"USW00012918",'
    '"ANN-TMAX-AVGNDS-GRTH090":"837","ANN-TMAX-AVGNDS-GRTH100":"13",'
    '"NAME":"HOUSTON WILLIAM P HOBBY AIRPORT, TX US",'
    '"LATITUDE":"29.638","LONGITUDE":"-95.282"}]\n'
)

_GSOY_HOUSTON_WIND = "\n".join([
    '{"DATE":"2020","AWND":"       3.6","STATION":"USW00012918"}',
    '{"DATE":"2021","AWND":"       3.4","STATION":"USW00012918"}',
    '{"DATE":"2022","AWND":"       3.5","STATION":"USW00012918"}',
])

_GSOY_HOUSTON_TMAX = "\n".join([
    '{"DATE":"2020","TMAX":"     27.84","STATION":"USW00012918"}',
    '{"DATE":"2021","TMAX":"     27.50","STATION":"USW00012918"}',
    '{"DATE":"2022","TMAX":"     27.50","STATION":"USW00012918"}',
])


# --- Pure-function unit tests (no HTTP) ---

class TestHaversine:
    def test_same_point_is_zero(self):
        assert _haversine_km(29.76, -95.37, 29.76, -95.37) == pytest.approx(0.0)

    def test_houston_to_galveston_approx_80km(self):
        dist = _haversine_km(29.7604, -95.3698, 29.2975, -94.7977)
        assert 70 <= dist <= 90

    def test_is_symmetric(self):
        d1 = _haversine_km(0, 0, 10, 10)
        d2 = _haversine_km(10, 10, 0, 0)
        assert d1 == pytest.approx(d2)


class TestNearestStation:
    _stations = [
        ("USW00012918", 29.638, -95.282),
        ("USW00094728", 40.779, -73.969),
        ("USW00012839", 25.796, -80.287),
    ]

    def test_returns_nearest(self):
        # Houston lat/lon → should pick USW00012918
        assert _nearest_station(self._stations, 29.76, -95.37) == "USW00012918"

    def test_returns_nearest_nyc(self):
        assert _nearest_station(self._stations, 40.71, -74.01) == "USW00094728"

    def test_returns_none_on_empty(self):
        assert _nearest_station([], 29.76, -95.37) is None


class TestHurricaneCoast:
    def test_houston_is_gulf_coast(self):
        assert _is_hurricane_coast(29.76, -95.37) is True

    def test_miami_is_atlantic_coast(self):
        assert _is_hurricane_coast(25.77, -80.19) is True

    def test_chicago_not_hurricane_coast(self):
        assert _is_hurricane_coast(41.88, -87.63) is False

    def test_seattle_not_hurricane_coast(self):
        assert _is_hurricane_coast(47.61, -122.33) is False


class TestParseNceiNdjson:
    def test_json_array(self):
        text = '[{"A":"1"},{"A":"2"}]'
        assert _parse_ncei_ndjson(text) == [{"A": "1"}, {"A": "2"}]

    def test_ndjson_lines(self):
        text = '{"A":"1"}\n{"A":"2"}'
        assert _parse_ncei_ndjson(text) == [{"A": "1"}, {"A": "2"}]

    def test_ndjson_with_trailing_comma(self):
        # NCEI sometimes emits lines like: ,{"A":"1"}
        text = '{"A":"1"}\n,{"A":"2"}\n'
        result = _parse_ncei_ndjson(text)
        assert len(result) == 2

    def test_empty_string(self):
        assert _parse_ncei_ndjson("") == []


class TestScoreHeat:
    def test_extreme_heat(self):
        # avg max ≥ 38°C → base 0.90
        result = _score_heat(39.0, 0.0, "s", "src")
        assert result.score == pytest.approx(0.90)
        assert result.level == "Extreme"

    def test_high_heat(self):
        result = _score_heat(35.0, 0.0, "s", "src")
        assert result.score == pytest.approx(0.70)
        assert result.level == "High"

    def test_medium_heat(self):
        result = _score_heat(30.0, 0.0, "s", "src")
        assert result.score == pytest.approx(0.50)
        assert result.level == "Medium"

    def test_low_heat(self):
        result = _score_heat(20.0, 0.0, "s", "src")
        assert result.score == pytest.approx(0.20)
        assert result.level == "Low"

    def test_hot_day_adjustment_capped(self):
        # 100 hot days → full +0.10 cap
        result = _score_heat(30.0, 100.0, "s", "src")
        assert result.score == pytest.approx(0.60)

    def test_details_populated(self):
        result = _score_heat(35.0, 50.0, "STN", "src")
        assert result.details["avg_max_temp_c"] == pytest.approx(35.0)
        assert result.details["station"] == "STN"


class TestScoreStorm:
    def test_high_wind_gives_high_score(self):
        # lat=29, lon=-90 = New Orleans area (Gulf Coast) — wind ≥ 8 m/s + hurricane boost
        result = _score_storm(9.0, 0.0, 29.0, -90.0, "s", "src")
        # avg wind ≥ 8 → base 0.80; Gulf Coast → +0.15 → capped at 0.95
        assert result.score == pytest.approx(0.95)

    def test_hurricane_coast_boost(self):
        # Houston: avg wind 3.5 m/s → base 0.40; hurricane coast → 0.55
        result = _score_storm(3.5, 0.0, 29.76, -95.37, "s", "src")
        assert result.score == pytest.approx(0.55)
        assert result.details["hurricane_coast"] is True

    def test_inland_low_wind(self):
        result = _score_storm(2.0, 0.0, 41.88, -87.63, "s", "src")
        assert result.score == pytest.approx(0.20)
        assert result.details["hurricane_coast"] is False


# --- Integration tests (HTTP mocked with respx) ---

@pytest.mark.anyio
@respx.mock
async def test_noaa_heat_uses_normals_without_token(monkeypatch):
    """get_heat_risk() uses NCEI normals when no NOAA_TOKEN is set."""
    from app.services import noaa as noaa_module
    from app.services.noaa import get_heat_risk
    import app.services.noaa as nm

    # Ensure no token is visible
    monkeypatch.setattr(nm.get_settings(), "noaa_token", "", raising=False)

    # Mock station inventory download
    respx.get(GHCND_STATIONS_URL).mock(
        return_value=httpx.Response(200, text=_GHCND_STATION_LINES)
    )
    # Mock normals query
    respx.get(re.compile(r".*normals-annualseasonal.*")).mock(
        return_value=httpx.Response(200, text=_NORMALS_HOUSTON)
    )

    # Reset the in-process cache so this test fetches fresh
    noaa_module._usw_station_cache = None

    result = await get_heat_risk(29.7604, -95.3698)

    # Houston normals: 790 tenths-°F = 79.0°F = 26.1°C → base 0.20 (annual avg < 28°C)
    # + heat-day adj from 83.7 days ≥ 90°F and 1.3 days ≥ 100°F → extreme_heat_days ≈ 34
    # → adj = min(34/100, 0.10) = 0.10 → final score ≈ 0.30
    assert result.score == pytest.approx(0.30, abs=0.05)
    assert result.confidence == "High"
    assert "NOAA Climate Normals" in result.details["source"]


@pytest.mark.anyio
@respx.mock
async def test_noaa_storm_uses_gsoy_without_token(monkeypatch):
    """get_storm_risk() uses NCEI GSOY when no NOAA_TOKEN is set."""
    from app.services import noaa as noaa_module
    from app.services.noaa import get_storm_risk

    monkeypatch.setattr(noaa_module.get_settings(), "noaa_token", "", raising=False)

    respx.get(GHCND_STATIONS_URL).mock(
        return_value=httpx.Response(200, text=_GHCND_STATION_LINES)
    )
    respx.get(re.compile(r".*global-summary-of-the-year.*")).mock(
        return_value=httpx.Response(200, text=_GSOY_HOUSTON_WIND)
    )

    noaa_module._usw_station_cache = None

    result = await get_storm_risk(29.7604, -95.3698)

    # avg wind ≈ 3.5 m/s → base 0.40; Gulf Coast → +0.15 → 0.55
    assert result.score == pytest.approx(0.55, abs=0.05)
    assert result.details["hurricane_coast"] is True
    assert "NOAA Global Summary" in result.details["source"]


@pytest.mark.anyio
@respx.mock
async def test_noaa_heat_falls_back_on_station_download_failure(monkeypatch):
    """If the GHCND inventory download fails, heat service returns Low confidence fallback."""
    from app.services import noaa as noaa_module
    from app.services.noaa import get_heat_risk

    monkeypatch.setattr(noaa_module.get_settings(), "noaa_token", "", raising=False)
    noaa_module._usw_station_cache = None

    respx.get(GHCND_STATIONS_URL).mock(
        side_effect=httpx.ConnectError("station list unreachable")
    )

    result = await get_heat_risk(29.7604, -95.3698)

    assert result.confidence == "Low"
    assert "latitude" in result.details.get("note", "").lower()


@pytest.mark.anyio
@respx.mock
async def test_noaa_storm_falls_back_on_ncei_failure(monkeypatch):
    """If NCEI v1 returns no data, storm service uses geography-based fallback."""
    from app.services import noaa as noaa_module
    from app.services.noaa import get_storm_risk

    monkeypatch.setattr(noaa_module.get_settings(), "noaa_token", "", raising=False)
    noaa_module._usw_station_cache = None

    respx.get(GHCND_STATIONS_URL).mock(
        return_value=httpx.Response(200, text=_GHCND_STATION_LINES)
    )
    respx.get(re.compile(r".*global-summary-of-the-year.*")).mock(
        return_value=httpx.Response(200, text="[]")
    )

    result = await get_storm_risk(29.7604, -95.3698)

    assert result.confidence == "Low"
