/**
 * UncertaintyChart.tsx
 * Fan/area chart showing Monte Carlo uncertainty bands (p10–p90) per risk pillar.
 * Uses Recharts AreaChart with stacked areas for the interquartile range.
 */
"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface PercentileBand {
  pillar: string;
  point_estimate: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

interface UncertaintyChartProps {
  bands: PercentileBand[];
  nIterations?: number;
}

interface TooltipPayloadItem {
  payload?: {
    floor: number;
    low_outer: number;
    iqr: number;
    high_outer: number;
    median: number;
    point: number;
  };
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}

// Transform flat bands array → one data-point per pillar for bar-style uncertainty chart
function buildChartData(bands: PercentileBand[]) {
  return bands.map((b) => ({
    pillar: b.pillar,
    // Stacked areas: bottom invisible → p10-p25 band → p25-p75 IQR → p75-p90 band
    floor:      +(b.p10 * 100).toFixed(1),
    low_outer:  +((b.p25 - b.p10) * 100).toFixed(1),
    iqr:        +((b.p75 - b.p25) * 100).toFixed(1),
    high_outer: +((b.p90 - b.p75) * 100).toFixed(1),
    median:     +(b.p50 * 100).toFixed(1),
    point:      +(b.point_estimate * 100).toFixed(1),
  }));
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  const p10 = d.floor;
  const p25 = +(d.floor + d.low_outer).toFixed(1);
  const p75 = +(p25 + d.iqr).toFixed(1);
  const p90 = +(p75 + d.high_outer).toFixed(1);
  return (
    <div className="rounded-lg border border-white/10 bg-[#0f1117] p-3 text-xs shadow-xl">
      <p className="mb-1 font-semibold text-white">{label}</p>
      <p className="text-slate-300">Point estimate: <span className="text-white font-medium">{d.point}%</span></p>
      <p className="text-slate-300">Median (p50):   <span className="text-white font-medium">{d.median}%</span></p>
      <p className="text-slate-400">p10 – p90:      <span className="text-slate-200">{p10}% – {p90}%</span></p>
      <p className="text-slate-400">IQR (p25–p75):  <span className="text-slate-200">{p25}% – {p75}%</span></p>
    </div>
  );
};

export default function UncertaintyChart({ bands, nIterations = 1000 }: UncertaintyChartProps) {
  const data = buildChartData(bands);

  return (
    <div className="w-full">
      <p className="mb-3 text-xs text-slate-400">
        Uncertainty bands from {nIterations.toLocaleString()} Monte Carlo iterations. Darker centre = IQR (p25–p75); lighter wings = p10–p90 range.
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="pillar"
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v) => `${v}%`}
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
            domain={[0, 100]}
          />
          <Tooltip content={<CustomTooltip />} />

          {/* Invisible floor so stacking aligns to p10 */}
          <Area
            type="monotone"
            dataKey="floor"
            stackId="1"
            stroke="none"
            fill="transparent"
            legendType="none"
            isAnimationActive={false}
          />

          {/* p10–p25 outer band */}
          <Area
            type="monotone"
            dataKey="low_outer"
            stackId="1"
            stroke="none"
            fill="#3b82f6"
            fillOpacity={0.12}
            legendType="none"
            isAnimationActive={false}
          />

          {/* p25–p75 IQR — main band */}
          <Area
            type="monotone"
            dataKey="iqr"
            stackId="1"
            stroke="#3b82f6"
            strokeWidth={1.5}
            fill="#3b82f6"
            fillOpacity={0.30}
            name="IQR (p25–p75)"
            isAnimationActive={true}
          />

          {/* p75–p90 outer band */}
          <Area
            type="monotone"
            dataKey="high_outer"
            stackId="1"
            stroke="none"
            fill="#3b82f6"
            fillOpacity={0.12}
            legendType="none"
            isAnimationActive={false}
          />

          <Legend
            wrapperStyle={{ fontSize: 11, color: "#94a3b8", paddingTop: 8 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
