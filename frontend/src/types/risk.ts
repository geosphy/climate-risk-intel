/**
 * TypeScript types for the ClimateRisk Intel API responses.
 * Mirror of the backend Pydantic models in schemas.py
 */

export type RiskLevel = "Low" | "Medium" | "High" | "Extreme";
export type ConfidenceLevel = "Low" | "Medium" | "High";
export type AssetType = "building" | "land" | "infrastructure";
export type HazardType = "flood" | "heat" | "storm";

export interface HazardScore {
  score: number;           // 0.0 to 1.0
  level: RiskLevel;
  confidence: ConfidenceLevel;
  details: Record<string, unknown>;
}

export interface RiskReport {
  address: string;
  canonical_address: string;
  latitude: number;
  longitude: number;
  flood_risk: HazardScore;
  heat_risk: HazardScore;
  storm_risk: HazardScore;
  overall_risk: HazardScore;
  ai_narrative: string;
  data_sources: string[];
  generated_at: string;
  warnings?: string[];
}

export interface RiskRequest {
  address: string;
  asset_type: AssetType;
}

// Color mapping for risk levels
export const RISK_COLORS: Record<RiskLevel, string> = {
  Low: "#22c55e",      // green-500
  Medium: "#eab308",   // yellow-500
  High: "#f97316",     // orange-500
  Extreme: "#ef4444",  // red-500
};

// Tailwind class mapping for risk level badges
export const RISK_BADGE_CLASSES: Record<RiskLevel, string> = {
  Low: "bg-green-100 text-green-800 border-green-300",
  Medium: "bg-yellow-100 text-yellow-800 border-yellow-300",
  High: "bg-orange-100 text-orange-800 border-orange-300",
  Extreme: "bg-red-100 text-red-800 border-red-300",
};
