"use client";

/**
 * RiskDashboard — overall risk banner + 3 HazardCards.
 * Rendered below the map once a risk assessment completes.
 */
import { RiskReport, RISK_COLORS, RISK_BADGE_CLASSES } from "@/types/risk";
import HazardCard from "./HazardCard";

interface RiskDashboardProps {
  report: RiskReport;
}

export default function RiskDashboard({ report }: RiskDashboardProps) {
  const { overall_risk: overall, canonical_address, data_sources } = report;
  const color      = RISK_COLORS[overall.level];
  const badgeClass = RISK_BADGE_CLASSES[overall.level];
  const scorePct   = Math.round(overall.score * 100);

  return (
    <div className="w-full space-y-4">
      {/* ── Overall risk banner ─────────────────────────────────────────── */}
      <div
        className="rounded-xl p-5 text-white flex flex-col sm:flex-row items-center gap-4"
        style={{ backgroundColor: color }}
      >
        {/* Big score circle */}
        <div
          className="shrink-0 w-20 h-20 rounded-full border-4 border-white/30
                     flex flex-col items-center justify-center bg-white/20"
        >
          <span className="text-2xl font-bold leading-none">{scorePct}</span>
          <span className="text-xs opacity-80 leading-none mt-0.5">/100</span>
        </div>

        {/* Label block */}
        <div className="text-center sm:text-left">
          <p className="text-xs font-medium uppercase tracking-widest opacity-80 mb-0.5">
            Overall Climate Risk
          </p>
          <p className="text-3xl font-extrabold leading-tight">{overall.level}</p>
          <p className="text-sm opacity-70 mt-1 truncate max-w-xs">
            {canonical_address}
          </p>
        </div>

        {/* Risk level badge (shown on wider screens) */}
        <div className="sm:ml-auto shrink-0">
          <span
            className={`hidden sm:inline-block text-sm font-bold px-3 py-1.5 rounded-full border bg-white ${badgeClass}`}
          >
            {overall.level} Risk
          </span>
        </div>
      </div>

      {/* ── 3 hazard cards ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <HazardCard type="flood" score={report.flood_risk} />
        <HazardCard type="heat"  score={report.heat_risk}  />
        <HazardCard type="storm" score={report.storm_risk} />
      </div>

      {/* ── Data source attribution ─────────────────────────────────────── */}
      {data_sources.length > 0 && (
        <p className="text-xs text-gray-400 text-center leading-relaxed">
          <span className="font-medium text-gray-500">Sources: </span>
          {data_sources.join(" · ")}
        </p>
      )}
    </div>
  );
}
