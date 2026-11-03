import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./ForecastSlider.module.css";

interface Props {
  hour: number;
  maxHour: number;
  timeLabel: string | null;
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
  const [localHour, setLocalHour] = useState(hour);
  const [playing, setPlaying] = useState(false);
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

  useEffect(() => {
    if (!playing || disabled || safeMax <= 0) return;
    const id = window.setInterval(() => {
      const next = (latestRef.current + 1) % (safeMax + 1);
      latestRef.current = next;
      setLocalHour(next);
      onChange(next);
    }, 400);
    return () => window.clearInterval(id);
  }, [playing, disabled, safeMax, onChange]);

  const ticks = useMemo(() => {
    const out: number[] = [];
    for (let h = 0; h <= safeMax; h += 6) out.push(h);
    if (out[out.length - 1] !== safeMax) out.push(safeMax);
    return out;
  }, [safeMax]);

  const onSlide = (next: number) => {
    setPlaying(false);
    setLocalHour(next);
    latestRef.current = next;
    if (pendingRef.current != null) return;
    pendingRef.current = requestAnimationFrame(() => {
      pendingRef.current = null;
      onChange(latestRef.current);
    });
  };

  return (
    <div className={styles.panel}>
      <div className={styles.top}>
        <div className={`${styles.label} tabular`}>
          {timeLabel ?? (localHour <= 0 ? "Now" : `Now +${localHour}h`)}
        </div>
        <div className={styles.controls}>
          <label className={styles.heat}>
            Heat
            <input
              type="checkbox"
              checked={showHeatmap}
              onChange={(e) => onToggleHeatmap(e.target.checked)}
              aria-label="Toggle weather heatmap"
            />
          </label>
          <button
            type="button"
            className={styles.play}
            disabled={disabled || safeMax <= 0}
            aria-label={playing ? "Pause forecast" : "Play forecast"}
            onClick={() => setPlaying((p) => !p)}
          >
            {playing ? "❚❚" : "▶"}
          </button>
        </div>
      </div>

      <input
        className={styles.range}
        type="range"
        min={0}
        max={safeMax || 1}
        step={1}
        value={Math.min(localHour, safeMax)}
        disabled={disabled || safeMax <= 0}
        onChange={(e) => onSlide(Number(e.target.value))}
        aria-label="Forecast hour"
      />

      <div className={`${styles.ticks} tabular`}>
        {ticks.map((h) => (
          <span key={h}>{h}h</span>
        ))}
      </div>
    </div>
  );
}
