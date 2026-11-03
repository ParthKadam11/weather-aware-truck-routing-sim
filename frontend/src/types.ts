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

export interface AnalyzeResponse {
  origin: { query: string; lat: number; lng: number; label: string };
  destination: { query: string; lat: number; lng: number; label: string };
  departure_utc: string;
  load_lb: number;
  interval_miles: number;
  display_tz: string;
  demo_storm: boolean;
  recommendation: {
    route_id: string;
    reason: string;
    ranked_ids: string[];
  };
  routes: RouteOption[];
}

export interface HeatmapCell {
  lat: number;
  lng: number;
  wind_mph: number;
  precip_in: number;
  snow_in: number;
  intensity: number;
}

export interface HeatmapFrame {
  hour: number;
  time_utc: string | null;
  cells: HeatmapCell[];
}

export interface HeatmapResponse {
  bbox: [number, number, number, number];
  hours: number;
  demo_storm: boolean;
  frames: HeatmapFrame[];
}

export interface AnalyzeRequest {
  origin: string;
  destination: string;
  departure: string;
  load_lb: number;
  interval_miles: 10 | 25 | 50;
  display_tz?: string;
  demo_storm?: boolean | null;
}

/** Risk palette — cool slate → amber → rose (no green). */
export const RISK_COLORS: Record<RiskLabel, string> = {
  Low: "#6b8fad",
  Moderate: "#c4a35a",
  High: "#d17a45",
  Severe: "#c44b4b",
  "No Travel": "#5c3d6e",
};

export const ROUTE_COLORS = {
  recommended: "#c9922a",
  recommendedHalo: "#c9922a",
  selected: "#3d5a80",
  muted: "#8a93a3",
} as const;
