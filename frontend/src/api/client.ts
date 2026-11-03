import type { AnalyzeRequest, AnalyzeResponse, HeatmapResponse } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      (data && (data.error || JSON.stringify(data))) || `HTTP ${res.status}`;
    throw new Error(typeof msg === "string" ? msg : "Request failed");
  }
  return data as T;
}

export function analyzeRoutes(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  return post<AnalyzeResponse>("/routes/analyze", req);
}

export function fetchHeatmap(body: {
  origin: string;
  destination: string;
  hours?: number;
  demo_storm?: boolean | null;
}): Promise<HeatmapResponse> {
  return post<HeatmapResponse>("/weather/heatmap", body);
}
