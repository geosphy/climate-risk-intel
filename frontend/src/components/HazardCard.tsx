"use client";

/**
 * HazardCard — displays a single climate hazard risk score.
 * Shows lucide-react icon, risk-level badge, animated score bar, and a key data point.
 */
import { Waves, Thermometer, Wind } from "lucide-react";
import { HazardScore, HazardType, RISK_BADGE_CLASSES, RISK_COLORS } from "@/types/risk";

interface HazardCardProps {
  type: HazardType;
  score: HazardScore;
}

type HazardConfig = {
  label: string;
  Icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  detailKey: string;
  detailLabel: string;
  detailFormat: (v: unknown) => string;
};

const HAZARD_CONFIG: Record<HazardType, HazardConfig> = {
  flood: {
    label:       "Flood & Sea Level Rise",
    Icon:        Waves,
    detailKey:   "fema_zone",
    detailLabel: "FEMA Zone",
    detailFormat: (v) => (v !== undefined && v !== null ? String(v) : "N/A"),
  },
  heat: {
    label:       "Extreme Heat",
    Icon:        Thermometer,
    detailKey:   "avg_max_temp_c",
    detailLabel: "Avg Max Temp",
    detailFormat: (v) =>
      v !== undefined && v !== null ? `${Number(v).toFixed(1)} °C` : "N/A",
  },
  storm: {
    label:       "Storm & Wind",
    Icon:        Wind,
    detailKey:   "avg_wind_speed_ms",
    detailLabel: "Avg Wind Speed",
    detailFormat: (v) =>
      v !== undefined && v !== null ? `${Number(v).toFixed(1)} m/s` : "N/A",
  },
};

// Subtle tinted background for the card header per risk level
const HEADER_BG: Record<string, string> = {
  Low:     "bg-green-50",
  Medium:  "bg-yellow-50",
  High:    "bg-orange-50",
  Extreme: "bg-red-50",
};

export default function HazardCard({ type, score }: HazardCardProps) {
  const { label, Icon, detailKey, detailLabel, detailFormat } = HAZARD_CONFIG[type];

  const badgeClass  = RISK_BADGE_CLASSES[score.level];
  const barColor    = RISK_COLORS[score.level];
  const barPct      = Math.round(score.score * 100);
  const headerBg    = HEADER_BG[score.level] ?? "bg-gray-50";
  const detailText  = detailFormat(score.details[detailKey]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden flex flex-col">
      {/* Tinted header strip */}
      <div className={`${headerBg} px-4 pt-4 pb-3 flex items-center justify-between gap-2`}>
        <div className="flex items-center gap-2 min-w-0">
          <Icon size={20} strokeWidth={2} style={{ color: barColor }} className="shrink-0" />
          <h3 className="font-semibold text-gray-800 text-sm leading-tight truncate">
            {label}
          </h3>
        </div>
        <span className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full border ${badgeClass}`}>
          {score.level}
        </span>
      </div>

      {/* Card body */}
      <div className="px-4 py-3 flex-1 flex flex-col gap-3">
        {/* Numeric score + bar */}
        <div>
          <div className="flex justify-between items-baseline mb-1.5">
            <span className="text-xs text-gray-500">Risk Score</span>
            <span className="text-xl font-bold font-mono" style={{ color: barColor }}>
              {barPct}
              <span className="text-xs font-normal text-gray-400">/100</span>
            </span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{ width: `${barPct}%`, backgroundColor: barColor }}
            />
          </div>
        </div>

        {/* Key data point */}
        <div className="flex justify-between items-center text-xs border-t border-gray-100 pt-2">
          <span className="text-gray-500">{detailLabel}</span>
          <span className="font-semibold text-gray-700">{detailText}</span>
        </div>

        {/* Data confidence */}
        <div className="flex justify-between items-center text-xs text-gray-400">
          <span>Confidence</span>
          <span>{score.confidence}</span>
        </div>
      </div>
    </div>
  );
}
