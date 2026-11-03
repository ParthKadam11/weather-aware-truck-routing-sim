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
import { MUTED_ROUTE, RISK_COLORS, ROUTE_CASING } from "../types";
import styles from "./MapView.module.css";

const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
const MH_CENTER: [number, number] = [75.7, 19.2];
const MH_ZOOM = 6.4;
const HEATMAP_LAYER_ID = "corridor-heatmap";

interface Props {
  analysis: AnalyzeResponse | null;
  selectedRouteId: string | null;
  heatmap: HeatmapResponse | null;
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
      padding: { top: 72, bottom: 140, left: 400, right: 72 },
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

  // Muted first; selected last (on top)
  const ordered = [...routes].sort((a, b) => {
    const score = (r: RouteOption) => (r.id === selected?.id ? 1 : 0);
    return score(a) - score(b);
  });

  const layers: Layer[] = [];

  for (const route of ordered) {
    const isSelected = selected?.id === route.id;
    const segments = buildRiskSegments(route);

    if (isSelected) {
      // 7px dark casing under 5px risk-colored stroke
      layers.push(
        new PathLayer<RiskSegment>({
          id: `casing-${route.id}`,
          data: segments,
          getPath: (s) => s.path,
          getColor: hexToRgba(ROUTE_CASING, 230),
          getWidth: 7,
          widthUnits: "pixels",
          pickable: false,
          jointRounded: true,
          capRounded: true,
        }),
      );
      layers.push(
        new PathLayer<RiskSegment>({
          id: `path-${route.id}`,
          data: segments,
          getPath: (s) => s.path,
          getColor: (s) => hexToRgba(RISK_COLORS[s.risk], 255),
          getWidth: 5,
          widthUnits: "pixels",
          pickable: true,
          jointRounded: true,
          capRounded: true,
          updateTriggers: {
            getColor: route.checkpoints.map((c) => c.risk).join(","),
          },
        }),
      );
    } else {
      // Other routes: 3px #94a3b8 at 60%
      layers.push(
        new PathLayer<RouteOption>({
          id: `path-${route.id}`,
          data: [route],
          getPath: (r) =>
            r.geometry.map((p) => [p.lng, p.lat] as [number, number]),
          getColor: hexToRgba(MUTED_ROUTE, Math.round(0.6 * 255)),
          getWidth: 3,
          widthUnits: "pixels",
          pickable: true,
          jointRounded: true,
          capRounded: true,
        }),
      );
    }
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
          d.kind === "Origin" ? [15, 23, 42, 240] : [34, 197, 94, 255],
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
    getWeight: (_d: HeatmapPoint, info: { index: number }) =>
      weights[info.index] ?? 0,
    radiusPixels: 48,
    intensity: 1.2,
    threshold: 0.03,
    opacity: 0.55,
    colorDomain: [0, 1],
    colorRange: [
      [34, 197, 94],
      [234, 179, 8],
      [249, 115, 22],
      [220, 38, 38],
      [76, 29, 149],
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
          return {
            className: "deck-tooltip",
            html: `<strong>${c.risk}</strong><br/>
              <span style="opacity:.85">${c.risk_reason || "—"}</span><br/>
              ETA ${formatEta(c.eta_local)}<br/>
              Wind ${c.weather.wind_mph.toFixed(1)} mph ·
              Rain ${c.weather.precip_in_hr.toFixed(2)} in/h ·
              Snow ${c.weather.snow_in_hr.toFixed(2)} in/h`,
          };
        }
        if (layer?.id?.startsWith("path-")) {
          const s = object as RiskSegment | RouteOption;
          if ("routeLabel" in s) {
            return {
              className: "deck-tooltip",
              html: `<strong>${s.routeLabel}</strong><br/>${s.risk}`,
            };
          }
          return {
            className: "deck-tooltip",
            html: `<strong>${(s as RouteOption).label}</strong>`,
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

  useEffect(() => {
    showHeatmapRef.current = showHeatmap;
    if (loading || !analysis) {
      routeLayersRef.current = [];
      overlayRef.current?.setProps({ layers: [] });
      return;
    }
    routeLayersRef.current = buildRouteLayers(analysis, selectedRouteId);
    paint(hourRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis, selectedRouteId, heatmap, showHeatmap, loading]);

  useEffect(() => {
    showHeatmapRef.current = showHeatmap;
    schedulePaint(hour);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hour]);

  return (
    <div className={styles.stage}>
      <div ref={containerRef} className={styles.canvas} />
    </div>
  );
}
