/**
 * SimulationPanel.tsx
 * Container for the Monte Carlo stochastic simulation feature.
 * - Input sliders for ROI parameters (CapEx, power, tariff, revenue, SAIDI)
 * - "Run Simulation" button that POSTs to /api/v1/simulate
 * - Renders UncertaintyChart (fan chart) and TornadoChart (sensitivity) on result
 */
"use client";

import { useState } from "react";
import { Activity, ChevronDown, ChevronUp, Loader2, BarChart2, AlertTriangle, Download } from "lucide-react";
import UncertaintyChart from "./UncertaintyChart";
import TornadoChart from "./TornadoChart";

// ─── Types ────────────────────────────────────────────────────────────────────

interface RiskScores {
  thermal_score: number;
  flood_score: number;
  water_score: number;
  storm_score: number;
  grid_score: number;
  overall_score: number;
}

interface PercentileBand {
  pillar: string;
  point_estimate: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

interface ROISensitivityItem {
  driver: string;
  base_impact_usd: number;
  low_impact_usd: number;
  high_impact_usd: number;
  swing_usd: number;
  pct_of_total: number;
}

interface SimulationResult {
  n_iterations: number;
  pillar_bands: PercentileBand[];
  roi_sensitivity: ROISensitivityItem[];
  total_base_impact_usd: number;
  total_worst_case_usd: number;
  total_best_case_usd: number;
  overall_histogram: { bucket_min: number; bucket_max: number; count: number; frequency: number }[];
}

interface SimulationPanelProps {
  scores: RiskScores;
  apiUrl: string;
  location?: string;   // canonical address for the PDF header
}

// ─── Slider helper ────────────────────────────────────────────────────────────

function SliderRow({
  label,
  unit,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span className="font-medium text-slate-200">
          {value.toLocaleString(undefined, { maximumFractionDigits: 3 })} {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-blue-500"
      />
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function SimulationPanel({ scores, apiUrl, location = "Unknown Location" }: SimulationPanelProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);

  async function downloadPdf() {
    if (!result) return;
    setPdfLoading(true);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30_000);

      const res = await fetch(`${apiUrl}/api/v1/simulate/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          simulation_result: result,
          location,
          risk_scores: scores,
        }),
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }

      // Stream the PDF blob and trigger a browser download
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `geosphy_climate_risk_${location.split(",")[0].trim().toLowerCase().replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      if (err.name === "AbortError") {
        setError("PDF generation timed out. Please try again.");
      } else {
        setError(`PDF error: ${err.message ?? "Unknown error"}`);
      }
    } finally {
      setPdfLoading(false);
    }
  }

  // ROI parameter state
  const [capex, setCapex] = useState(50);          // $M
  const [revenue, setRevenue] = useState(20);       // $M/yr
  const [tariff, setTariff] = useState(0.08);       // $/kWh
  const [powerMw, setPowerMw] = useState(5);        // MW
  const [saidi, setSaidi] = useState(0.5);          // hours/yr
  const [iterations, setIterations] = useState(1000);

  async function runSimulation() {
    setLoading(true);
    setError(null);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30_000); // 30s timeout

    try {
      const res = await fetch(`${apiUrl}/api/v1/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          ...scores,
          capex_usd_million: capex,
          annual_revenue_usd_million: revenue,
          energy_cost_usd_per_kwh: tariff,
          dc_power_mw: powerMw,
          saidi_hours: saidi,
          n_iterations: iterations,
          confidence_width: 0.15,
        }),
      });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail ?? `HTTP ${res.status}`);
      }
      const data: SimulationResult = await res.json();
      setResult(data);
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") {
        setError("Request timed out after 30 s. Make sure the backend is running on port 8000.");
      } else if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError")) {
        setError("Cannot reach backend. Start it with: cd backend && uvicorn app.main:app --reload");
      } else {
        setError(err.message ?? "Simulation failed");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-[#111827]/80 backdrop-blur-sm overflow-hidden">
      {/* ── Header ── */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/15">
            <Activity className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <p className="font-semibold text-white">Stochastic Climate Risk Simulation</p>
            <p className="text-xs text-slate-400">Monte Carlo uncertainty &amp; ROI sensitivity analysis</p>
          </div>
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {/* ── Body ── */}
      {open && (
        <div className="border-t border-white/8 px-6 pb-8 pt-6 space-y-6">
          {/* Parameter sliders */}
          <div className="rounded-xl border border-white/8 bg-white/3 p-5 space-y-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Asset &amp; Financial Parameters
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <SliderRow label="Data Center CapEx" unit="$M" value={capex} min={5} max={500} step={5} onChange={setCapex} />
              <SliderRow label="Annual IT Revenue" unit="$M/yr" value={revenue} min={1} max={200} step={1} onChange={setRevenue} />
              <SliderRow label="Electricity Tariff" unit="$/kWh" value={tariff} min={0.03} max={0.30} step={0.01} onChange={setTariff} />
              <SliderRow label="IT Load" unit="MW" value={powerMw} min={0.5} max={100} step={0.5} onChange={setPowerMw} />
              <SliderRow label="Grid Outage (SAIDI)" unit="hrs/yr" value={saidi} min={0} max={10} step={0.25} onChange={setSaidi} />
              <SliderRow label="Iterations" unit="" value={iterations} min={200} max={5000} step={200} onChange={setIterations} />
            </div>
          </div>

          {/* Run button */}
          <button
            onClick={runSimulation}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Running {iterations.toLocaleString()} iterations…
              </>
            ) : (
              <>
                <BarChart2 className="h-4 w-4" />
                Run Monte Carlo Simulation
              </>
            )}
          </button>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-red-800/40 bg-red-950/30 p-4 text-sm text-red-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
              <span>{error}</span>
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="space-y-6">
              {/* Uncertainty fan chart */}
              <div className="rounded-xl border border-white/8 bg-white/3 p-5">
                <div className="mb-4 flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-blue-400" />
                  <p className="text-sm font-semibold text-white">Risk Pillar Uncertainty Bands</p>
                  <span className="ml-auto text-xs text-slate-500">{result.n_iterations.toLocaleString()} iterations</span>
                </div>
                <UncertaintyChart bands={result.pillar_bands} nIterations={result.n_iterations} />
              </div>

              {/* Tornado sensitivity chart */}
              <div className="rounded-xl border border-white/8 bg-white/3 p-5">
                <div className="mb-4 flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-amber-400" />
                  <p className="text-sm font-semibold text-white">ROI Sensitivity (Tornado)</p>
                  <span className="ml-auto text-xs text-slate-500">Annual financial impact</span>
                </div>
                <TornadoChart
                  sensitivity={result.roi_sensitivity}
                  totalBaseImpact={result.total_base_impact_usd}
                  totalWorstCase={result.total_worst_case_usd}
                  totalBestCase={result.total_best_case_usd}
                />
              </div>

              {/* Download PDF button */}
              <button
                onClick={downloadPdf}
                disabled={pdfLoading}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-600 bg-slate-800 py-3 text-sm font-semibold text-slate-200 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {pdfLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating PDF…
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" />
                    Download PDF Report (CSRD / ESRS E1)
                  </>
                )}
              </button>

              {/* Methodology note */}
              <p className="text-center text-xs text-slate-600">
                Monte Carlo simulation using Beta distributions (Johnk's method) · CapEx risk premium, Cooling OpEx (PUE model), Downtime cost (SAIDI × revenue), Insurance premium · No external dependencies
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
