import dayjs from "dayjs";
import { useState } from "react";
import type { AnalyzeRequest } from "../types";

interface Props {
  loading: boolean;
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

export function RouteForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState("Mumbai, Maharashtra");
  const [destination, setDestination] = useState("Pune, Maharashtra");
  const [departure, setDeparture] = useState(
    dayjs().add(1, "hour").format("YYYY-MM-DDTHH:mm"),
  );
  const [loadLb, setLoadLb] = useState(45000);
  const [interval, setIntervalMi] = useState<10 | 25 | 50>(25);
  const [demoStorm, setDemoStorm] = useState(false);
  const [chipTarget, setChipTarget] = useState<"origin" | "destination">("origin");

  return (
    <form
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
      style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}
    >
      <div>
        <label className="field-label" htmlFor="origin">
          Origin
        </label>
        <input
          id="origin"
          className="field-input"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          onFocus={() => setChipTarget("origin")}
          required
          placeholder="e.g. Mumbai, Maharashtra"
          autoComplete="off"
        />
      </div>

      <div>
        <label className="field-label" htmlFor="destination">
          Destination
        </label>
        <input
          id="destination"
          className="field-input"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          onFocus={() => setChipTarget("destination")}
          required
          placeholder="e.g. Pune, Maharashtra"
          autoComplete="off"
        />
      </div>

      <div>
        <div className="field-label">
          Maharashtra places → {chipTarget === "origin" ? "origin" : "destination"}
        </div>
        <div className="place-chips">
          {MH_PLACES.map((place) => (
            <button
              key={place}
              type="button"
              className="place-chip"
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
        <label className="field-label" htmlFor="departure">
          Departure (Asia/Kolkata local browser clock → UTC)
        </label>
        <input
          id="departure"
          className="field-input"
          type="datetime-local"
          value={departure}
          onChange={(e) => setDeparture(e.target.value)}
          required
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
        }}
      >
        <div>
          <label className="field-label" htmlFor="load">
            Load (lb)
          </label>
          <input
            id="load"
            className="field-input tabular"
            type="number"
            min={0}
            step={1000}
            value={loadLb}
            onChange={(e) => setLoadLb(Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="field-label" htmlFor="interval">
            Checkpoints
          </label>
          <select
            id="interval"
            className="field-select"
            value={interval}
            onChange={(e) =>
              setIntervalMi(Number(e.target.value) as 10 | 25 | 50)
            }
          >
            <option value={10}>Every 10 mi</option>
            <option value={25}>Every 25 mi</option>
            <option value={50}>Every 50 mi</option>
          </select>
        </div>
      </div>

      <div className="toggle-row">
        <div>
          <div style={{ fontSize: "0.875rem", fontWeight: 600 }}>Demo storm</div>
          <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            Overlay severe weather on the corridor
          </div>
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            checked={demoStorm}
            onChange={(e) => setDemoStorm(e.target.checked)}
            aria-label="Toggle demo storm"
          />
          <span className="toggle-track" />
          <span className="toggle-thumb" />
        </label>
      </div>

      <button type="submit" className="btn-primary" disabled={loading}>
        {loading ? "Analyzing corridor…" : "Find safest routes"}
      </button>
    </form>
  );
}
