"use client";

import { HazardScore, HazardType, RISK_BADGE_CLASSES, RISK_COLORS } from "@/types/risk";

interface HazardCardProps {
  type: HazardType;
  score: HazardScore;
}

const HAZARD_CONFIG = {
  flood: { label: "Flood & Sea Level Rise", icon: "🌊", detailKey: "fema_zone", detailLabel: "FEMA Zone" },
  heat:  { label: "Extreme Heat", icon: "🌡️", detailKey: "avg_max_temp_c", detailLabel: "Avg Max Temp (°C)" },
  storm: { label: "Storm & Wind", icon: "🌀", detailKey: "avg_wind_speed_ms", detailLabel: "Avg Wind (m/s)" },
};

export default function HazardCard({ type, score }: HazardCardProps) {
  const config = HAZARD_CONFIG[type];
  const badgeClass = RISK_BADGE_CLASSES[score.level];
  const barColor = RISK_COLORS[score.level];
  const barWidth = `${Math.round(score.score * 100)}%`;
  const detailValue = score.details[config.detailKey];
  const detailDisplay = detailValue !== undefined ? String(detailValue) : "N/A";

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{config.icon}</span>
          <h3 className="font-semibold text-gray-800 text-sm">{config.label}</h3>
        </div>
        <span className={`text-xs font-bold px-2 py-1 rounded-full border ${badgeClass}`}>{score.level}</span>
      </div>
      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Risk Score</span>
          <span className="font-mono font-semibold">{Math.round(score.score * 100)}/100</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: barWidth, backgroundColor: barColor }} />
        </div>
      </div>
      <div className="flex justify-between text-xs text-gray-600 pt-2 border-t border-gray-100">
        <span>{config.detailLabel}</span>
        <span className="font-semibold">{detailDisplay}</span>
      </div>
      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>Confidence</span>
        <span>{score.confidence}</span>
      </div>
    </div>
  );
}
