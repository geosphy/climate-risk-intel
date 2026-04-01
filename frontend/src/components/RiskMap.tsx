"use client";

/**
 * RiskMap — Leaflet interactive map centred on the assessed address.
 *
 * Shows a colour-coded circle (500 m radius) reflecting overall risk level
 * and a marker popup with the risk score summary.
 * Defaults to a US overview when no report is loaded yet.
 *
 * MUST be dynamically imported with { ssr: false } because Leaflet needs a DOM:
 *   const RiskMap = dynamic(() => import("@/components/RiskMap"), { ssr: false });
 */
import { useEffect, useRef } from "react";
import { RiskReport, RISK_COLORS } from "@/types/risk";

interface RiskMapProps {
  report: RiskReport | null;
  defaultLat?: number;
  defaultLon?: number;
}

// Fix Leaflet's default icon paths when bundled with webpack / Next.js.
// Called once after the first import("leaflet") resolves.
let leafletIconFixed = false;
function fixLeafletIcons(L: typeof import("leaflet")) {
  if (leafletIconFixed) return;
  leafletIconFixed = true;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (L.Icon.Default.prototype as any)._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    iconUrl:       "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    shadowUrl:     "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  });
}

export default function RiskMap({
  report,
  defaultLat = 39.8283,
  defaultLon = -98.5795,
}: RiskMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<import("leaflet").Map | null>(null);
  const markerRef    = useRef<import("leaflet").Marker | null>(null);
  const circleRef    = useRef<import("leaflet").Circle | null>(null);

  // ── Effect 1: initialise map once on mount ──────────────────────────────
  useEffect(() => {
    if (typeof window === "undefined" || !containerRef.current) return;

    import("leaflet").then((L) => {
      // Guard against double-init in React Strict Mode
      if (!containerRef.current || mapRef.current) return;
      fixLeafletIcons(L);

      const map = L.map(containerRef.current).setView([defaultLat, defaultLon], 4);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '© <a href="https://openstreetmap.org">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      mapRef.current = map;
    });

    return () => {
      // Destroy on unmount only — not on every dep change
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current  = null;
        markerRef.current = null;
        circleRef.current = null;
      }
    };
  // defaultLat/Lon are stable props — intentionally omitted to run once
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Effect 2: update overlays whenever `report` changes ────────────────
  useEffect(() => {
    if (!mapRef.current) return;

    import("leaflet").then((L) => {
      const map = mapRef.current;
      if (!map) return;

      // Clear previous overlays
      if (markerRef.current) { markerRef.current.remove(); markerRef.current = null; }
      if (circleRef.current) { circleRef.current.remove(); circleRef.current = null; }

      if (!report) {
        map.setView([defaultLat, defaultLon], 4, { animate: true });
        return;
      }

      const { latitude: lat, longitude: lon, overall_risk, canonical_address } = report;
      const color = RISK_COLORS[overall_risk.level];

      map.setView([lat, lon], 13, { animate: true });

      // Colour-coded risk circle — 500 m radius
      circleRef.current = L.circle([lat, lon], {
        color,
        fillColor: color,
        fillOpacity: 0.22,
        radius:      500,
        weight:      2,
      }).addTo(map);

      // Marker + popup
      markerRef.current = L.marker([lat, lon])
        .addTo(map)
        .bindPopup(
          `<div style="font-family:system-ui,sans-serif;font-size:13px;line-height:1.6">
             <strong style="color:${color}">${overall_risk.level} Risk</strong><br/>
             ${canonical_address}<br/>
             <span style="color:#555">Score: ${Math.round(overall_risk.score * 100)}/100</span>
           </div>`,
        )
        .openPopup();
    });
  }, [report, defaultLat, defaultLon]);

  return (
    <div className="relative w-full rounded-xl overflow-hidden border border-white/10 shadow-lg">
      {/*
        Leaflet CSS — loaded client-side only.
        Safe here because this component is always imported with ssr:false.
      */}
      {/* eslint-disable-next-line @next/next/no-css-tags */}
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div ref={containerRef} className="w-full h-64 sm:h-80" />
    </div>
  );
}
