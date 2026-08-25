import type { GateViewModel } from "../types/research";
import { GateBadge } from "./GateBadge";

export function GateSummary({ gates, compact = false }: { gates: GateViewModel[]; compact?: boolean }) {
  return <div className={`gate-summary ${compact ? "gate-summary-compact" : ""}`}>{gates.map((gate) => <div className="gate-summary-item" key={gate.kind}><GateBadge gate={gate} />{!compact && <small>{gate.detail}</small>}</div>)}</div>;
}
