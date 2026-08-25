import { useEffect, useMemo, useState } from "react";
import {
  workflowApi,
  type AgentCapability,
  type ApprovalRequest,
  type RuntimeStatus,
  type WorkflowState,
} from "../api/workflow";
import type { WorkspaceTab } from "../App";
import { HumanGatePanel } from "../components/HumanGatePanel";
import { TechnicalTrace } from "../components/TechnicalTrace";
import {
  demoAgents,
  demoApproval,
  demoExecutionRows,
  demoRuntime,
  demoRouteRows,
  demoWorkflowState,
} from "../demo/data";

type AgentCodexPageProps = {
  projectId: string;
  onNavigate: (tab: WorkspaceTab) => void;
};

const agentMeta: Record<string, { label: string; short: string; tone: string }> = {
  mentor_planning: { label: "研究导师", short: "界定研究问题和边界", tone: "agent-teal" },
  evidence_review: { label: "证据综述员", short: "整理文献和证据缺口", tone: "agent-blue" },
  research_design: { label: "研究设计师", short: "生成可审批研究方案", tone: "agent-violet" },
  data_analysis: { label: "数据分析师", short: "产出前分析与统计计划", tone: "agent-gold" },
  paper_writing: { label: "论文写作助手", short: "把结果回写成论文段落", tone: "agent-rose" },
  independent_review: { label: "独立审查员", short: "检查证据、方法和可复现性", tone: "agent-slate" },
};

const codexDraft = `# candidate_analysis.py

def run_analysis(data, pretest_col, posttest_col, transfer_col):
    # candidate code only: review before approval
    change_score = data[posttest_col] - data[pretest_col]
    transfer_summary = data[transfer_col].describe()
    return {
        "change_score": change_score.describe(),
        "transfer_summary": transfer_summary,
    }`;

export function AgentCodexPage({ projectId, onNavigate }: AgentCodexPageProps) {
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
  const [agents, setAgents] = useState<AgentCapability[]>(demoMode ? demoAgents : []);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(demoMode ? demoRuntime : null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(demoMode ? demoWorkflowState : null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(demoMode ? demoApproval : null);
  const [routes, setRoutes] = useState<Array<Record<string, unknown>>>(
    demoMode ? (demoRouteRows as unknown as Array<Record<string, unknown>>) : [],
  );
  const [executions, setExecutions] = useState<Array<Record<string, unknown>>>(
    demoMode ? (demoExecutionRows as Array<Record<string, unknown>>) : [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const [nextAgents, nextRuntime, nextWorkflow, nextRoutes, nextExecutions] = await Promise.all([
          workflowApi.listAgents(),
          workflowApi.getRuntime(),
          workflowApi.getProject(projectId),
          workflowApi.listRoutes(projectId),
          workflowApi.listExecutions(projectId),
        ]);
        if (!mounted) return;
        setAgents(nextAgents);
        setRuntime(nextRuntime);
        setWorkflow(nextWorkflow);
        setRoutes(nextRoutes as unknown as Array<Record<string, unknown>>);
        setExecutions(nextExecutions as unknown as Array<Record<string, unknown>>);
        setApproval(nextWorkflow.pending_approval_ref ? demoApproval : null);
      } catch {
        if (!mounted || !demoMode) setError("Agent 工作流暂时无法读取");
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, [demoMode, projectId]);

  const activeAgent = workflow?.last_route_decision?.selected_route ?? "research_design";
  const activeMeta = agentMeta[activeAgent] ?? agentMeta.research_design;
  const approvedCount = agents.filter((agent) => !agent.forbidden_actions.includes("approve")).length;
  const canRunCodex = Boolean(runtime?.codex_available);

  const runWorkflow = async (action: "start" | "next") => {
    setBusy(true);
    setError("");
    try {
      if (action === "start") {
        const result = await workflowApi.startProject({
          project_id: projectId,
          research_intent: "生成式 AI 分层支架与师范生 Python 物理建模能力",
        });
        setWorkflow(result.workflow_state);
        setApproval(result.approval_request);
      } else {
        const result = await workflowApi.runNext(projectId);
        setWorkflow(result.workflow_state);
        setApproval(result.approval_request);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "流程操作失败");
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

  const agentStats = useMemo(() => [
    { label: "可调度 Agent", value: agents.length || 6 },
    { label: "受控动作", value: approvedCount || 6 },
    { label: "待审批", value: approval ? 1 : 0 },
    { label: "执行记录", value: executions.length },
  ], [agents.length, approvedCount, approval, executions.length]);

  return (
    <div className="workspace agent-page">
      <header className="page-hero">
        <div>
          <span className="eyebrow">AGENT / CODEX CONTROL ROOM</span>
          <h1>Agent 与 Codex</h1>
          <p>Agent 只提出候选，Controller 推进状态，Codex 只生成受控代码，所有执行都停在人工审批边界之外。</p>
        </div>
        <div className="hero-actions">
          <button className="secondary-action" onClick={() => onNavigate("editor")} type="button">回到论文编辑</button>
          <button className="primary-action" disabled={busy} onClick={() => void runWorkflow(workflow ? "next" : "start")} type="button">
            {busy ? "处理中..." : workflow ? "推进下一阶段" : "启动研究流程"}
          </button>
        </div>
      </header>

      <section className="metric-grid agent-metrics">
        {agentStats.map((item) => (
          <article className="metric-card" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <small>项目 {projectId}</small>
          </article>
        ))}
      </section>

      <div className="agent-layout">
        <main className="agent-main">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">SIX AGENT CONTROLLER</span>
                <h2>研究角色</h2>
              </div>
              <span className={`status-badge ${approval ? "status-review" : "status-ready"}`}>{approval ? "等待人工审批" : "可继续推进"}</span>
            </div>
            <div className="agent-grid">
              {(agents.length ? agents : demoAgents).map((agent) => {
                const meta = agentMeta[agent.agent_id] ?? {
                  label: agent.agent_id,
                  short: "受控研究角色",
                  tone: "agent-slate",
                };
                const selected = agent.agent_id === activeAgent;
                return (
                  <article className={`agent-card ${meta.tone} ${selected ? "agent-card-selected" : ""}`} key={agent.agent_id}>
                    <div className="agent-card-topline">
                      <span className="agent-index">{selected ? "当前" : "候选"}</span>
                      <span className="status-badge status-muted">{agent.read_only_global_state ? "只读状态" : "可写状态"}</span>
                    </div>
                    <h3>{meta.label}</h3>
                    <p>{meta.short}</p>
                    <div className="agent-capabilities">
                      {agent.allowed_output_types.slice(0, 2).map((capability) => <span key={capability}>{capability}</span>)}
                    </div>
                    <small>禁止：{agent.forbidden_actions.slice(0, 3).join("、")}</small>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="panel controller-flow">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">CONTROLLER STATE</span>
                <h2>当前协作链</h2>
              </div>
              <span className="status-badge status-ready">{workflow?.current_stage ?? "WAITING_HUMAN"}</span>
            </div>
            <div className="controller-steps">
              <div><span>01</span><strong>研究问题</strong><small>项目研究意图和上下文</small></div>
              <div><span>02</span><strong>{activeMeta.label}</strong><small>{workflow?.last_route_decision?.reason ?? "等待 Controller 选择研究角色"}</small></div>
              <div><span>03</span><strong>候选工件</strong><small>{workflow?.research_state?.artifact_refs.length ?? 0} 个候选输出</small></div>
              <div><span>04</span><strong>Human Gate</strong><small>{approval ? "等待研究者确认" : "当前没有待审批请求"}</small></div>
            </div>
            <div className="button-row">
              <button className="secondary-action" disabled={busy} onClick={() => void runWorkflow(workflow ? "next" : "start")} type="button">
                {workflow ? "调度下一 Agent" : "运行 Mentor Planning"}
              </button>
              <button className="text-action" onClick={() => onNavigate("audit")} type="button">查看审计验证</button>
            </div>
          </section>

          <section className="panel route-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">ROUTE & EXECUTION LOG</span>
                <h2>路由与执行记录</h2>
              </div>
              <span className="result-count">{routes.length + executions.length} 条记录</span>
            </div>
            <div className="route-list">
              {[...routes, ...executions].slice(0, 6).map((row, index) => (
                <article key={`${String(row.created_at ?? row.finished_at ?? "row")}-${index}`}>
                  <strong>{String(row.selected_route ?? row.operator_id ?? "研究动作")}</strong>
                  <span>{String(row.status ?? row.reason ?? "已记录")}</span>
                  <small>{String(row.created_at ?? row.finished_at ?? "刚刚")}</small>
                </article>
              ))}
            </div>
            <TechnicalTrace title="查看 Controller 原始状态">
              <pre>{JSON.stringify({ workflow, routes, executions }, null, 2)}</pre>
            </TechnicalTrace>
          </section>
        </main>

        <aside className="agent-right">
          {approval ? (
            <HumanGatePanel approval={approval} busy={busy} onDecide={(decision) => void decide(decision)} />
          ) : (
            <section className="panel approval-empty">
              <span className="eyebrow">HUMAN GATE</span>
              <h3>当前没有待审批请求</h3>
              <p>Agent 输出始终先停在候选状态，只有研究者确认后才能推进。</p>
              <button className="secondary-action full-width" onClick={() => void runWorkflow("next")} type="button">刷新工作流状态</button>
            </section>
          )}

          <section className="panel codex-panel-new">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">CONTROLLED CODING</span>
                <h3>Codex 分析候选</h3>
              </div>
              <span className={`status-badge ${canRunCodex ? "status-ready" : "status-review"}`}>{canRunCodex ? "可用" : "未启用"}</span>
            </div>
            <div className="codex-summary">
              <div><span>代码提供者</span><strong>{runtime?.coding_provider ?? "deterministic"}</strong></div>
              <div><span>执行状态</span><strong>{canRunCodex ? "等待审批" : runtime?.codex_reason ?? "CODEX_PROVIDER_NOT_SELECTED"}</strong></div>
              <div><span>数据绑定</span><strong>待冻结数据</strong></div>
            </div>
            <pre className="code-preview-new">{codexDraft}</pre>
            <div className="codex-warning">
              <strong>受控模式</strong>
              <span>候选代码只能进入静态审查和人工审批，不能在前端直接执行。</span>
            </div>
            <button className="secondary-action full-width" disabled={!canRunCodex} type="button">请求代码审查</button>
          </section>
        </aside>
      </div>

      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  );
}
