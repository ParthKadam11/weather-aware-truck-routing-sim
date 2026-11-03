import { useCallback, useMemo, useState } from "react";
import { analyzeRoutes } from "./api/client";
import { ForecastSlider } from "./components/ForecastSlider";
import { MapView } from "./components/MapView";
import { RiskLegend } from "./components/RiskLegend";
import { RouteForm } from "./components/RouteForm";
import { RouteSummaryCards } from "./components/RouteSummaryCards";
import { memoizeHeatmapFrames } from "./lib/heatmapFrames";
import type { AnalyzeRequest, AnalyzeResponse, HeatmapResponse } from "./types";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hour, setHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);

  const heatmapFrames = useMemo(() => memoizeHeatmapFrames(heatmap), [heatmap]);

  const onSubmit = useCallback(async (req: AnalyzeRequest) => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setHeatmap(null);
    setSelectedId(null);
    setHour(0);
    try {
      const result = await analyzeRoutes(req);
      setAnalysis(result);
      setHeatmap(result.heatmap ?? null);
      setSelectedId(result.recommendation.route_id);
      setHour(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const maxHour = Math.max(
    0,
    (heatmap?.hours ?? (heatmapFrames.length || 1)) - 1,
  );
  const timeLabel = heatmap?.times_utc?.[hour] ?? null;

  return (
    <div className="app-shell">
      <MapView
        analysis={analysis}
        selectedRouteId={selectedId}
        heatmap={heatmap}
        heatmapFrames={heatmapFrames}
        hour={hour}
        showHeatmap={showHeatmap}
        loading={loading}
      />

      <aside className="glass-panel-strong panel-scroll side-panel">
        <header>
          <h1 className="brand-mark">Corridor</h1>
          <p className="brand-sub">
            Weather-aware truck routing — pick the safest of three paths.
          </p>
        </header>

        <RouteForm loading={loading} onSubmit={onSubmit} />

        {loading && (
          <div className="loading-pulse">
            <span className="spinner" aria-hidden />
            Routing · weather · risk…
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        {analysis && !loading && (
          <RouteSummaryCards
            data={analysis}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        )}

        {!analysis && !loading && !error && (
          <p
            style={{
              margin: 0,
              fontSize: "0.8rem",
              color: "var(--muted)",
              textWrap: "pretty",
            }}
          >
            Defaults to Maharashtra (Mumbai → Pune). Tap a place chip into the
            focused field, then analyze to see routes and the heatmap.
          </p>
        )}
      </aside>

      <div className="glass-panel-strong forecast-bar">
        <ForecastSlider
          hour={hour}
          maxHour={maxHour}
          timeLabel={timeLabel}
          onChange={setHour}
          disabled={!heatmap || loading}
          showHeatmap={showHeatmap}
          onToggleHeatmap={setShowHeatmap}
        />
        <RiskLegend />
      </div>
    </div>
  );
}
