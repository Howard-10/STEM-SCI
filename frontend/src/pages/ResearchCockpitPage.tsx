import { useEffect, useMemo, useState } from "react";
import { qaApi, type QAAnswerResponse } from "../api/qa";
import { workflowApi, type ApprovalRequest, type WorkflowState } from "../api/workflow";
import { api } from "../api/client";
import type { SharedChunkHit, SharedCorpusSummary } from "../types/context";
import type { WorkspaceTab } from "../App";
import { ArtifactSummary } from "../components/ArtifactSummary";
import { CitationDetailDrawer } from "../components/CitationDetailDrawer";
import { EvidenceCoverage } from "../components/EvidenceCoverage";
import { EvidencePanel } from "../components/EvidencePanel";
import { GateSummary } from "../components/GateSummary";
import { HumanGatePanel } from "../components/HumanGatePanel";
import { StageTimeline } from "../components/StageTimeline";
import { buildAnswerView, buildResearchContext, evidenceView } from "../utils/researchViewModel";
import type { EvidenceViewModel } from "../types/research";

const presets = [
  "生成式 AI 分层支架是否改善师范生 Python 物理建模能力？",
  "如何设计 Physics-STEM 物理建模研究的对照组与主要结果变量？",
  "有前测、后测和迁移测验时应采用什么分析方法？",
];

export function ResearchCockpitPage({ onNavigate }: { onNavigate: (tab: WorkspaceTab) => void }) {
  const [projectId, setProjectId] = useState("physics-ai-demo");
  const [question, setQuestion] = useState(presets[0]);
  const [conversationId, setConversationId] = useState<string>();
  const [answer, setAnswer] = useState<QAAnswerResponse | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [corpus, setCorpus] = useState<SharedCorpusSummary | null>(null);
  const [sharedHits, setSharedHits] = useState<SharedChunkHit[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceViewModel | null>(null);
  const [mode, setMode] = useState<"discovery" | "formal">("discovery");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { void api.listSharedCorpora().then((items) => setCorpus(items.find((item) => item.corpus_id === "physics_stem_v1") ?? null)).catch(() => undefined); }, []);
  const context = useMemo(() => buildResearchContext(workflow, approval, buildAnswerView(answer, null, sharedHits).evidence), [workflow, approval, answer, sharedHits]);
  const answerView = useMemo(() => buildAnswerView(answer, null, sharedHits), [answer, sharedHits]);
  const activeEvidence = answerView.evidence;

  const ask = async () => {
    if (!question.trim()) return;
    setBusy(true); setError("");
    try {
      const response = await qaApi.answer({ project_id: projectId, question, conversation_id: conversationId, allow_llm: true });
      setAnswer(response); setConversationId(response.conversation_id);
      if (response.workflow_action?.workflow_state) setWorkflow(response.workflow_action.workflow_state as unknown as WorkflowState);
      if (response.workflow_action?.approval_request) setApproval(response.workflow_action.approval_request as unknown as ApprovalRequest);
      const result = await api.searchSharedCorpus(projectId, response.rewritten_query || question, mode);
      setSharedHits(result.chunk_hits);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "暂时无法完成研究检索"); } finally { setBusy(false); }
  };

  const decide = async (decision: "approved" | "rejected", reason: string) => { if (!approval) return; setBusy(true); try { await workflowApi.approve(projectId, decision, "researcher"); const next = await workflowApi.getProject(projectId); setWorkflow(next); setApproval(null); } catch (caught) { setError(caught instanceof Error ? caught.message : "审批未完成"); } finally { setBusy(false); } };

  return <div className="workspace"><header className="workspace-intro"><div><span className="eyebrow">RESEARCH COCKPIT / PHYSICS-STEM</span><h1>让每一个研究结论都能回到证据</h1><p>围绕真实物理教育研究问题，完成检索、设计、审批与验证。</p></div><div className="project-chip"><span>当前项目</span><strong>{projectId}</strong></div></header><div className="cockpit-gates"><GateSummary gates={context.gates} /></div><div className="cockpit-grid"><aside className="stage-sidebar"><div className="sidebar-heading"><span className="eyebrow">RESEARCH STAGES</span><h2>研究进度</h2></div><StageTimeline context={context} /><div className="stage-current"><span className="eyebrow">当前阶段</span><strong>{context.stageDefinition.label}</strong><p>主导：{context.stageDefinition.lead.label}</p><p className="muted">支持：{context.stageDefinition.support.map((item) => item.label).join("、")}</p><ArtifactSummary artifacts={context.artifacts} /></div></aside><section className="research-center"><div className="question-block"><div className="section-heading"><div><span className="eyebrow">RESEARCH QUESTION</span><h2>从一个问题开始</h2></div><div className="segmented-control"><button className={mode === "discovery" ? "selected" : ""} onClick={() => setMode("discovery")} type="button">发现探索</button><button className={mode === "formal" ? "selected" : ""} disabled={!corpus?.formal_evidence_ready} onClick={() => setMode("formal")} type="button">正式证据</button></div></div><div className="preset-list">{presets.map((preset) => <button className={question === preset ? "preset selected" : "preset"} key={preset} onClick={() => setQuestion(preset)} type="button">{preset}</button>)}</div><textarea aria-label="研究问题" value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} /><div className="question-actions"><label className="project-field">项目 ID<input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label><button className="primary-action" disabled={busy || !question.trim()} onClick={() => void ask()} type="button">{busy ? "正在检索…" : "开始研究"}</button></div>{mode === "formal" && !corpus?.formal_evidence_ready && <p className="warning-text">当前仍有证据未通过 Evidence Gate，因此正式证据模式暂不可用。</p>}</div>{answer ? <article className="conclusion-block"><div className="conclusion-meta"><span className="ai-label">AI 生成 · 需依据引用核验</span><span>{answer.answer_mode === "llm" ? "结构化模型回答" : "确定性证据摘要"}</span></div><h2>研究结论</h2><p className="answer-text">{answer.answer}</p><EvidenceCoverage coverage={answerView.coverage} /><div className="conclusion-grid"><div><span className="eyebrow">关键依据</span><strong>{activeEvidence.length ? `${activeEvidence.length} 条材料已关联` : "暂无引用"}</strong></div><div><span className="eyebrow">下一步建议</span><strong>{answer.workflow_action?.next_available_actions?.[0] ?? "进入证据综述并确认研究范围"}</strong></div></div><details className="research-boundary"><summary>研究边界与检索说明</summary><p>{answer.risk_flags.length ? answer.risk_flags.join("；") : "回答仅基于当前检索到的 Physics-STEM 材料。"}</p><code>{answer.rewritten_query}</code></details><div className="button-row"><button className="secondary-action" onClick={() => onNavigate("evidence")} type="button">查看完整证据库</button><button className="secondary-action" onClick={() => onNavigate("workflow")} type="button">进入研究流程</button></div></article> : <div className="empty-research"><span className="empty-number">01</span><h2>输入一个 Physics-STEM 研究问题</h2><p>系统会先检索证据，再给出带有引用和研究边界的结论。</p></div>}</section><aside className="evidence-sidebar"><EvidencePanel evidence={activeEvidence} gates={context.gates} onOpen={setSelectedEvidence} />{approval && <HumanGatePanel approval={approval} busy={busy} onDecide={decide} />}</aside></div>{error && <p className="error-text" role="alert">{error}</p>}<CitationDetailDrawer item={selectedEvidence} onClose={() => setSelectedEvidence(null)} /></div>;
}
