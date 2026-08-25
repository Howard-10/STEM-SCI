import { useState } from "react";
import type { ApprovalRequest } from "../api/workflow";

export function HumanGatePanel({ approval, busy, onDecide }: { approval: ApprovalRequest; busy?: boolean; onDecide: (decision: "approved" | "rejected", reason: string) => void }) {
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [reason, setReason] = useState(approval.reason);
  return <section className="human-gate-panel"><div className="panel-kicker"><span className="gate-icon gate-pending">◷</span><span>Human Gate</span><span className="status-label status-pending">待批准</span></div><h3>需要研究者确认</h3><p>{approval.reason}</p><p className="muted">{approval.risk_summary}</p><button className="primary-action" disabled={busy} onClick={() => setOpen(true)} type="button">查看并处理</button>{open && <div className="confirm-panel"><label>决策<select value={decision} onChange={(event) => setDecision(event.target.value as "approved" | "rejected")}><option value="approved">批准并继续</option><option value="rejected">退回并说明</option></select></label><label>确认理由<textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="button-row"><button className="primary-action" disabled={busy || !reason.trim()} onClick={() => { onDecide(decision, reason); setOpen(false); }} type="button">确认提交</button><button className="secondary-action" onClick={() => setOpen(false)} type="button">取消</button></div></div>}</section>;
}
