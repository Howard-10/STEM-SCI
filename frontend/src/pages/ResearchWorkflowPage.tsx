import { useEffect, useMemo, useState } from "react";
import { workflowApi, type AgentCapability, type ApprovalRequest, type WorkflowState } from "../api/workflow";
import { ArtifactSummary } from "../components/ArtifactSummary";
import { GateSummary } from "../components/GateSummary";
import { HumanGatePanel } from "../components/HumanGatePanel";
import { StageTimeline } from "../components/StageTimeline";
import { TechnicalTrace } from "../components/TechnicalTrace";
import { buildResearchContext } from "../utils/researchViewModel";
import { demoAgents, demoApproval, demoWorkflowState } from "../demo/data";

export function ResearchWorkflowPage() {
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
  const [projectId, setProjectId] = useState(
    import.meta.env.VITE_PROJECT_ID && import.meta.env.VITE_PROJECT_ID !== "demo"
      ? import.meta.env.VITE_PROJECT_ID
      : "physics-ai-demo",
  );
  const [workflow, setWorkflow] = useState<WorkflowState | null>(demoMode ? demoWorkflowState : null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(demoMode ? demoApproval : null);
  const [agents, setAgents] = useState<AgentCapability[]>(demoMode ? demoAgents : []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void workflowApi.listAgents().then(setAgents).catch(() => undefined);
  }, []);

  const context = useMemo(() => buildResearchContext(workflow, approval, []), [workflow, approval]);
  const lead = context.stageDefinition.lead;

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await workflowApi.startProject({
        project_id: projectId,
        research_intent: "生成式 AI 分层支架与师范生 Python 物理建模能力",
      });
      setWorkflow(result.workflow_state);
      setApproval(result.approval_request);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "研究流程无法启动");
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    setBusy(true);
    setError("");
    try {
      const nextWorkflow = await workflowApi.getProject(projectId);
      setWorkflow(nextWorkflow);
      setApproval(nextWorkflow.pending_approval_ref ? demoApproval : null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "研究流程状态无法刷新");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision: "approved" | "rejected") => {
    if (!approval) return;
    setBusy(true);
    setError("");
    try {
      await workflowApi.approve(projectId, decision, "researcher");
      setWorkflow(await workflowApi.getProject(projectId));
      setApproval(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "审批未完成");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="workspace workflow-workspace">
      <header className="workspace-intro compact-intro">
        <div>
          <span className="eyebrow">RESEARCH WORKFLOW</span>
          <h1>研究生命周期中的每一次协作</h1>
          <p>Stage 描述研究进度，Agent 负责参与其中，Gate 负责控制可信边界。</p>
        </div>
        <div className="workflow-actions">
          <input aria-label="项目 ID" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
          <button
            className="primary-action"
            disabled={busy}
            onClick={() => void (workflow ? refresh() : start())}
            type="button"
          >
            {busy ? "处理中..." : workflow ? "刷新状态" : "启动研究项目"}
          </button>
        </div>
      </header>

      <div className="workflow-gates">
        <GateSummary gates={context.gates} />
      </div>

      <div className="workflow-layout">
        <aside className="workflow-sidebar">
          <span className="eyebrow">STAGE TIMELINE</span>
          <h2>九阶段研究进度</h2>
          <StageTimeline context={context} />
        </aside>

        <section className="workflow-main">
          <div className="workflow-stage-heading">
            <div>
              <span className="eyebrow">CURRENT STAGE</span>
              <h2>{context.stageDefinition.label}</h2>
              <p>{context.stageStatus === "waiting" ? "当前需要研究者确认后继续。" : "当前阶段正在等待研究动作。"}</p>
            </div>
            <span className="stage-badge">{context.stageDefinition.lead.label}</span>
          </div>
          <div className="workflow-flow">
            <div><span>INPUT</span><strong>{workflow?.last_route_decision?.reason ?? "研究问题与项目范围"}</strong></div>
            <div><span>ROLE</span><strong>{lead.label}</strong><small>支持：{context.stageDefinition.support.map((item) => item.label).join("、")}</small></div>
            <div><span>ACTION</span><strong>{workflow?.last_route_decision?.reason ?? "等待研究角色生成候选方案"}</strong></div>
            <div><span>EVIDENCE</span><strong>{context.researchState?.evidence_refs.length ? `${context.researchState.evidence_refs.length} 条研究证据` : "等待 Evidence Gate"}</strong></div>
            <div><span>OUTPUT</span><ArtifactSummary artifacts={context.artifacts} /></div>
            <div><span>GATE</span><GateSummary gates={context.gates} compact /></div>
            <div><span>NEXT</span><strong>{approval ? "完成 Human Gate 后继续" : "请回到对话窗口生成 Agent 计划"}</strong></div>
          </div>
          <TechnicalTrace>
            <pre>{JSON.stringify({ route: workflow?.last_route_decision, agentRuns: agents.length }, null, 2)}</pre>
          </TechnicalTrace>
        </section>

        <aside className="workflow-right">
          {approval ? (
            <HumanGatePanel approval={approval} busy={busy} onDecide={(decision) => void decide(decision)} />
          ) : (
            <section className="next-action-panel">
              <span className="eyebrow">NEXT ACTION</span>
              <h3>{workflow ? "使用 Agent 计划继续" : "从研究问题开始"}</h3>
              <p>{workflow ? "固定顺序调度已停用。新的 Agent 调用需要先由自然语言生成计划，再由研究者批准执行。" : "创建项目后，Controller 会在关键决策处暂停等待确认。"}</p>
              <button className="secondary-action" disabled={busy} onClick={() => void (workflow ? refresh() : start())} type="button">
                {workflow ? "刷新状态" : "创建研究项目"}
              </button>
            </section>
          )}
        </aside>
      </div>

      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  );
}
