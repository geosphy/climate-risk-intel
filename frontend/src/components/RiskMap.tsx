"use client";

/**
 * RiskMap — Leaflet.js interactive map showing the asset location
 * with a color-coded circle overlay based on overall risk score.
 *
 * IMPORTANT: This component must be dynamically imported in page.tsx
 * with { ssr: false } because Leaflet requires a browser environment.
 *
 * Usage in page.tsx:
 *   const RiskMap = dynamic(() => import("@/components/RiskMap"), { ssr: false });
 */
import { useEffect, useRef } from "react";
import { RiskReport, RISK_COLORS } from "@/types/risk";

interface RiskMapProps {
  report: RiskReport | null;
  defaultLat?: number;
  defaultLon?: number;
}

export default function RiskMap({
  report,
  defaultLat = 39.8283,
  defaultLon = -98.5795,
}: RiskMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<unknown>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !mapRef.current) return;

    // Dynamically import Leaflet (browser-only)
    import("leaflet").then((L) => {
      // Fix default icon paths for Next.js
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      // Initialize map if not already done
      if (!mapInstanceRef.current && mapRef.current) {
        const lat = report?.latitude ?? defaultLat;
        const lon = report?.longitude ?? defaultLon;
        const zoom = report ? 13 : 4;

        const map = L.map(mapRef.current).setView([lat, lon], zoom);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a> contributors',
          maxZoom: 19,
        }).addTo(map);

        mapInstanceRef.current = map;
      }

      // Update map when report changes
      if (report && mapInstanceRef.current) {
        const map = mapInstanceRef.current as ReturnType<typeof L.map>;
        map.setView([report.latitude, report.longitude], 13, { animate: true });

        // Remove existing markers/circles
        map.eachLayer((layer) => {
          if (layer instanceof L.Marker || layer instanceof L.Circle) {
            map.removeLayer(layer);
          }
        });

        // Add risk circle overlay
        const color = RISK_COLORS[report.overall_risk.level];
        L.circle([report.latitude, report.longitude], {
          color,
          fillColor: color,
          fillOpacity: 0.25,
          radius: 500,
          weight: 2,
        }).addTo(map);

        // Add marker with popup
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
        (mapInstanceRef.current as ReturnType<typeof import("leaflet").map>).remove();
        mapInstanceRef.current = null;
      }
    };
  }, [report, defaultLat, defaultLon]);

  return (
    <div className="relative w-full h-64 sm:h-80 rounded-xl overflow-hidden border border-gray-200 shadow-sm">
      {/* Leaflet CSS */}
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossOrigin=""
      />
      <div ref={mapRef} className="w-full h-full" />
    </div>
  );
}
