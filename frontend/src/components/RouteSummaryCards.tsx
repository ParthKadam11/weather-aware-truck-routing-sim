import type { AnalyzeResponse, RouteOption } from "../types";
import { RISK_COLORS } from "../types";

interface Props {
  data: AnalyzeResponse;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function RiskMiles({ route }: { route: RouteOption }) {
  const order = ["No Travel", "Severe", "High", "Moderate", "Low"] as const;
  const present = order.filter((label) => (route.miles_by_risk[label] ?? 0) > 0);
  if (!present.length) return null;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.4rem 0.65rem",
        marginTop: "0.55rem",
      }}
    >
      {present.map((label) => (
        <span
          key={label}
          className="tabular"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            fontSize: "0.7rem",
            color: "var(--muted)",
          }}
        >
          <span className="risk-dot" style={{ background: RISK_COLORS[label] }} />
          {label} {(route.miles_by_risk[label] ?? 0).toFixed(0)} mi
        </span>
      ))}
    </div>
  );
}

export function RouteSummaryCards({ data, selectedId, onSelect }: Props) {
  // Stable A / B / C order (response order), not internal rank ids
  const cards = [...data.routes].sort((a, b) => a.label.localeCompare(b.label));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div className="reason-banner">
        <strong style={{ color: "var(--accent-ink)" }}>Recommended · </strong>
        {data.recommendation.reason}
      </div>

      {data.routing_note ? (
        <p
          style={{
            margin: 0,
            fontSize: "0.72rem",
            color: "var(--muted)",
            textWrap: "pretty",
          }}
        >
          {data.routing_note}
        </p>
      ) : null}

      {cards.map((route) => {
        const selected = route.id === selectedId;
        const cls = [
          "route-option",
          selected ? "is-selected" : "",
          route.recommended ? "is-recommended" : "",
        ]
          .filter(Boolean)
          .join(" ");

        return (
          <button
            key={route.id}
            type="button"
            className={cls}
            onClick={() => onSelect(route.id)}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                gap: "0.5rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 600,
                  fontSize: "0.95rem",
                  letterSpacing: "-0.02em",
                }}
              >
                {route.label}
                {route.recommended ? (
                  <span
                    style={{
                      marginLeft: 8,
                      fontSize: "0.65rem",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: "var(--accent-ink)",
                      letterSpacing: "0.04em",
                    }}
                  >
                    Best
                  </span>
                ) : null}
              </span>
            </div>
            <div
              className="tabular"
              style={{
                marginTop: 4,
                fontSize: "0.78rem",
                color: "var(--muted)",
              }}
            >
              {route.distance_miles.toFixed(0)} mi · {route.duration_hours.toFixed(1)}{" "}
              h · avg {route.average_risk.toFixed(2)}
            </div>
            <RiskMiles route={route} />
          </button>
        );
      })}

      <p
        style={{
          margin: 0,
          fontSize: "0.7rem",
          color: "var(--muted)",
          textWrap: "pretty",
        }}
      >
        {data.demo_storm
          ? "Demo storm on — corridor weather is intensified."
          : "Live Open-Meteo forecast."}{" "}
        Checkpoints every {data.interval_miles} mi · load{" "}
        <span className="tabular">{data.load_lb.toLocaleString()}</span> lb
      </p>
    </div>
  );
}
