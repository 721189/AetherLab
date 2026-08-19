"use client";

import React from "react";
import { MapPin } from "lucide-react";
import "mapbox-gl/dist/mapbox-gl.css";

export interface MapMarker {
  name: string;
  lat: number;
  lon: number;
  aqi: number | null;
  color: string;
}

interface MapViewProps {
  markers: MapMarker[];
}

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

export function MapView({ markers }: MapViewProps) {
  if (MAPBOX_TOKEN) {
    return <LiveMap markers={markers} />;
  }
  return <FallbackMap markers={markers} />;
}

// Live interactive map (requires a Mapbox public token).
function LiveMap({ markers }: MapViewProps) {
  // Dynamically import react-map-gl so mapbox css only loads when a token exists.
  const MapComponent = React.lazy(() =>
    import("react-map-gl").then((m) => ({ default: m.Map }))
  );
  const Marker = React.lazy(() =>
    import("react-map-gl").then((m) => ({ default: m.Marker }))
  );

  const center = markers.length
    ? {
        longitude: markers[0].lon,
        latitude: markers[0].lat,
        zoom: 3,
      }
    : { longitude: 0, latitude: 20, zoom: 1 };

  return (
    <React.Suspense fallback={<div className="h-full animate-pulse rounded-lg bg-muted" />}>
      <MapComponent
        initialViewState={center}
        style={{ width: "100%", height: "100%" }}
        mapStyle="mapbox://styles/mapbox/light-v11"
        mapboxAccessToken={MAPBOX_TOKEN}
      >
        {markers.map((m) => (
          <Marker key={m.name} longitude={m.lon} latitude={m.lat}>
            <div
              className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-white shadow"
              style={{ background: m.color }}
              title={`${m.name}: AQI ${m.aqi ?? "n/a"}`}
            >
              <MapPin className="h-3 w-3 text-white" />
            </div>
          </Marker>
        ))}
      </MapComponent>
    </React.Suspense>
  );
}

// Token-free fallback: stylised geographic view with projected markers.
function FallbackMap({ markers }: MapViewProps) {
  const lats = markers.map((m) => m.lat);
  const lons = markers.map((m) => m.lon);
  const minLat = Math.min(...lats, 0);
  const maxLat = Math.max(...lats, 0);
  const minLon = Math.min(...lons, 0);
  const maxLon = Math.max(...lons, 0);
  const padLat = (maxLat - minLat) * 0.15 || 10;
  const padLon = (maxLon - minLon) * 0.15 || 10;

  const project = (lat: number, lon: number) => {
    const x = ((lon - (minLon - padLon)) / (maxLon + padLon - (minLon - padLon))) * 100;
    const y = ((maxLat + padLat - lat) / (maxLat + padLat - (minLat - padLat))) * 100;
    return { x: Math.max(2, Math.min(98, x)), y: Math.max(4, Math.min(96, y)) };
  };

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border bg-gradient-to-br from-emerald-50 via-sky-50 to-slate-100">
      {/* subtle grid */}
      <div
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "linear-gradient(#94a3b8 1px, transparent 1px), linear-gradient(90deg, #94a3b8 1px, transparent 1px)",
          backgroundSize: "50px 50px",
        }}
      />
      {markers.map((m) => {
        const pos = project(m.lat, m.lon);
        return (
          <div
            key={m.name}
            className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center"
            style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
          >
            <div
              className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-white shadow-md"
              style={{ background: m.color }}
              title={`${m.name}: AQI ${m.aqi ?? "n/a"}`}
            >
              <MapPin className="h-3 w-3 text-white" />
            </div>
            <span className="mt-1 rounded bg-white/90 px-1.5 py-0.5 text-[10px] font-medium text-slate-700 shadow">
              {m.name}
            </span>
          </div>
        );
      })}
      <div className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-[10px] text-muted-foreground">
        Map preview — add NEXT_PUBLIC_MAPBOX_TOKEN for a live Mapbox map.
      </div>
    </div>
  );
}