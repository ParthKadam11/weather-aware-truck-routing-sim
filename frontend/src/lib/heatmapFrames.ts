import type { HeatmapFrameWeights, HeatmapPoint, HeatmapResponse } from "../types";

/** Map risk score 1–5 → HeatmapLayer weight. */
export function riskToWeight(score: number): number {
  return Math.max(0.05, (score - 1) / 4);
}

/**
 * Precompute all 48 hourly weight arrays once when the heatmap response arrives.
 * Slider changes only index into this — no network, no geometry rebuild.
 */
export function memoizeHeatmapFrames(
  heatmap: HeatmapResponse | null,
): HeatmapFrameWeights[] {
  if (!heatmap?.points?.length) return [];
  const hours = Math.max(1, heatmap.hours || 48);
  const frames: HeatmapFrameWeights[] = new Array(hours);
  for (let h = 0; h < hours; h++) {
    frames[h] = heatmap.points.map((p: HeatmapPoint) =>
      riskToWeight(p.risk[h] ?? p.risk[0] ?? 1),
    );
  }
  return frames;
}
