import { useEffect, useState } from "react";
import { workflowApi } from "../api/workflow";
import { GateBadge } from "../components/GateBadge";
import { TechnicalTrace } from "../components/TechnicalTrace";
import { demoExecutionRows, demoRouteRows, demoRuntime } from "../demo/data";

type AuditTab = "citations" | "execution" | "validation" | "system";
const labels: Record<AuditTab, string> = { citations: "引用追溯", execution: "执行记录", validation: "结果验证", system: "系统状态" };

export function AuditValidationPage() {
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
  const [tab, setTab] = useState<AuditTab>("citations");
  const [projectId, setProjectId] = useState(
    import.meta.env.VITE_PROJECT_ID && import.meta.env.VITE_PROJECT_ID !== "demo"
      ? import.meta.env.VITE_PROJECT_ID
      : "physics-ai-demo",
  );
  const [data, setData] = useState<Array<Record<string, unknown>>>(
    demoMode ? demoRouteRows as unknown as Array<Record<string, unknown>> : [],
  );
  const [runtime, setRuntime] = useState<Record<string, unknown> | null>(
    demoMode ? demoRuntime as unknown as Record<string, unknown> : null,
  );
  useEffect(() => { if (tab === "system") void workflowApi.getRuntime().then((value) => setRuntime(value as unknown as Record<string, unknown>)).catch(() => setRuntime(null)); else if (tab === "execution") void workflowApi.listExecutions(projectId).then(setData).catch(() => setData([])); else if (tab === "citations") void workflowApi.listRoutes(projectId).then(setData).catch(() => setData([])); else setData([]); }, [tab, projectId]);
  return <div className="workspace audit-workspace"><header className="workspace-intro compact-intro"><div><span className="eyebrow">AUDIT & VALIDATION</span><h1>每个结论都留下可复核的路径</h1><p>面向评委展示引用、执行、验证和系统状态；原始技术记录默认收起。</p></div><label className="project-field">项目 ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label></header><div className="audit-tabs">{(Object.keys(labels) as AuditTab[]).map((item) => <button className={tab === item ? "selected" : ""} key={item} onClick={() => setTab(item)} type="button">{labels[item]}</button>)}</div>{tab === "citations" && <section className="audit-section"><div className="audit-chain"><strong>研究问题</strong><span>→</span><strong>Query Rewrite</strong><span>→</span><strong>Retrieval</strong><span>→</span><strong>Evidence</strong><span>→</span><strong>PDF 定位</strong><span>→</span><strong>AI 综合</strong><span>→</span><strong>人工核验</strong></div><AuditRecords rows={data} /></section>}{tab === "execution" && <section className="audit-section"><div className="audit-chain"><strong>Agent</strong><span>→</span><strong>研究动作</strong><span>→</span><strong>研究产物</strong><span>→</span><strong>审核</strong></div><AuditRecords rows={data} /></section>}{tab === "validation" && <section className="audit-section"><div className="validation-chain"><div><span>Frozen Dataset</span><strong>已记录</strong></div><div><span>Data Hash</span><strong>已记录</strong></div><div><span>Analysis Plan</span><strong>待验证</strong></div><div><span>Execution</span><strong>待验证</strong></div><div><span>Statistical Result</span><strong>待验证</strong></div><div><span>Independent Review</span><strong>待验证</strong></div></div><div className="gate-callout"><GateBadge gate={{ kind: "validation", label: "Validation Gate", tone: "pending", detail: "尚无明确验证成功证据" }} /><p>当前没有明确的验证成功证据，因此保守显示“待验证”。结果引用不会被自动视为验证通过。</p></div></section>}{tab === "system" && <section className="audit-section"><div className="system-grid">{Object.entries(runtime ?? { status: "读取中" }).map(([key, value]) => <div className="system-item" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{String(value)}</strong></div>)}</div></section>}<TechnicalTrace title="查看原始记录"><pre>{JSON.stringify(tab === "system" ? runtime : data, null, 2)}</pre></TechnicalTrace></div>;
}

function AuditRecords({ rows }: { rows: Array<Record<string, unknown>> }) { return rows.length ? <div className="audit-records">{rows.map((row, index) => <article key={index}><strong>{String(row.operator_id ?? row.selected_route ?? "研究记录")}</strong><span>{String(row.status ?? row.reason ?? "已记录")}</span><small>{String(row.created_at ?? row.finished_at ?? "")}</small></article>)}</div> : <div className="empty-state large-empty"><strong>尚无可展示记录</strong><span>完成一次研究检索或工作流动作后，这里会出现可复核记录。</span></div>; }
