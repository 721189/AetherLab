import { apiFetch } from "./client";
import type { EnvironmentalReading, EnvironmentalSummary } from "@/types";

export async function getLatest(
  locationName: string,
  limit = 10
): Promise<EnvironmentalSummary[]> {
  const qs = new URLSearchParams({ location_name: locationName, limit: String(limit) });
  return apiFetch<EnvironmentalSummary[]>(`/api/v1/environmental/latest?${qs}`, {}, false);
}

export async function getHistorical(
  locationName: string,
  hours = 24
): Promise<EnvironmentalSummary[]> {
  const qs = new URLSearchParams({ location_name: locationName, hours: String(hours) });
  return apiFetch<EnvironmentalSummary[]>(`/api/v1/environmental/historical?${qs}`, {}, false);
}

export async function getReading(id: number): Promise<EnvironmentalReading> {
  return apiFetch<EnvironmentalReading>(`/api/v1/environmental/readings/${id}`, {}, false);
}

export async function getByGeofence(
  lat: number,
  lon: number,
  radiusKm = 100
): Promise<EnvironmentalSummary[]> {
  const qs = new URLSearchParams({ lat: String(lat), lon: String(lon), radius_km: String(radiusKm) });
  return apiFetch<EnvironmentalSummary[]>(`/api/v1/environmental/?${qs}`, {}, false);
}

// Known cities (name -> coords) used to place markers without needing geocoding.
export const CITIES: Record<string, { lat: number; lon: number }> = {
  London: { lat: 51.5074, lon: -0.1278 },
  "New York": { lat: 40.7128, lon: -74.006 },
  Tokyo: { lat: 35.6762, lon: 139.6503 },
  Delhi: { lat: 28.7041, lon: 77.1025 },
  "San Francisco": { lat: 37.7749, lon: -122.4194 },
  Sydney: { lat: -33.8688, lon: 151.2093 },
  Berlin: { lat: 52.52, lon: 13.405 },
  Paris: { lat: 48.8566, lon: 2.3522 },
  Singapore: { lat: 1.3521, lon: 103.8198 },
  Mumbai: { lat: 19.076, lon: 72.8777 },
};