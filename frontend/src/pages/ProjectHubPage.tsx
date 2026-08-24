import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  authApi,
  readStoredAuth,
  type ApiConversationSummary,
  type ApiProjectDocument,
  type ApiResearchProject,
  type AuthState,
  type UserProfile,
} from "../api/auth";
import { workflowApi, type RuntimeStatus, type WorkflowState } from "../api/workflow";
import { GateSummary } from "../components/GateSummary";
import { TechnicalTrace } from "../components/TechnicalTrace";
import { demoCorpus, demoRuntime, demoWorkflowState } from "../demo/data";
import { demoDocumentsByProject, demoProjects } from "../demo/projectHub";
import type { WorkspaceTab } from "../App";
import type { SharedCorpusSummary } from "../types/context";

type ProjectHubPageProps = {
  projectId: string;
  onOpenProject: (projectId: string) => void;
  onNavigate: (tab: WorkspaceTab) => void;
};

const formatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDate(value?: string | null) {
  if (!value) return "刚刚";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatter.format(date);
}

function statusTone(status: ApiResearchProject["status"]) {
  return status === "active" ? "status-ready" : "status-muted";
}

function roleTone(role: ApiResearchProject["role"]) {
  if (role === "owner") return "status-ready";
  if (role === "editor") return "status-review";
  return "status-muted";
}

function docTone(type: ApiProjectDocument["document_type"]) {
  if (type === "manuscript") return "status-ready";
  if (type === "dataset") return "status-review";
  if (type === "reference") return "status-muted";
  return "status-muted";
}

function docLabel(type: ApiProjectDocument["document_type"]) {
  if (type === "manuscript") return "正文";
  if (type === "reference") return "文献";
  if (type === "dataset") return "数据";
  if (type === "protocol") return "方案";
  return "笔记";
}

function createSampleProjects(corpus: SharedCorpusSummary | null): ApiResearchProject[] {
  const direction = corpus?.formal_evidence_ready
    ? "生成式 AI 分层支架与师范生 Python 物理建模"
    : "生成式 AI 分层支架与师范生 Python 物理建模";
  return demoProjects.map((project: ApiResearchProject, index: number) => ({
    ...project,
    title: index === 0 ? "生成式 AI 分层支架研究" : project.title,
    research_direction: index === 0 ? direction : project.research_direction,
  }));
}

export function ProjectHubPage({ projectId, onOpenProject, onNavigate }: ProjectHubPageProps) {
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
  const [auth, setAuth] = useState<AuthState | null>(() => readStoredAuth());
  const [user, setUser] = useState<UserProfile | null>(auth?.user ?? null);
  const [projects, setProjects] = useState<ApiResearchProject[]>(demoMode ? createSampleProjects(demoCorpus) : []);
  const [documentsByProject, setDocumentsByProject] = useState<Record<string, ApiProjectDocument[]>>(demoDocumentsByProject);
  const [conversationsByProject, setConversationsByProject] = useState<Record<string, ApiConversationSummary[]>>({});
  const [workflowByProject, setWorkflowByProject] = useState<Record<string, WorkflowState | null>>({
    [projectId]: demoWorkflowState,
  });
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(demoMode ? demoRuntime : null);
  const [corpus, setCorpus] = useState<SharedCorpusSummary | null>(demoMode ? demoCorpus : null);
  const [selectedId, setSelectedId] = useState(projectId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setSelectedId(projectId);
  }, [projectId]);

  useEffect(() => {
    const stored = readStoredAuth();
    if (stored) setAuth(stored);
    const token = stored?.access_token ?? "";
    let mounted = true;

    async function load() {
      if (!token) {
        if (demoMode) {
          setUser(stored?.user ?? { ...demoUser });
          setProjects(createSampleProjects(demoCorpus));
          setDocumentsByProject(demoDocumentsByProject);
          setConversationsByProject(demoConversationsByProject);
          setWorkflowByProject({ [projectId]: demoWorkflowState });
          setRuntime(demoRuntime);
          setCorpus(demoCorpus);
        }
        return;
      }

      try {
        const [profile, projectList, corpora, runtimeState] = await Promise.all([
          authApi.me(token),
          authApi.listProjects(token),
          api.listSharedCorpora(),
          workflowApi.getRuntime(),
        ]);
        if (!mounted) return;
        setUser(profile);
        setProjects(projectList.length ? projectList : createSampleProjects(corpora[0] ?? null));
        setRuntime(runtimeState);
        setCorpus(corpora.find((item) => item.corpus_id === "physics_stem_v1") ?? corpora[0] ?? null);

        const docsEntries = await Promise.all(
          projectList.map(async (project) => [project.project_id, await authApi.listDocuments(token, project.project_id)] as const),
        );
        const conversationEntries = await Promise.all(
          projectList.map(async (project) => {
            try {
              const conversations = await authApi.listConversations(token, project.project_id);
              return [project.project_id, conversations] as const;
            } catch {
              return [project.project_id, []] as const;
            }
          }),
        );
        const workflowEntries = await Promise.all(
          projectList.map(async (project) => {
            try {
              return [project.project_id, await workflowApi.getProject(project.project_id)] as const;
            } catch {
              return [project.project_id, null] as const;
            }
          }),
        );

        if (!mounted) return;
        setDocumentsByProject(Object.fromEntries(docsEntries));
        setConversationsByProject(Object.fromEntries(conversationEntries));
        setWorkflowByProject(Object.fromEntries(workflowEntries));
      } catch {
        if (!mounted) return;
        if (demoMode) {
          setUser(stored?.user ?? { ...demoUser });
          setProjects(createSampleProjects(demoCorpus));
          setDocumentsByProject(demoDocumentsByProject);
          setConversationsByProject(demoConversationsByProject);
          setWorkflowByProject({ [projectId]: demoWorkflowState });
          setRuntime(demoRuntime);
          setCorpus(demoCorpus);
        } else {
          setError("项目数据暂时无法读取");
        }
      }
    }

    void load();
    return () => {
      mounted = false;
    };
  }, [demoMode, projectId]);

  useEffect(() => {
    const token = auth?.access_token ?? "";
    if (!token || !selectedId) return;
    let mounted = true;

    async function loadSelected() {
      try {
        const [workflowState, docs, conversations] = await Promise.all([
          workflowApi.getProject(selectedId),
          authApi.listDocuments(token, selectedId),
          authApi.listConversations(token, selectedId),
        ]);
        if (!mounted) return;
        setWorkflowByProject((current) => ({ ...current, [selectedId]: workflowState }));
        setDocumentsByProject((current) => ({ ...current, [selectedId]: docs }));
        setConversationsByProject((current) => ({ ...current, [selectedId]: conversations }));
      } catch {
        if (!mounted || !demoMode) return;
        setWorkflowByProject((current) => ({ ...current, [selectedId]: demoWorkflowState }));
        setDocumentsByProject((current) => ({ ...current, [selectedId]: demoDocumentsByProject[selectedId] ?? [] }));
        setConversationsByProject((current) => ({ ...current, [selectedId]: demoConversationsByProject[selectedId] ?? [] }));
      }
    }

    void loadSelected();
    return () => {
      mounted = false;
    };
  }, [auth?.access_token, demoMode, selectedId]);

  const activeProject = useMemo(
    () => projects.find((item) => item.project_id === selectedId) ?? projects[0] ?? null,
    [projects, selectedId],
  );
  const activeWorkflow = workflowByProject[selectedId] ?? null;
  const activeDocuments = documentsByProject[selectedId] ?? [];
  const activeConversations = conversationsByProject[selectedId] ?? [];
  const activeConversation = activeConversations[0] ?? demoConversationsByProject[selectedId]?.[0] ?? null;
  const stageTone = activeWorkflow?.current_stage === "WAITING_HUMAN" ? "status-review" : "status-ready";
  const projectCount = projects.length;
  const documentCount = Object.values(documentsByProject).flat().length;
  const conversationCount = Object.values(conversationsByProject).flat().length;

  return (
    <div className="workspace hub-page">
      <header className="page-hero">
        <div className="hero-copy">
          <span className="eyebrow">PROJECT HUB</span>
          <h1>我的研究项目</h1>
          <p>
            项目、正文、对话、Agent 和审计放在同一页，先看全局，再进入具体写作和协作。
          </p>
        </div>
        <div className="hero-actions">
          <button className="secondary-action" onClick={() => onNavigate("editor")} type="button">
            打开论文编辑
          </button>
          <button className="primary-action" onClick={() => onNavigate("workspace")} type="button">
            进入工作台
          </button>
        </div>
      </header>

      <section className="metric-grid">
        <article className="metric-card">
          <span>项目数量</span>
          <strong>{projectCount}</strong>
          <small>当前可见的研究项目</small>
        </article>
        <article className="metric-card">
          <span>文档总数</span>
          <strong>{documentCount}</strong>
          <small>草稿、参考和数据文件</small>
        </article>
        <article className="metric-card">
          <span>会话数量</span>
          <strong>{conversationCount}</strong>
          <small>最近对话与历史记录</small>
        </article>
        <article className="metric-card">
          <span>语料状态</span>
          <strong>{corpus?.discovery_ready ? "可检索" : "待就绪"}</strong>
          <small>{corpus?.formal_evidence_ready ? "正式证据可用" : "发现模式可用"}</small>
        </article>
      </section>

      <section className="hub-layout">
        <aside className="hub-rail">
          <div className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">PROJECT LIST</span>
                <h2>项目切换</h2>
              </div>
            </div>
            <div className="project-grid compact-project-grid">
              {projects.map((project) => {
                const isSelected = project.project_id === selectedId;
                const docs = documentsByProject[project.project_id] ?? [];
                const conversations = conversationsByProject[project.project_id] ?? [];
                const workflow = workflowByProject[project.project_id] ?? null;
                const progress = project.status === "active" ? 82 : 54;
                return (
                  <button
                    className={`project-card ${isSelected ? "project-selected" : ""}`}
                    key={project.project_id}
                    onClick={() => {
                      setSelectedId(project.project_id);
                      onOpenProject(project.project_id);
                    }}
                    type="button"
                  >
                    <div className="card-topline">
                      <span className={`status-badge ${statusTone(project.status)}`}>{project.status === "active" ? "进行中" : "已归档"}</span>
                      <small>{formatDate(project.updated_at)}</small>
                    </div>
                    <h2>{project.title}</h2>
                    <p>{project.research_direction}</p>
                    <dl>
                      <div>
                        <dt>角色</dt>
                        <dd>
                          <span className={`status-badge ${roleTone(project.role)}`}>{project.role === "owner" ? "负责人" : project.role === "editor" ? "协作" : "只读"}</span>
                        </dd>
                      </div>
                      <div>
                        <dt>文档</dt>
                        <dd>{docs.length} 个</dd>
                      </div>
                      <div>
                        <dt>会话</dt>
                        <dd>{conversations.length} 条</dd>
                      </div>
                      <div>
                        <dt>阶段</dt>
                        <dd>{workflow?.current_stage ?? "WAITING_HUMAN"}</dd>
                      </div>
                    </dl>
                    <div className="card-progress">
                      <i style={{ width: `${progress}%` }} />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>

        <main className="hub-main">
          <section className="panel project-hero-card">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">ACTIVE PROJECT</span>
                <h2>{activeProject?.title ?? "暂无项目"}</h2>
              </div>
              <div className="hero-chip-row">
                <span className={`status-badge ${stageTone}`}>{activeWorkflow?.current_stage ?? "WAITING_HUMAN"}</span>
                <span className={`status-badge ${statusTone(activeProject?.status ?? "active")}`}>{activeProject?.status ?? "active"}</span>
              </div>
            </div>
            <p className="hero-copy-line">{activeProject?.research_direction ?? "请选择一个项目查看概览。"}</p>
            <p className="muted">{activeProject?.abstract ?? "项目摘要会在这里展开，连接文档、对话和后续工作流。"}</p>
            <div className="button-row">
              <button className="primary-action" onClick={() => onNavigate("workspace")} type="button">
                打开工作台
              </button>
              <button className="secondary-action" onClick={() => onNavigate("agent")} type="button">
                查看 Agent / Codex
              </button>
            </div>
          </section>

          <section className="panel overview-grid">
            <div className="overview-card">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">DOCUMENTS</span>
                  <h3>项目文档</h3>
                </div>
                <span className="result-count">{activeDocuments.length} 个</span>
              </div>
              <div className="document-list">
                {activeDocuments.length ? (
                  activeDocuments.slice(0, 5).map((document) => (
                    <button
                      className="document-row"
                      key={document.document_id}
                      onClick={() => onNavigate("workspace")}
                      type="button"
                    >
                      <div className="card-topline">
                        <strong>{document.title}</strong>
                        <span className={`status-badge ${docTone(document.document_type)}`}>{docLabel(document.document_type)}</span>
                      </div>
                      <span>
                        {document.format} · v{document.current_version} · {document.size_bytes} bytes
                      </span>
                    </button>
                  ))
                ) : (
                  <div className="empty-state small-empty">
                    <strong>没有文档</strong>
                    <span>文档列表会从项目接口加载。</span>
                  </div>
                )}
              </div>
            </div>

            <div className="overview-card">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">CONVERSATIONS</span>
                  <h3>最近会话</h3>
                </div>
                <span className="result-count">{activeConversations.length} 条</span>
              </div>
              {activeConversation ? (
                <div className="conversation-preview">
                  <strong>{activeConversation.title}</strong>
                  <p>{activeConversation.last_question}</p>
                  <small>{activeConversation.last_answer_preview}</small>
                </div>
              ) : (
                <div className="empty-state small-empty">
                  <strong>暂无会话</strong>
                  <span>提问后，这里会显示最近的对话摘要。</span>
                </div>
              )}
            </div>

            <div className="overview-card">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">WORKFLOW</span>
                  <h3>当前阶段</h3>
                </div>
                <span className={`status-badge ${stageTone}`}>{activeWorkflow?.current_stage ?? "WAITING_HUMAN"}</span>
              </div>
              <GateSummary
                gates={[
                  {
                    kind: "human",
                    label: "Human Gate",
                    tone: activeWorkflow?.pending_approval_ref ? "pending" : "approved",
                    detail: activeWorkflow?.pending_approval_ref ? "存在待审批任务" : "当前没有待审批任务",
                  },
                  {
                    kind: "evidence",
                    label: "Evidence Gate",
                    tone: corpus?.formal_evidence_ready ? "verified" : "pending",
                    detail: corpus?.formal_evidence_ready ? "正式证据链可用" : "先使用发现模式",
                  },
                ]}
              />
              <button className="secondary-action full-width" onClick={() => onNavigate("audit")} type="button">
                打开审计视图
              </button>
            </div>
          </section>
        </main>

        <aside className="hub-side">
          <section className="panel side-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">ACCOUNT</span>
                <h3>身份</h3>
              </div>
              <span className={`status-badge ${auth ? "status-ready" : "status-review"}`}>{auth ? "已登录" : "演示"}</span>
            </div>
            <div className="summary-list">
              <div>
                <span>用户</span>
                <strong>{user?.display_name ?? user?.username ?? "Demo Researcher"}</strong>
              </div>
              <div>
                <span>邮箱</span>
                <strong>{user?.email ?? "demo@stem-sci.local"}</strong>
              </div>
              <div>
                <span>项目</span>
                <strong>{activeProject?.project_id ?? selectedId}</strong>
              </div>
            </div>
          </section>

          <section className="panel side-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">RUNTIME</span>
                <h3>环境</h3>
              </div>
            </div>
            <div className="summary-list">
              <div>
                <span>语料</span>
                <strong>{corpus?.paper_count ?? "—"} 篇</strong>
              </div>
              <div>
                <span>切片</span>
                <strong>{corpus?.vector_chunk_count ?? "—"} 条</strong>
              </div>
              <div>
                <span>Codex</span>
                <strong>{runtime?.codex_available ? "可用" : runtime?.codex_reason ?? "未启用"}</strong>
              </div>
            </div>
          </section>

          <section className="panel side-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">TRACE</span>
                <h3>工作流快照</h3>
              </div>
            </div>
            <TechnicalTrace>
              <pre>{JSON.stringify(activeWorkflow ?? demoWorkflowState, null, 2)}</pre>
            </TechnicalTrace>
          </section>
        </aside>
      </section>

      {error && <p className="error-text">{error}</p>}
    </div>
  );
}

const demoUser: UserProfile = {
  user_id: "user-demo",
  username: "demo",
  email: "demo@stem-sci.local",
  display_name: "Demo Researcher",
  created_at: "2026-08-23T08:00:00Z",
};

const demoConversationsByProject: Record<string, ApiConversationSummary[]> = {
  "physics-ai-demo": [
    {
      conversation_id: "conversation-demo-001",
      project_id: "physics-ai-demo",
      title: "研究设计草案",
      last_question: "如何设计师范生 Python 物理建模研究？",
      last_answer_preview: "建议采用前测、后测与迁移测验相结合的准实验设计。",
      turn_count: 4,
      created_at: "2026-08-23T08:10:00Z",
      updated_at: "2026-08-23T08:30:00Z",
    },
  ],
  "stem-design-lab": [
    {
      conversation_id: "conversation-demo-002",
      project_id: "stem-design-lab",
      title: "文献筛选",
      last_question: "哪些文献可以支持设计论证？",
      last_answer_preview: "已筛选出三篇高相关论文，可作为设计参考。",
      turn_count: 2,
      created_at: "2026-08-22T09:15:00Z",
      updated_at: "2026-08-22T09:42:00Z",
    },
  ],
  "assessment-workbench": [],
};
