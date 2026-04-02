"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { assessRisk, APIError } from "@/lib/api";
import SearchBar from "@/components/SearchBar";

const RiskMap = dynamic(() => import("@/components/RiskMap"), { ssr: false });

const RISK_COLORS: Record<string, string> = {
  Low: "#22c55e", Medium: "#eab308", High: "#f97316", Extreme: "#ef4444"
};

const RISK_BG: Record<string, string> = {
  Low: "bg-green-100 text-green-800 border-green-300",
  Medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  High: "bg-orange-100 text-orange-800 border-orange-300",
  Extreme: "bg-red-100 text-red-800 border-red-300",
};

function RiskBadge({ level }: { level: string }) {
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${RISK_BG[level] || RISK_BG.Low}`}>
      {level}
    </span>
  );
}

function ScoreBar({ score, level }: { score: number; level: string }) {
  return (
    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mt-1">
      <div className="h-full rounded-full" style={{ width: `${Math.round(score * 100)}%`, backgroundColor: RISK_COLORS[level] }} />
    </div>
  );
}

function KPICard({ icon, title, level, score, kpis }: {
  icon: string; title: string; level: string; score: number; kpis: { label: string; value: string }[]
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xl">{icon}</span>
          <span className="font-semibold text-gray-800 text-sm">{title}</span>
        </div>
        <RiskBadge level={level} />
      </div>
      <ScoreBar score={score} level={level} />
      <div className="mt-3 space-y-1">
        {kpis.map((kpi, i) => (
          <div key={i} className="flex justify-between text-xs text-gray-600">
            <span className="text-gray-400">{kpi.label}</span>
            <span className="font-medium">{kpi.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function HomePage() {
  const [report, setReport] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (address: string) => {
    setIsLoading(true); setError(null); setReport(null);
    try {
      const result = await assessRisk({ address, asset_type: "data_center" });
      setReport(result);
    } catch (err) {
      setError(err instanceof APIError ? (err.detail || err.message) : "Unexpected error. Please try again.");
    } finally { setIsLoading(false); }
  };

  const r = report;

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 to-blue-950">
      {/* Header */}
      <div className="text-white pt-10 pb-6 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-2">
            <span className="text-3xl">🏢</span>
            <h1 className="text-2xl sm:text-3xl font-bold">Geosphy&#8482;</h1>
          </div>
          <p className="text-blue-200 text-sm mb-1">Data Center Climate Risk Intelligence</p>
          <p className="text-blue-300 text-xs opacity-70 mb-5">
            CSRD / ESRS E1 · EU Taxonomy · DORA · EU Delegated Reg 2024/1364
          </p>
          <div className="flex justify-center">
            <SearchBar onSearch={handleSearch} isLoading={isLoading} />
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 pb-10 space-y-4">
        {/* Loading */}
        {isLoading && (
          <div className="text-center py-10 text-white">
            <div className="inline-flex items-center gap-3">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              <span className="text-sm">Analysing climate risk across 6 pillars...</span>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Map */}
        <RiskMap report={r ? { latitude: r.latitude, longitude: r.longitude, overall_risk: { level: r.overall_risk_level, score: r.overall_risk_score }, canonical_address: r.canonical_address } : null} />

        {/* Results */}
        {r && (
          <>
            {/* Overall Banner */}
            <div className="rounded-xl p-4 text-white text-center" style={{ backgroundColor: RISK_COLORS[r.overall_risk_level] }}>
              <div className="text-xs opacity-80 mb-1">Overall Climate Risk Score</div>
              <div className="text-3xl font-bold">{r.overall_risk_level}</div>
              <div className="text-sm opacity-80">{Math.round(r.overall_risk_score * 100)}/100 · {r.canonical_address}</div>
            </div>

            {/* 6 KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <KPICard
                icon="🌡️" title="Thermal Stress" level={r.thermal_risk.level} score={r.thermal_risk.score}
                kpis={[
                  { label: "Cooling Degree Days", value: `${Math.round(r.thermal_risk.cooling_degree_days)} CDD/yr` },
                  { label: "Days >35°C/yr", value: `${r.thermal_risk.days_above_35c}` },
                  { label: "2050 Temp Increase", value: `+${r.thermal_risk.projected_temp_increase_2050_c}°C` },
                  { label: "ASHRAE Class", value: r.thermal_risk.ashrae_class_required },
                  { label: "PUE Impact", value: `${Math.round(r.thermal_risk.pue_impact_score * 100)}%` },
                ]}
              />
              <KPICard
                icon="🌊" title="Flood Risk" level={r.flood_risk.level} score={r.flood_risk.score}
                kpis={[
                  { label: "Zone", value: r.flood_risk.zone },
                  { label: "Confidence", value: r.flood_risk.confidence },
                ]}
              />
              <KPICard
                icon="💧" title="Water Stress" level={r.water_risk.level} score={r.water_risk.score}
                kpis={[
                  { label: "WRI Aqueduct Index", value: `${r.water_risk.water_stress_index}/5` },
                  { label: "WUE Status", value: r.water_risk.wue_compliance_status },
                  { label: "EU Reg 2024/1364", value: r.water_risk.regulation_exposure },
                  { label: "2050 Scarcity", value: r.water_risk.water_scarcity_2050 },
                ]}
              />
              <KPICard
                icon="🌀" title="Storm & Wind" level={r.storm_risk.level} score={r.storm_risk.score}
                kpis={[
                  { label: "Confidence", value: r.storm_risk.confidence },
                ]}
              />
              <KPICard
                icon="⚡" title="Power Grid" level={r.power_grid_risk.level} score={r.power_grid_risk.score}
                kpis={[
                  { label: "Grid Reliability", value: `${Math.round(r.power_grid_risk.grid_reliability * 100)}%` },
                  { label: "Renewables", value: `${r.power_grid_risk.renewable_energy_pct}%` },
                  { label: "Carbon Intensity", value: `${r.power_grid_risk.carbon_intensity_gco2_kwh} gCO₂/kWh` },
                ]}
              />
              <KPICard
                icon="📋" title="Regulatory" level={r.regulatory_compliance.esrs_e1_physical_risk_score >= 60 ? "High" : r.regulatory_compliance.esrs_e1_physical_risk_score >= 35 ? "Medium" : "Low"} score={r.regulatory_compliance.esrs_e1_physical_risk_score / 100}
                kpis={[
                  { label: "ESRS E1 Score", value: `${r.regulatory_compliance.esrs_e1_physical_risk_score}/100` },
                  { label: "EU Taxonomy", value: r.regulatory_compliance.eu_taxonomy_alignment.split(" ")[0] },
                  { label: "DORA ICT Flag", value: r.regulatory_compliance.dora_ict_risk_flag ? "⚠️ Yes" : "✓ No" },
                ]}
              />
            </div>

            {/* Required Disclosures */}
            <div className="bg-blue-950 border border-blue-800 rounded-xl p-4">
              <h3 className="text-white font-semibold text-sm mb-2">📄 Required EU Disclosures</h3>
              <ul className="space-y-1">
                {r.regulatory_compliance.required_disclosures.map((d: string, i: number) => (
                  <li key={i} className="text-blue-200 text-xs flex items-start gap-2">
                    <span className="text-blue-400 mt-0.5">→</span>{d}
                  </li>
                ))}
              </ul>
              <div className="mt-2 text-xs text-blue-400 border-t border-blue-800 pt-2">
                CSRD Materiality: {r.regulatory_compliance.csrd_materiality}
              </div>
            </div>

            {/* AI Narrative */}
            {r.ai_narrative && (
              <div className="bg-gradient-to-br from-slate-800 to-blue-900 rounded-xl border border-blue-700 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-lg">🤖</span>
                  <span className="font-semibold text-white text-sm">ESRS E1 Risk Narrative</span>
                  <span className="text-xs text-blue-300 bg-blue-900 px-2 py-0.5 rounded-full border border-blue-700">Claude AI</span>
                </div>
                {r.ai_narrative.split("\n\n").map((para: string, i: number) => (
                  <p key={i} className="text-blue-100 text-sm leading-relaxed mb-3">{para}</p>
                ))}
              </div>
            )}

            {/* Data Sources */}
            <div className="text-center text-blue-400 text-xs opacity-50">
              Data: {r.data_sources.join(" · ")}
            </div>
          </>
        )}

        {!r && !isLoading && !error && (
          <p className="text-center text-blue-300 text-sm opacity-50 mt-2">
            Enter a data center address to generate an EU-compliant climate risk report
          </p>
        )}
      </div>
    </main>
  );
}
