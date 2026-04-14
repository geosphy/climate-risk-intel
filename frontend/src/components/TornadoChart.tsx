/**
 * TornadoChart.tsx
 * Horizontal bar chart (tornado diagram) showing ROI sensitivity per climate driver.
 * Bars represent the swing in annual cost impact from p10 to p90 scenario.
 */
"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

interface ROISensitivityItem {
  driver: string;
  base_impact_usd: number;
  low_impact_usd: number;
  high_impact_usd: number;
  swing_usd: number;
  pct_of_total: number;
}

interface TornadoChartProps {
  sensitivity: ROISensitivityItem[];
  totalBaseImpact: number;
  totalWorstCase: number;
  totalBestCase: number;
}

function fmt(usd: number): string {
  if (Math.abs(usd) >= 1_000_000)
    return `$${(usd / 1_000_000).toFixed(2)}M`;
  if (Math.abs(usd) >= 1_000)
    return `$${(usd / 1_000).toFixed(0)}K`;
  return `$${usd.toFixed(0)}`;
}

const COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#a855f7"];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const d: ROISensitivityItem = payload[0]?.payload;
  return (
    <div className="rounded-lg border border-white/10 bg-[#0f1117] p-3 text-xs shadow-xl">
      <p className="mb-1 font-semibold text-white">{d.driver}</p>
      <p className="text-slate-300">Base impact:  <span className="text-white font-medium">{fmt(d.base_impact_usd)}/yr</span></p>
      <p className="text-slate-300">Best case (p10): <span className="text-emerald-400 font-medium">{fmt(d.low_impact_usd)}/yr</span></p>
      <p className="text-slate-300">Worst case (p90): <span className="text-red-400 font-medium">{fmt(d.high_impact_usd)}/yr</span></p>
      <p className="text-slate-400 mt-1">Swing: <span className="text-amber-300 font-medium">{fmt(d.swing_usd)}</span> ({d.pct_of_total.toFixed(1)}% of total)</p>
    </div>
  );
};

const CustomYAxisTick = ({ x, y, payload }: any) => (
  <text x={x} y={y} dy={4} textAnchor="end" fill="#94a3b8" fontSize={11}>
    {payload.value}
  </text>
);

export default function TornadoChart({
  sensitivity,
  totalBaseImpact,
  totalWorstCase,
  totalBestCase,
}: TornadoChartProps) {
  // Sort by swing descending (widest bar at top)
  const sorted = [...sensitivity].sort((a, b) => b.swing_usd - a.swing_usd);

  return (
    <div className="w-full space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-md bg-emerald-950/40 border border-emerald-800/30 p-2">
          <p className="text-xs text-slate-400">Best Case (p10)</p>
          <p className="text-sm font-semibold text-emerald-400">{fmt(totalBestCase)}/yr</p>
        </div>
        <div className="rounded-md bg-slate-800/40 border border-slate-700/30 p-2">
          <p className="text-xs text-slate-400">Base Case</p>
          <p className="text-sm font-semibold text-white">{fmt(totalBaseImpact)}/yr</p>
        </div>
        <div className="rounded-md bg-red-950/40 border border-red-800/30 p-2">
          <p className="text-xs text-slate-400">Worst Case (p90)</p>
          <p className="text-sm font-semibold text-red-400">{fmt(totalWorstCase)}/yr</p>
        </div>
      </div>

      <p className="text-xs text-slate-400">
        Bars show the swing in annual financial impact from optimistic (p10) to stressed (p90) scenarios. Wider bar = higher sensitivity to uncertainty.
      </p>

      <ResponsiveContainer width="100%" height={Math.max(220, sorted.length * 52)}>
        <BarChart
          layout="vertical"
          data={sorted}
          margin={{ top: 4, right: 24, left: 120, bottom: 4 }}
          barSize={22}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v) => fmt(v)}
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="driver"
            tick={<CustomYAxisTick />}
            axisLine={false}
            tickLine={false}
            width={115}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          <ReferenceLine x={totalBaseImpact} stroke="#64748b" strokeDasharray="4 2" />
          <Bar dataKey="swing_usd" name="Swing (p10→p90)" radius={[0, 4, 4, 0]}>
            {sorted.map((entry, index) => (
              <Cell key={entry.driver} fill={COLORS[index % COLORS.length]} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
