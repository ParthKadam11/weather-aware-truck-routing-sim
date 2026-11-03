import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { analyzeRoutes } from "./api/client";
import { ForecastSlider } from "./components/ForecastSlider";
import { MapView } from "./components/MapView";
import { RiskLegend } from "./components/RiskLegend";
import { RouteForm } from "./components/RouteForm";
import { RouteSummaryCards } from "./components/RouteSummaryCards";
import { formatForecastIstLabel } from "./lib/forecastLabel";
import { memoizeHeatmapFrames } from "./lib/heatmapFrames";
import type { AnalyzeRequest, AnalyzeResponse, HeatmapResponse } from "./types";
import styles from "./App.module.css";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hour, setHour] = useState(0);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const heatmapFrames = useMemo(() => memoizeHeatmapFrames(heatmap), [heatmap]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const onSubmit = useCallback(async (req: AnalyzeRequest) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setLoadingStep("Routing…");
    setError(null);
    setAnalysis(null);
    setHeatmap(null);
    setSelectedId(null);
    setHour(0);

    try {
      setLoadingStep("Weather · risk…");
      const result = await analyzeRoutes(req, ac.signal);
      if (ac.signal.aborted) return;
      setAnalysis(result);
      setHeatmap(result.heatmap ?? null);
      setSelectedId(result.recommendation.route_id);
      setHour(0);
    } catch (e) {
      if (ac.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) {
        return;
      }
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      if (!ac.signal.aborted) {
        setLoading(false);
        setLoadingStep(null);
      }
    }
  }, []);

  const maxHour = Math.max(
    0,
    (heatmap?.hours ?? (heatmapFrames.length || 1)) - 1,
  );
  const timeLabel = formatForecastIstLabel(hour, heatmap?.times_utc);

  return (
    <div className={styles.shell}>
      <div className={styles.map}>
        <MapView
          analysis={analysis}
          selectedRouteId={selectedId}
          heatmap={heatmap}
          heatmapFrames={heatmapFrames}
          hour={hour}
          showHeatmap={showHeatmap}
          loading={loading}
        />
      </div>

      {loading ? (
        <div className={styles.dim} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden />
        </div>
      ) : null}

      <aside className={styles.sidebar}>
        <header>
          <h1 className={styles.brand}>Corridor</h1>
          <p className={styles.brandSub}>
            Weather-aware truck routing — pick the safest path.
          </p>
        </header>

        <RouteForm
          loading={loading}
          loadingStep={loadingStep}
          onSubmit={onSubmit}
        />

        {error ? <p className={styles.error}>{error}</p> : null}

        {analysis && !loading ? (
          <RouteSummaryCards
            data={analysis}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ) : null}

        {!analysis && !loading && !error ? (
          <p className={styles.hint}>
            Defaults to Mumbai → Pune. Swap ends, pick a checkpoint spacing,
            then analyze.
          </p>
        ) : null}
      </aside>

      <div className={styles.legendDock}>
        <RiskLegend />
      </div>

      <div className={styles.sliderDock}>
        <ForecastSlider
          hour={hour}
          maxHour={maxHour}
          timeLabel={timeLabel}
          onChange={setHour}
          disabled={!heatmap || loading}
          showHeatmap={showHeatmap}
          onToggleHeatmap={setShowHeatmap}
        />
      </div>
    </div>
  );
}
