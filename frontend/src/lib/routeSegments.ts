import type { RiskLabel, RouteOption } from "../types";

const EARTH_MI = 3958.8;

function haversineMi(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number },
): number {
  const toR = Math.PI / 180;
  const dLat = (b.lat - a.lat) * toR;
  const dLng = (b.lng - a.lng) * toR;
  const lat1 = a.lat * toR;
  const lat2 = b.lat * toR;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_MI * Math.asin(Math.min(1, Math.sqrt(h)));
}

export interface RiskSegment {
  id: string;
  path: [number, number][];
  risk: RiskLabel;
  recommended: boolean;
  routeLabel: string;
}

/** Slice polyline between two cumulative mileages along the geometry. */
function sliceByMiles(
  geom: { lng: number; lat: number }[],
  cumMi: number[],
  startMi: number,
  endMi: number,
): [number, number][] {
  if (endMi <= startMi + 1e-6) return [];
  const path: [number, number][] = [];

  for (let i = 0; i < geom.length - 1; i++) {
    const aMi = cumMi[i];
    const bMi = cumMi[i + 1];
    if (bMi < startMi || aMi > endMi) continue;

    const a = geom[i];
    const b = geom[i + 1];
    const segLen = bMi - aMi || 1e-9;

    let t0 = (startMi - aMi) / segLen;
    let t1 = (endMi - aMi) / segLen;
    t0 = Math.max(0, Math.min(1, t0));
    t1 = Math.max(0, Math.min(1, t1));
    if (t1 <= t0) continue;

    const p0: [number, number] = [
      a.lng + (b.lng - a.lng) * t0,
      a.lat + (b.lat - a.lat) * t0,
    ];
    const p1: [number, number] = [
      a.lng + (b.lng - a.lng) * t1,
      a.lat + (b.lat - a.lat) * t1,
    ];

    if (!path.length) path.push(p0);
    else {
      const last = path[path.length - 1];
      if (Math.abs(last[0] - p0[0]) > 1e-8 || Math.abs(last[1] - p0[1]) > 1e-8) {
        path.push(p0);
      }
    }
    path.push(p1);
  }

  return path;
}

/**
 * Color each forward segment (checkpoint i → i+1) by checkpoint i's risk.
 * Matches backend forward_segment_miles ownership.
 */
export function buildRiskSegments(route: RouteOption): RiskSegment[] {
  const geom = route.geometry;
  if (geom.length < 2) return [];

  const cumMi: number[] = [0];
  for (let i = 1; i < geom.length; i++) {
    cumMi.push(cumMi[i - 1] + haversineMi(geom[i - 1], geom[i]));
  }

  const cps = [...route.checkpoints].sort(
    (a, b) => a.distance_miles - b.distance_miles,
  );

  if (cps.length < 2) {
    const risk = (cps[0]?.risk ?? "Low") as RiskLabel;
    return [
      {
        id: `${route.id}-full`,
        path: geom.map((p) => [p.lng, p.lat] as [number, number]),
        risk,
        recommended: route.recommended,
        routeLabel: route.label,
      },
    ];
  }

  const out: RiskSegment[] = [];
  for (let i = 0; i < cps.length - 1; i++) {
    const path = sliceByMiles(
      geom,
      cumMi,
      cps[i].distance_miles,
      cps[i + 1].distance_miles,
    );
    if (path.length < 2) continue;
    out.push({
      id: `${route.id}-seg-${cps[i].index}`,
      path,
      risk: cps[i].risk,
      recommended: route.recommended,
      routeLabel: route.label,
    });
  }
  return out;
}
