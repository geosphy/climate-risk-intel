"use client";

/**
 * RiskDashboard — shows overall risk score and 3 hazard cards.
 * Displayed below the map after a risk assessment completes.
 */
import { RiskReport, RISK_BADGE_CLASSES, RISK_COLORS } from "@/types/risk";
import HazardCard from "./HazardCard";

interface RiskDashboardProps {
  report: RiskReport;
}

export default function RiskDashboard({ report }: RiskDashboardProps) {
  const overall = report.overall_risk;
  const badgeClass = RISK_BADGE_CLASSES[overall.level];

  return (
    <div className="w-full space-y-4">
      {/* Overall risk banner */}
      <div
        className="rounded-xl p-4 text-white text-center"
        style={{ backgroundColor: RISK_COLORS[overall.level] }}
      >
        <div className="text-sm font-medium opacity-90 mb-1">
          Overall Climate Risk
        </div>
        <div className="text-3xl font-bold">{overall.level}</div>
        <div className="text-sm opacity-80 mt-1">
          Score: {Math.round(overall.score * 100)}/100
        </div>
        <div className="text-xs opacity-70 mt-1 truncate">
          {report.canonical_address}
        </div>
      </div>

      {/* 3 hazard cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <HazardCard type="flood" score={report.flood_risk} />
        <HazardCard type="heat" score={report.heat_risk} />
        <HazardCard type="storm" score={report.storm_risk} />
      </div>

      {/* Data sources */}
      <div className="text-xs text-gray-400 text-center">
        Data sources: {report.data_sources.join(" · ")}
      </div>
    </div>
  );
}
