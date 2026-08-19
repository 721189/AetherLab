"use client";

import { aqiColor } from "@/lib/utils";

interface AqiGaugeProps {
  aqi: number | null;
}

// Semi-circular AQI gauge on a 0–300 scale, colour-coded.
export function AqiGauge({ aqi }: AqiGaugeProps) {
  const value = aqi ?? 0;
  const pct = Math.min(value / 300, 1);
  const angle = -120 + pct * 240; // -120° .. +120°
  const rad = (angle * Math.PI) / 180;
  const color = aqiColor(aqi);

  // Gauge arc geometry (centered at 100,100, radius 80).
  const cx = 100;
  const cy = 100;
  const r = 80;
  const arcStart = {
    x: cx + r * Math.cos((-120 * Math.PI) / 180),
    y: cy + r * Math.sin((-120 * Math.PI) / 180),
  };
  const arcEnd = {
    x: cx + r * Math.cos((120 * Math.PI) / 180),
    y: cy + r * Math.sin((120 * Math.PI) / 180),
  };
  const needleX = cx + r * 0.6 * Math.cos(rad);
  const needleY = cy + r * 0.6 * Math.sin(rad);

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 150" className="w-56">
        <path
          d={`M ${arcStart.x} ${arcStart.y} A ${r} ${r} 0 0 1 ${arcEnd.x} ${arcEnd.y}`}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="14"
          strokeLinecap="round"
        />
        <line x1={cx} y1={cy} x2={needleX} y2={needleY} stroke={color} strokeWidth="4" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="6" fill={color} />
        <text x="100" y="52" textAnchor="middle" className="fill-foreground text-lg font-bold">
          {aqi ?? "—"}
        </text>
      </svg>
      <div className="mt-1 flex w-56 justify-between text-[10px] text-muted-foreground">
        <span>0</span>
        <span>150</span>
        <span>300</span>
      </div>
    </div>
  );
}