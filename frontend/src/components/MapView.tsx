import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { Layer } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { MapLibreOverlay } from "@deck.gl/maplibre";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type {
  AnalyzeResponse,
  Checkpoint,
  HeatmapCell,
  HeatmapFrame,
  RiskLabel,
  RouteOption,
} from "../types";
import { RISK_COLORS, ROUTE_COLORS } from "../types";

const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

/** Maharashtra approximate center */
const MH_CENTER: [number, number] = [75.7, 19.2];
const MH_ZOOM = 6.4;

interface Props {
  analysis: AnalyzeResponse | null;
  selectedRouteId: string | null;
  heatmapFrame: HeatmapFrame | null;
  showHeatmap: boolean;
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

function buildLayers(
  analysis: AnalyzeResponse | null,
  selectedRouteId: string | null,
  heatmapFrame: HeatmapFrame | null,
  showHeatmap: boolean,
): Layer[] {
  const routes = analysis?.routes ?? [];
  const selected = selectedRouteId
    ? routes.find((r) => r.id === selectedRouteId)
    : (routes.find((r) => r.recommended) ?? routes[0]);

  const ordered = [...routes].sort((a, b) => {
    const score = (r: RouteOption) =>
      r.id === selected?.id ? 2 : r.recommended ? 1 : 0;
    return score(a) - score(b);
  });

  const layers: Layer[] = [];

  // Heatmap first (under routes). Aggregation layers need non-interleaved overlay.
  if (showHeatmap && heatmapFrame?.cells?.length) {
    const cells = heatmapFrame.cells.filter((c) => c.intensity > 0.02);
    if (cells.length) {
      layers.push(
        new HeatmapLayer<HeatmapCell>({
          id: `weather-heatmap-${heatmapFrame.hour}`,
          data: cells,
          getPosition: (d) => [d.lng, d.lat],
          getWeight: (d) => Math.max(0.05, d.intensity),
          radiusPixels: 55,
          intensity: 1.4,
          threshold: 0.08,
          opacity: 0.55,
          // RGB only — alpha channels break HeatmapLayer color ramps
          colorRange: [
            [107, 143, 173],
            [196, 163, 90],
            [209, 122, 69],
            [196, 75, 75],
            [92, 61, 110],
          ],
        }),
      );
    }
  }

  for (const route of ordered) {
    const isSelected = selected?.id === route.id;
    const isRec = route.recommended;

    if (isRec || isSelected) {
      layers.push(
        new PathLayer<RouteOption>({
          id: `halo-${route.id}`,
          data: [route],
          getPath: (r) =>
            r.geometry.map((p) => [p.lng, p.lat] as [number, number]),
          getColor: isRec
            ? hexToRgba(ROUTE_COLORS.recommended, 55)
            : hexToRgba(ROUTE_COLORS.selected, 45),
          getWidth: 14,
          widthUnits: "pixels",
          pickable: false,
          jointRounded: true,
          capRounded: true,
        }),
      );
    }

    layers.push(
      new PathLayer<RouteOption>({
        id: `path-${route.id}`,
        data: [route],
        getPath: (r) =>
          r.geometry.map((p) => [p.lng, p.lat] as [number, number]),
        getColor: isRec
          ? hexToRgba(ROUTE_COLORS.recommended, 245)
          : isSelected
            ? hexToRgba(ROUTE_COLORS.selected, 235)
            : hexToRgba(ROUTE_COLORS.muted, 150),
        getWidth: isRec ? 5.5 : isSelected ? 4.5 : 2.5,
        widthUnits: "pixels",
        pickable: true,
        jointRounded: true,
        capRounded: true,
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

export function MapView({
  analysis,
  selectedRouteId,
  heatmapFrame,
  showHeatmap,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapLibreOverlay | null>(null);

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

    // Non-interleaved so HeatmapLayer (aggregation) actually paints
    const overlay = new MapLibreOverlay({
      interleaved: false,
      layers: [],
    });
    map.addControl(overlay);
    overlayRef.current = overlay;

    map.on("error", (e) => console.error("[MapLibre]", e.error ?? e));

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    requestAnimationFrame(() => map.resize());

    return () => {
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
    const overlay = overlayRef.current;
    if (!overlay) return;

    const layers = buildLayers(
      analysis,
      selectedRouteId,
      heatmapFrame,
      showHeatmap,
    );

    overlay.setProps({
      layers,
      getTooltip: ({ object, layer }) => {
        if (!object) return null;
        if (layer?.id === "checkpoints") {
          const c = object as Checkpoint;
          return {
            className: "deck-tooltip",
            html: `<strong>${c.risk}</strong> · ${c.distance_miles.toFixed(0)} mi<br/>
              ETA ${new Date(c.eta_local).toLocaleString()}<br/>
              Wind ${c.weather.wind_mph} mph · Rain ${c.weather.precip_in_hr} in/h · Snow ${c.weather.snow_in_hr} in/h`,
          };
        }
        if (layer?.id?.startsWith("path-")) {
          const r = object as RouteOption;
          return {
            className: "deck-tooltip",
            html: `<strong>${r.label}</strong><br/>${r.distance_miles.toFixed(0)} mi · ${r.duration_hours.toFixed(1)} h`,
          };
        }
        if (layer?.id === "endpoints") {
          const d = object as { kind: string };
          return { className: "deck-tooltip", html: `<strong>${d.kind}</strong>` };
        }
        return null;
      },
    });
  }, [analysis, selectedRouteId, heatmapFrame, showHeatmap]);

  return (
    <div className="map-stage" style={{ background: "var(--map-wash)" }}>
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
    </div>
  );
}
