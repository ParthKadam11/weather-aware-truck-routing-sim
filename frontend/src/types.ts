export type RiskLabel = "Low" | "Moderate" | "High" | "Severe" | "No Travel";

export interface WeatherAtPoint {
  wind_mph: number;
  precip_in_hr: number;
  snow_in_hr: number;
}

export interface Checkpoint {
  index: number;
  lat: number;
  lng: number;
  distance_miles: number;
  segment_miles: number;
  eta_utc: string;
  eta_local: string;
  weather: WeatherAtPoint;
  risk: RiskLabel;
  risk_score: number;
  risk_reason: string;
}

export interface RouteOption {
  id: string;
  label: string;
  distance_miles: number;
  duration_s: number;
  duration_hours: number;
  geometry: { lng: number; lat: number }[];
  checkpoints: Checkpoint[];
  miles_by_risk: Record<string, number>;
  average_risk: number;
  recommended: boolean;
  rank: number;
}

/** Corridor grid point: GeoJSON [lng, lat] + 48 hourly risk scores (1–5). */
export interface HeatmapPoint {
  coordinates: [number, number];
  risk: number[];
}

export interface HeatmapResponse {
  bbox: [number, number, number, number];
  hours: number;
  times_utc: string[];
  coordinate_order: "lng,lat";
  buffer_km: number;
  demo_storm: boolean;
  points: HeatmapPoint[];
}

export interface AnalyzeResponse {
  origin: { query: string; lat: number; lng: number; label: string };
  destination: { query: string; lat: number; lng: number; label: string };
  departure_utc: string;
  load_lb: number;
  interval_miles: number;
  display_tz: string;
  demo_storm: boolean;
  routing_note?: string | null;
  recommendation: {
    route_id: string;
    reason: string;
    ranked_ids: string[];
  };
  routes: RouteOption[];
  heatmap: HeatmapResponse;
}

export type HeatmapFrameWeights = number[];

export interface AnalyzeRequest {
  origin: string;
  destination: string;
  departure: string;
  load_lb: number;
  interval_miles: 10 | 25 | 50;
  display_tz?: string;
  demo_storm?: boolean | null;
}

/** Risk palette — Low / Moderate / High / Severe / No Travel */
export const RISK_COLORS: Record<RiskLabel, string> = {
  Low: "#22c55e",
  Moderate: "#eab308",
  High: "#f97316",
  Severe: "#dc2626",
  "No Travel": "#4c1d95",
};

export const RISK_ORDER: RiskLabel[] = [
  "Low",
  "Moderate",
  "High",
  "Severe",
  "No Travel",
];

export const MUTED_ROUTE = "#94a3b8";
export const ROUTE_CASING = "#0f172a";
