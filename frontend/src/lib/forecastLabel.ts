/** Format slider hour as IST: "Now +12h · Wed 10:00 IST" */

const IST = "Asia/Kolkata";

export function formatForecastIstLabel(
  hour: number,
  timesUtc: string[] | null | undefined,
): string {
  const prefix = hour <= 0 ? "Now" : `Now +${hour}h`;
  const raw = timesUtc?.[hour] ?? timesUtc?.[0];
  if (!raw) return prefix;

  // Open-Meteo times are "YYYY-MM-DDTHH:MM" in UTC (no Z) when timezone=UTC
  const iso = /Z$|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}:00Z`;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return prefix;

  const weekday = new Intl.DateTimeFormat("en-US", {
    timeZone: IST,
    weekday: "short",
  }).format(date);
  const clock = new Intl.DateTimeFormat("en-GB", {
    timeZone: IST,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);

  return `${prefix} · ${weekday} ${clock} IST`;
}
