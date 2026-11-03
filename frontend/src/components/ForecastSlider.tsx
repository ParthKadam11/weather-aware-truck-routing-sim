import { useEffect, useRef, useState } from "react";

interface Props {
  hour: number;
  maxHour: number;
  timeLabel: string | null;
  /** Called at most once per animation frame while dragging. */
  onChange: (hour: number) => void;
  disabled?: boolean;
  showHeatmap: boolean;
  onToggleHeatmap: (v: boolean) => void;
}

export function ForecastSlider({
  hour,
  maxHour,
  timeLabel,
  onChange,
  disabled,
  showHeatmap,
  onToggleHeatmap,
}: Props) {
  const safeMax = Math.max(0, maxHour);
  // Local value for snappy thumb; parent notified via rAF
  const [localHour, setLocalHour] = useState(hour);
  const pendingRef = useRef<number | null>(null);
  const latestRef = useRef(hour);

  useEffect(() => {
    setLocalHour(hour);
    latestRef.current = hour;
  }, [hour]);

  useEffect(() => {
    return () => {
      if (pendingRef.current != null) cancelAnimationFrame(pendingRef.current);
    };
  }, []);

  const shortTime = timeLabel ? timeLabel.replace("T", " ").slice(0, 16) : null;

  const onSlide = (next: number) => {
    setLocalHour(next);
    latestRef.current = next;
    if (pendingRef.current != null) return;
    pendingRef.current = requestAnimationFrame(() => {
      pendingRef.current = null;
      onChange(latestRef.current);
    });
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.4rem",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem", minWidth: 0 }}>
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: "0.8rem",
            }}
          >
            Forecast
          </span>
          <span
            className="tabular"
            style={{
              fontSize: "0.72rem",
              color: "var(--muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {localHour}h{shortTime ? ` · ${shortTime}` : ""}
          </span>
        </div>

        <div className="toggle-row" style={{ padding: 0, gap: "0.4rem", flexShrink: 0 }}>
          <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Heat</span>
          <label className="toggle">
            <input
              type="checkbox"
              checked={showHeatmap}
              onChange={(e) => onToggleHeatmap(e.target.checked)}
              aria-label="Toggle weather heatmap"
            />
            <span className="toggle-track" />
            <span className="toggle-thumb" />
          </label>
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={safeMax || 1}
        step={1}
        value={Math.min(localHour, safeMax)}
        disabled={disabled || safeMax <= 0}
        onChange={(e) => onSlide(Number(e.target.value))}
        aria-label="Forecast hour"
        style={{
          width: "100%",
          accentColor: "var(--accent)",
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      />

      <div
        className="tabular"
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "0.62rem",
          color: "var(--muted)",
        }}
      >
        <span>0h</span>
        <span>48h in memory</span>
        <span>{safeMax}h</span>
      </div>
    </div>
  );
}
