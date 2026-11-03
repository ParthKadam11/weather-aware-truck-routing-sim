import { formatMilesDuration, rankBadge, routeLetter } from "../lib/format";
import type { AnalyzeResponse, RiskLabel, RouteOption } from "../types";
import { RISK_COLORS, RISK_ORDER } from "../types";
import styles from "./RouteCards.module.css";

interface Props {
  data: AnalyzeResponse;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function StackedRiskBar({ route }: { route: RouteOption }) {
  const total = RISK_ORDER.reduce(
    (s, k) => s + (route.miles_by_risk[k] ?? 0),
    0,
  );
  if (total <= 0) return null;
  return (
    <div className={styles.bar} aria-hidden>
      {RISK_ORDER.map((label: RiskLabel) => {
        const mi = route.miles_by_risk[label] ?? 0;
        if (mi <= 0) return null;
        return (
          <div
            key={label}
            className={styles.seg}
            style={{
              width: `${(mi / total) * 100}%`,
              background: RISK_COLORS[label],
            }}
            title={`${label}: ${mi.toFixed(0)} mi`}
          />
        );
      })}
    </div>
  );
}

export function RouteSummaryCards({ data, selectedId, onSelect }: Props) {
  const cards = [...data.routes].sort((a, b) => a.label.localeCompare(b.label));

  return (
    <div className={styles.wrap}>
      <p className={styles.banner}>
        <strong>Recommended · </strong>
        {data.recommendation.reason}
      </p>

      {data.routing_note ? (
        <p className={styles.note}>{data.routing_note}</p>
      ) : null}

      {cards.map((route) => {
        const selected = route.id === selectedId;
        const badge = rankBadge(route.rank, route.recommended);
        return (
          <button
            key={route.id}
            type="button"
            className={`${styles.card} ${selected ? styles.selected : ""}`}
            onClick={() => onSelect(route.id)}
          >
            <div className={styles.head}>
              <div className={styles.left}>
                <span className={styles.letter}>{routeLetter(route.label)}</span>
                <span
                  className={`${styles.badge} ${badge === "Best" ? styles.badgeBest : ""}`}
                >
                  {badge}
                </span>
              </div>
            </div>
            <div className={`${styles.meta} tabular`}>
              {formatMilesDuration(route.distance_miles, route.duration_s)}
            </div>
            <StackedRiskBar route={route} />
          </button>
        );
      })}

      <p className={styles.foot}>
        {data.demo_storm ? "Demo storm on. " : "Live Open-Meteo. "}
        Checkpoints every {data.interval_miles} mi · load{" "}
        <span className="tabular">{data.load_lb.toLocaleString()}</span> lb
      </p>
    </div>
  );
}
