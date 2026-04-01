/**
 * API client for the ClimateRisk Intel backend.
 * All external data fetching goes through the FastAPI backend — never directly.
 */
import { RiskReport, RiskRequest } from "@/types/risk";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class APIError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string
  ) {
    super(message);
    this.name = "APIError";
  }
}

/**
 * Assess climate risk for a given address.
 */
export async function assessRisk(request: RiskRequest): Promise<RiskReport> {
  const response = await fetch(`${API_URL}/api/risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new APIError(
      response.status,
      `Risk assessment failed (${response.status})`,
      errorData.detail || "Unknown error"
    );
  }

  return response.json() as Promise<RiskReport>;
}

/**
 * Check API health status.
 */
export async function checkHealth(): Promise<{ status: string; services: Record<string, boolean> }> {
  const response = await fetch(`${API_URL}/api/health`);
  return response.json();
}
