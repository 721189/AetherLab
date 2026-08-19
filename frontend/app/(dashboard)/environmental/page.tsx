"use client";

import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Thermometer, Wind, CloudRain } from "lucide-react";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AqiGauge } from "@/components/environmental/AqiGauge";
import { MetricCard } from "@/components/environmental/MetricCard";
import { MapView } from "@/components/environmental/MapView";
import { TrendChart } from "@/components/charts/TrendChart";
import { CITIES } from "@/lib/api/environmental";
import { envKeys } from "@/hooks/useEnvironmental";
import * as envApi from "@/lib/api/environmental";
import { useLatestEnv, useHistoricalEnv } from "@/hooks/useEnvironmental";
import { aqiColor, aqiLabel } from "@/lib/utils";

const cityNames = Object.keys(CITIES);

export default function EnvironmentalPage() {
  const [city, setCity] = useState("London");

  const { data: latest, isLoading: latestLoading } = useLatestEnv(city, 1);
  const { data: historical, isLoading: historicalLoading } = useHistoricalEnv(city, 24);

  const reading = latest?.[0];

  // Fetch a summary for every city to colour the map markers.
  const cityQueries = useQueries({
    queries: cityNames.map((name) => ({
      queryKey: envKeys.latest(name),
      queryFn: () => envApi.getLatest(name, 1),
    })),
  });

  const markers = cityNames.map((name, i) => {
    const aqi = cityQueries[i]?.data?.[0]?.aqi ?? null;
    const coords = CITIES[name];
    return { name, ...coords, aqi, color: aqiColor(aqi) };
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Environmental monitor</h1>
          <p className="text-sm text-muted-foreground">
            Live air quality and weather readings.
          </p>
        </div>
        <div className="w-52">
          <Select value={city} onChange={(e) => setCity(e.target.value)}>
            {cityNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">
                Air Quality Index — {city}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center">
              {latestLoading ? (
                <Skeleton className="h-44 w-56" />
              ) : (
                <>
                  <AqiGauge aqi={reading?.aqi ?? null} />
                  <p className="mt-2 text-sm font-medium">
                    {reading?.aqi != null ? aqiLabel(reading.aqi) : "No data"}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-1">
            <MetricCard
              label="Temperature"
              value={reading?.temperature != null ? `${Math.round(reading.temperature)}°C` : "—"}
              sub={city}
              icon={<Thermometer className="h-5 w-5" />}
              accent="#22c55e"
            />
            <MetricCard
              label="PM2.5"
              value={reading?.pm25 != null ? `${reading.pm25} µg/m³` : "—"}
              sub="Fine particulate matter"
              icon={<CloudRain className="h-5 w-5" />}
              accent="#06b6d4"
            />
            <MetricCard
              label="Source"
              value={reading?.source ?? "—"}
              sub={reading ? new Date(reading.recorded_at).toLocaleString() : "Awaiting data"}
              icon={<Wind className="h-5 w-5" />}
              accent="#8b5cf6"
            />
          </div>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">
                Location map (AQI)
              </CardTitle>
            </CardHeader>
            <CardContent className="h-[340px] p-0">
              <MapView markers={markers} />
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardContent className="pt-6">
            {historicalLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <TrendChart data={historical ?? []} dataKey="temperature" label="Temperature (°C) — last 24h" color="#22c55e" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            {historicalLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <TrendChart data={historical ?? []} dataKey="aqi" label="Air Quality Index — last 24h" color="#f59e0b" />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}