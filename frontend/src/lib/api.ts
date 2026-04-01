/**
 * API client for the ClimateRisk Intel backend.
 *
 * Uses RELATIVE paths (/api/...) so all requests route through the
 * Next.js reverse-proxy rewrite defined in next.config.js. This avoids
 * two problems with using a full URL:
 *
 *  1. CORS — the browser never makes a cross-origin request.
 *  2. Docker build-time baking — NEXT_PUBLIC_* vars are embedded at
 *     `docker build` time, but the backend hostname in Docker Compose is
 *     only known at runtime (http://backend:8000). The proxy rewrite reads
 *     BACKEND_URL at server start, so the correct internal hostname is used
 *     without ever exposing it to the client bundle.
 */
import { RiskReport, RiskRequest } from "@/types/risk";

export class APIError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
  ) {
    super(message);
    this.name = "APIError";
  }
}

/**
 * Assess climate risk for a given address.
 *
 * @param request  Address + asset type.
 * @param signal   Optional AbortSignal so callers can cancel in-flight requests.
 */
export async function assessRisk(
  request: RiskRequest,
  signal?: AbortSignal,
): Promise<RiskReport> {
  const response = await fetch("/api/risk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new APIError(
      response.status,
      `Risk assessment failed (${response.status})`,
      errorData.detail ?? "Unknown error",
    );
  }

  return response.json() as Promise<RiskReport>;
}

export interface HealthStatus {
  status: string;
  version: string;
  services: Record<string, boolean>;
}

/**
 * Ping the backend health endpoint.
 * Returns null if the backend is unreachable (network error, timeout, etc.)
 */
export async function checkHealth(): Promise<HealthStatus | null> {
  try {
    const response = await fetch("/api/health", {
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return null;
    return response.json() as Promise<HealthStatus>;
  } catch {
    return null;
  }
}
