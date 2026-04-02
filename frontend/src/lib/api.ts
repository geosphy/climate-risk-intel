/**
 * API client for Geosphy Data Center Climate Risk backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://climate-risk-intel-production.up.railway.app";

export class APIError extends Error {
  constructor(public status: number, message: string, public detail?: string) {
    super(message);
    this.name = "APIError";
  }
}

export async function assessRisk(request: { address: string; asset_type: string }): Promise<any> {
  const response = await fetch(`${API_URL}/api/risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new APIError(response.status, `Risk assessment failed (${response.status})`, errorData.detail || "Unknown error");
  }
  return response.json();
}
