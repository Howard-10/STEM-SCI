import { useEffect, useMemo, useRef, useState } from "react";
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
<<<<<<< HEAD
import { demoBundle, demoCorpus, demoQAResponse, demoRuntime } from "./demo/data";
import { demoDocumentContents, demoDocumentsByProject, demoProjects } from "./demo/projectHub";

type WorkspaceView = "knowledge" | "codex" | "audit";
=======
import {
  workflowApi,
  type ControllerWorkflowState,
  type DataPipelineState,
  type RuntimeStatus,
} from "./api/workflow";
import { demoBundle, demoCorpus, demoQAResponse, demoRuntime } from "./demo/data";
import { demoDocumentContents, demoDocumentsByProject, demoProjects } from "./demo/projectHub";

type WorkspaceView = "knowledge" | "codex" | "analysis" | "audit";
>>>>>>> origin/main
export type WorkspaceTab = "home" | "workspace" | "editor" | "agent" | "audit";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: QAAnswerResponse;
  attachments?: ChatAttachment[];
};

type ChatAttachment = {
  id: string;
  name: string;
  kind: "PDF" | "WORD" | "IMAGE";
  sizeLabel: string;
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
<<<<<<< HEAD
  ["01", "导师规划", "界定研究问题与范围", "已完成"],
  ["02", "证据审查", "筛选、核验和组织文献证据", "进行中"],
  ["03", "研究设计", "形成可审批的研究方案", "待启动"],
  ["04", "数据分析", "编译分析计划与结果检查", "待启动"],
  ["05", "论文写作", "生成基于证据的写作草案", "待启动"],
  ["06", "独立审查", "检查风险、引用和方法", "待启动"],
];
=======
  ["01", "mentor_planning", "导师规划", "界定研究问题与范围"],
  ["02", "evidence_review", "证据审查", "筛选、核验和组织文献证据"],
  ["03", "research_design", "研究设计", "形成可审批的研究方案"],
  ["04", "data_analysis", "数据分析", "编译分析计划与结果检查"],
  ["05", "paper_writing", "论文写作", "生成基于证据的写作草案"],
  ["06", "independent_review", "独立审查", "检查风险、引用和方法"],
] as const;

const completedAgentsByStage: Record<string, string[]> = {
  INTAKE: [],
  SCOPED: ["mentor_planning"],
  EVIDENCE_READY: ["mentor_planning", "evidence_review"],
  STUDY_PROTOCOL_APPROVED: ["mentor_planning", "evidence_review", "research_design"],
  DATA_READY: ["mentor_planning", "evidence_review", "research_design"],
  ANALYZED: ["mentor_planning", "evidence_review", "research_design", "data_analysis"],
  DRAFTED: ["mentor_planning", "evidence_review", "research_design", "data_analysis", "paper_writing"],
  VERIFIED: ["mentor_planning", "evidence_review", "research_design", "data_analysis", "paper_writing", "independent_review"],
  RELEASED: ["mentor_planning", "evidence_review", "research_design", "data_analysis", "paper_writing", "independent_review"],
};

function agentStatus(snapshot: ControllerWorkflowState | null, agentId: string): string {
  if (!snapshot) return "读取中";
  const routeAgent = snapshot.last_route_decision?.selected_route;
  if (snapshot.current_stage === "WAITING_HUMAN" && routeAgent === agentId) {
    return "等待审批";
  }
  if (snapshot.current_stage === "REWORK" && snapshot.research_state?.rework_target_agent === agentId) {
    return "待返工";
  }
  if (completedAgentsByStage[snapshot.current_stage]?.includes(agentId)) {
    return "已完成";
  }
  return "待启动";
}
>>>>>>> origin/main

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
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [projectForm, setProjectForm] = useState({
    project_id: "",
    title: "",
    research_direction: "",
    abstract: "",
  });
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [documents, setDocuments] = useState<ApiProjectDocument[]>([]);
  const [conversations, setConversations] = useState<ApiConversationSummary[]>([]);
  const [documentsBusy, setDocumentsBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const uploadInputRef = useRef<HTMLInputElement>(null);
<<<<<<< HEAD
=======
  const analysisInputRef = useRef<HTMLInputElement>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus>(demoRuntime);
  const [workflowSnapshot, setWorkflowSnapshot] = useState<ControllerWorkflowState | null>(null);
  const [analysisState, setAnalysisState] = useState<DataPipelineState | null>(null);
  const [analysisStage, setAnalysisStage] = useState("STUDY_PROTOCOL_APPROVED");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
>>>>>>> origin/main
  const chatAttachmentInputRef = useRef<HTMLInputElement>(null);
  const [chatAttachments, setChatAttachments] = useState<ChatAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<SelectedDocument | null>(null);
  const [documentTitleDraft, setDocumentTitleDraft] = useState("");
  const [documentContentDraft, setDocumentContentDraft] = useState("");
  const [documentEditBusy, setDocumentEditBusy] = useState(false);
  const [documentEditError, setDocumentEditError] = useState("");
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation | null>(null);
  const [rightPaneVisible, setRightPaneVisible] = useState(true);
  const [paneWidths, setPaneWidths] = useState<PaneWidths>({ sidebar: 246, output: 374 });
  const [draggingPane, setDraggingPane] = useState<"sidebar" | "output" | null>(null);

  const activeProject = useMemo(
    () => projects.find((project) => project.project_id === projectId) ?? projects[0] ?? null,
    [projectId, projects],
  );
  const activeDocuments = auth?.access_token
    ? documents
    : demoDocumentsByProject[projectId] ?? demoDocumentsByProject[demoProjectId] ?? [];
  const draftDocuments = activeDocuments.filter((document) => document.document_type === "manuscript");
  const projectPapers = activeDocuments.filter((document) => document.document_type !== "manuscript");
  const citations = lastResponse?.citations ?? demoQAResponse.citations;

  useEffect(() => {
    if (!auth?.access_token) {
      setProjects(demoProjects);
      return;
    }
    setProjects([]);
    let mounted = true;
    void authApi.listProjects(auth.access_token).then((next) => {
      if (!mounted) return;
      setProjects(next);
      if (next.length && !next.some((project) => project.project_id === projectId)) {
        setProjectId(next[0].project_id);
      } else if (!next.length) {
        setProjectId("");
      }
    }).catch(() => {
      if (mounted) {
        setProjects([]);
        setProjectId("");
      }
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
      setDocuments([]);
      setConversations([]);
    }).finally(() => {
      if (mounted) setDocumentsBusy(false);
    });

    return () => {
      mounted = false;
    };
  }, [auth?.access_token, projectId]);

  useEffect(() => {
<<<<<<< HEAD
=======
    let mounted = true;
    setAnalysisError("");
    void Promise.all([
      workflowApi.getRuntime(),
      workflowApi.getControllerProject(projectId),
    ]).then(([runtime, controllerState]) => {
      if (!mounted) return;
      setRuntimeStatus(runtime);
      setWorkflowSnapshot(controllerState);
      setAnalysisStage(controllerState.current_stage);
      setAnalysisState(controllerState.data_pipeline);
    }).catch((error) => {
      if (!mounted) return;
      setAnalysisError(error instanceof Error ? error.message : "无法读取数据分析状态");
    });
    return () => {
      mounted = false;
    };
  }, [projectId]);

  useEffect(() => {
>>>>>>> origin/main
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

  const selectChatFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const nextAttachments: ChatAttachment[] = [];
    for (const file of Array.from(files)) {
      const lowerName = file.name.toLowerCase();
      const kind = lowerName.endsWith(".pdf")
        ? "PDF"
        : lowerName.endsWith(".doc") || lowerName.endsWith(".docx")
          ? "WORD"
          : file.type.startsWith("image/")
            ? "IMAGE"
            : null;
      if (!kind) {
        setAttachmentError("附件仅支持 PDF、Word 和图片");
        continue;
      }
      if (file.size > 20 * 1024 * 1024) {
        setAttachmentError("单个附件不能超过 20 MB");
        continue;
      }
      nextAttachments.push({
        id: `${file.name}-${file.lastModified}-${Math.random().toString(16).slice(2)}`,
        name: file.name,
        kind,
        sizeLabel: file.size >= 1024 * 1024
          ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
          : `${Math.max(1, Math.round(file.size / 1024))} KB`,
      });
    }
    setChatAttachments((current) => [...current, ...nextAttachments].slice(0, 5));
    if (nextAttachments.length && nextAttachments.length + chatAttachments.length <= 5) {
      setAttachmentError("");
    }
    if (chatAttachmentInputRef.current) chatAttachmentInputRef.current.value = "";
  };

  const removeChatAttachment = (attachmentId: string) => {
    setChatAttachments((current) => current.filter((attachment) => attachment.id !== attachmentId));
    setAttachmentError("");
  };

  const submitQuestion = async (value = question) => {
    const trimmed = value.trim();
    if (!trimmed || busy || !activeProject) return;
    setMessages((current) => [...current, {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      attachments: chatAttachments,
    }]);
    setQuestion("");
    setChatAttachments([]);
    setAttachmentError("");
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

  const openCreateProject = () => {
    setProjectForm({
      project_id: "",
      title: "",
      research_direction: "",
      abstract: "",
    });
    setProjectError("");
    setCreateProjectOpen(true);
  };

  const createProject = async () => {
    if (!auth?.access_token) {
      setProjectError("请先登录后再创建项目");
      return;
    }
    if (!projectForm.title.trim() || !projectForm.research_direction.trim()) {
      setProjectError("请填写项目名称和研究方向");
      return;
    }
    setProjectBusy(true);
    setProjectError("");
    try {
      const created = await authApi.createProject(auth.access_token, {
        project_id: projectForm.project_id.trim() || undefined,
        title: projectForm.title.trim(),
        research_direction: projectForm.research_direction.trim(),
        abstract: projectForm.abstract.trim() || null,
      });
      setProjects((current) => [created, ...current.filter((item) => item.project_id !== created.project_id)]);
      setProjectId(created.project_id);
      setDocuments([]);
      setConversations([]);
      setConversationId(undefined);
      setMessages([makeWelcome(created.title)]);
      setLastResponse(demoQAResponse);
      setCreateProjectOpen(false);
    } catch (error) {
      setProjectError(error instanceof Error ? error.message : "创建项目失败");
    } finally {
      setProjectBusy(false);
    }
  };

  const uploadDocument = async (file: File) => {
    if (!auth?.access_token || !projectId) {
      setUploadError("请先登录并选择一个项目");
      return;
    }
    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith(".pdf") && !lowerName.endsWith(".docx")) {
      setUploadError("目前支持 PDF 和 DOCX 文件");
      return;
    }
    setUploadBusy(true);
    setUploadError("");
    try {
      const created = await authApi.uploadDocument(auth.access_token, projectId, file);
      setDocuments((current) => [created, ...current.filter((item) => item.document_id !== created.document_id)]);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传文档失败");
    } finally {
      setUploadBusy(false);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
    }
  };

<<<<<<< HEAD
=======
  const refreshAnalysisState = async () => {
    if (!projectId) return;
    const controllerState = await workflowApi.getControllerProject(projectId);
    setWorkflowSnapshot(controllerState);
    setAnalysisStage(controllerState.current_stage);
    setAnalysisState(controllerState.data_pipeline);
  };

  const uploadAnalysisDataset = async (file: File) => {
    if (!projectId) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setAnalysisError("数据分析目前只接受 CSV 文件，避免把未结构化文档直接送入统计执行链。");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setAnalysisError("CSV 文件不能超过 50 MB。");
      return;
    }
    setAnalysisBusy(true);
    setAnalysisError("");
    try {
      const next = await workflowApi.uploadRawCsv(projectId, file);
      setAnalysisState(next);
      setAnalysisStage(next.stage);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "实验数据上传失败");
    } finally {
      setAnalysisBusy(false);
      if (analysisInputRef.current) analysisInputRef.current.value = "";
    }
  };

  const decideAnalysisStep = async (decision: "approved" | "rejected") => {
    if (!projectId || !analysisState?.pending_approval) return;
    setAnalysisBusy(true);
    setAnalysisError("");
    try {
      const decidedBy = auth?.user.username ?? "researcher";
      const next = await workflowApi.decideDataPipeline(projectId, decision, decidedBy);
      setAnalysisState(next);
      setAnalysisStage(next.stage);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "数据分析审批失败");
    } finally {
      setAnalysisBusy(false);
    }
  };

  const runAnalysisAgent = async () => {
    if (!projectId) return;
    setAnalysisBusy(true);
    setAnalysisError("");
    try {
      await workflowApi.runPublicNext(projectId);
      await refreshAnalysisState();
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "数据分析 Agent 暂时无法启动");
    } finally {
      setAnalysisBusy(false);
    }
  };

>>>>>>> origin/main
  const createDraft = async () => {
    if (!auth?.access_token || !projectId) {
      setUploadError("请先登录并选择一个项目");
      return;
    }
    setDocumentEditBusy(true);
    setDocumentEditError("");
    try {
      const created = await authApi.createDocument(auth.access_token, projectId, {
        title: "论文草稿",
        document_type: "manuscript",
        format: "markdown",
        content: "# 论文草稿\n\n## 研究问题\n\n## 研究设计\n\n## 结果与讨论\n",
        change_note: "创建论文草稿",
      });
      setDocuments((current) => [
        created,
        ...current.filter((item) => item.document_id !== created.document_id),
      ]);
      await openDocument(created);
    } catch (error) {
      setDocumentEditError(error instanceof Error ? error.message : "创建论文草稿失败");
    } finally {
      setDocumentEditBusy(false);
    }
  };

  const openDocument = async (document: ApiProjectDocument) => {
    setSelectedDocument({ document, version: null });
    setDocumentTitleDraft(document.title);
    setDocumentContentDraft("");
    setDocumentEditError("");
    if (!auth?.access_token) {
      const content = demoDocumentContents[document.document_id] ?? "演示文档暂无正文。";
      setSelectedDocument({
        document,
        version: {
          document_id: document.document_id,
          project_id: document.project_id,
          version: document.current_version,
          format: document.format,
          content,
          sha256: document.current_sha256,
          size_bytes: document.size_bytes,
          storage_ref: `demo://${document.document_id}`,
          change_note: null,
          created_by: document.created_by,
          created_at: document.updated_at,
        },
      });
      setDocumentContentDraft(content);
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
      setDocumentTitleDraft(document.title);
      setDocumentContentDraft(version.content);
    } catch {
      setSelectedDocument({ document, version: null });
      setDocumentEditError("无法读取文档正文");
    }
  };

  const saveSelectedDocument = async () => {
    if (!auth?.access_token || !selectedDocument?.version) return;
    setDocumentEditBusy(true);
    setDocumentEditError("");
    try {
      let nextDocument = selectedDocument.document;
      let nextVersion = selectedDocument.version;
      const nextTitle = documentTitleDraft.trim();
      if (nextTitle && nextTitle !== nextDocument.title) {
        nextDocument = await authApi.updateDocument(
          auth.access_token,
          projectId,
          nextDocument.document_id,
          { title: nextTitle },
        );
      }
      if (documentContentDraft !== selectedDocument.version.content) {
        nextVersion = await authApi.saveDocumentVersion(
          auth.access_token,
          projectId,
          nextDocument.document_id,
          documentContentDraft,
          "在平台编辑论文草稿",
        );
        nextDocument = {
          ...nextDocument,
          current_version: nextVersion.version,
          current_sha256: nextVersion.sha256,
          size_bytes: nextVersion.size_bytes,
          updated_by: nextVersion.created_by,
          updated_at: nextVersion.created_at,
        };
      }
      setDocuments((current) =>
        current.map((item) => item.document_id === nextDocument.document_id ? nextDocument : item),
      );
      setSelectedDocument({ document: nextDocument, version: nextVersion });
      setDocumentTitleDraft(nextDocument.title);
      setDocumentContentDraft(nextVersion.content);
    } catch (error) {
      setDocumentEditError(error instanceof Error ? error.message : "保存论文草稿失败");
    } finally {
      setDocumentEditBusy(false);
    }
  };

  const deleteSelectedDocument = async () => {
    if (!auth?.access_token || !selectedDocument) return;
    if (selectedDocument.document.document_type !== "manuscript") return;
    if (!window.confirm(`确定删除“${selectedDocument.document.title}”吗？`)) return;
    setDocumentEditBusy(true);
    setDocumentEditError("");
    try {
      await authApi.deleteDocument(
        auth.access_token,
        projectId,
        selectedDocument.document.document_id,
      );
      setDocuments((current) =>
        current.filter((item) => item.document_id !== selectedDocument.document.document_id),
      );
      setSelectedDocument(null);
    } catch (error) {
      setDocumentEditError(error instanceof Error ? error.message : "删除论文草稿失败");
    } finally {
      setDocumentEditBusy(false);
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
<<<<<<< HEAD
=======
          <button className={view === "analysis" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => setView("analysis")}>
            <span className="ui-icon">◫</span>
            数据分析
          </button>
>>>>>>> origin/main
          <button className={view === "audit" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => setView("audit")}>
            <span className="ui-icon">✓</span>
            数据审查
          </button>
        </div>

        <div className="sidebar-section project-section">
          <div className="sidebar-section-heading">
            <span className="sidebar-label">项目</span>
            <button className="plain-icon-button" type="button" title="新建项目" onClick={openCreateProject}>＋</button>
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
                {message.attachments && message.attachments.length > 0 && (
                  <div className="message-attachments" aria-label="本条消息的附件">
                    {message.attachments.map((attachment) => (
                      <span className="message-attachment" key={attachment.id}>
                        <strong>{attachment.kind}</strong>
                        <span>{attachment.name}</span>
                        <small>{attachment.sizeLabel}</small>
                      </span>
                    ))}
                  </div>
                )}
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
            {chatAttachments.length > 0 && (
              <div className="attachment-preview" aria-label="待发送附件">
                {chatAttachments.map((attachment) => (
                  <div className="attachment-chip" key={attachment.id}>
                    <span className="attachment-chip-kind">{attachment.kind}</span>
                    <span className="attachment-chip-copy">
                      <strong>{attachment.name}</strong>
                      <small>{attachment.sizeLabel}</small>
                    </span>
                    <button
                      className="attachment-remove"
                      type="button"
                      title={`移除 ${attachment.name}`}
                      onClick={() => removeChatAttachment(attachment.id)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            {attachmentError && <p className="attachment-error">{attachmentError}</p>}
            <div className="composer-toolbar">
              <div className="composer-tools">
                <button
                  className="composer-tool composer-attach-tool"
                  type="button"
                  title="添加 PDF、Word 或图片"
                  onClick={() => chatAttachmentInputRef.current?.click()}
                >
                  ＋
                </button>
                <input
                  ref={chatAttachmentInputRef}
                  className="visually-hidden"
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*"
                  onChange={(event) => selectChatFiles(event.target.files)}
                />
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
<<<<<<< HEAD
            <h2>{view === "knowledge" ? "知识库" : view === "codex" ? "Codex 工作区" : "数据审查"}</h2>
=======
            <h2>{view === "knowledge" ? "知识库" : view === "codex" ? "Codex 工作区" : view === "analysis" ? "数据分析" : "数据审查"}</h2>
>>>>>>> origin/main
          </div>
          <button className="header-icon-button" type="button" title="隐藏右侧面板，进入双栏模式" onClick={() => setRightPaneVisible(false)}>→</button>
        </div>

        {view === "knowledge" && (
          <div className="output-content">
            <section className="output-section">
              <div className="output-section-heading">
                <h3>当前项目论文</h3>
                <div className="output-heading-actions">
                  <span>{documentsBusy ? "加载中..." : `${activeDocuments.length} 篇`}</span>
                  <button
                    className="upload-doc-button"
                    type="button"
                    title="上传 PDF 或 DOCX"
                    disabled={uploadBusy || !auth?.access_token || !projectId}
                    onClick={() => uploadInputRef.current?.click()}
                  >
                    {uploadBusy ? "上传中..." : "上传"}
                  </button>
                  <input
                    ref={uploadInputRef}
                    className="visually-hidden"
                    type="file"
                    accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void uploadDocument(file);
                    }}
                  />
                </div>
              </div>
              <div className="paper-list">
                {projectPapers.map((document) => (
                  <button className="paper-item" type="button" key={document.document_id} onClick={() => void openDocument(document)}>
                    <span className="paper-file-icon">{document.format.toUpperCase()}</span>
                    <span><strong>{document.title}</strong><small>版本 {document.current_version} · {document.document_type}</small></span>
                    <span className="row-arrow">›</span>
                  </button>
                ))}
                {!documentsBusy && !projectPapers.length && (
                  <div className="empty-documents">
                    <strong>还没有项目论文</strong>
                    <span>上传 PDF 或 DOCX 后，论文会出现在这里并可供对话检索。</span>
                  </div>
                )}
                {uploadError && <p className="upload-error">{uploadError}</p>}
              </div>
            </section>
            <section className="output-section draft-section">
              <div className="output-section-heading">
                <div>
                  <h3>论文草稿</h3>
                  <p className="section-subtitle">可直接编辑，保存后自动生成新版本</p>
                </div>
                <button
                  className="draft-create-button"
                  type="button"
                  disabled={documentEditBusy || !auth?.access_token || !projectId}
                  onClick={() => void createDraft()}
                >
                  ＋ 新建
                </button>
              </div>
              <div className="paper-list">
                {draftDocuments.map((document) => (
                  <button className="paper-item draft-paper-item" type="button" key={document.document_id} onClick={() => void openDocument(document)}>
                    <span className="paper-file-icon draft-file-icon">稿</span>
                    <span>
                      <strong>{document.title}</strong>
                      <small>版本 {document.current_version} · 可编辑</small>
                    </span>
                    <span className="row-arrow">›</span>
                  </button>
                ))}
                {!documentsBusy && !draftDocuments.length && (
                  <div className="empty-documents draft-empty">
                    <strong>还没有论文草稿</strong>
                    <span>创建草稿后，可以在平台内直接编辑、保存版本或删除。</span>
                  </div>
                )}
                {documentEditError && <p className="upload-error">{documentEditError}</p>}
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
<<<<<<< HEAD
              <button className="primary-inline-button" type="button">打开代码编辑器 <span>→</span></button>
=======
              <button
                className="primary-inline-button"
                type="button"
                onClick={() => {
                  setView("analysis");
                  setQuestion("请根据当前研究问题和已审批的分析计划生成 Python 分析代码草案，并说明每一步的统计目的。");
                }}
              >
                转到数据分析 <span>→</span>
              </button>
>>>>>>> origin/main
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>运行环境</h3><span className="review-tag">开发模式</span></div>
              <div className="runtime-list">
<<<<<<< HEAD
                <div><span>代码提供方</span><strong>{demoRuntime.coding_provider}</strong></div>
                <div><span>Codex CLI</span><strong>{demoRuntime.codex_available ? "可用" : "未配置"}</strong></div>
                <div><span>SPSS</span><strong>{demoRuntime.spss_available ? "可用" : "未配置"}</strong></div>
=======
                <div><span>代码提供方</span><strong>{runtimeStatus.coding_provider}</strong></div>
                <div><span>Codex CLI</span><strong>{runtimeStatus.codex_available ? "可用" : runtimeStatus.codex_reason ?? "未配置"}</strong></div>
                <div><span>SPSS</span><strong>{runtimeStatus.spss_available ? "可用" : runtimeStatus.spss_reason ?? "未配置"}</strong></div>
>>>>>>> origin/main
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>最近代码任务</h3><span>0</span></div>
              <div className="empty-output"><span className="empty-symbol">⌘</span><p>在对话中描述你的分析需求，Codex 会先生成代码草案。</p></div>
            </section>
          </div>
        )}

<<<<<<< HEAD
=======
        {view === "analysis" && (
          <div className="output-content">
            <section className="analysis-summary">
              <div className="analysis-summary-icon">◫</div>
              <div>
                <strong>实验数据进入受控分析链</strong>
                <p>上传 CSV 后先做数据审查，再逐步审批处理、冻结和执行。Codex 只生成候选代码，SPSS 未配置时不会伪装成已完成。</p>
              </div>
            </section>

            <section className="output-section">
              <div className="output-section-heading">
                <h3>当前链路</h3>
                <button
                  className="plain-action"
                  type="button"
                  disabled={analysisBusy || !projectId}
                  onClick={() => void refreshAnalysisState()}
                >
                  刷新
                </button>
              </div>
              <div className="analysis-stage">
                <div className={analysisStage === "STUDY_PROTOCOL_APPROVED" ? "analysis-stage-item active" : "analysis-stage-item"}>
                  <span>1</span><strong>研究方案</strong><small>{analysisStage === "STUDY_PROTOCOL_APPROVED" ? "等待启动分析 Agent" : "已完成或已进入数据阶段"}</small>
                </div>
                <div className={analysisState ? "analysis-stage-item active" : "analysis-stage-item"}>
                  <span>2</span><strong>数据管道</strong><small>{analysisState?.stage ?? "尚未建立分析计划"}</small>
                </div>
                <div className={analysisState?.statistical_result_card ? "analysis-stage-item active" : "analysis-stage-item"}>
                  <span>3</span><strong>结果验证</strong><small>{analysisState?.statistical_result_card ? "已有结果卡" : "等待受控执行"}</small>
                </div>
              </div>
              {!analysisState && (
                <div className="analysis-inline-note">
                  <strong>还没有 Controller 数据管道</strong>
                  <span>请先在研究流程中完成研究方案审批，再由数据分析 Agent 生成分析规格。当前页面不会绕过这一步直接执行代码。</span>
                  {analysisStage === "STUDY_PROTOCOL_APPROVED" && (
                    <button className="secondary-inline-button" type="button" disabled={analysisBusy} onClick={() => void runAnalysisAgent()}>
                      {analysisBusy ? "正在启动…" : "运行数据分析 Agent"}
                      <span>→</span>
                    </button>
                  )}
                </div>
              )}
            </section>

            {analysisState && (
              <>
                <section className="output-section">
                  <div className="output-section-heading">
                    <div>
                      <h3>实验数据</h3>
                      <p className="section-subtitle">只接受 CSV，原始文件会先经过确定性审查</p>
                    </div>
                    <div className="output-heading-actions">
                      <span className={analysisState.data_audit_report?.passed ? "ready-text" : ""}>
                        {analysisState.data_audit_report ? (analysisState.data_audit_report.passed ? "审查通过" : "需要修正") : "等待上传"}
                      </span>
                      <button
                        className="upload-doc-button"
                        type="button"
                        disabled={analysisBusy || analysisState.stage !== "WAITING_RAW_DATA"}
                        onClick={() => analysisInputRef.current?.click()}
                      >
                        {analysisBusy ? "处理中..." : "上传 CSV"}
                      </button>
                      <input
                        ref={analysisInputRef}
                        className="visually-hidden"
                        type="file"
                        accept=".csv,text/csv"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) void uploadAnalysisDataset(file);
                        }}
                      />
                    </div>
                  </div>
                  {analysisState.raw_dataset ? (
                    <div className="analysis-dataset-row">
                      <span className="paper-file-icon">CSV</span>
                      <div>
                        <strong>{String(analysisState.raw_dataset.dataset_id ?? "原始实验数据")}</strong>
                        <small>数据集已登记 · {analysisState.data_audit_report?.passed ? "通过基础字段审查" : "存在审查问题"}</small>
                      </div>
                      <span className="analysis-dataset-status">{analysisState.stage}</span>
                    </div>
                  ) : (
                    <div className="analysis-file-drop">
                      <strong>上传实验数据 CSV</strong>
                      <span>建议包含清晰的分组、结果变量和必要的受试者标识；系统会先检查列名、类型、缺失和隐私风险。</span>
                    </div>
                  )}
                  {analysisState.data_audit_report?.risk_flags.length ? (
                    <div className="analysis-risk-list">
                      {analysisState.data_audit_report.risk_flags.map((flag) => <span key={flag}>! {flag}</span>)}
                    </div>
                  ) : null}
                </section>

                <section className="output-section">
                  <div className="output-section-heading"><h3>代码与统计引擎</h3><span>{analysisState.executable_plan?.analysis_mode ?? "等待分析计划"}</span></div>
                  <div className="analysis-engine-grid">
                    <div className="analysis-engine-row">
                      <span>Codex / Python</span>
                      <strong>{analysisState.code_artifact_ref ? "候选代码已生成" : runtimeStatus.codex_available ? "可生成候选代码" : "使用受控模板或待配置"}</strong>
                      <small>{analysisState.code_review_ref ? "已记录代码审查" : "执行前需要代码审查和人工确认"}</small>
                    </div>
                    <div className="analysis-engine-row">
                      <span>SPSS</span>
                      <strong>{runtimeStatus.spss_available ? "SPSS 可用" : "SPSS 未配置"}</strong>
                      <small>{runtimeStatus.spss_available ? "双引擎模式可在审批后执行" : runtimeStatus.spss_reason ?? "需要配置 SPSS 批处理程序"}</small>
                    </div>
                  </div>
                  <div className="analysis-code-ref">
                    <span>代码工件</span>
                    <code>{analysisState.code_artifact_ref ?? "尚未生成，需先完成数据冻结和执行审批"}</code>
                  </div>
                </section>

                {analysisState.pending_approval && (
                  <section className="output-section analysis-approval">
                    <div className="output-section-heading"><h3>待人工确认</h3><span>{analysisState.pending_approval.approval_type}</span></div>
                    <p>{analysisState.pending_approval.reason}</p>
                    <div className="analysis-approval-actions">
                      <button className="secondary-inline-button" type="button" disabled={analysisBusy} onClick={() => void decideAnalysisStep("rejected")}>退回修正<span>↩</span></button>
                      <button className="primary-inline-button" type="button" disabled={analysisBusy} onClick={() => void decideAnalysisStep("approved")}>{analysisBusy ? "处理中..." : "确认并继续"}<span>→</span></button>
                    </div>
                  </section>
                )}

                <section className="output-section compact-section">
                  <div className="output-section-heading"><h3>分析结果</h3><span>{analysisState.statistical_result_card ? "已生成" : "等待执行"}</span></div>
                  {analysisState.statistical_result_card ? (
                    <div className="analysis-result-grid">
                      {Object.entries(analysisState.statistical_result_card.values).map(([key, value]) => (
                        <div key={key}><strong>{String(value)}</strong><small>{key.replaceAll("_", " ")}</small></div>
                      ))}
                      <p className="analysis-result-note">结果状态：{analysisState.statistical_result_card.execution_status}。正式解释仍需遵守结果卡和人工审查边界。</p>
                    </div>
                  ) : (
                    <div className="empty-output"><span className="empty-symbol">∿</span><p>完成数据审查、冻结和执行审批后，结果卡会出现在这里。</p></div>
                  )}
                </section>
              </>
            )}
            {analysisError && <p className="upload-error" role="alert">{analysisError}</p>}
          </div>
        )}

>>>>>>> origin/main
        {view === "audit" && (
          <div className="output-content">
            <section className="audit-summary">
              <div className="audit-summary-icon">✓</div>
              <div><strong>研究链路正在审查</strong><p>当前回答已关联证据，正式发布前仍需检查数据和引用。</p></div>
            </section>
            <section className="output-section">
<<<<<<< HEAD
              <div className="output-section-heading"><h3>六个 Agent</h3><span>1 / 6 活跃</span></div>
              <div className="agent-list">
                {agentRows.map(([index, name, description, status]) => (
                  <div className="agent-row" key={index}>
                    <span className="agent-index">{index}</span>
                    <span><strong>{name}</strong><small>{description}</small></span>
                    <span className={status === "进行中" ? "agent-status active" : "agent-status"}>{status}</span>
                  </div>
                ))}
=======
              <div className="output-section-heading">
                <h3>六个 Agent</h3>
                <span>
                  {workflowSnapshot
                    ? `${agentRows.filter(([, agentId]) => agentStatus(workflowSnapshot, agentId) === "等待审批").length} 个待审批`
                    : "读取中..."}
                </span>
              </div>
              <div className="agent-list">
                {agentRows.map(([index, agentId, name, description]) => {
                  const status = agentStatus(workflowSnapshot, agentId);
                  return (
                  <div className="agent-row" key={index}>
                    <span className="agent-index">{index}</span>
                    <span><strong>{name}</strong><small>{description}</small></span>
                    <span className={status === "等待审批" ? "agent-status active" : "agent-status"}>{status}</span>
                  </div>
                  );
                })}
>>>>>>> origin/main
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>本轮审查</h3><span>{lastResponse.risk_flags.length} 项提醒</span></div>
              <div className="review-list">
                {lastResponse.risk_flags.map((flag) => <div className="review-item" key={flag}><span>!</span><p>{flag}</p></div>)}
              </div>
<<<<<<< HEAD
=======
              {workflowSnapshot?.pending_approval_ref && (
                <div className="audit-pending-note">
                  <strong>当前存在 Human Gate</strong>
                  <p>
                    {workflowSnapshot.last_route_decision?.selected_route ?? "当前 Agent"} 已生成候选结果，
                    需要研究者在研究流程中确认后才能进入下一阶段。
                  </p>
                </div>
              )}
>>>>>>> origin/main
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
                <span className="chat-kicker">
                  {selectedDocument.document.document_type === "manuscript" ? "论文草稿编辑器" : "项目文档"}
                </span>
                <h2>{selectedDocument.document.title}</h2>
                <small>版本 {selectedDocument.version?.version ?? selectedDocument.document.current_version} · {selectedDocument.document.format}</small>
              </div>
              <button className="header-icon-button" type="button" title="关闭" onClick={() => setSelectedDocument(null)}>×</button>
            </div>
            {selectedDocument.document.document_type === "manuscript" ? (
              <div className="document-editor">
                <label className="document-editor-label">
                  草稿标题
                  <input
                    value={documentTitleDraft}
                    onChange={(event) => setDocumentTitleDraft(event.target.value)}
                    placeholder="输入论文标题"
                  />
                </label>
                <label className="document-editor-label">
                  草稿正文
                  <textarea
                    value={documentContentDraft}
                    onChange={(event) => setDocumentContentDraft(event.target.value)}
                    placeholder="在这里编辑论文草稿..."
                    disabled={!selectedDocument.version || documentEditBusy}
                  />
                </label>
                {documentEditError && <p className="document-editor-error">{documentEditError}</p>}
                <div className="document-editor-actions">
                  <button
                    className="delete-draft-button"
                    type="button"
                    disabled={documentEditBusy}
                    onClick={() => void deleteSelectedDocument()}
                  >
                    删除草稿
                  </button>
                  <button
                    className="primary-inline-button"
                    type="button"
                    disabled={
                      documentEditBusy
                      || !selectedDocument.version
                      || !documentTitleDraft.trim()
                    }
                    onClick={() => void saveSelectedDocument()}
                  >
                    {documentEditBusy ? "保存中..." : "保存新版本"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="document-content">
                {selectedDocument.version?.content ?? "正在读取文档内容..."}
              </div>
            )}
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

      {createProjectOpen && (
        <div className="workspace-drawer-backdrop" role="presentation" onClick={() => setCreateProjectOpen(false)}>
          <section className="workspace-modal create-project-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="workspace-drawer-header">
              <div>
                <span className="chat-kicker">项目管理</span>
                <h2>新建研究项目</h2>
                <small>创建后会自动切换到新项目，不会清空已有项目。</small>
              </div>
              <button className="header-icon-button" type="button" title="关闭" onClick={() => setCreateProjectOpen(false)}>×</button>
            </div>
            <div className="create-project-form">
              <label>
                项目名称
                <input
                  value={projectForm.title}
                  onChange={(event) => setProjectForm((current) => ({ ...current, title: event.target.value }))}
                  placeholder="例如：生成式 AI 物理建模研究"
                />
              </label>
              <label>
                研究方向
                <input
                  value={projectForm.research_direction}
                  onChange={(event) => setProjectForm((current) => ({ ...current, research_direction: event.target.value }))}
                  placeholder="例如：师范生 Python 物理建模与生成式 AI 支架"
                />
              </label>
              <label>
                项目标识（可选）
                <input
                  value={projectForm.project_id}
                  onChange={(event) => setProjectForm((current) => ({ ...current, project_id: event.target.value }))}
                  placeholder="留空则由后端自动生成"
                />
              </label>
              <label>
                项目简介（可选）
                <textarea
                  value={projectForm.abstract}
                  onChange={(event) => setProjectForm((current) => ({ ...current, abstract: event.target.value }))}
                  placeholder="描述这个项目要解决的问题和计划产出"
                  rows={4}
                />
              </label>
              {projectError && <p className="project-form-error">{projectError}</p>}
              <div className="modal-actions">
                <button className="secondary-inline-button" type="button" onClick={() => setCreateProjectOpen(false)}>取消</button>
                <button className="primary-inline-button" type="button" disabled={projectBusy} onClick={() => void createProject()}>
                  {projectBusy ? "创建中..." : "创建项目"}
                </button>
              </div>
            </div>
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
