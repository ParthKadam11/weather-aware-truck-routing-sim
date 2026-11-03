import { useMemo, useState } from "react";
import type { AnalyzeRequest } from "../types";
import styles from "./RouteForm.module.css";

interface Props {
  loading: boolean;
  loadingStep?: string | null;
  onSubmit: (req: AnalyzeRequest) => void;
}

const MH_PLACES = [
  "Mumbai, Maharashtra",
  "Pune, Maharashtra",
  "Nagpur, Maharashtra",
  "Nashik, Maharashtra",
  "Aurangabad, Maharashtra",
  "Kolhapur, Maharashtra",
] as const;

function defaultDepartureLocal(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function RouteForm({ loading, loadingStep, onSubmit }: Props) {
  const [origin, setOrigin] = useState("Mumbai, Maharashtra");
  const [destination, setDestination] = useState("Pune, Maharashtra");
  const [departure, setDeparture] = useState(defaultDepartureLocal);
  const [loadLb, setLoadLb] = useState(45000);
  const [interval, setIntervalMi] = useState<10 | 25 | 50>(25);
  const [demoStorm, setDemoStorm] = useState(false);
  const [chipTarget, setChipTarget] = useState<"origin" | "destination">("origin");

  const buttonText = useMemo(() => {
    if (!loading) return "Find safest routes";
    return loadingStep || "Analyzing…";
  }, [loading, loadingStep]);

  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          origin,
          destination,
          departure: new Date(departure).toISOString(),
          load_lb: loadLb,
          interval_miles: interval,
          demo_storm: demoStorm,
          display_tz: "Asia/Kolkata",
        });
      }}
    >
      <div className={styles.odRow}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="origin">
            Origin
          </label>
          <input
            id="origin"
            className={styles.input}
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            onFocus={() => setChipTarget("origin")}
            required
            autoComplete="off"
          />
        </div>
        <button
          type="button"
          className={styles.swap}
          aria-label="Swap origin and destination"
          onClick={() => {
            setOrigin(destination);
            setDestination(origin);
          }}
        >
          ⇄
        </button>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="destination">
            Destination
          </label>
          <input
            id="destination"
            className={styles.input}
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            onFocus={() => setChipTarget("destination")}
            required
            autoComplete="off"
          />
        </div>
      </div>

      <div>
        <div className={styles.label}>
          Places → {chipTarget === "origin" ? "origin" : "destination"}
        </div>
        <div className={styles.chips}>
          {MH_PLACES.map((place) => (
            <button
              key={place}
              type="button"
              className={styles.chip}
              onClick={() => {
                if (chipTarget === "origin") setOrigin(place);
                else setDestination(place);
              }}
            >
              {place.replace(", Maharashtra", "")}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className={styles.label} htmlFor="departure">
          Departure
        </label>
        <input
          id="departure"
          className={styles.input}
          type="datetime-local"
          value={departure}
          onChange={(e) => setDeparture(e.target.value)}
          required
        />
      </div>

      <div className={styles.row2}>
        <div>
          <label className={styles.label} htmlFor="load">
            Load (lb)
          </label>
          <input
            id="load"
            className={`${styles.input} tabular`}
            type="number"
            min={0}
            step={1000}
            value={loadLb}
            onChange={(e) => setLoadLb(Number(e.target.value))}
            required
          />
        </div>
        <div>
          <div className={styles.label}>Checkpoints</div>
          <div className={styles.segment} role="group" aria-label="Checkpoint interval">
            {([10, 25, 50] as const).map((mi) => (
              <button
                key={mi}
                type="button"
                className={`${styles.segBtn} ${interval === mi ? styles.segBtnActive : ""}`}
                onClick={() => setIntervalMi(mi)}
              >
                {mi} mi
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.toggleRow}>
        <div>
          <div className={styles.toggleTitle}>Demo storm</div>
          <div className={styles.toggleHint}>Severe weather on 1–2 routes</div>
        </div>
        <label className={styles.switch}>
          <input
            type="checkbox"
            checked={demoStorm}
            onChange={(e) => setDemoStorm(e.target.checked)}
            aria-label="Toggle demo storm"
          />
          <span className={styles.track} />
          <span className={styles.thumb} />
        </label>
      </div>

      <button type="submit" className={styles.submit} disabled={loading}>
        {buttonText}
      </button>
    </form>
  );
}
