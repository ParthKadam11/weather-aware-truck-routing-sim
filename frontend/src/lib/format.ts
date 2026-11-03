/** "92 mi · 2h 05m" */
export function formatMilesDuration(miles: number, durationS: number): string {
  const totalMin = Math.max(0, Math.round(durationS / 60));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  const time =
    h > 0
      ? `${h}h ${String(m).padStart(2, "0")}m`
      : `${m}m`;
  return `${Math.round(miles)} mi · ${time}`;
}

export function routeLetter(label: string): string {
  const m = label.match(/Route\s+([A-Z])/i);
  return m ? m[1].toUpperCase() : label.slice(0, 1).toUpperCase();
}

export function rankBadge(rank: number, recommended: boolean): string {
  if (recommended || rank === 1) return "Best";
  if (rank === 2) return "2nd";
  if (rank === 3) return "3rd";
  return `${rank}th`;
}
