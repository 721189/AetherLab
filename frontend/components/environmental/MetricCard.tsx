"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ReactNode;
  accent?: string;
  className?: string;
}

export function MetricCard({ label, value, sub, icon, accent, className }: MetricCardProps) {
  return (
    <Card className={cn("h-full", className)}>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        {icon && <span style={{ color: accent }}>{icon}</span>}
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold" style={{ color: accent }}>
          {value}
        </div>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}