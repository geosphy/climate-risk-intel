"use client";

/**
 * RiskMap — Leaflet.js map showing asset location with risk overlay.
 * Must be dynamically imported with { ssr: false } in page.tsx.
 */
import { useEffect, useRef } from "react";

interface MapReport {
  latitude: number;
  longitude: number;
  canonical_address: string;
  overall_risk: { level: string; score: number };
}

const RISK_COLORS: Record<string, string> = {
  Low: "#22c55e",
  Medium: "#eab308",
  High: "#f97316",
  Extreme: "#ef4444",
};

interface RiskMapProps {
  report: MapReport | null;
}

export default function RiskMap({ report }: RiskMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<unknown>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !mapRef.current) return;

    import("leaflet").then((L) => {
      // Fix default icon paths
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const lat = report?.latitude ?? 51.1657;
      const lon = report?.longitude ?? 10.4515;
      const zoom = report ? 13 : 5;

      if (!mapInstanceRef.current && mapRef.current) {
        const map = L.map(mapRef.current).setView([lat, lon], zoom);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap contributors",
          maxZoom: 19,
        }).addTo(map);
        mapInstanceRef.current = map;
      }

      if (report && mapInstanceRef.current) {
        const map = mapInstanceRef.current as ReturnType<typeof L.map>;
        map.setView([report.latitude, report.longitude], 13, { animate: true });

        map.eachLayer((layer) => {
          if (layer instanceof L.Marker || layer instanceof L.Circle) {
            map.removeLayer(layer);
          }
        });

        const color = RISK_COLORS[report.overall_risk.level] ?? "#94a3b8";
        L.circle([report.latitude, report.longitude], {
          color, fillColor: color, fillOpacity: 0.25, radius: 500, weight: 2,
        }).addTo(map);

        L.marker([report.latitude, report.longitude])
          .addTo(map)
          .bindPopup(
            `<strong>${report.overall_risk.level} Risk</strong><br/>
             ${report.canonical_address}<br/>
             <small>Score: ${Math.round(report.overall_risk.score * 100)}/100</small>`
          )
          .openPopup();
      }
    });

    return () => {
      if (mapInstanceRef.current) {
        (mapInstanceRef.current as { remove: () => void }).remove();
        mapInstanceRef.current = null;
      }
    };
  }, [report]);

  return (
    <div className="relative w-full h-64 sm:h-72 rounded-xl overflow-hidden border border-gray-700 shadow-sm">
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div ref={mapRef} className="w-full h-full" />
    </div>
  );
}
