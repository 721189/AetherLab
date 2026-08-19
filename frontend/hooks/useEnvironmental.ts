"use client";

import { useQuery } from "@tanstack/react-query";
import * as envApi from "@/lib/api/environmental";

export const envKeys = {
  latest: (location: string) => ["env", "latest", location] as const,
  historical: (location: string, hours: number) =>
    ["env", "historical", location, hours] as const,
  reading: (id: number) => ["env", "reading", id] as const,
  geofence: (lat: number, lon: number, radius: number) =>
    ["env", "geofence", lat, lon, radius] as const,
};

export function useLatestEnv(location: string, limit = 10) {
  return useQuery({
    queryKey: envKeys.latest(location),
    queryFn: () => envApi.getLatest(location, limit),
    enabled: location.length > 0,
  });
}

export function useHistoricalEnv(location: string, hours = 24) {
  return useQuery({
    queryKey: envKeys.historical(location, hours),
    queryFn: () => envApi.getHistorical(location, hours),
    enabled: location.length > 0,
  });
}

export function useReading(id: number | undefined) {
  return useQuery({
    queryKey: envKeys.reading(id!),
    queryFn: () => envApi.getReading(id!),
    enabled: id != null,
  });
}

export function useGeofence(lat: number, lon: number, radiusKm = 100) {
  return useQuery({
    queryKey: envKeys.geofence(lat, lon, radiusKm),
    queryFn: () => envApi.getByGeofence(lat, lon, radiusKm),
    enabled: Number.isFinite(lat) && Number.isFinite(lon),
  });
}
