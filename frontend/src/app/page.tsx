"use client";

/**
 * Home page — main application page.
 * Composes SearchBar, RiskMap, RiskDashboard, and RiskReport.
 */
import { useState } from "react";
import dynamic from "next/dynamic";
import { RiskReport } from "@/types/risk";
import { assessRisk, APIError } from "@/lib/api";
import SearchBar from "@/components/SearchBar";
import RiskDashboard from "@/components/RiskDashboard";
import RiskReportComponent from "@/components/RiskReport";

// Leaflet requires browser environment — disable SSR
const RiskMap = dynamic(() => import("@/components/RiskMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-64 bg-gray-100 rounded-xl animate-pulse flex items-center justify-center text-gray-400 text-sm">
      Loading map...
    </div>
  ),
});

export default function HomePage() {
  const [report, setReport] = useState<RiskReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (address: string) => {
    setIsLoading(true);
    setError(null);
    setReport(null);

    try {
      const result = await assessRisk({ address, asset_type: "building" });
      setReport(result);
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.detail || err.message);
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-950">
      {/* Hero header */}
      <div className="bg-gradient-to-br from-slate-900 to-blue-950 text-white pt-12 pb-8 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-3">
            <span className="text-3xl">🌍</span>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              ClimateRisk Intel
            </h1>
          </div>
          <p className="text-blue-200 text-sm sm:text-base mb-6">
            AI-Native climate risk intelligence for physical assets.
            Enter any address to assess flood, heat, and storm risk.
          </p>

          {/* Search bar */}
          <div className="flex justify-center">
            <SearchBar onSearch={handleSearch} isLoading={isLoading} />
          </div>
        </div>
      </div>

      {/* Content area */}
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {/* Loading state */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="inline-flex items-center gap-3 text-white">
              <svg className="animate-spin h-6 w-6" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              <span className="text-sm">
                Querying FEMA, NOAA, World Bank & CLIMADA...
              </span>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Results */}
        {report && (
          <>
            <RiskMap report={report} />
            <RiskDashboard report={report} />
            <RiskReportComponent report={report} />
          </>
        )}

        {/* Empty state */}
        {!report && !isLoading && !error && (
          <div className="text-center py-12 text-blue-200 text-sm">
            <RiskMap report={null} />
            <p className="mt-4 opacity-60">
              Enter an address above to see climate risk intelligence
            </p>
          </div>
        )}

        {/* Footer */}
        <div className="text-center text-blue-300 text-xs pb-6 opacity-50">
          Open source · Built with FEMA, NOAA, World Bank CCKP, CLIMADA, IBM Prithvi & Claude AI ·{" "}
          <a
            href="https://github.com/YOUR_USERNAME/climate-risk-intel"
            className="hover:underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </div>
      </div>
    </main>
  );
}
