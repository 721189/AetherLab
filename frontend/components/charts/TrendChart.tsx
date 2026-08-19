"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { EnvironmentalSummary } from "@/types";

export function TrendChart({
  data,
  dataKey,
  color = "#0d9488",
  label,
}: {
  data: EnvironmentalSummary[];
  dataKey: "temperature" | "aqi" | "pm25";
  color?: string;
  label: string;
}) {
  const points = data
    .filter((d) => d[dataKey] != null)
    .map((d) => ({
      t: new Date(d.recorded_at).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      }),
      v: d[dataKey] as number,
    }));

  return (
    <div className="h-64 w-full">
      <p className="mb-2 text-sm font-medium text-muted-foreground">{label}</p>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="t" fontSize={11} stroke="var(--muted-foreground)" />
          <YAxis fontSize={11} stroke="var(--muted-foreground)" />
          <Tooltip
            contentStyle={{
              background: "var(--popover)",
              border: "1px solid var(--border)",
              borderRadius: 8,
            }}
          />
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}