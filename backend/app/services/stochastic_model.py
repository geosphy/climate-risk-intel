"""
Stochastic Climate Risk Model — Monte Carlo Simulation Engine.

Runs N iterations sampling each risk pillar score from a Beta distribution,
then feeds sampled scores through a ROI impact model to produce:
  - Uncertainty bands (p10 / p50 / p90) per pillar
  - ROI sensitivity: how much each risk driver swings total ROI impact
  - Full distribution data for histogram / fan chart rendering

ROI Impact Model (annual, USD):
  - CapEx risk premium   : flood + structural risk → % uplift on construction cost
  - Cooling OpEx         : thermal score × PUE penalty × energy cost
  - Downtime cost        : grid score × SAIDI hours × hourly revenue
  - Insurance premium    : overall score × base insurance rate
"""
import math
import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Input / Output schemas (plain dataclasses — no Pydantic needed here)
# ---------------------------------------------------------------------------

@dataclass
class SimulationRequest:
    # Point-estimate risk scores (0-1) from the main assess endpoint
    thermal_score: float
    flood_score: float
    water_score: float
    storm_score: float
    grid_score: float
    overall_score: float

    # ROI model inputs
    capex_usd_million: float = 50.0          # Data center construction cost ($M)
    annual_revenue_usd_million: float = 20.0 # Annual IT revenue ($M)
    energy_cost_usd_per_kwh: float = 0.08    # Local electricity tariff
    dc_power_mw: float = 5.0                 # IT load in MW
    saidi_hours: float = 0.5                 # Grid outage hours/year (from power_grid KPI)

    # Simulation parameters
    n_iterations: int = 1000
    confidence_width: float = 0.15           # ±spread around point estimate


@dataclass
class PercentileBand:
    pillar: str
    point_estimate: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


@dataclass
class ROISensitivityItem:
    driver: str                  # e.g. "Thermal / Cooling OpEx"
    base_impact_usd: float       # At point estimate score
    low_impact_usd: float        # At p10 score (best case)
    high_impact_usd: float       # At p90 score (worst case)
    swing_usd: float             # high - low (size of bar in tornado chart)
    pct_of_total: float          # % of total swing


@dataclass
class SimulationResult:
    n_iterations: int
    pillar_bands: list[PercentileBand]
    roi_sensitivity: list[ROISensitivityItem]
    total_base_impact_usd: float
    total_worst_case_usd: float
    total_best_case_usd: float
    # Histogram data for overall score distribution
    overall_histogram: list[dict]   # [{bucket: float, count: int}]


# ---------------------------------------------------------------------------
# Beta distribution sampling (no scipy — pure Python)
# ---------------------------------------------------------------------------

def _beta_sample(mean: float, width: float) -> float:
    """
    Sample from a Beta(alpha, beta) distribution using the mean and
    a confidence half-width. Uses the Johnk method via Python's random module.

    mean:  point estimate (0-1)
    width: half-width of the 80% confidence interval (clamped to [0.05, 0.4])
    """
    width = max(0.05, min(0.40, width))
    # Clamp mean away from boundaries
    mean = max(0.05, min(0.95, mean))

    # Method of moments for Beta parameters
    variance = (width / 1.645) ** 2   # treat width as ~1.645σ (90th pct)
    variance = min(variance, mean * (1 - mean) * 0.99)

    alpha = mean * (mean * (1 - mean) / variance - 1)
    beta_param = (1 - mean) * (mean * (1 - mean) / variance - 1)

    alpha = max(0.5, alpha)
    beta_param = max(0.5, beta_param)

    # Johnk's method for Beta sampling using gamma variates
    # Python's random.gammavariate implements this
    x = random.gammavariate(alpha, 1.0)
    y = random.gammavariate(beta_param, 1.0)
    return max(0.0, min(1.0, x / (x + y)))


def _percentiles(values: list[float], pcts: list[float]) -> list[float]:
    """Return requested percentiles from a sorted list."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result = []
    for p in pcts:
        idx = (p / 100) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        result.append(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)
    return result


# ---------------------------------------------------------------------------
# ROI Impact Functions
# ---------------------------------------------------------------------------

def _capex_risk_premium(flood_score: float, storm_score: float,
                         capex_usd_million: float) -> float:
    """
    CapEx uplift from flood-proofing, elevated foundations, storm hardening.
    Range: 0% (score=0) to 18% (score=1) of total CapEx.
    Combined flood+storm driver.
    """
    combined = flood_score * 0.65 + storm_score * 0.35
    pct_uplift = combined * 0.18
    return capex_usd_million * 1_000_000 * pct_uplift


def _cooling_opex(thermal_score: float, dc_power_mw: float,
                   energy_cost_usd_per_kwh: float) -> float:
    """
    Annual cooling energy cost driven by thermal risk.
    PUE ranges from 1.2 (low thermal) to 1.8 (extreme thermal).
    Cooling energy = (PUE - 1) × IT load × 8760h × tariff
    """
    pue = 1.2 + thermal_score * 0.6           # 1.2 → 1.8
    cooling_mw = (pue - 1.0) * dc_power_mw
    return cooling_mw * 1000 * 8760 * energy_cost_usd_per_kwh  # kWh × $/kWh


def _downtime_cost(grid_score: float, saidi_hours: float,
                   annual_revenue_usd_million: float) -> float:
    """
    Revenue loss from grid outages and storm events.
    grid_score amplifies the base SAIDI; each outage hour = hourly revenue.
    """
    # Grid score amplifies effective outage: 1× (score=0) to 4× (score=1)
    effective_outage_hours = saidi_hours * (1 + grid_score * 3)
    hourly_revenue = (annual_revenue_usd_million * 1_000_000) / 8760
    return effective_outage_hours * hourly_revenue


def _insurance_premium(overall_score: float,
                        capex_usd_million: float) -> float:
    """
    Annual insurance premium scaling with overall risk score.
    Industry range: 0.3% to 2.5% of asset value per year.
    """
    rate = 0.003 + overall_score * 0.022      # 0.3% → 2.5%
    return capex_usd_million * 1_000_000 * rate


def _total_roi_impact(req: SimulationRequest,
                       thermal: float, flood: float,
                       storm: float, grid: float,
                       overall: float) -> float:
    """Sum all four annual ROI impact components."""
    return (
        _capex_risk_premium(flood, storm, req.capex_usd_million) +
        _cooling_opex(thermal, req.dc_power_mw, req.energy_cost_usd_per_kwh) +
        _downtime_cost(grid, req.saidi_hours, req.annual_revenue_usd_million) +
        _insurance_premium(overall, req.capex_usd_million)
    )


# ---------------------------------------------------------------------------
# Main Simulation Engine
# ---------------------------------------------------------------------------

def run_simulation(req: SimulationRequest) -> SimulationResult:
    """
    Run Monte Carlo simulation and return uncertainty bands + ROI sensitivity.

    Algorithm:
      For each iteration i in 1..N:
        1. Sample all 6 risk scores from Beta distributions
        2. Compute overall as weighted average of sampled scores
        3. Compute total ROI impact from sampled scores
        4. Record all values

      Post-processing:
        - Compute p10/p25/p50/p75/p90 for each pillar
        - Build ROI sensitivity (tornado) by running impact at p10/p90 per driver
          while holding others at point estimate
    """
    random.seed(42)  # Reproducible results for the same inputs

    w = req.confidence_width
    pillars = {
        "thermal": req.thermal_score,
        "flood":   req.flood_score,
        "water":   req.water_score,
        "storm":   req.storm_score,
        "grid":    req.grid_score,
    }
    weights = {"thermal": 0.28, "flood": 0.22, "water": 0.20,
               "storm": 0.15, "grid": 0.15}

    # Storage for samples
    samples: dict[str, list[float]] = {k: [] for k in pillars}
    overall_samples: list[float] = []
    roi_samples: list[float] = []

    for _ in range(req.n_iterations):
        s = {k: _beta_sample(v, w) for k, v in pillars.items()}
        overall = sum(s[k] * weights[k] for k in pillars)
        roi = _total_roi_impact(req, s["thermal"], s["flood"],
                                 s["storm"], s["grid"], overall)
        for k in pillars:
            samples[k].append(s[k])
        overall_samples.append(overall)
        roi_samples.append(roi)

    # --- Pillar uncertainty bands ---
    pillar_bands: list[PercentileBand] = []
    for name, point_est in pillars.items():
        p10, p25, p50, p75, p90 = _percentiles(samples[name],
                                                [10, 25, 50, 75, 90])
        pillar_bands.append(PercentileBand(
            pillar=name.title(),
            point_estimate=round(point_est, 3),
            p10=round(p10, 3),
            p25=round(p25, 3),
            p50=round(p50, 3),
            p75=round(p75, 3),
            p90=round(p90, 3),
        ))

    # Add overall band
    p10, p25, p50, p75, p90 = _percentiles(overall_samples, [10, 25, 50, 75, 90])
    pillar_bands.append(PercentileBand(
        pillar="Overall",
        point_estimate=round(req.overall_score, 3),
        p10=round(p10, 3), p25=round(p25, 3), p50=round(p50, 3),
        p75=round(p75, 3), p90=round(p90, 3),
    ))

    # --- ROI Sensitivity (Tornado) ---
    # Base ROI at point estimates
    base_roi = _total_roi_impact(
        req, req.thermal_score, req.flood_score,
        req.storm_score, req.grid_score, req.overall_score
    )

    # For each driver: hold others at point estimate, vary from p10 to p90
    def driver_band(name: str) -> tuple[float, float]:
        pts = _percentiles(samples[name], [10, 90])
        return pts[0], pts[1]

    drivers = []

    # Thermal → Cooling OpEx
    t_lo, t_hi = driver_band("thermal")
    drivers.append(("Thermal — Cooling OpEx",
        _cooling_opex(t_lo, req.dc_power_mw, req.energy_cost_usd_per_kwh),
        _cooling_opex(t_hi, req.dc_power_mw, req.energy_cost_usd_per_kwh),
        _cooling_opex(req.thermal_score, req.dc_power_mw, req.energy_cost_usd_per_kwh),
    ))

    # Flood+Storm → CapEx premium
    f_lo, f_hi = driver_band("flood")
    st_lo, st_hi = driver_band("storm")
    drivers.append(("Flood+Storm — CapEx Premium",
        _capex_risk_premium(f_lo, st_lo, req.capex_usd_million),
        _capex_risk_premium(f_hi, st_hi, req.capex_usd_million),
        _capex_risk_premium(req.flood_score, req.storm_score, req.capex_usd_million),
    ))

    # Grid → Downtime
    g_lo, g_hi = driver_band("grid")
    drivers.append(("Grid — Downtime Cost",
        _downtime_cost(g_lo, req.saidi_hours, req.annual_revenue_usd_million),
        _downtime_cost(g_hi, req.saidi_hours, req.annual_revenue_usd_million),
        _downtime_cost(req.grid_score, req.saidi_hours, req.annual_revenue_usd_million),
    ))

    # Overall → Insurance
    o_lo, o_hi = _percentiles(overall_samples, [10, 90])
    drivers.append(("Overall Risk — Insurance Premium",
        _insurance_premium(o_lo, req.capex_usd_million),
        _insurance_premium(o_hi, req.capex_usd_million),
        _insurance_premium(req.overall_score, req.capex_usd_million),
    ))

    total_swing = sum(abs(hi - lo) for _, lo, hi, _ in drivers)
    roi_sensitivity: list[ROISensitivityItem] = []
    for label, lo, hi, base in sorted(drivers, key=lambda x: abs(x[2] - x[1]), reverse=True):
        swing = abs(hi - lo)
        roi_sensitivity.append(ROISensitivityItem(
            driver=label,
            base_impact_usd=round(base),
            low_impact_usd=round(lo),
            high_impact_usd=round(hi),
            swing_usd=round(swing),
            pct_of_total=round(swing / total_swing * 100, 1) if total_swing > 0 else 0,
        ))

    # --- Overall histogram (20 buckets) ---
    min_r, max_r = min(roi_samples), max(roi_samples)
    bucket_size = (max_r - min_r) / 20 if max_r > min_r else 1
    histogram: list[dict] = []
    for i in range(20):
        lo_b = min_r + i * bucket_size
        hi_b = lo_b + bucket_size
        count = sum(1 for v in roi_samples if lo_b <= v < hi_b)
        histogram.append({
            "bucket_usd": round((lo_b + hi_b) / 2),
            "count": count,
            "bucket_label": f"${round(lo_b / 1_000_000, 1)}M",
        })

    return SimulationResult(
        n_iterations=req.n_iterations,
        pillar_bands=pillar_bands,
        roi_sensitivity=roi_sensitivity,
        total_base_impact_usd=round(base_roi),
        total_worst_case_usd=round(_percentiles(roi_samples, [90])[0]),
        total_best_case_usd=round(_percentiles(roi_samples, [10])[0]),
        overall_histogram=histogram,
    )
