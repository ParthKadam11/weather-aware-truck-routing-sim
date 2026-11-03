import { RISK_COLORS, type RiskLabel } from "../types";

const ORDER: RiskLabel[] = ["Low", "Moderate", "High", "Severe", "No Travel"];

export function RiskLegend() {
  return (
    <div className="legend-row" aria-label="Risk legend">
      {ORDER.map((label) => (
        <span key={label} className="legend-item">
          <span className="risk-dot" style={{ background: RISK_COLORS[label] }} />
          {label}
        </span>
      ))}
    </div>
  );
}
