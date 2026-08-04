import { useEffect, useMemo, useState } from "react";

import { workflowApi, type AgentCapability, type AgentResult, type ApprovalRequest, type ProjectStage, type RouteDecision, type WorkflowState } from "../api/workflow";

const stages: ProjectStage[] = [
  "INTAKE",
  "SCOPED",
  "EVIDENCE_READY",
  "STUDY_PROTOCOL_APPROVED",
  "DATA_READY",
  "ANALYZED",
  "DRAFTED",
  "VERIFIED",
  "RELEASED",
];

const stageLabels: Record<ProjectStage, string> = {
  INTAKE: "项目接入",
  SCOPED: "范围已确定",
  SEARCH_PROTOCOL_APPROVED: "检索协议已批准",
  EVIDENCE_READY: "证据就绪",
  RESEARCH_QUESTION_APPROVED: "研究问题已批准",
  STUDY_PROTOCOL_APPROVED: "研究方案已批准",
  DATA_READY: "数据就绪",
  ANALYZED: "分析完成",
  DRAFTED: "论文草稿",
  VERIFIED: "审查通过",
  RELEASED: "已发布",
  REWORK: "需要返工",
  BLOCKED: "项目阻塞",
  WAITING_HUMAN: "等待人工审批",
  FAILED: "执行失败",
};

function stageTone(stage: ProjectStage, current: ProjectStage) {
  if (stage === current) return "stage current";
  const currentIndex = stages.indexOf(current);
  const stageIndex = stages.indexOf(stage);
  if (currentIndex >= 0 && stageIndex >= 0 && stageIndex < currentIndex) return "stage done";
  return "stage";
}

export function WorkflowWorkspacePage() {
  const [projectId, setProjectId] = useState("physics-ai-demo");
  const [intent, setIntent] = useState("");
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [lastAgentResult, setLastAgentResult] = useState<AgentResult | null>(null);
  const [lastApproval, setLastApproval] = useState<ApprovalRequest | null>(null);
  const [lastRoute, setLastRoute] = useState<RouteDecision | null>(null);
  const [agents, setAgents] = useState<AgentCapability[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const currentStage = workflow?.current_stage ?? "INTAKE";
  const currentLabel = stageLabels[currentStage];
  const pending = Boolean(workflow?.pending_approval_ref && lastApproval);
  const hasProject = Boolean(workflow?.research_state);

  useEffect(() => {
    workflowApi.listAgents().then(setAgents).catch((caught) => setError(caught instanceof Error ? caught.message : "无法读取 Agent 能力"));
  }, []);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请求失败");
    } finally {
      setBusy(false);
    }
  };

  const start = () => run(async () => {
    const result = await workflowApi.startProject({ project_id: projectId, research_intent: intent });
    setWorkflow(result.workflow_state);
    setLastAgentResult(result.agent_result);
    setLastApproval(result.approval_request);
    setLastRoute(result.route_decision);
  });

  const approve = (decision: "approved" | "rejected") => run(async () => {
    await workflowApi.approve(projectId, decision, "researcher");
    const next = await workflowApi.getProject(projectId);
    setWorkflow(next);
    setLastApproval(null);
  });

  const routeNext = () => run(async () => {
    const result = await workflowApi.runNext(projectId);
    setWorkflow(result.workflow_state);
    setLastAgentResult(result.agent_result);
    setLastApproval(result.approval_request);
    setLastRoute(result.route_decision);
  });

  const routeDescription = useMemo(() => {
    if (!lastRoute) return "项目尚未经过 Controller 路由。";
    return `${lastRoute.selected_route} · ${lastRoute.reason}`;
  }, [lastRoute]);

  return (
    <main className="platform-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">STEM-SCI / RESEARCH WORKSPACE</p>
          <h1>科研流程工作台</h1>
          <p className="lede">Controller 驱动的六 Agent 研究协议与证据闭环</p>
        </div>
        <div className="status-block">
          <span className="status-dot" />
          <span>{currentLabel}</span>
        </div>
      </header>

      <section className="project-intake grid-panel">
        <div>
          <p className="section-kicker">01 / 项目接入</p>
          <h2>研究者需求与项目画像</h2>
          <p className="muted">先提交研究意图，Controller 会生成规划候选并在关键决策处暂停。</p>
        </div>
        <div className="form-grid">
          <label>
            项目 ID
            <input value={projectId} onChange={(event) => setProjectId(event.target.value)} disabled={hasProject} />
          </label>
          <label className="wide-field">
            研究意图
            <textarea
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              placeholder="例如：研究分层生成式 AI 支架对师范生 Python 物理建模迁移能力的影响"
              rows={3}
              disabled={hasProject}
            />
          </label>
          <button className="primary-action" onClick={start} disabled={busy || hasProject || !projectId.trim() || !intent.trim()}>
            {busy ? "处理中..." : "创建研究项目"}
          </button>
        </div>
      </section>

      <section className="stage-panel grid-panel">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">02 / Controller</p>
            <h2>研究流程轨道</h2>
          </div>
          <span className="stage-code">{currentStage}</span>
        </div>
        <div className="stage-rail">
          {stages.map((stage, index) => (
            <div className={stageTone(stage, currentStage)} key={stage}>
              <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
              <span>{stageLabels[stage]}</span>
            </div>
          ))}
        </div>
        <div className="route-strip">
          <span>最近路由</span>
          <strong>{routeDescription}</strong>
        </div>
      </section>

      <div className="content-grid">
        <section className="grid-panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">03 / Agent result</p>
              <h2>候选工件</h2>
            </div>
            {lastAgentResult && <span className="agent-tag">{lastAgentResult.agent_id}</span>}
          </div>
          {lastAgentResult ? (
            <>
              <div className="ref-list">
                {lastAgentResult.candidate_artifact_refs.map((ref) => <code key={ref}>{ref}</code>)}
              </div>
              {lastAgentResult.evidence_refs.length > 0 && (
                <div className="ref-list evidence-refs">
                  {lastAgentResult.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}
                </div>
              )}
              <div className="signal-grid">
                <div><span>证据引用</span><strong>{lastAgentResult.evidence_refs.length}</strong></div>
                <div><span>Operator 运行</span><strong>{workflow?.research_state?.execution_run_refs.length ?? 0}</strong></div>
                <div><span>工具请求</span><strong>{lastAgentResult.tool_requests.length}</strong></div>
                <div><span>风险标记</span><strong>{lastAgentResult.risk_flags.length}</strong></div>
                <div><span>未决问题</span><strong>{lastAgentResult.unresolved_questions.length}</strong></div>
              </div>
            </>
          ) : <p className="empty-state">创建项目后，Controller 的候选输出会显示在这里。</p>}
        </section>

        <section className="grid-panel approval-panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">04 / Gate</p>
              <h2>人工决策</h2>
            </div>
            {pending && <span className="approval-tag">待处理</span>}
          </div>
          {pending && lastApproval ? (
            <>
              <p>{lastApproval.reason}</p>
              <code>{lastApproval.artifact_ref}</code>
              <div className="button-row">
                <button className="primary-action" onClick={() => approve("approved")} disabled={busy}>批准并继续</button>
                <button className="secondary-action" onClick={() => approve("rejected")} disabled={busy}>退回返工</button>
              </div>
            </>
          ) : (
            <>
              <p className="empty-state">当前没有待处理审批。</p>
              {hasProject && currentStage !== "WAITING_HUMAN" && currentStage !== "RELEASED" && (
                <button className="secondary-action" onClick={routeNext} disabled={busy}>调度下一步 Agent</button>
              )}
            </>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
        </section>
      </div>

      <section className="grid-panel agent-directory">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">05 / Capability registry</p>
            <h2>六类专业 Agent</h2>
          </div>
          <span className="stage-code">{agents.length} roles</span>
        </div>
        <div className="agent-grid">
          {agents.map((agent) => (
            <article className="agent-card" key={agent.agent_id}>
              <div className="agent-card-heading"><strong>{agent.agent_id}</strong><span>READ ONLY</span></div>
              <p>{agent.supported_task_types.join(" · ")}</p>
              <small>输出 {agent.allowed_output_types.length} 类候选工件</small>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
