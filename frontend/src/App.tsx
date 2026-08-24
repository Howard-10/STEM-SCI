import { useEffect, useMemo, useState } from "react";
import {
  authApi,
  clearAuth,
  readStoredAuth,
  saveAuth,
  type ApiConversationSummary,
  type ApiDocumentVersion,
  type ApiProjectDocument,
  type ApiResearchProject,
  type AuthState,
} from "./api/auth";
import { qaApi, type QAAnswerResponse, type QAContextMode } from "./api/qa";
import { demoBundle, demoCorpus, demoQAResponse, demoRuntime } from "./demo/data";
import { demoDocumentContents, demoDocumentsByProject, demoProjects } from "./demo/projectHub";

type WorkspaceView = "knowledge" | "codex" | "audit";
export type WorkspaceTab = "home" | "workspace" | "editor" | "agent" | "audit";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: QAAnswerResponse;
};

type PaneWidths = {
  sidebar: number;
  output: number;
};

type SelectedDocument = {
  document: ApiProjectDocument;
  version: ApiDocumentVersion | null;
};

type SelectedCitation = QAAnswerResponse["citations"][number];

const demoProjectId = import.meta.env.VITE_PROJECT_ID && import.meta.env.VITE_PROJECT_ID !== "demo"
  ? import.meta.env.VITE_PROJECT_ID
  : "physics-ai-demo";
const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";

const starterPrompts = [
  "帮我梳理这个研究方向的核心文献与研究空白",
  "根据当前证据设计一个师范生 Python 物理建模实验",
  "检查我的研究问题、变量和数据分析方案是否一致",
];

const agentRows = [
  ["01", "导师规划", "界定研究问题与范围", "已完成"],
  ["02", "证据审查", "筛选、核验和组织文献证据", "进行中"],
  ["03", "研究设计", "形成可审批的研究方案", "待启动"],
  ["04", "数据分析", "编译分析计划与结果检查", "待启动"],
  ["05", "论文写作", "生成基于证据的写作草案", "待启动"],
  ["06", "独立审查", "检查风险、引用和方法", "待启动"],
];

const capabilityCards = [
  {
    icon: "⌕",
    title: "论文检索",
    description: "从当前项目和共享知识库中找到相关论文与原文片段。",
    prompt: "帮我梳理这个研究方向的核心文献与研究空白",
  },
  {
    icon: "◈",
    title: "证据回答",
    description: "回答会带有检索轨迹、引用和待核验风险提示。",
    prompt: "根据当前证据给出一个有引用的研究结论",
  },
  {
    icon: "✦",
    title: "Agent 协作",
    description: "把研究问题交给规划、设计、分析和审查 Agent。",
    prompt: "根据当前证据设计一个师范生 Python 物理建模实验",
  },
  {
    icon: "⌘",
    title: "代码与审查",
    description: "为数据分析生成代码草案，并在执行前经过审查。",
    prompt: "检查我的研究问题、变量和数据分析方案是否一致",
  },
];

function makeWelcome(projectTitle: string): ChatMessage {
  return {
    id: "welcome",
    role: "assistant",
    content: `你好，我是 STEM-SCI 研究助手。当前项目是“${projectTitle}”。\n\n你可以直接告诉我研究方向、论文问题或数据分析需求。我会先检索相关论文，再把证据、研究建议和需要人工确认的地方整理到右侧。`,
  };
}

export function App() {
  const [auth, setAuth] = useState<AuthState | null>(() => readStoredAuth());
  const [projects, setProjects] = useState<ApiResearchProject[]>(demoProjects);
  const [projectId, setProjectId] = useState(demoProjects[0]?.project_id ?? demoProjectId);
  const [view, setView] = useState<WorkspaceView>("knowledge");
  const [mode, setMode] = useState<QAContextMode>("discovery");
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([
    makeWelcome(demoProjects[0]?.title ?? "科研项目"),
  ]);
  const [lastResponse, setLastResponse] = useState<QAAnswerResponse>(demoQAResponse);
  const [busy, setBusy] = useState(false);
  const [loginValue, setLoginValue] = useState("");
  const [passwordValue, setPasswordValue] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [documents, setDocuments] = useState<ApiProjectDocument[]>([]);
  const [conversations, setConversations] = useState<ApiConversationSummary[]>([]);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<SelectedDocument | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation | null>(null);
  const [rightPaneVisible, setRightPaneVisible] = useState(true);
  const [paneWidths, setPaneWidths] = useState<PaneWidths>({ sidebar: 246, output: 374 });
  const [draggingPane, setDraggingPane] = useState<"sidebar" | "output" | null>(null);

  const activeProject = useMemo(
    () => projects.find((project) => project.project_id === projectId) ?? projects[0] ?? null,
    [projectId, projects],
  );
  const activeDocuments = documents.length
    ? documents
    : demoDocumentsByProject[projectId] ?? demoDocumentsByProject[demoProjectId] ?? [];
  const citations = lastResponse?.citations ?? demoQAResponse.citations;

  useEffect(() => {
    if (!auth?.access_token) {
      setProjects(demoProjects);
      return;
    }
    let mounted = true;
    void authApi.listProjects(auth.access_token).then((next) => {
      if (!mounted) return;
      setProjects(next.length ? next : demoProjects);
      if (next.length && !next.some((project) => project.project_id === projectId)) {
        setProjectId(next[0].project_id);
      }
    }).catch(() => {
      if (mounted) setProjects(demoProjects);
    });
    return () => {
      mounted = false;
    };
  }, [auth?.access_token]);

  useEffect(() => {
    let mounted = true;
    setDocumentsBusy(true);
    setSelectedDocument(null);
    setSelectedCitation(null);
    if (!auth?.access_token) {
      setDocuments(demoDocumentsByProject[projectId] ?? demoDocumentsByProject[demoProjectId] ?? []);
      setConversations([]);
      setDocumentsBusy(false);
      return () => {
        mounted = false;
      };
    }

    void Promise.all([
      authApi.listDocuments(auth.access_token, projectId),
      authApi.listConversations(auth.access_token, projectId),
    ]).then(([nextDocuments, nextConversations]) => {
      if (!mounted) return;
      setDocuments(nextDocuments);
      setConversations(nextConversations);
    }).catch(() => {
      if (!mounted) return;
      setDocuments(demoDocumentsByProject[projectId] ?? demoDocumentsByProject[demoProjectId] ?? []);
      setConversations([]);
    }).finally(() => {
      if (mounted) setDocumentsBusy(false);
    });

    return () => {
      mounted = false;
    };
  }, [auth?.access_token, projectId]);

  useEffect(() => {
    if (!draggingPane) return;
    const onPointerMove = (event: PointerEvent) => {
      if (draggingPane === "sidebar") {
        setPaneWidths((current) => ({
          ...current,
          sidebar: Math.max(190, Math.min(360, event.clientX)),
        }));
      } else {
        const nextOutput = window.innerWidth - event.clientX;
        setPaneWidths((current) => ({
          ...current,
          output: Math.max(280, Math.min(520, nextOutput)),
        }));
      }
    };
    const onPointerUp = () => setDraggingPane(null);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.body.classList.add("pane-resizing");
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.body.classList.remove("pane-resizing");
    };
  }, [draggingPane]);

  const submitQuestion = async (value = question) => {
    const trimmed = value.trim();
    if (!trimmed || busy || !activeProject) return;
    setMessages((current) => [...current, {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
    }]);
    setQuestion("");
    setBusy(true);
    try {
      const response = auth?.access_token
        ? await authApi.projectChatAnswer(auth.access_token, {
          project_id: projectId,
          question: trimmed,
          mode,
          conversation_id: conversationId,
          allow_llm: true,
          top_k: 8,
          token_budget: 3000,
        })
        : await qaApi.answer({
          project_id: projectId,
          question: trimmed,
          mode,
          conversation_id: conversationId,
          allow_llm: true,
          top_k: 8,
          token_budget: 3000,
        });
      setConversationId(response.conversation_id);
      setLastResponse(response);
      setMessages((current) => [...current, {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: response.answer,
        response,
      }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "对话服务暂时不可用";
      setMessages((current) => [...current, {
        id: `assistant-error-${Date.now()}`,
        role: "assistant",
        content: `暂时无法连接后端问答服务。\n\n${message}\n\n当前界面仍保留演示证据，你可以稍后重试。`,
        response: demoMode ? demoQAResponse : undefined,
      }]);
    } finally {
      setBusy(false);
    }
  };

  const signIn = async () => {
    if (!loginValue.trim() || !passwordValue.trim()) return;
    setAuthBusy(true);
    setAuthError("");
    try {
      const next = await authApi.login({ login: loginValue.trim(), password: passwordValue });
      saveAuth(next);
      setAuth(next);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "登录失败");
    } finally {
      setAuthBusy(false);
    }
  };

  const signOut = async () => {
    try {
      if (auth?.access_token) await authApi.logout(auth.access_token);
    } catch {
      // Local session is still cleared when the API is unavailable.
    }
    clearAuth();
    setAuth(null);
  };

  const switchProject = (nextProjectId: string) => {
    setProjectId(nextProjectId);
    setProjectMenuOpen(false);
    setConversationId(undefined);
    setConversations([]);
    const project = projects.find((item) => item.project_id === nextProjectId);
    setMessages([makeWelcome(project?.title ?? "科研项目")]);
  };

  const openDocument = async (document: ApiProjectDocument) => {
    setSelectedDocument({ document, version: null });
    if (!auth?.access_token) {
      setSelectedDocument({
        document,
        version: {
          document_id: document.document_id,
          project_id: document.project_id,
          version: document.current_version,
          format: document.format,
          content: demoDocumentContents[document.document_id] ?? "演示文档暂无正文。",
          sha256: document.current_sha256,
          size_bytes: document.size_bytes,
          storage_ref: `demo://${document.document_id}`,
          change_note: null,
          created_by: document.created_by,
          created_at: document.updated_at,
        },
      });
      return;
    }
    try {
      const version = await authApi.getDocumentVersion(
        auth.access_token,
        projectId,
        document.document_id,
        document.current_version,
      );
      setSelectedDocument({ document, version });
    } catch {
      setSelectedDocument({ document, version: null });
    }
  };

  const openConversation = async (conversation: ApiConversationSummary) => {
    setConversationId(conversation.conversation_id);
    if (!auth?.access_token) return;
    try {
      const turns = await authApi.listConversationTurns(auth.access_token, projectId, conversation.conversation_id);
      const nextMessages: ChatMessage[] = [];
      turns.forEach((turn) => {
        nextMessages.push({
          id: `${turn.memory_id}-question`,
          role: "user",
          content: turn.question,
        });
        nextMessages.push({
          id: `${turn.memory_id}-answer`,
          role: "assistant",
          content: turn.answer,
          response: {
            project_id: turn.project_id,
            conversation_id: turn.conversation_id,
            question: turn.question,
            rewritten_query: turn.rewritten_query,
            route: {
              route: turn.route,
              reason: "从已保存的对话记录恢复",
              recommended_agent: null,
            },
            answer: turn.answer,
            citations: turn.citations,
            retrieval_status: "RESTORED",
            retrieval_trace_ref: turn.retrieval_trace_ref,
            context_bundle_ref: null,
            memory_ref: turn.memory_id,
            risk_flags: [],
            answer_mode: "fallback",
            confidence: 0,
            needs_follow_up: false,
            follow_up_question: null,
            tool_calls: [],
            workflow_action: null,
          },
        });
      });
      if (nextMessages.length) {
        setMessages(nextMessages);
        const last = turns[turns.length - 1];
        setLastResponse({
          project_id: last.project_id,
          conversation_id: last.conversation_id,
          question: last.question,
          rewritten_query: last.rewritten_query,
          route: {
            route: last.route,
            reason: "从已保存的对话记录恢复",
            recommended_agent: null,
          },
          answer: last.answer,
          citations: last.citations,
          retrieval_status: "RESTORED",
          retrieval_trace_ref: last.retrieval_trace_ref,
          context_bundle_ref: null,
          memory_ref: last.memory_id,
          risk_flags: [],
          answer_mode: "fallback",
          confidence: 0,
          needs_follow_up: false,
          follow_up_question: null,
          tool_calls: [],
          workflow_action: null,
        });
      }
    } catch {
      // Keep the current view if a stored conversation cannot be restored.
    }
  };

  const resetConversation = () => {
    setConversationId(undefined);
    setMessages([makeWelcome(activeProject?.title ?? "科研项目")]);
    setLastResponse(demoQAResponse);
  };

  const workspaceStyle = {
    gridTemplateColumns: rightPaneVisible
      ? `${paneWidths.sidebar}px 8px minmax(420px, 1fr) 8px ${paneWidths.output}px`
      : `${paneWidths.sidebar}px 8px minmax(0, 1fr)`,
  };

  return (
    <div className={`research-app ${rightPaneVisible ? "" : "research-app-two-pane"}`} style={workspaceStyle}>
      <aside className="research-sidebar">
        <div className="research-brand">
          <div className="research-logo">S</div>
          <div>
            <strong>STEM-SCI</strong>
            <span>科研智能工作台</span>
          </div>
        </div>

        <button className="new-conversation" type="button" onClick={() => setMessages([makeWelcome(activeProject?.title ?? "科研项目")])}>
          <span className="ui-icon">＋</span>
          新建对话
        </button>

        <div className="sidebar-section">
          <span className="sidebar-label">工作区</span>
          <button className="sidebar-link sidebar-link-active" type="button">
            <span className="ui-icon">⌕</span>
            研究助手
          </button>
          <button className={view === "knowledge" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => setView("knowledge")}>
            <span className="ui-icon">▱</span>
            知识库
          </button>
          <button className={view === "codex" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => setView("codex")}>
            <span className="ui-icon">⌘</span>
            Codex
          </button>
          <button className={view === "audit" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => setView("audit")}>
            <span className="ui-icon">✓</span>
            数据审查
          </button>
        </div>

        <div className="sidebar-section project-section">
          <div className="sidebar-section-heading">
            <span className="sidebar-label">项目</span>
            <button className="plain-icon-button" type="button" title="新建项目">＋</button>
          </div>
          <button className="project-select" type="button" onClick={() => setProjectMenuOpen((open) => !open)}>
            <span className="project-avatar">{(activeProject?.title ?? "研").slice(0, 1)}</span>
            <span className="project-select-copy">
              <strong>{activeProject?.title ?? "选择项目"}</strong>
              <small>{activeProject?.research_direction ?? "开始一个研究项目"}</small>
            </span>
            <span className="chevron">{projectMenuOpen ? "⌃" : "⌄"}</span>
          </button>
          {projectMenuOpen && (
            <div className="project-menu">
              {projects.map((project) => (
                <button
                  className={project.project_id === projectId ? "project-menu-item selected" : "project-menu-item"}
                  key={project.project_id}
                  type="button"
                  onClick={() => switchProject(project.project_id)}
                >
                  <strong>{project.title}</strong>
                  <small>{project.status === "active" ? "进行中" : "已归档"}</small>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="sidebar-section recent-section">
          <span className="sidebar-label">最近对话</span>
          {conversations.length ? conversations.slice(0, 4).map((conversation) => (
            <button
              className={conversation.conversation_id === conversationId ? "recent-chat selected" : "recent-chat"}
              type="button"
              key={conversation.conversation_id}
              onClick={() => void openConversation(conversation)}
            >
              <strong>{conversation.title || conversation.last_question}</strong>
              <small>{conversation.turn_count} 轮 · {conversation.last_answer_preview.slice(0, 16)}</small>
            </button>
          )) : (
            <button className="recent-chat selected" type="button">
              <strong>{conversationId ? "当前研究讨论" : "研究设计与文献证据"}</strong>
              <small>刚刚 · {(activeProject?.title ?? "科研项目").slice(0, 12)}</small>
            </button>
          )}
          <button className="recent-chat" type="button" onClick={() => setMessages([makeWelcome(activeProject?.title ?? "科研项目")])}>
            <strong>新建研究问题</strong>
            <small>开始新的研究对话</small>
          </button>
        </div>

        <div className="sidebar-bottom">
          <div className="service-status"><span className="status-pulse" /> 后端服务已连接</div>
          {auth ? (
            <button className="account-row" type="button" onClick={() => void signOut()}>
              <span className="account-avatar">{(auth.user.display_name ?? auth.user.username).slice(0, 1)}</span>
              <span><strong>{auth.user.display_name ?? auth.user.username}</strong><small>退出登录</small></span>
              <span className="more-icon">···</span>
            </button>
          ) : (
            <div className="account-row account-row-demo">
              <span className="account-avatar">D</span>
              <span><strong>演示访客</strong><small>登录以保存项目</small></span>
            </div>
          )}
        </div>
      </aside>
      <div className="pane-resizer pane-resizer-sidebar" role="separator" aria-label="调整左侧栏宽度" onPointerDown={() => setDraggingPane("sidebar")} />

      <main className="chat-pane">
        <header className="chat-header">
          <div>
            <span className="chat-kicker">研究助手</span>
            <h1>{activeProject?.title ?? "科研智能工作台"}</h1>
          </div>
          <div className="chat-header-actions">
            <span className={mode === "formal" ? "mode-pill formal" : "mode-pill"}>{mode === "formal" ? "正式证据模式" : "探索模式"}</span>
            <button className="header-icon-button" type="button" title="清空当前对话" onClick={resetConversation}>⌫</button>
          </div>
        </header>

        <section className="chat-thread" aria-live="polite">
          {messages.length === 1 && messages[0].id === "welcome" && (
            <section className="capability-section">
              <div className="capability-panel-heading">
                <div>
                  <span className="chat-kicker">你可以这样开始</span>
                  <h2>把研究问题交给工作台</h2>
                </div>
                <span className="capability-count">4 项能力</span>
              </div>
              <div className="capability-grid">
                {capabilityCards.map((card) => (
                  <button
                    className="capability-card"
                    key={card.title}
                    type="button"
                    onClick={() => void submitQuestion(card.prompt)}
                  >
                    <span className="capability-icon">{card.icon}</span>
                    <strong>{card.title}</strong>
                    <p>{card.description}</p>
                    <span className="capability-arrow">开始使用 →</span>
                  </button>
                ))}
              </div>
            </section>
          )}
          {messages.map((message) => (
            <article className={message.role === "user" ? "chat-message user-message" : "chat-message assistant-message"} key={message.id}>
              {message.role === "assistant" && <div className="assistant-mark">S</div>}
              <div className="message-body">
                <div className="message-meta">{message.role === "user" ? "你" : "STEM-SCI"} <span>·</span> {message.role === "user" ? "研究问题" : "研究助手"}</div>
                <p>{message.content}</p>
                {message.response && (
                  <div className="message-signal-row">
                    <span className="signal-chip signal-green">证据 {message.response.citations.length} 条</span>
                    <span className="signal-chip">{message.response.route.recommended_agent ?? "检索链路"}</span>
                    <span className="signal-chip">{message.response.answer_mode === "llm" ? "模型已综合" : "确定性摘要"}</span>
                  </div>
                )}
              </div>
            </article>
          ))}
          {busy && (
            <article className="chat-message assistant-message">
              <div className="assistant-mark">S</div>
              <div className="message-body typing-state"><span /><span /><span /></div>
            </article>
          )}
        </section>

        <section className="composer-area">
          <div className="starter-row">
            {starterPrompts.map((prompt) => (
              <button className="starter-prompt" key={prompt} type="button" onClick={() => void submitQuestion(prompt)}>{prompt}</button>
            ))}
          </div>
          <div className="composer-box">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submitQuestion();
                }
              }}
              placeholder="描述你的研究问题，或粘贴一段论文内容..."
              rows={3}
            />
            <div className="composer-toolbar">
              <div className="composer-tools">
                <button className="composer-tool" type="button" title="添加论文">＋</button>
                <button className="composer-tool" type="button" title="引用知识库">▱ <span>知识库</span></button>
                <button className="composer-tool" type="button" title="选择证据模式" onClick={() => setMode((current) => current === "discovery" ? "formal" : "discovery")}>
                  ◈ <span>{mode === "formal" ? "正式" : "探索"}</span>
                </button>
              </div>
              <button className="send-button" type="button" disabled={busy || !question.trim()} onClick={() => void submitQuestion()} title="发送消息">↑</button>
            </div>
          </div>
          <p className="composer-note">STEM-SCI 会优先使用当前项目论文和共享知识库回答，并标记需要人工核验的证据。</p>
        </section>
      </main>

      <div className="pane-resizer pane-resizer-output" role="separator" aria-label="调整右侧栏宽度" onPointerDown={() => setDraggingPane("output")} />
      <aside className={`output-pane ${rightPaneVisible ? "" : "output-pane-hidden"}`}>
        <div className="output-header">
          <div>
            <span className="chat-kicker">研究上下文</span>
            <h2>{view === "knowledge" ? "知识库" : view === "codex" ? "Codex 工作区" : "数据审查"}</h2>
          </div>
          <button className="header-icon-button" type="button" title="隐藏右侧面板，进入双栏模式" onClick={() => setRightPaneVisible(false)}>→</button>
        </div>

        {view === "knowledge" && (
          <div className="output-content">
            <section className="output-section">
              <div className="output-section-heading">
                <h3>当前项目论文</h3>
                <span>{documentsBusy ? "加载中..." : `${activeDocuments.length} 篇`}</span>
              </div>
              <div className="paper-list">
                {activeDocuments.map((document) => (
                  <button className="paper-item" type="button" key={document.document_id} onClick={() => void openDocument(document)}>
                    <span className="paper-file-icon">{document.format === "pdf" ? "PDF" : "MD"}</span>
                    <span><strong>{document.title}</strong><small>版本 {document.current_version} · {document.document_type}</small></span>
                    <span className="row-arrow">›</span>
                  </button>
                ))}
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>相关证据</h3><span>{citations.length} 条</span></div>
              <div className="evidence-list">
                {citations.map((citation, index) => (
                  <button className="evidence-item" type="button" key={citation.canonical_chunk_id} onClick={() => setSelectedCitation(citation)}>
                    <div className="evidence-item-topline"><span className="citation-number">{index + 1}</span><span className={index === 0 ? "verified-tag" : "review-tag"}>{index === 0 ? "已核验" : "待核验"}</span></div>
                    <strong>{citation.paper_title}</strong>
                    <p>{citation.excerpt}</p>
                    <small>{citation.source_filename} · Chunk {citation.chunk_index}</small>
                  </button>
                ))}
              </div>
            </section>
            <section className="output-section compact-section">
              <div className="output-section-heading"><h3>知识库状态</h3><span className="ready-text">可检索</span></div>
              <div className="corpus-stats">
                <div><strong>{demoCorpus.paper_count}</strong><small>篇论文</small></div>
                <div><strong>{demoCorpus.vector_chunk_count}</strong><small>文本块</small></div>
                <div><strong>{demoBundle.evidence_refs.length}</strong><small>本轮证据</small></div>
              </div>
            </section>
          </div>
        )}

        {view === "codex" && (
          <div className="output-content">
            <section className="codex-hero">
              <span className="codex-symbol">⌘</span>
              <h3>面向研究的代码工作区</h3>
              <p>在当前项目中编写、解释和审查 Python 分析代码。代码执行仍然需要经过数据审查和人工确认。</p>
              <button className="primary-inline-button" type="button">打开代码编辑器 <span>→</span></button>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>运行环境</h3><span className="review-tag">开发模式</span></div>
              <div className="runtime-list">
                <div><span>代码提供方</span><strong>{demoRuntime.coding_provider}</strong></div>
                <div><span>Codex CLI</span><strong>{demoRuntime.codex_available ? "可用" : "未配置"}</strong></div>
                <div><span>SPSS</span><strong>{demoRuntime.spss_available ? "可用" : "未配置"}</strong></div>
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>最近代码任务</h3><span>0</span></div>
              <div className="empty-output"><span className="empty-symbol">⌘</span><p>在对话中描述你的分析需求，Codex 会先生成代码草案。</p></div>
            </section>
          </div>
        )}

        {view === "audit" && (
          <div className="output-content">
            <section className="audit-summary">
              <div className="audit-summary-icon">✓</div>
              <div><strong>研究链路正在审查</strong><p>当前回答已关联证据，正式发布前仍需检查数据和引用。</p></div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>六个 Agent</h3><span>1 / 6 活跃</span></div>
              <div className="agent-list">
                {agentRows.map(([index, name, description, status]) => (
                  <div className="agent-row" key={index}>
                    <span className="agent-index">{index}</span>
                    <span><strong>{name}</strong><small>{description}</small></span>
                    <span className={status === "进行中" ? "agent-status active" : "agent-status"}>{status}</span>
                  </div>
                ))}
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>本轮审查</h3><span>{lastResponse.risk_flags.length} 项提醒</span></div>
              <div className="review-list">
                {lastResponse.risk_flags.map((flag) => <div className="review-item" key={flag}><span>!</span><p>{flag}</p></div>)}
              </div>
              <button className="secondary-inline-button" type="button">查看完整审查记录 <span>→</span></button>
            </section>
          </div>
        )}
      </aside>

      {!rightPaneVisible && (
        <button className="restore-output-button" type="button" title="显示右侧输出面板" onClick={() => setRightPaneVisible(true)}>
          ← <span>显示输出</span>
        </button>
      )}

      {selectedDocument && (
        <div className="workspace-drawer-backdrop" role="presentation" onClick={() => setSelectedDocument(null)}>
          <section className="workspace-drawer document-drawer" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="workspace-drawer-header">
              <div>
                <span className="chat-kicker">项目文档</span>
                <h2>{selectedDocument.document.title}</h2>
                <small>版本 {selectedDocument.version?.version ?? selectedDocument.document.current_version} · {selectedDocument.document.format}</small>
              </div>
              <button className="header-icon-button" type="button" title="关闭" onClick={() => setSelectedDocument(null)}>×</button>
            </div>
            <div className="document-content">
              {selectedDocument.version?.content ?? "正在读取文档内容..."}
            </div>
            <div className="document-meta">
              <span>项目隔离：{selectedDocument.document.project_id}</span>
              <span>SHA256：{selectedDocument.document.current_sha256.slice(0, 12)}...</span>
            </div>
          </section>
        </div>
      )}

      {selectedCitation && (
        <div className="workspace-drawer-backdrop" role="presentation" onClick={() => setSelectedCitation(null)}>
          <section className="workspace-drawer citation-drawer-new" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="workspace-drawer-header">
              <div>
                <span className="chat-kicker">检索证据</span>
                <h2>{selectedCitation.paper_title}</h2>
              </div>
              <button className="header-icon-button" type="button" title="关闭" onClick={() => setSelectedCitation(null)}>×</button>
            </div>
            <blockquote>{selectedCitation.excerpt}</blockquote>
            <dl className="citation-meta-list">
              <div><dt>来源文件</dt><dd>{selectedCitation.source_filename}</dd></div>
              <div><dt>Chunk</dt><dd>{selectedCitation.canonical_chunk_id}</dd></div>
              <div><dt>论文标识</dt><dd>{selectedCitation.canonical_paper_id}</dd></div>
              <div><dt>DOI</dt><dd>{selectedCitation.normalized_doi ?? "未提供"}</dd></div>
            </dl>
            <p className="drawer-note">这条证据来自本轮问答返回的检索结果。正式模式下还需要满足来源定位和核验条件。</p>
          </section>
        </div>
      )}

      {!auth && (
        <div className="login-overlay">
          <div className="login-card">
            <div className="research-logo large">S</div>
            <span className="chat-kicker">STEM-SCI</span>
            <h2>登录你的科研工作台</h2>
            <p>登录后可以保存项目、对话、论文和长期研究记忆。</p>
            <label>邮箱或用户名<input value={loginValue} onChange={(event) => setLoginValue(event.target.value)} placeholder="researcher" /></label>
            <label>密码<input type="password" value={passwordValue} onChange={(event) => setPasswordValue(event.target.value)} placeholder="••••••••" /></label>
            <button className="login-submit" type="button" disabled={authBusy} onClick={() => void signIn()}>{authBusy ? "正在登录..." : "登录并进入工作台"}</button>
            {authError && <p className="login-error">{authError}</p>}
            {demoMode && <small className="login-demo-note">当前为演示模式，可先直接浏览界面和示例证据。</small>}
          </div>
        </div>
      )}
    </div>
  );
}
