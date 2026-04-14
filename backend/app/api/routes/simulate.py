"""
/api/v1/simulate — Monte Carlo Stochastic Simulation Endpoint.

Accepts risk scores + ROI parameters and returns:
  - Uncertainty bands (p10/p50/p90) per risk pillar
  - ROI sensitivity (tornado chart data)
  - Full ROI distribution histogram
"""
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import io

from app.services.stochastic_model import SimulationRequest, SimulationResult, run_simulation
from app.services.pdf_report import build_simulation_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas (Pydantic wrappers for the HTTP layer)
# ---------------------------------------------------------------------------

class SimulateRequest(BaseModel):
    # Risk pillar scores (0-1) from the main /assess endpoint
    thermal_score: float = Field(..., ge=0.0, le=1.0)
    flood_score: float   = Field(..., ge=0.0, le=1.0)
    water_score: float   = Field(..., ge=0.0, le=1.0)
    storm_score: float   = Field(..., ge=0.0, le=1.0)
    grid_score: float    = Field(..., ge=0.0, le=1.0)
    overall_score: float = Field(..., ge=0.0, le=1.0)

    # ROI model parameters
    capex_usd_million: float       = Field(50.0,  gt=0, description="Data center CapEx in $M")
    annual_revenue_usd_million: float = Field(20.0, gt=0, description="Annual IT revenue in $M")
    energy_cost_usd_per_kwh: float = Field(0.08,  gt=0, description="Local electricity tariff $/kWh")
    dc_power_mw: float             = Field(5.0,   gt=0, description="IT load in MW")
    saidi_hours: float             = Field(0.5,   ge=0, description="Grid outage hours/year")

    # Simulation control
    n_iterations: int    = Field(1000, ge=100, le=20000)
    confidence_width: float = Field(0.15, ge=0.05, le=0.40)


class PercentileBandOut(BaseModel):
    pillar: str
    point_estimate: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class ROISensitivityOut(BaseModel):
    driver: str
    base_impact_usd: float
    low_impact_usd: float
    high_impact_usd: float
    swing_usd: float
    pct_of_total: float


class SimulateResponse(BaseModel):
    n_iterations: int
    pillar_bands: list[PercentileBandOut]
    roi_sensitivity: list[ROISensitivityOut]
    total_base_impact_usd: float
    total_worst_case_usd: float
    total_best_case_usd: float
    overall_histogram: list[dict]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/v1/simulate", response_model=SimulateResponse)
def simulate_climate_risk(body: SimulateRequest) -> SimulateResponse:
    """
    Run a Monte Carlo simulation over the provided risk scores.
    Synchronous def → FastAPI runs this in a thread pool, keeping the
    event loop free while the CPU-bound simulation executes.
    Returns uncertainty bands per pillar and ROI sensitivity data
    for tornado chart and fan chart visualization.
    """
    try:
        req = SimulationRequest(
            thermal_score=body.thermal_score,
            flood_score=body.flood_score,
            water_score=body.water_score,
            storm_score=body.storm_score,
            grid_score=body.grid_score,
            overall_score=body.overall_score,
            capex_usd_million=body.capex_usd_million,
            annual_revenue_usd_million=body.annual_revenue_usd_million,
            energy_cost_usd_per_kwh=body.energy_cost_usd_per_kwh,
            dc_power_mw=body.dc_power_mw,
            saidi_hours=body.saidi_hours,
            n_iterations=body.n_iterations,
            confidence_width=body.confidence_width,
        )

        result: SimulationResult = run_simulation(req)

        return SimulateResponse(
            n_iterations=result.n_iterations,
            pillar_bands=[
                PercentileBandOut(
                    pillar=b.pillar,
                    point_estimate=b.point_estimate,
                    p10=b.p10,
                    p25=b.p25,
                    p50=b.p50,
                    p75=b.p75,
                    p90=b.p90,
                )
                for b in result.pillar_bands
            ],
            roi_sensitivity=[
                ROISensitivityOut(
                    driver=s.driver,
                    base_impact_usd=s.base_impact_usd,
                    low_impact_usd=s.low_impact_usd,
                    high_impact_usd=s.high_impact_usd,
                    swing_usd=s.swing_usd,
                    pct_of_total=s.pct_of_total,
                )
                for s in result.roi_sensitivity
            ],
            total_base_impact_usd=result.total_base_impact_usd,
            total_worst_case_usd=result.total_worst_case_usd,
            total_best_case_usd=result.total_best_case_usd,
            overall_histogram=result.overall_histogram,
        )

    except Exception as exc:
        logger.error(f"Simulation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(exc)}")


# ---------------------------------------------------------------------------
# PDF Report endpoint
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    """Wraps the simulation result + location metadata for PDF generation."""
    simulation_result: dict          # Full SimulateResponse as dict
    location: str = "Unknown Location"
    risk_scores: dict | None = None  # optional {thermal, flood, ...} point estimates


@router.post("/v1/simulate/report")
def generate_simulation_report(body: ReportRequest) -> StreamingResponse:
    """
    Accept a previously-computed simulation result and return a
    professional PDF report as a downloadable file.

    The client should POST the same SimulateResponse JSON it received from
    /api/v1/simulate, plus a 'location' string (canonical address).
    """
    try:
        pdf_bytes = build_simulation_pdf(
            simulation_result=body.simulation_result,
            location=body.location,
            risk_scores=body.risk_scores,
        )
        filename = (
            "geosphy_climate_risk_report_"
            + body.location.split(",")[0].strip().lower().replace(" ", "_")[:30]
            + ".pdf"
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logger.error(f"PDF generation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF error: {str(exc)}")
