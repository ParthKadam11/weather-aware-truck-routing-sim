import { useCallback, useState } from "react";
import { analyzeRoutes, fetchHeatmap } from "./api/client";
import { ForecastSlider } from "./components/ForecastSlider";
import { MapView } from "./components/MapView";
import { RiskLegend } from "./components/RiskLegend";
import { RouteForm } from "./components/RouteForm";
import { RouteSummaryCards } from "./components/RouteSummaryCards";
import type { AnalyzeRequest, AnalyzeResponse, HeatmapResponse } from "./types";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hour, setHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);

  const onSubmit = useCallback(async (req: AnalyzeRequest) => {
    setLoading(true);
    setError(null);
    try {
      const [result, grid] = await Promise.all([
        analyzeRoutes(req),
        fetchHeatmap({
          origin: req.origin,
          destination: req.destination,
          hours: 48,
          demo_storm: req.demo_storm,
        }),
      ]);
      setAnalysis(result);
      setHeatmap(grid);
      setSelectedId(result.recommendation.route_id);
      setHour(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const frame = heatmap?.frames[hour] ?? null;

  return (
    <div className="app-shell">
      {/* Full-bleed map */}
      <MapView
        analysis={analysis}
        selectedRouteId={selectedId}
        heatmapFrame={frame}
        showHeatmap={showHeatmap}
      />

      {/* Floating glass sidebar */}
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

      {/* Bottom glass forecast bar */}
      <div className="glass-panel-strong forecast-bar">
        <ForecastSlider
          hour={hour}
          maxHour={Math.max(0, (heatmap?.hours ?? 1) - 1)}
          timeLabel={frame?.time_utc ?? null}
          onChange={setHour}
          disabled={!heatmap}
          showHeatmap={showHeatmap}
          onToggleHeatmap={setShowHeatmap}
        />
        <RiskLegend />
      </div>
    </div>
  );
}
