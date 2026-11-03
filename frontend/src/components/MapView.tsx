import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { Layer } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { MapLibreOverlay } from "@deck.gl/maplibre";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import { buildRiskSegments, type RiskSegment } from "../lib/routeSegments";
import type {
  AnalyzeResponse,
  Checkpoint,
  HeatmapFrameWeights,
  HeatmapPoint,
  HeatmapResponse,
  RiskLabel,
  RouteOption,
} from "../types";
import { RISK_COLORS, ROUTE_COLORS } from "../types";

const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
const MH_CENTER: [number, number] = [75.7, 19.2];
const MH_ZOOM = 6.4;

const HEATMAP_LAYER_ID = "corridor-heatmap";

interface Props {
  analysis: AnalyzeResponse | null;
  selectedRouteId: string | null;
  heatmap: HeatmapResponse | null;
  /** Precomputed weights for all 48 hours — indexed on slider change only. */
  heatmapFrames: HeatmapFrameWeights[];
  hour: number;
  showHeatmap: boolean;
  loading?: boolean;
}

function hexToRgba(hex: string, alpha = 255): [number, number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
    alpha,
  ];
}

function fitBounds(map: maplibregl.Map, analysis: AnalyzeResponse) {
  const bounds = new maplibregl.LngLatBounds();
  for (const r of analysis.routes) {
    for (const p of r.geometry) bounds.extend([p.lng, p.lat]);
  }
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, {
      padding: { top: 72, bottom: 120, left: 420, right: 72 },
      duration: 700,
      maxZoom: 10,
    });
  }
}

function formatEta(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function buildRouteLayers(
  analysis: AnalyzeResponse | null,
  selectedRouteId: string | null,
): Layer[] {
  if (!analysis?.routes?.length) return [];

  const routes = analysis.routes;
  const selected = selectedRouteId
    ? routes.find((r) => r.id === selectedRouteId)
    : (routes.find((r) => r.recommended) ?? routes[0]);

  // Draw muted first; recommended last so it sits on top
  const ordered = [...routes].sort((a, b) => {
    const score = (r: RouteOption) =>
      r.recommended ? 2 : r.id === selected?.id ? 1 : 0;
    return score(a) - score(b);
  });

  const layers: Layer[] = [];

  for (const route of ordered) {
    const segments = buildRiskSegments(route);
    const isRec = route.recommended;
    const alpha = isRec ? 245 : 130;
    const width = isRec ? 5 : 2.5;

    if (isRec) {
      layers.push(
        new PathLayer<RiskSegment>({
          id: `halo-${route.id}`,
          data: segments,
          getPath: (s) => s.path,
          getColor: hexToRgba(ROUTE_COLORS.recommended, 40),
          getWidth: 12,
          widthUnits: "pixels",
          pickable: false,
          jointRounded: true,
          capRounded: true,
        }),
      );
    }

    layers.push(
      new PathLayer<RiskSegment>({
        id: `path-${route.id}`,
        data: segments,
        getPath: (s) => s.path,
        getColor: (s) => hexToRgba(RISK_COLORS[s.risk], alpha),
        getWidth: width,
        widthUnits: "pixels",
        pickable: true,
        jointRounded: true,
        capRounded: true,
        updateTriggers: {
          getColor: route.checkpoints.map((c) => c.risk).join(","),
        },
      }),
    );
  }

  const checkpoints = selected?.checkpoints ?? [];

  layers.push(
    new ScatterplotLayer<Checkpoint>({
      id: "checkpoint-rings",
      data: checkpoints,
      getPosition: (c) => [c.lng, c.lat],
      getFillColor: [255, 255, 255, 230],
      getLineColor: (c) => hexToRgba(RISK_COLORS[c.risk as RiskLabel], 255),
      getRadius: 9,
      radiusUnits: "pixels",
      stroked: true,
      filled: true,
      lineWidthMinPixels: 2.5,
      pickable: false,
    }),
  );

  layers.push(
    new ScatterplotLayer<Checkpoint>({
      id: "checkpoints",
      data: checkpoints,
      getPosition: (c) => [c.lng, c.lat],
      getFillColor: (c) => hexToRgba(RISK_COLORS[c.risk as RiskLabel], 255),
      getRadius: 4.5,
      radiusUnits: "pixels",
      pickable: true,
      stroked: false,
    }),
  );

  if (selected && selected.geometry.length >= 2) {
    const start = selected.geometry[0];
    const end = selected.geometry[selected.geometry.length - 1];
    layers.push(
      new ScatterplotLayer({
        id: "endpoints",
        data: [
          { lng: start.lng, lat: start.lat, kind: "Origin" },
          { lng: end.lng, lat: end.lat, kind: "Destination" },
        ],
        getPosition: (d: { lng: number; lat: number }) => [d.lng, d.lat],
        getFillColor: (d: { kind: string }) =>
          d.kind === "Origin"
            ? [14, 20, 32, 240]
            : hexToRgba(ROUTE_COLORS.recommended, 255),
        getRadius: 7,
        radiusUnits: "pixels",
        stroked: true,
        getLineColor: [255, 255, 255, 255],
        lineWidthMinPixels: 2,
        pickable: true,
      }),
    );
  }

  return layers;
}

function buildHeatmapLayer(
  points: HeatmapPoint[],
  weights: HeatmapFrameWeights,
  hour: number,
  visible: boolean,
): Layer | null {
  if (!visible || !points.length || !weights.length) return null;
  return new HeatmapLayer<HeatmapPoint>({
    id: HEATMAP_LAYER_ID,
    data: points,
    getPosition: (d) => d.coordinates,
    // Index into the memoized frame — no risk array re-walk beyond O(1) lookup
    getWeight: (_d: HeatmapPoint, info: { index: number }) =>
      weights[info.index] ?? 0.05,
    radiusPixels: 48,
    intensity: 1.35,
    threshold: 0.05,
    opacity: 0.58,
    colorRange: [
      [47, 158, 68],
      [230, 184, 0],
      [232, 89, 12],
      [201, 42, 42],
      [26, 16, 36],
    ],
    updateTriggers: {
      getWeight: hour,
    },
  });
}

export function MapView({
  analysis,
  selectedRouteId,
  heatmap,
  heatmapFrames,
  hour,
  showHeatmap,
  loading = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapLibreOverlay | null>(null);

  const routeLayersRef = useRef<Layer[]>([]);
  const hourRef = useRef(hour);
  const showHeatmapRef = useRef(showHeatmap);
  const rafRef = useRef<number | null>(null);

  const framesRef = useRef(heatmapFrames);
  const pointsRef = useRef(heatmap?.points ?? []);

  useEffect(() => {
    framesRef.current = heatmapFrames;
    pointsRef.current = heatmap?.points ?? [];
  }, [heatmapFrames, heatmap]);

  const paint = (h: number) => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    const weights = framesRef.current[h] ?? framesRef.current[0] ?? [];
    const heat = buildHeatmapLayer(
      pointsRef.current,
      weights,
      h,
      showHeatmapRef.current,
    );
    // Heatmap under routes; same route layer instances reused across hours
    const layers = heat
      ? [heat, ...routeLayersRef.current]
      : [...routeLayersRef.current];
    overlay.setProps({ layers });
  };

  const schedulePaint = (h: number) => {
    hourRef.current = h;
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      paint(hourRef.current);
    });
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el || mapRef.current) return;

    const map = new maplibregl.Map({
      container: el,
      style: MAP_STYLE,
      center: MH_CENTER,
      zoom: MH_ZOOM,
      preserveDrawingBuffer: true,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;

    const overlay = new MapLibreOverlay({
      interleaved: false,
      layers: [],
      getTooltip: ({ object, layer }) => {
        if (!object) return null;
        if (layer?.id === "checkpoints") {
          const c = object as Checkpoint;
          const reason = c.risk_reason || "—";
          return {
            className: "deck-tooltip",
            html: `<strong>${c.risk}</strong><br/>
              <span style="opacity:.85">${reason}</span><br/>
              ETA ${formatEta(c.eta_local)}<br/>
              Wind ${c.weather.wind_mph.toFixed(1)} mph ·
              Rain ${c.weather.precip_in_hr.toFixed(2)} in/h ·
              Snow ${c.weather.snow_in_hr.toFixed(2)} in/h`,
          };
        }
        if (layer?.id?.startsWith("path-")) {
          const s = object as RiskSegment;
          return {
            className: "deck-tooltip",
            html: `<strong>${s.routeLabel}</strong><br/>${s.risk}`,
          };
        }
        if (layer?.id === "endpoints") {
          const d = object as { kind: string };
          return { className: "deck-tooltip", html: `<strong>${d.kind}</strong>` };
        }
        return null;
      },
    });
    map.addControl(overlay);
    overlayRef.current = overlay;

    map.on("error", (e) => console.error("[MapLibre]", e.error ?? e));

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    requestAnimationFrame(() => map.resize());

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      ro.disconnect();
      overlay.finalize?.();
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !analysis) return;
    const run = () => {
      fitBounds(map, analysis);
      map.resize();
    };
    if (map.loaded()) run();
    else map.once("load", run);
  }, [analysis]);

  // Structural rebuild only when routes / selection / heatmap presence change — NOT on hour
  useEffect(() => {
    showHeatmapRef.current = showHeatmap;
    if (loading || !analysis) {
      routeLayersRef.current = [];
      const overlay = overlayRef.current;
      overlay?.setProps({ layers: [] });
      return;
    }
    routeLayersRef.current = buildRouteLayers(analysis, selectedRouteId);
    paint(hourRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hour handled separately via rAF
  }, [analysis, selectedRouteId, heatmap, showHeatmap, loading]);

  // Slider: update only heatmap weights (same layer id + updateTriggers), rAF-throttled
  useEffect(() => {
    showHeatmapRef.current = showHeatmap;
    schedulePaint(hour);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hour]);

  return (
    <div className="map-stage" style={{ background: "var(--map-wash)" }}>
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      {loading ? (
        <div className="map-loading" role="status" aria-live="polite">
          <span className="spinner" aria-hidden />
          <span>Updating routes &amp; weather…</span>
        </div>
      ) : null}
    </div>
  );
}
