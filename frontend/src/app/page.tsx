"use client";

/**
 * Home page — composes SearchBar, RiskMap, RiskDashboard, and RiskReport.
 *
 * Request lifecycle:
 *  1. User submits an address via SearchBar.
 *  2. assessRisk() POSTs to /api/risk (proxied by Next.js to the FastAPI backend).
 *  3. An AbortController cancels any in-flight previous request before the new
 *     one starts, preventing stale results from overwriting newer ones.
 *  4. On success the report is passed to RiskMap, RiskDashboard, and RiskReport.
 */
import { useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import { RiskReport } from "@/types/risk";
import { assessRisk, APIError } from "@/lib/api";
import SearchBar from "@/components/SearchBar";
import RiskDashboard from "@/components/RiskDashboard";
import RiskReportComponent from "@/components/RiskReport";

// Leaflet requires the browser DOM — disable SSR for RiskMap.
const RiskMap = dynamic(() => import("@/components/RiskMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-64 sm:h-80 bg-slate-800/50 rounded-xl animate-pulse
                    flex items-center justify-center text-white/30 text-sm border border-white/10">
      Loading map…
    </div>
  ),
});

// ── Small shared components ──────────────────────────────────────────────────

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10"
              stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

function BackendBanner({ health }: { health: HealthStatus | null }) {
  if (health === null) {
    // null means the health check returned — backend is unreachable
    return (
      <div className="bg-yellow-900/40 border border-yellow-500/30 rounded-xl px-4 py-3
                      flex items-start gap-3 text-sm">
        <span className="text-yellow-400 text-base shrink-0">⚠️</span>
        <div>
          <p className="text-yellow-300 font-semibold">Backend not reachable</p>
          <p className="text-yellow-400/70 text-xs mt-0.5">
            Start the FastAPI server:{" "}
            <code className="bg-yellow-900/50 px-1 py-0.5 rounded text-yellow-200">
              cd backend &amp;&amp; uvicorn app.main:app --reload
            </code>
          </p>
        </div>
      </div>
    );
  }
  return null; // backend is healthy — show nothing
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [report, setReport]       = useState<RiskReport | null>(null);
  const [isLoading, setLoading]   = useState(false);
  const [error, setError]         = useState<string | null>(null);
  // undefined = health check in progress; null = backend down; HealthStatus = up
  const [health, setHealth]       = useState<HealthStatus | null | undefined>(undefined);

  // Holds the AbortController for the currently in-flight assessRisk request.
  const abortRef = useRef<AbortController | null>(null);

  // ── Ping the backend once on mount ──────────────────────────────────────
  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  // ── Handle address submission ────────────────────────────────────────────
  const handleSearch = async (address: string) => {
    // Cancel any previous in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setReport(null);

    try {
      const result = await assessRisk(
        { address, asset_type: "building" },
        controller.signal,
      );
      setReport(result);
    } catch (err) {
      // Ignore errors from requests we intentionally cancelled
      if (err instanceof DOMException && err.name === "AbortError") return;

      if (err instanceof APIError) {
        if (err.status === 422) {
          setError(
            `Could not locate "${address}". Try a full address (e.g. "Houston, TX 77002") or a US zip code.`,
          );
        } else {
          setError(err.detail ?? err.message);
        }
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      // Only update loading state if this request wasn't superseded
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  };

  const showMap = !isLoading && (report !== null || (!error));

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-blue-950">

      {/* ── Hero / search header ──────────────────────────────────────────── */}
      <header className="pt-12 pb-10 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <div className="flex items-center justify-center gap-3 mb-3">
            <span className="w-10 h-10 rounded-xl bg-blue-500/20 border border-blue-400/30
                             flex items-center justify-center text-xl">
              🌍
            </span>
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
              Geosphy™
            </h1>
          </div>
          <p className="text-blue-200/70 text-sm sm:text-base mb-8 max-w-lg mx-auto">
            AI‑native climate risk intelligence for physical assets.
            Enter any address to assess flood, heat, and storm risk.
          </p>
          <div className="flex justify-center">
            <SearchBar onSearch={handleSearch} isLoading={isLoading} />
          </div>
        </div>
      </header>

      {/* ── Content area ─────────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-4 pb-16 space-y-5">

        {/* Backend connectivity warning (shown once health check resolves to null) */}
        {health === null && <BackendBanner health={null} />}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex flex-col items-center gap-2 py-10">
            <div className="flex items-center gap-3 text-white/60 text-sm">
              <Spinner />
              Querying FEMA, NOAA, World Bank &amp; CLIMADA…
            </div>
            <p className="text-white/25 text-xs">
              Usually takes 5–15 seconds
            </p>
          </div>
        )}

        {/* Error message */}
        {error && !isLoading && (
          <div className="bg-red-950/50 border border-red-500/30 rounded-xl p-4 flex gap-3">
            <span className="text-red-400 text-lg shrink-0">⚠️</span>
            <div>
              <p className="text-red-300 font-semibold text-sm">Assessment failed</p>
              <p className="text-red-400/70 text-xs mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Map — always visible when not loading (empty = US overview, filled = result) */}
        {showMap && <RiskMap report={report} />}

        {/* Empty state hint */}
        {!report && !isLoading && !error && (
          <p className="text-center text-white/25 text-xs">
            Enter an address above to generate a climate risk report
          </p>
        )}

        {/* Results */}
        {report && !isLoading && (
          <>
            <RiskDashboard report={report} />
            <RiskReportComponent report={report} />
          </>
        )}

        {/* Footer */}
        <footer className="text-center text-white/20 text-xs pt-4 space-y-1">
          <p>Open source · FEMA · NOAA · World Bank CCKP · CLIMADA · Claude AI</p>
          {health && (
            <p className="text-white/15">
              API v{health.version} ·{" "}
              {Object.entries(health.services)
                .filter(([, v]) => v)
                .map(([k]) => k)
                .join(" · ")}
            </p>
          )}
        </footer>
      </section>
    </main>
  );
}
