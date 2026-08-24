import { useEffect, useMemo, useState } from "react";
import { authApi, readStoredAuth } from "../api/auth";
import { qaApi, type QAAnswerResponse, type QAContextMode } from "../api/qa";
import { workflowApi, type ApprovalRequest, type WorkflowState } from "../api/workflow";
import { api } from "../api/client";
import type { SharedChunkHit, SharedCorpusSummary } from "../types/context";
import type { WorkspaceTab } from "../App";
import { ArtifactSummary } from "../components/ArtifactSummary";
import { CitationDetailDrawer } from "../components/CitationDetailDrawer";
import { EvidenceCoverage } from "../components/EvidenceCoverage";
import { EvidencePanel } from "../components/EvidencePanel";
import { HumanGatePanel } from "../components/HumanGatePanel";
import { StageTimeline } from "../components/StageTimeline";
import { buildAnswerView, buildResearchContext } from "../utils/researchViewModel";
import type { EvidenceViewModel } from "../types/research";
import { demoApproval, demoCorpus, demoQAResponse, demoRetrieval, demoWorkflowState } from "../demo/data";

const presets = [
  "生成式 AI 分层支架是否改善师范生 Python 物理建模能力？",
  "如何设计 Physics-STEM 物理建模研究的对照组与主要结果变量？",
  "有前测、后测和迁移测验时应采用什么分析方法？",
];

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: QAAnswerResponse;
  mode?: QAContextMode;
  evidence: EvidenceViewModel[];
};

function newMessageId(role: ChatMessage["role"]) {
  return `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function retrievalLabel(response: QAAnswerResponse) {
  if (response.retrieval_status === "READY") return "检索完成";
  if (response.retrieval_status === "DEGRADED") return "检索降级";
  if (response.retrieval_status === "UNAVAILABLE") return "检索不可用";
  return response.retrieval_status;
}

function modeLabel(mode: QAContextMode) {
  return mode === "formal" ? "正式证据" : "发现探索";
}

function AnswerMessage({
  message,
  onOpenEvidence,
  onNavigate,
}: {
  message: ChatMessage;
  onOpenEvidence: (item: EvidenceViewModel) => void;
  onNavigate: (tab: WorkspaceTab) => void;
}) {
  const response = message.response;
  const evidence = message.evidence;
  if (!response) {
    return (
      <div className="chat-message chat-message-assistant">
        <div className="assistant-avatar">S</div>
        <div className="chat-bubble assistant-bubble welcome-bubble">
          <div className="message-label">STEM-SCI 研究助手</div>
          <p>{message.text}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-message chat-message-assistant">
      <div className="assistant-avatar">S</div>
      <div className="chat-bubble assistant-bubble answer-bubble">
        <div className="message-toolbar">
          <span className="message-label">研究助手回答</span>
          <span className="answer-time">{modeLabel(message.mode ?? "discovery")}</span>
        </div>
        <p className="answer-text">{response.answer}</p>
        <div className="answer-status-row" aria-label="回答状态">
          <span className={`answer-status status-${response.retrieval_status.toLowerCase()}`}>
            <i className="status-dot" />
            {retrievalLabel(response)}
          </span>
          <span className="answer-status">{response.answer_mode === "llm" ? "模型综合" : "证据摘要"}</span>
          <span className="answer-status">置信度 {Math.round(response.confidence * 100)}%</span>
        </div>
        <EvidenceCoverage coverage={buildAnswerView(response, null, []).coverage} />
        {response.risk_flags.length > 0 && (
          <div className="risk-callout">
            <strong>需要注意</strong>
            <span>{response.risk_flags.join("；")}</span>
          </div>
        )}
        {evidence.length > 0 ? (
          <div className="inline-citations">
            <div className="inline-citations-heading">
              <strong>回答依据</strong>
              <span>{evidence.length} 条检索材料</span>
            </div>
            <div className="inline-citation-list">
              {evidence.slice(0, 3).map((item, index) => (
                <button className="inline-citation" key={item.id} onClick={() => onOpenEvidence(item)} type="button">
                  <span className="citation-index">{index + 1}</span>
                  <span className="inline-citation-copy">
                    <strong>{item.title}</strong>
                    <span>{item.excerpt}</span>
                    <small>
                      {item.source}
                      {item.page ? ` · ${item.page}` : " · 位置待补充"} · {item.verification}
                    </small>
                  </span>
                  <span className="citation-arrow" aria-hidden="true">
                    {"->"}
                  </span>
                </button>
              ))}
            </div>
            {evidence.length > 3 && <span className="citation-more">还有 {evidence.length - 3} 条依据，可在证据库查看</span>}
          </div>
        ) : (
          <div className="no-citation-callout">
            <strong>当前回答没有可展示的引用</strong>
            <span>可以继续补充问题，或打开证据库查看检索结果。</span>
          </div>
        )}
        <div className="answer-actions">
          <button className="text-action" onClick={() => onNavigate("workspace")} type="button">
            打开项目工作台
          </button>
          <button className="text-action" onClick={() => onNavigate("agent")} type="button">
            查看 Agent / Codex
          </button>
        </div>
      </div>
    </div>
  );
}

export function ProjectWorkspacePage({ projectId: projectIdProp, onNavigate }: { projectId: string; onNavigate: (tab: WorkspaceTab) => void }) {
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
  const auth = readStoredAuth();
  const token = auth?.access_token;
  const [projectId, setProjectId] = useState(projectIdProp);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>(
    demoMode ? demoQAResponse.conversation_id : undefined,
  );
  const [answer, setAnswer] = useState<QAAnswerResponse | null>(demoMode ? demoQAResponse : null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(demoMode ? demoWorkflowState : null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(demoMode ? demoApproval : null);
  const [corpus, setCorpus] = useState<SharedCorpusSummary | null>(demoMode ? demoCorpus : null);
  const [sharedHits, setSharedHits] = useState<SharedChunkHit[]>(
    demoMode ? demoRetrieval.chunk_hits : [],
  );
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceViewModel | null>(null);
  const [mode, setMode] = useState<QAContextMode>("discovery");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const welcome: ChatMessage = {
      id: "welcome",
      role: "assistant",
      text: "你好，我是 STEM-SCI 研究助手。你可以直接描述一个 Physics-STEM 研究问题，我会先检索知识库，再给出回答、依据和研究边界。",
      evidence: [],
    };
    if (!demoMode) return [welcome];
    return [
      welcome,
      {
        id: "demo-user-question",
        role: "user",
        text: demoQAResponse.question,
        evidence: [],
      },
      {
        id: "demo-assistant-answer",
        role: "assistant",
        text: demoQAResponse.answer,
        response: demoQAResponse,
        mode: "discovery",
        evidence: buildAnswerView(demoQAResponse, null, demoRetrieval.chunk_hits).evidence,
      },
    ];
  });

  useEffect(() => {
    setProjectId(projectIdProp);
  }, [projectIdProp]);

  useEffect(() => {
    void api
      .listSharedCorpora()
      .then((items) => setCorpus(items.find((item) => item.corpus_id === "physics_stem_v1") ?? null))
      .catch(() => undefined);
  }, []);

  const answerView = useMemo(() => buildAnswerView(answer, null, sharedHits), [answer, sharedHits]);
  const context = useMemo(
    () => buildResearchContext(workflow, approval, answerView.evidence),
    [workflow, approval, answerView.evidence],
  );

  const ask = async (preset?: string) => {
    const askedQuestion = (preset ?? question).trim();
    if (!askedQuestion || busy) return;
    setBusy(true);
    setError("");
    setQuestion("");
    setMessages((current) => [
      ...current,
      { id: newMessageId("user"), role: "user", text: askedQuestion, evidence: [] },
    ]);

    try {
      const response = token
        ? await authApi.projectChatAnswer(token, {
            project_id: projectId,
            question: askedQuestion,
            mode,
            conversation_id: conversationId ?? null,
            allow_llm: true,
          })
        : await qaApi.answer({
            project_id: projectId,
            question: askedQuestion,
            mode,
            conversation_id: conversationId,
            allow_llm: true,
          });
      setAnswer(response);
      setConversationId(response.conversation_id);
      if (response.workflow_action?.workflow_state) {
        setWorkflow(response.workflow_action.workflow_state as unknown as WorkflowState);
      }
      if (response.workflow_action?.approval_request) {
        setApproval(response.workflow_action.approval_request as unknown as ApprovalRequest);
      }
      let nextEvidence = buildAnswerView(response, null, []).evidence;
      try {
        const result = await api.searchSharedCorpus(projectId, response.rewritten_query || askedQuestion, mode);
        setSharedHits(result.chunk_hits);
        nextEvidence = buildAnswerView(response, null, result.chunk_hits).evidence;
      } catch {
        setSharedHits([]);
      }
      setMessages((current) => [
        ...current,
        {
          id: newMessageId("assistant"),
          role: "assistant",
          text: response.answer,
          response,
          mode,
          evidence: nextEvidence,
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "暂时无法完成研究检索");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision: "approved" | "rejected", _reason: string) => {
    if (!approval) return;
    setBusy(true);
    try {
      await workflowApi.approve(projectId, decision, "researcher");
      const next = await workflowApi.getProject(projectId);
      setWorkflow(next);
      setApproval(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "审批未完成");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="workspace">
      <header className="workspace-intro chat-intro">
        <div>
          <span className="eyebrow">PROJECT WORKSPACE / EVIDENCE-AWARE RESEARCH</span>
          <h1>围绕一篇论文推进研究。</h1>
          <p>项目资料在左，研究对话在中，证据和审批在右，所有下一步都回到当前项目。</p>
        </div>
        <div className="project-chip">
          <span>当前项目</span>
          <strong>{projectId}</strong>
        </div>
      </header>

      <div className="cockpit-gates">
        <div className="chat-page-status">
          <span className="status-live">
            <i className="status-dot" />
            本地后端已连接
          </span>
          <span className="status-note">{corpus?.formal_evidence_ready ? "正式证据可用" : "当前使用发现探索模式"}</span>
          <button className="text-action" onClick={() => onNavigate("workspace")} type="button">
            查看项目证据
          </button>
          <button className="text-action" onClick={() => onNavigate("agent")} type="button">
            Agent / Codex
          </button>
        </div>
      </div>

      <div className="cockpit-grid chat-first-grid">
        <aside className="stage-sidebar">
          <div className="sidebar-heading">
            <div>
              <span className="eyebrow">RESEARCH WORKFLOW</span>
              <h2>研究进度</h2>
            </div>
          </div>
          <StageTimeline context={context} />
          <div className="stage-current">
            <span className="eyebrow">当前阶段</span>
            <strong>{context.stageDefinition.label}</strong>
            <p>主导：{context.stageDefinition.lead.label}</p>
            <p className="muted">支持：{context.stageDefinition.support.map((item) => item.label).join("、")}</p>
            <ArtifactSummary artifacts={context.artifacts} />
          </div>
        </aside>

        <section className="research-center chat-workspace" aria-label="研究对话">
          <div className="chat-header">
            <div>
              <span className="eyebrow">RESEARCH CHAT</span>
              <h2>和研究助手对话</h2>
              <p>回答会显示检索状态、风险提示和对应的原文摘录。</p>
            </div>
            <div className="chat-header-meta">
              <span>{messages.filter((item) => item.role === "user").length} 个问题</span>
              <span className={mode === "formal" ? "mode-pill mode-formal" : "mode-pill"}>{modeLabel(mode)}</span>
            </div>
          </div>

          <div className="chat-thread" aria-live="polite">
            {messages.map((message) =>
              message.role === "assistant" ? (
                <AnswerMessage key={message.id} message={message} onOpenEvidence={setSelectedEvidence} onNavigate={onNavigate} />
              ) : (
                <div className="chat-message chat-message-user" key={message.id}>
                  <div className="chat-bubble user-bubble">{message.text}</div>
                </div>
              ),
            )}
            {busy && (
              <div className="chat-message chat-message-assistant">
                <div className="assistant-avatar">S</div>
                <div className="chat-bubble assistant-bubble typing-bubble">
                  <span className="typing-indicator" aria-label="研究助手正在检索">
                    <i />
                    <i />
                    <i />
                  </span>
                  正在检索知识库并整理回答
                </div>
              </div>
            )}
          </div>

          <div className="chat-composer">
            <div className="composer-topline">
              <label className="project-field">
                <span>项目 ID</span>
                <input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
              </label>
              <div className="segmented-control" aria-label="回答模式">
                <button className={mode === "discovery" ? "selected" : ""} onClick={() => setMode("discovery")} type="button">
                  发现探索
                </button>
                <button
                  className={mode === "formal" ? "selected" : ""}
                  disabled={!corpus?.formal_evidence_ready}
                  onClick={() => setMode("formal")}
                  title={corpus?.formal_evidence_ready ? "使用已定位并核验的正式证据" : "正式证据仍需完成来源定位与核验"}
                  type="button"
                >
                  正式证据
                </button>
              </div>
            </div>
            <textarea
              aria-label="输入研究问题"
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void ask();
                }
              }}
              placeholder="输入你的研究问题，例如：如何设计一个可检验的 Python 物理建模实验？"
              rows={3}
              value={question}
            />
            <div className="composer-bottomline">
              <span>Enter 发送，Shift + Enter 换行</span>
              <button className="primary-action send-action" disabled={busy || !question.trim()} onClick={() => void ask()} type="button">
                {busy ? "检索中..." : "发送问题"}
              </button>
            </div>
            <div className="preset-list composer-presets">
              <span className="preset-label">试试：</span>
              {presets.map((preset) => (
                <button className="preset" key={preset} onClick={() => void ask(preset)} type="button">
                  {preset}
                </button>
              ))}
            </div>
          </div>
        </section>

        <aside className="evidence-sidebar">
          <EvidencePanel evidence={answerView.evidence} gates={context.gates} onOpen={setSelectedEvidence} />
          {approval && <HumanGatePanel approval={approval} busy={busy} onDecide={decide} />}
        </aside>
      </div>

      {error && <p className="error-text" role="alert">{error}</p>}
      <CitationDetailDrawer item={selectedEvidence} onClose={() => setSelectedEvidence(null)} />
    </div>
  );
}
