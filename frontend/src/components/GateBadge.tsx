import type { GateViewModel } from "../types/research";
import { gateToneClass } from "../utils/researchViewModel";

const icons = { verified: "✓", approved: "✓", pending: "◷", insufficient: "!", rejected: "×", unknown: "•" } as const;

export function GateBadge({ gate }: { gate: GateViewModel }) {
  return <span className={`gate-badge ${gateToneClass(gate.tone)}`} title={gate.detail}><span aria-hidden="true">{icons[gate.tone]}</span>{gate.label} · {gate.tone === "verified" ? "已核验" : gate.tone === "approved" ? "已批准" : gate.tone === "rejected" ? "已退回" : gate.tone === "pending" ? "待处理" : gate.tone === "insufficient" ? "证据不足" : "待确认"}</span>;
}
