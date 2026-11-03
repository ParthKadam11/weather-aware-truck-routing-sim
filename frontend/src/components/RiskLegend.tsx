import { RISK_COLORS, RISK_ORDER, type RiskLabel } from "../types";
import styles from "./RiskLegend.module.css";

export function RiskLegend() {
  return (
    <div className={styles.panel} aria-label="Risk legend">
      {RISK_ORDER.map((label: RiskLabel) => (
        <span key={label} className={styles.item}>
          <span
            className={styles.dot}
            style={{ background: RISK_COLORS[label] }}
          />
          {label}
        </span>
      ))}
    </div>
  );
}
