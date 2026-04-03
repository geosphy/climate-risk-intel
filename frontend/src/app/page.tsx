"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle,
  CheckCircle2,
  CloudLightning,
  Droplets,
  FileText,
  Globe2,
  Loader2,
  Server,
  ShieldCheck,
  Thermometer,
  Waves,
  Zap,
} from "lucide-react";
import { assessRisk, APIError } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import SearchBar from "@/components/SearchBar";

const RiskMap = dynamic(() => import("@/components/RiskMap"), { ssr: false });

// ---------------------------------------------------------------------------
// Risk helpers
// ---------------------------------------------------------------------------
type RiskLevel = "Low" | "Medium" | "High" | "Extreme";

const RISK_BADGE_CLASS: Record<string, string> = {
  Low:     "border-green-500/40  bg-green-500/10  text-green-400",
  Medium:  "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
  High:    "border-orange-500/40 bg-orange-500/10 text-orange-400",
  Extreme: "border-red-500/40    bg-red-500/10    text-red-400",
};

const RISK_BAR_CLASS: Record<string, string> = {
  Low:     "bg-green-500",
  Medium:  "bg-yellow-500",
  High:    "bg-orange-500",
  Extreme: "bg-red-500",
};

const RISK_GLOW: Record<string, string> = {
  Low:     "shadow-green-500/10",
  Medium:  "shadow-yellow-500/10",
  High:    "shadow-orange-500/10",
  Extreme: "shadow-red-500/10",
};

function RiskBadge({ level }: { level: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-semibold tracking-wide uppercase text-[10px] px-2 py-0.5",
        RISK_BADGE_CLASS[level] ?? RISK_BADGE_CLASS.Medium
      )}
    >
      {level}
    </Badge>
  );
}

function ScoreBar({ score, level }: { score: number; level: string }) {
  return (
    <div className="w-full h-1 rounded-full bg-muted overflow-hidden mt-2">
      <div
        className={cn("h-full rounded-full transition-all", RISK_BAR_CLASS[level] ?? "bg-primary")}
        style={{ width: `${Math.round(score * 100)}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI Card with Table inside
// ---------------------------------------------------------------------------
function KPICard({
  icon: Icon,
  title,
  level,
  score,
  rows,
}: {
  icon: React.ElementType;
  title: string;
  level: string;
  score: number;
  rows: { label: string; value: React.ReactNode }[];
}) {
  return (
    <Card className={cn("shadow-lg", RISK_GLOW[level])}>
      <CardHeader className="pb-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Icon className="w-4 h-4" />
            <CardTitle className="text-sm font-medium">{title}</CardTitle>
          </div>
          <RiskBadge level={level} />
        </div>
        <div className="flex items-center justify-between pt-1">
          <CardDescription className="text-xs">
            Score: {Math.round(score * 100)}/100
          </CardDescription>
        </div>
        <ScoreBar score={score} level={level} />
      </CardHeader>
      <CardContent className="pt-0 pb-3">
        <Table>
          <TableBody>
            {rows.map((row, i) => (
              <TableRow key={i} className="border-b-0 hover:bg-transparent">
                <TableCell className="py-1 px-0 text-xs text-muted-foreground w-1/2">
                  {row.label}
                </TableCell>
                <TableCell className="py-1 px-0 text-xs font-medium text-right">
                  {row.value}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Overall score display
// ---------------------------------------------------------------------------
function OverallScore({ level, score, address }: { level: string; score: number; address: string }) {
  const COLOR: Record<string, string> = {
    Low: "text-green-400", Medium: "text-yellow-400",
    High: "text-orange-400", Extreme: "text-red-400",
  };
  return (
    <Card className="border-border/50">
      <CardContent className="pt-5 pb-5">
        <div className="flex flex-col sm:flex-row items-center sm:items-start gap-5">
          {/* Score circle */}
          <div className="flex flex-col items-center gap-1.5 shrink-0">
            <div className={cn("text-5xl font-bold tabular-nums", COLOR[level] ?? "text-foreground")}>
              {Math.round(score * 100)}
              <span className="text-xl text-muted-foreground font-normal">/100</span>
            </div>
            <RiskBadge level={level} />
          </div>
          {/* Separator */}
          <div className="hidden sm:block w-px h-16 bg-border" />
          {/* Address + weights */}
          <div className="flex-1 min-w-0 space-y-1">
            <p className="text-sm text-foreground font-medium leading-snug">{address}</p>
            <p className="text-xs text-muted-foreground">
              Weighted across 6 pillars: Thermal 28% · Flood 22% · Water 20% · Storm 15% · Grid 15%
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function HomePage() {
  const [report, setReport] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (address: string) => {
    setIsLoading(true);
    setError(null);
    setReport(null);
    try {
      const result = await assessRisk({ address, asset_type: "data_center" });
      setReport(result);
    } catch (err) {
      setError(
        err instanceof APIError
          ? err.detail || err.message
          : "Unexpected error. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const r = report;

  return (
    <div className="min-h-screen bg-background">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <Globe2 className="w-5 h-5 text-primary" />
            <span className="font-bold text-sm tracking-tight">Geosphy™</span>
            <span className="hidden sm:inline text-muted-foreground text-xs ml-1">
              Data Center Climate Risk
            </span>
          </div>
          <Badge variant="outline" className="text-xs shrink-0">CSRD · EU Taxonomy · DORA</Badge>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        {/* ── Search ── */}
        <div className="flex flex-col items-center gap-3">
          <div className="text-center space-y-1">
            <h1 className="text-xl font-semibold">Data Center Climate Risk Assessment</h1>
            <p className="text-sm text-muted-foreground">
              Enter an address to generate an EU-compliant physical risk report
            </p>
          </div>
          <SearchBar onSearch={handleSearch} isLoading={isLoading} />
        </div>

        {/* ── Error ── */}
        {error && (
          <Card className="border-destructive/40 bg-destructive/5">
            <CardContent className="pt-4 pb-4 flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {error}
            </CardContent>
          </Card>
        )}

        {/* ── Loading ── */}
        {isLoading && (
          <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
            <Loader2 className="w-7 h-7 animate-spin text-primary" />
            <p className="text-sm">Analysing climate risk across 6 pillars…</p>
          </div>
        )}

        {/* ── Map (always visible once report loads) ── */}
        {r && (
          <RiskMap
            report={{
              latitude: r.latitude,
              longitude: r.longitude,
              overall_risk: { level: r.overall_risk_level, score: r.overall_risk_score },
              canonical_address: r.canonical_address,
            }}
          />
        )}

        {/* ── Report ── */}
        {r && !isLoading && (
          <>
            {/* Overall */}
            <OverallScore
              level={r.overall_risk_level}
              score={r.overall_risk_score}
              address={r.canonical_address}
            />

            {/* 6 KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <KPICard
                icon={Thermometer}
                title="Thermal Stress"
                level={r.thermal_risk.level}
                score={r.thermal_risk.score}
                rows={[
                  { label: "Cooling Degree Days", value: `${Math.round(r.thermal_risk.cooling_degree_days)} CDD/yr` },
                  { label: "Days above 35°C/yr", value: String(r.thermal_risk.days_above_35c) },
                  { label: "2050 temp increase", value: `+${r.thermal_risk.projected_temp_increase_2050_c}°C` },
                  { label: "ASHRAE Class", value: r.thermal_risk.ashrae_class_required },
                  { label: "PUE impact score", value: `${Math.round(r.thermal_risk.pue_impact_score * 100)}%` },
                ]}
              />

              <KPICard
                icon={Waves}
                title="Flood Risk"
                level={r.flood_risk.level}
                score={r.flood_risk.score}
                rows={[
                  { label: "Flood Zone", value: r.flood_risk.zone },
                  { label: "Confidence", value: r.flood_risk.confidence },
                ]}
              />

              <KPICard
                icon={Droplets}
                title="Water Stress"
                level={r.water_risk.level}
                score={r.water_risk.score}
                rows={[
                  { label: "WRI Aqueduct Index", value: `${r.water_risk.water_stress_index}/5` },
                  { label: "WUE Status", value: r.water_risk.wue_compliance_status },
                  { label: "EU Reg 2024/1364", value: r.water_risk.regulation_exposure },
                  { label: "2050 Scarcity", value: r.water_risk.water_scarcity_2050 },
                ]}
              />

              <KPICard
                icon={CloudLightning}
                title="Storm & Wind"
                level={r.storm_risk.level}
                score={r.storm_risk.score}
                rows={[
                  { label: "Confidence", value: r.storm_risk.confidence },
                ]}
              />

              <KPICard
                icon={Zap}
                title="Power Grid"
                level={r.power_grid_risk.level}
                score={r.power_grid_risk.score}
                rows={[
                  { label: "Grid Reliability", value: `${Math.round(r.power_grid_risk.grid_reliability * 100)}%` },
                  { label: "Renewables", value: `${r.power_grid_risk.renewable_energy_pct}%` },
                  { label: "Carbon Intensity", value: `${r.power_grid_risk.carbon_intensity_gco2_kwh} gCO₂/kWh` },
                ]}
              />

              {/* Regulatory — uses esrs score as the 0-1 score */}
              <KPICard
                icon={ShieldCheck}
                title="Regulatory"
                level={
                  r.regulatory_compliance.esrs_e1_physical_risk_score >= 60
                    ? "High"
                    : r.regulatory_compliance.esrs_e1_physical_risk_score >= 35
                    ? "Medium"
                    : "Low"
                }
                score={r.regulatory_compliance.esrs_e1_physical_risk_score / 100}
                rows={[
                  { label: "ESRS E1 Score", value: `${r.regulatory_compliance.esrs_e1_physical_risk_score}/100` },
                  { label: "EU Taxonomy", value: r.regulatory_compliance.eu_taxonomy_alignment.split(" ")[0] },
                  {
                    label: "DORA ICT Risk",
                    value: r.regulatory_compliance.dora_ict_risk_flag ? (
                      <span className="text-orange-400">⚠ Flagged</span>
                    ) : (
                      <span className="text-green-400">✓ Clear</span>
                    ),
                  },
                  { label: "CSRD Materiality", value: r.regulatory_compliance.csrd_materiality },
                ]}
              />
            </div>

            {/* Required EU Disclosures */}
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-primary" />
                  <CardTitle className="text-sm">Required EU Disclosures</CardTitle>
                </div>
                <CardDescription className="text-xs">
                  Obligations triggered at current risk levels
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Table>
                  <TableBody>
                    {r.regulatory_compliance.required_disclosures.map((d: string, i: number) => (
                      <TableRow key={i} className="border-b-0 hover:bg-transparent">
                        <TableCell className="py-1.5 px-0 flex items-start gap-2 text-sm text-muted-foreground">
                          <CheckCircle2 className="w-3.5 h-3.5 text-primary mt-0.5 shrink-0" />
                          {d}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* AI Narrative */}
            {r.ai_narrative && (
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-primary" />
                    <CardTitle className="text-sm">ESRS E1 Risk Narrative</CardTitle>
                    <Badge variant="secondary" className="text-xs ml-1 font-normal">
                      Claude AI · for review
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    Draft disclosure text for CSRD sustainability report
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="space-y-3">
                    {r.ai_narrative.split("\n\n").map((para: string, i: number) => (
                      <p key={i} className="text-sm text-muted-foreground leading-relaxed">
                        {para}
                      </p>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Data Sources */}
            {r.data_sources?.length > 0 && (
              <p className="text-center text-xs text-muted-foreground/50">
                Sources: {r.data_sources.join(" · ")}
              </p>
            )}
          </>
        )}

        {/* Empty state */}
        {!r && !isLoading && !error && (
          <div className="flex flex-col items-center gap-3 py-20 text-muted-foreground">
            <Server className="w-10 h-10 opacity-20" />
            <p className="text-sm">Enter a data center address above to begin</p>
          </div>
        )}
      </main>
    </div>
  );
}
