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
import {
  workflowApi,
  type AgentExecutionPlan,
  type AgentExecutionMode,
  type AgentPageMaterial,
  type AgentOutputSummary,
  type FormalEvidenceRecord,
  type WorkflowState,
  type ControllerWorkflowState,
  type DataPipelineState,
  type RuntimeStatus,
} from "./api/workflow";
import { api } from "./api/client";
import type { SearchResult, SharedCorpusSummary } from "./types/context";
import { demoBundle, demoQAResponse, demoRuntime } from "./demo/data";
import { demoDocumentContents, demoDocumentsByProject, demoProjects } from "./demo/projectHub";

type WorkspaceView = "knowledge" | "codex" | "analysis" | "audit";
type ContextTab = "workspace" | "evidence" | "agent-work" | "agent-plan" | "agent-outputs";
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

const starterAgentFeatures = [
  {
    agent: "导师规划",
    description: "界定研究问题与范围",
    prompt: "请由导师规划 Agent 帮我界定当前研究问题、研究范围和可行性。",
  },
  {
    agent: "证据审查",
    description: "筛选、核验文献证据",
    prompt: "请由证据审查 Agent 检索并整理当前研究问题相关的文献证据和研究空白。",
  },
  {
    agent: "研究设计",
    description: "设计测量与研究方案",
    prompt: "请由研究设计 Agent 设计前测、后测和迁移任务，并明确变量与测量指标。",
  },
  {
    agent: "数据分析",
    description: "制定分析计划与代码规格",
    prompt: "请由数据分析 Agent 检查数据需求，并制定数据审查、统计分析和代码规格。",
  },
  {
    agent: "论文写作",
    description: "整理论文结构与草稿",
    prompt: "请由论文写作 Agent 根据已保留的研究材料生成论文结构和中文草稿。",
  },
  {
    agent: "独立审查",
    description: "检查证据、方法与风险",
    prompt: "请由独立审查 Agent 检查证据引用、研究设计、分析逻辑和可复现性风险。",
  },
];

const agentRows = [
  ["01", "mentor_planning", "导师规划", "界定研究问题与范围"],
  ["02", "evidence_review", "证据审查", "筛选、核验和组织文献证据"],
  ["03", "research_design", "研究设计", "形成可审批的研究方案"],
  ["04", "data_analysis", "数据分析", "编译分析计划与结果检查"],
  ["05", "paper_writing", "论文写作", "生成基于证据的写作草案"],
  ["06", "independent_review", "独立审查", "检查风险、引用和方法"],
] as const;

const agentCompletionStages: Record<string, string[]> = {
  mentor_planning: ["SCOPED", "EVIDENCE_READY", "STUDY_PROTOCOL_APPROVED", "DATA_READY", "ANALYZED", "DRAFTED", "VERIFIED", "RELEASED"],
  evidence_review: ["EVIDENCE_READY", "STUDY_PROTOCOL_APPROVED", "DATA_READY", "ANALYZED", "DRAFTED", "VERIFIED", "RELEASED"],
  research_design: ["STUDY_PROTOCOL_APPROVED", "DATA_READY", "ANALYZED", "DRAFTED", "VERIFIED", "RELEASED"],
  data_analysis: ["ANALYZED", "DRAFTED", "VERIFIED", "RELEASED"],
  paper_writing: ["DRAFTED", "VERIFIED", "RELEASED"],
  independent_review: ["VERIFIED", "RELEASED"],
};

function workflowAgentStatus(
  agentId: string,
  workflow: WorkflowState | null,
): "已完成" | "待审批" | "进行中" | "待启动" {
  if (!workflow) return "待启动";
  const currentStage = workflow.current_stage;
  if (agentCompletionStages[agentId]?.includes(currentStage)) return "已完成";
  if (workflow.last_route_decision?.selected_route === agentId && currentStage === "WAITING_HUMAN") {
    return "待审批";
  }
  if (workflow.last_route_decision?.selected_route === agentId) return "进行中";
  return "待启动";
}

const dataPipelineLabels: Record<string, string> = {
  WAITING_RAW_DATA: "等待原始 CSV",
  WAITING_PROCESSING_APPROVAL: "等待数据处理审批",
  WAITING_FREEZE_APPROVAL: "等待数据冻结审批",
  WAITING_EXECUTION_APPROVAL: "等待分析执行审批",
  ANALYZED: "分析结果已验证",
  REWORK: "需要返工",
  BLOCKED: "流程已阻断",
};

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

const agentDisplayNames: Record<string, string> = {
  mentor_planning: "导师规划",
  evidence_review: "证据审查",
  research_design: "研究设计",
  data_analysis: "数据分析",
  paper_writing: "论文写作",
  independent_review: "独立审查",
};

const agentTaskStatusLabels: Record<string, string> = {
  PLANNED: "待执行",
  WAITING_DEPENDENCY: "等待依赖",
  SKIPPED: "已跳过",
  RUNNING: "执行中",
  COMPLETED: "已完成",
  FAILED: "失败",
  BLOCKED: "已阻断",
};

const agentPlanStatusLabels: Record<string, string> = {
  PENDING_APPROVAL: "等待批准",
  APPROVED: "已批准，等待执行",
  RUNNING: "执行中",
  COMPLETED: "已完成",
  PARTIAL: "部分完成",
  REJECTED: "已拒绝",
  BLOCKED: "已阻断",
  WAITING_TASK_APPROVAL: "等待逐项确认",
  REWORK_REQUIRED: "等待返工",
};

const agentOutputDecisionLabels: Record<string, string> = {
  candidate: "候选",
  retained: "已保留",
  applied: "已应用",
  promoted: "已提升",
  review_required: "待核验",
  reject: "已拒绝",
};

const agentTargetPages: Record<string, string[]> = {
  mentor_planning: ["research_questions", "workspace"],
  evidence_review: ["knowledge_evidence", "evidence_gate"],
  research_design: ["research_design", "data_collection"],
  data_analysis: ["data_analysis", "codex"],
  paper_writing: ["paper_editor"],
  independent_review: ["audit_validation"],
};

function isFormalCitation(citation: SelectedCitation) {
  return (
    citation.verification_status === "source_verified"
    || citation.verification_status === "human_verified"
  ) && citation.locator_status === "RESOLVED";
}

function citationStatusLabel(citation: SelectedCitation) {
  if (citation.source_type === "paper") return "候选论文";
  if (isFormalCitation(citation)) {
    return citation.verification_status === "human_verified" ? "人工核验" : "来源已核验";
  }
  if (citation.locator_status === "RESOLVED") return "已定位，待核验";
  return "待定位/核验";
}

function citationPageLabel(citation: SelectedCitation) {
  if (citation.page_start == null) return "页码待补充";
  return `第 ${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `-${citation.page_end}` : ""} 页`;
}

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

function outputSummariesFromPlan(plan: AgentExecutionPlan): AgentOutputSummary[] {
  return plan.tasks
    .filter((task) => task.status !== "PLANNED" && task.status !== "WAITING_DEPENDENCY" && task.status !== "SKIPPED")
    .filter((task) => task.persisted_artifact_ids.length > 0 || task.error || task.status === "BLOCKED")
    .map((task) => ({
      plan_id: plan.plan_id,
      task_id: task.task_id,
      project_id: plan.project_id,
      user_request: plan.user_request,
      conversation_id: plan.conversation_id,
      turn_id: plan.turn_id,
      agent_id: task.agent_id,
      task_type: task.task_type,
      status: task.status,
      input_refs: task.input_refs,
      depends_on: task.depends_on,
      risk_level: task.risk_level,
      output_types: task.output_refs.map((ref) => ref.split("/").at(-1) ?? ref),
      artifact_ids: task.persisted_artifact_ids,
      artifact_refs: task.output_refs,
      evidence_refs: task.evidence_refs,
      output_previews: [],
      risk_flags: task.risk_flags,
      unresolved_questions: task.unresolved_questions,
      decision: "candidate",
      target_pages: agentTargetPages[task.agent_id] ?? ["workspace"],
      error: task.error,
      primary_artifact_id: null,
      researcher_answer: "",
      summary_mode: "deterministic",
    }));
}

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
  const [projectsReady, setProjectsReady] = useState(!readStoredAuth()?.access_token);
  const [projectId, setProjectId] = useState(demoProjects[0]?.project_id ?? demoProjectId);
  const [view, setView] = useState<WorkspaceView>("knowledge");
  const [contextTab, setContextTab] = useState<ContextTab>("evidence");
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
  const rawCsvInputRef = useRef<HTMLInputElement>(null);
  const evidenceInputRef = useRef<HTMLInputElement>(null);
  const analysisInputRef = useRef<HTMLInputElement>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus>(demoRuntime);
  const [workflowSnapshot, setWorkflowSnapshot] = useState<ControllerWorkflowState | null>(null);
  const [analysisState, setAnalysisState] = useState<DataPipelineState | null>(null);
  const [analysisStage, setAnalysisStage] = useState("STUDY_PROTOCOL_APPROVED");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const chatAttachmentInputRef = useRef<HTMLInputElement>(null);
  const [chatAttachments, setChatAttachments] = useState<ChatAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<SelectedDocument | null>(null);
  const [documentTitleDraft, setDocumentTitleDraft] = useState("");
  const [documentContentDraft, setDocumentContentDraft] = useState("");
  const [documentEditBusy, setDocumentEditBusy] = useState(false);
  const [documentEditError, setDocumentEditError] = useState("");
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation | null>(null);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [rightPaneVisible, setRightPaneVisible] = useState(true);
  const [paneWidths, setPaneWidths] = useState<PaneWidths>({ sidebar: 246, output: 374 });
  const [draggingPane, setDraggingPane] = useState<"sidebar" | "output" | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState("");
  const [evidenceRows, setEvidenceRows] = useState<SearchResult[]>([]);
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const [corpusSummary, setCorpusSummary] = useState<SharedCorpusSummary | null>(null);
  const [agentPlan, setAgentPlan] = useState<AgentExecutionPlan | null>(null);
  const [agentPlans, setAgentPlans] = useState<AgentExecutionPlan[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<AgentOutputSummary[]>([]);
  const [pageMaterials, setPageMaterials] = useState<AgentPageMaterial[]>([]);
  const [formalEvidence, setFormalEvidence] = useState<FormalEvidenceRecord[]>([]);
  const [agentPlanDraft, setAgentPlanDraft] = useState("");
  const [selectedAgentTaskIds, setSelectedAgentTaskIds] = useState<string[]>([]);
  const [agentPlanBusy, setAgentPlanBusy] = useState(false);
  const [agentPlanError, setAgentPlanError] = useState("");
  const [agentOutputDecisions, setAgentOutputDecisions] = useState<Record<string, string>>({});
  const [agentOutputTargets, setAgentOutputTargets] = useState<Record<string, string>>({});
  const [agentPlanPanelOpen, setAgentPlanPanelOpen] = useState(true);
  const [agentOutputBoxOpen, setAgentOutputBoxOpen] = useState(true);
  const [agentOutputScope, setAgentOutputScope] = useState<"turn" | "question" | "project">("turn");
  const [agentExecutionMode, setAgentExecutionMode] = useState<AgentExecutionMode>("automatic");

  useEffect(() => {
    if (contextTab === "agent-plan" || contextTab === "agent-outputs") {
      setContextTab("agent-work");
    }
  }, [contextTab]);

  const activeProject = useMemo(
    () => projects.find((project) => project.project_id === projectId) ?? projects[0] ?? null,
    [projectId, projects],
  );
  const activeDocuments = auth?.access_token
    ? documents
    : demoDocumentsByProject[projectId] ?? demoDocumentsByProject[demoProjectId] ?? [];
  const draftDocuments = activeDocuments.filter((document) => document.document_type === "manuscript");
  const projectPapers = activeDocuments.filter((document) => document.document_type !== "manuscript");
  const selectedTurnResponse = messages.find(
    (message) => message.id === selectedTurnId && message.role === "assistant",
  )?.response;
  const activeResponse = selectedTurnResponse ?? lastResponse;
  const citations = activeResponse?.citations ?? demoQAResponse.citations;

  useEffect(() => {
    if (!auth?.access_token) {
      setProjects(demoProjects);
      setProjectsReady(true);
      return;
    }
    setProjectsReady(false);
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
        setProjectsReady(true);
      }
    }).finally(() => {
      if (mounted) setProjectsReady(true);
    });
    return () => {
      mounted = false;
    };
  }, [auth?.access_token]);

  useEffect(() => {
    let mounted = true;
    void api.listSharedCorpora().then((corpora) => {
      if (mounted) {
        const summary = corpora[0] ?? null;
        setCorpusSummary(summary);
        if (summary?.formal_evidence_ready) setMode("formal");
      }
    }).catch(() => {
      if (mounted) setCorpusSummary(null);
    });
    return () => {
      mounted = false;
    };
  }, []);

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
    let mounted = true;
    setWorkflowError("");
    if (!auth?.access_token || !projectId || !projectsReady) {
      setWorkflow(null);
      return () => { mounted = false; };
    }
    void workflowApi.getProject(projectId).then((next) => {
      if (mounted) setWorkflow(next);
    }).catch(() => {
      if (mounted) setWorkflow(null);
    });
    return () => { mounted = false; };
  }, [auth?.access_token, projectId]);

  useEffect(() => {
    let mounted = true;
    setAnalysisError("");
    if (!auth?.access_token || !projectId || !projectsReady) {
      setRuntimeStatus(demoRuntime);
      setWorkflowSnapshot(null);
      setAnalysisStage("STUDY_PROTOCOL_APPROVED");
      setAnalysisState(null);
      return () => {
        mounted = false;
      };
    }
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
    let mounted = true;
    if (!auth?.access_token || !projectId || !projectsReady) {
      setAgentOutputs([]);
      setPageMaterials([]);
      setFormalEvidence([]);
      setAgentPlans([]);
      setAgentPlan(null);
      return () => {
        mounted = false;
      };
    }
    void Promise.allSettled([
      workflowApi.listAgentOutputs(projectId),
      workflowApi.listAgentPageMaterials(projectId),
      workflowApi.listAgentPlans(projectId),
      workflowApi.listFormalEvidence(projectId),
    ]).then(([outputResult, materialResult, planResult, formalEvidenceResult]) => {
      if (!mounted) return;
      const plans = planResult.status === "fulfilled" ? planResult.value : [];
      const fallbackOutputs = plans.flatMap(outputSummariesFromPlan);
      const outputs = outputResult.status === "fulfilled" && outputResult.value.length
        ? outputResult.value
        : fallbackOutputs;
      const materials = materialResult.status === "fulfilled" ? materialResult.value : [];
      const formal = formalEvidenceResult.status === "fulfilled" ? formalEvidenceResult.value : [];
      setAgentOutputs(outputs);
      setPageMaterials(materials);
      setFormalEvidence(formal);
      setAgentPlans(plans);
      setAgentPlan((current) => current?.project_id === projectId ? current : plans[0] ?? null);
    });
    return () => {
      mounted = false;
    };
  }, [auth?.access_token, projectId, projectsReady]);

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

  const refreshWorkflow = async () => {
    const next = await workflowApi.getProject(projectId);
    setWorkflow(next);
    return next;
  };

  const searchProjectEvidence = async () => {
    if (!projectId || !activeProject) return;
    setEvidenceBusy(true);
    setEvidenceError("");
    try {
      const query = activeProject.research_direction || activeProject.title;
      setEvidenceRows(await api.search(projectId, query));
    } catch (error) {
      setEvidenceError(error instanceof Error ? error.message : "无法读取项目证据");
    } finally {
      setEvidenceBusy(false);
    }
  };

  const uploadEvidenceSource = async (file: File) => {
    setEvidenceBusy(true);
    setEvidenceError("");
    try {
      await api.importSource(projectId, file);
      await searchProjectEvidence();
    } catch (error) {
      setEvidenceError(error instanceof Error ? error.message : "证据来源上传失败");
    } finally {
      setEvidenceBusy(false);
      if (evidenceInputRef.current) evidenceInputRef.current.value = "";
    }
  };

  const verifyProjectEvidence = async (evidenceId: string) => {
    setEvidenceBusy(true);
    setEvidenceError("");
    try {
      await api.verifySource(
        projectId,
        evidenceId,
        auth?.user.username ?? "researcher",
        "已人工核对上传来源与对应原文片段。",
      );
      await searchProjectEvidence();
    } catch (error) {
      setEvidenceError(error instanceof Error ? error.message : "证据核验失败");
    } finally {
      setEvidenceBusy(false);
    }
  };

  const uploadRawCsv = async (file: File) => {
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      await workflowApi.uploadRawCsv(projectId, file);
      await refreshWorkflow();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "CSV 上传或审查失败");
    } finally {
      setWorkflowBusy(false);
      if (rawCsvInputRef.current) rawCsvInputRef.current.value = "";
    }
  };

  const decideDataPipeline = async (decision: "approved" | "rejected") => {
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      await workflowApi.decideDataPipeline(
        projectId,
        decision,
        auth?.user.username ?? "researcher",
      );
      await refreshWorkflow();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "数据 Gate 审批失败");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const openAgentPlanner = (draft?: string) => {
    setRightPaneVisible(true);
    setContextTab("agent-work");
    setAgentPlanPanelOpen(true);
    setAgentPlanError("");
    if (!agentPlan && agentPlans[0]) {
      setAgentPlan(agentPlans[0]);
      setSelectedAgentTaskIds(agentPlans[0].approved_task_ids);
    }
    setAgentPlanDraft(
      draft?.trim()
      ||
      question.trim()
      || activeResponse?.question
      || "请根据当前研究问题判断需要调用哪些 Agent。",
    );
  };

  const createAgentPlan = async () => {
    const request = agentPlanDraft.trim();
    if (!request || !projectId || agentPlanBusy) return;
    if (!auth?.access_token && !demoMode) {
      setAgentPlanError("请先登录后再调用 Agent");
      return;
    }
    setAgentPlanBusy(true);
    setAgentPlanError("");
    try {
      const next = await workflowApi.createAgentPlan({
        project_id: projectId,
        user_request: request,
        conversation_id: conversationId,
        turn_id: activeResponse?.turn_id ?? selectedTurnId ?? undefined,
        context_refs: activeResponse?.context_bundle_ref ? [activeResponse.context_bundle_ref] : [],
        conversation_context: messages
          .filter((message) => message.id !== "welcome")
          .slice(-5)
          .map((message) => `${message.role === "user" ? "研究者" : "助手"}：${message.content}`),
      });
      setAgentPlan(next);
      setAgentPlans((current) => [next, ...current.filter((item) => item.plan_id !== next.plan_id)]);
      setSelectedAgentTaskIds(
        next.tasks
          .filter((task) => task.blocked_reason === null && task.status !== "SKIPPED")
          .map((task) => task.task_id),
      );
      setAgentOutputs([]);
      setAgentExecutionMode("automatic");
    } catch (error) {
      setAgentPlanError(error instanceof Error ? error.message : "Agent 计划生成失败");
    } finally {
      setAgentPlanBusy(false);
    }
  };

  const toggleAgentTask = (taskId: string) => {
    setSelectedAgentTaskIds((current) => current.includes(taskId)
      ? current.filter((item) => item !== taskId)
      : [...current, taskId]);
  };

  const approveAndExecuteAgentPlan = async () => {
    if (!agentPlan || agentPlan.status !== "PENDING_APPROVAL" || agentPlanBusy) return;
    setAgentPlanBusy(true);
    setAgentPlanError("");
    try {
      const decidedBy = auth?.user.username ?? "researcher";
      const approved = await workflowApi.approveAgentPlan(
        projectId,
        agentPlan.plan_id,
        "approved",
        decidedBy,
        selectedAgentTaskIds,
        agentExecutionMode,
      );
      setAgentPlan(approved);
      setAgentPlans((current) => current.map((item) => item.plan_id === approved.plan_id ? approved : item));
      const executed = await workflowApi.executeAgentPlan(projectId, approved.plan_id);
      setAgentPlan(executed);
      setAgentPlans((current) => current.map((item) => item.plan_id === executed.plan_id ? executed : item));
      const fallbackOutputs = outputSummariesFromPlan(executed);
      setAgentOutputs(fallbackOutputs);
      setAgentOutputScope("question");
      try {
        const outputs = await workflowApi.listPlanOutputs(projectId, executed.plan_id);
        if (outputs.length) setAgentOutputs(outputs);
      } catch {
        setAgentPlanError("计划已经执行；产出预览暂时无法读取，请在任务状态中查看已生成的候选产物。");
      }
      setContextTab("agent-work");
    } catch (error) {
      setAgentPlanError(error instanceof Error ? error.message : "Agent 执行失败");
    } finally {
      setAgentPlanBusy(false);
    }
  };

  const continueStepwiseAgentPlan = async (decision: "approved" | "rework") => {
    if (!agentPlan || agentPlan.status !== "WAITING_TASK_APPROVAL" || agentPlanBusy) return;
    const task = agentPlan.tasks.find((item) => item.task_id === agentPlan.pending_review_task_id);
    const note = decision === "rework"
      ? window.prompt("说明需要修改的地方。系统会带着本轮上下文回到对话中。")?.trim()
      : undefined;
    if (decision === "rework" && note === undefined) return;
    setAgentPlanBusy(true);
    setAgentPlanError("");
    try {
      const updated = await workflowApi.continueAgentPlan(
        projectId,
        agentPlan.plan_id,
        decision,
        auth?.user.username ?? "researcher",
        note || undefined,
      );
      setAgentPlan(updated);
      setAgentPlans((current) => current.map((item) => item.plan_id === updated.plan_id ? updated : item));
      const outputs = await workflowApi.listPlanOutputs(projectId, updated.plan_id);
      setAgentOutputs(outputs);
      if (decision === "rework") {
        const agentName = task ? (agentDisplayNames[task.agent_id] ?? task.agent_id) : "当前 Agent";
        const outputRefs = task?.persisted_artifact_ids.join("、") || "当前候选产出";
        setQuestion(`请根据本轮研究需求修改 ${agentName} 的候选方案。\n原需求：${agentPlan.user_request}\n待修改产出：${outputRefs}\n修改意见：${note || "请重新审查并调整。"}`);
        setAgentPlanDraft(`基于以下研究需求与修改意见，重新生成 Agent 计划：\n${agentPlan.user_request}\n\n当前步骤：${agentName}\n修改意见：${note || "请重新审查并调整。"}`);
      }
    } catch (error) {
      setAgentPlanError(error instanceof Error ? error.message : "Agent 步骤确认失败");
    } finally {
      setAgentPlanBusy(false);
    }
  };

  const rejectAgentPlan = async () => {
    if (!agentPlan || agentPlan.status !== "PENDING_APPROVAL" || agentPlanBusy) return;
    setAgentPlanBusy(true);
    setAgentPlanError("");
    try {
      const rejected = await workflowApi.approveAgentPlan(
        projectId,
        agentPlan.plan_id,
        "rejected",
        auth?.user.username ?? "researcher",
      );
      setAgentPlan(rejected);
      setAgentPlans((current) => current.map((item) => item.plan_id === rejected.plan_id ? rejected : item));
    } catch (error) {
      setAgentPlanError(error instanceof Error ? error.message : "Agent 计划未能拒绝");
    } finally {
      setAgentPlanBusy(false);
    }
  };

  const decideAgentOutput = async (
    output: AgentOutputSummary,
    decision: "retain" | "reject" | "apply" | "promote",
  ) => {
    if (!output.artifact_ids.length || agentPlanBusy) return;
    const promotableTypes = new Set([
      "PaperCardCollection",
      "EvidenceMatrixCandidate",
      "BoundedEvidenceSynthesis",
    ]);
    const artifactIds = decision === "promote"
      ? output.output_previews
        .filter((preview) => promotableTypes.has(preview.artifact_type))
        .map((preview) => preview.artifact_id)
      : decision === "apply"
        ? (() => {
          const primary = primaryPreviewForAgent(output);
          return primary ? [primary.artifact_id] : output.artifact_ids.slice(0, 1);
        })()
      : output.artifact_ids;
    if (!artifactIds.length) {
      setAgentPlanError("当前产出不包含可正式化的来源绑定证据，请先生成并核验论文卡或证据矩阵。");
      return;
    }
    setAgentPlanBusy(true);
    setAgentPlanError("");
    try {
      let promotionBlockedReason = "";
      for (const artifactId of artifactIds) {
        const result = await workflowApi.decideAgentOutput(
          projectId,
          artifactId,
          decision,
          auth?.user.username ?? "researcher",
          agentOutputTargets[output.task_id] ?? output.target_pages[0],
        );
        if (decision === "promote" && result.formalization === "candidate_evidence_only") {
          const risks = Array.isArray(result.risk_flags)
            ? result.risk_flags.filter((item): item is string => typeof item === "string")
            : [];
          promotionBlockedReason = risks[0] ?? "FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION";
        }
      }
      setAgentOutputDecisions((current) => ({ ...current, [output.task_id]: decision }));
      const [outputs, materials, formal] = await Promise.all([
        workflowApi.listAgentOutputs(projectId),
        workflowApi.listAgentPageMaterials(projectId),
        workflowApi.listFormalEvidence(projectId),
      ]);
      setAgentOutputs(outputs);
      setPageMaterials(materials);
      setFormalEvidence(formal);
      if (promotionBlockedReason) {
        setAgentPlanError(`提升被拦截：${promotionBlockedReason}。请先上传来源、完成定位并核验证据。`);
      } else if (decision === "promote") {
        setAgentPlanError("已提升为正式证据，并已按证据标识写入正式证据库。");
      }
      if (decision === "apply") {
        setRightPaneVisible(true);
        const targetView = agentOutputTargetView(output);
        setView(targetView);
        setContextTab(targetView === "knowledge" ? "evidence" : "workspace");
      }
    } catch (error) {
      setAgentPlanError(error instanceof Error ? error.message : "Agent 产出处理失败");
    } finally {
      setAgentPlanBusy(false);
    }
  };

  const applyManuscriptCandidate = async (output: AgentOutputSummary) => {
    if (agentPlanBusy) return;
    const manuscriptPreview = output.output_previews.find(
      (preview) => preview.artifact_type === "ManuscriptDraftZh",
    ) ?? output.output_previews.find(
      (preview) => preview.artifact_type === "ManuscriptOutline",
    );
    if (!manuscriptPreview) {
      setAgentPlanError("本轮论文写作尚未生成可送入论文草稿的候选内容。");
      return;
    }
    setAgentPlanBusy(true);
    setAgentPlanError("");
    try {
      await workflowApi.applyAgentManuscript(projectId, manuscriptPreview.artifact_id);
      if (auth?.access_token) {
        setDocuments(await authApi.listDocuments(auth.access_token, projectId));
      }
      setAgentOutputDecisions((current) => ({ ...current, [output.task_id]: "applied" }));
      setView("knowledge");
      setContextTab("evidence");
      setRightPaneVisible(true);
    } catch (error) {
      setAgentPlanError(error instanceof Error ? error.message : "论文草稿写入失败");
    } finally {
      setAgentPlanBusy(false);
    }
  };

  const agentOutputTargetView = (output: AgentOutputSummary): WorkspaceView => {
    if (output.agent_id === "evidence_review" || output.target_pages.some((page) => page.includes("evidence"))) {
      return "knowledge";
    }
    if (output.agent_id === "data_analysis" || output.target_pages.some((page) => page.includes("analysis") || page.includes("codex"))) {
      return "analysis";
    }
    if (output.agent_id === "independent_review" || output.target_pages.some((page) => page.includes("audit") || page.includes("validation"))) {
      return "audit";
    }
    return "codex";
  };

  const targetPageLabels: Record<string, string> = {
    workspace: "工作区",
    research_questions: "研究问题",
    knowledge_evidence: "知识库证据",
    evidence_gate: "Evidence Gate",
    research_design: "研究设计",
    data_collection: "数据采集",
    data_analysis: "数据分析",
    codex: "Codex",
    paper_editor: "论文草稿",
    audit_validation: "Agent 工作 / 审查",
  };

  const targetPageLabel = (target: string) => targetPageLabels[target] ?? target;

  const outputDecision = (output: AgentOutputSummary) => (
    agentOutputDecisions[output.task_id] ?? output.decision
  );

  const activeTurnOutputs = agentOutputs.filter((output) => (
    (!conversationId || output.conversation_id === conversationId)
    && (!activeResponse?.turn_id || output.turn_id === activeResponse.turn_id)
  ));

  const selectedQuestionOutputs = agentPlan
    ? agentOutputs.filter((output) => output.plan_id === agentPlan.plan_id)
    : [];

  const visibleAgentOutputs = agentOutputScope === "project"
    ? agentOutputs
    : agentOutputScope === "question"
      ? selectedQuestionOutputs
      : activeTurnOutputs;

  const evidenceGateOutputs = (agentPlan
    ? agentOutputs.filter((output) => output.plan_id === agentPlan.plan_id)
    : activeTurnOutputs
  ).filter((output) => output.agent_id === "evidence_review");

  const pageMaterialsFor = (targets: string[]) => pageMaterials.filter((material) => (
    targets.includes(material.target)
    // Professional pages follow the selected Agent question. This prevents
    // an applied result from an earlier round appearing beside the current one.
    && (!agentPlan || material.plan_id === agentPlan.plan_id)
  ));

  const selectAgentQuestion = (plan: AgentExecutionPlan) => {
    setAgentPlan(plan);
    setSelectedAgentTaskIds(
      plan.approved_task_ids.length
        ? plan.approved_task_ids
        : plan.tasks
          .filter((task) => task.blocked_reason === null && task.status !== "SKIPPED")
          .map((task) => task.task_id),
    );
    setAgentOutputScope("question");
  };

  const previewValueText = (value: unknown): string => {
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) {
      return value.slice(0, 3).map(previewValueText).join("；") + (value.length > 3 ? "……" : "");
    }
    if (value && typeof value === "object") {
      return Object.entries(value as Record<string, unknown>)
        .slice(0, 3)
        .map(([key, item]) => `${key}：${previewValueText(item)}`)
        .join("；");
    }
    return "暂无内容";
  };

  const primaryPreviewForAgent = (output: AgentOutputSummary) => {
    if (output.primary_artifact_id) {
      const persisted = output.output_previews.find(
        (preview) => preview.artifact_id === output.primary_artifact_id,
      );
      if (persisted) return persisted;
    }
    const preferredTypes: Record<string, string[]> = {
      mentor_planning: ["ResearchQuestionTree", "FeasibilityReport"],
      evidence_review: ["EvidenceMatrixCandidate", "BoundedEvidenceSynthesis", "PaperCardCollection"],
      research_design: ["StudyProtocolCandidate", "MeasurementPlan"],
      data_analysis: ["DataProcessingPlanCandidate", "ExecutableAnalysisPlanCandidate"],
      paper_writing: ["ManuscriptDraftZh", "ManuscriptOutline"],
      independent_review: ["ReviewReport", "ReproducibilityReviewReport"],
    };
    const preferred = preferredTypes[output.agent_id] ?? [];
    return preferred
      .map((artifactType) => output.output_previews.find((preview) => preview.artifact_type === artifactType))
      .find((preview): preview is AgentOutputSummary["output_previews"][number] => Boolean(preview))
      ?? output.output_previews[0];
  };

  const outputPreviewText = (output: AgentOutputSummary) => {
    const preview = primaryPreviewForAgent(output);
    if (!preview) return output.output_types.join("、") || "候选输出引用已记录";
    const body = preview.content;
    const candidates = [
      body.title,
      body.research_question,
      body.primary_question,
      body.design_question,
      body.primary_outcome,
      body.sufficiency_judgement,
      body.corpus_coverage,
      body.summary,
      body.overall_recommendation,
      body.output_boundary,
      body.recommendation,
      body.status,
      Array.isArray(body.recommendations) ? body.recommendations[0] : null,
      Array.isArray(body.unresolved_questions) ? body.unresolved_questions[0] : null,
    ].filter((item): item is string => typeof item === "string" && item.trim().length > 0);
    return candidates[0] ?? preview.artifact_type;
  };

  const riskFlagText = (flag: string) => ({
    FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION: "正式证据仍需完成来源核验和定位。",
    MANUSCRIPT_OUTPUT_REMAINS_CANDIDATE: "论文输出仍是候选草稿，需人工审查后使用。",
    PLANNER_MODEL_FALLBACK: "本次计划使用受控规则生成，未使用模型规划。",
    OUTPUT_CAPABILITY_NOT_GRANTED: "本轮仅生成计划指定的候选材料。",
  }[flag] ?? flag);

  const canPromoteEvidence = (output: AgentOutputSummary) => {
    const promotable = new Set([
      "PaperCardCollection",
      "EvidenceMatrixCandidate",
      "BoundedEvidenceSynthesis",
    ]);
    return output.agent_id === "evidence_review" && (
      output.output_types.some((type) => promotable.has(type))
      || output.output_previews.some((preview) => promotable.has(preview.artifact_type))
    );
  };

  const renderAgentOutputCard = (output: AgentOutputSummary, compact = false) => {
    const decision = outputDecision(output);
    const primaryPreview = primaryPreviewForAgent(output);
    const visibleRiskFlags = output.risk_flags.filter((flag) => flag !== "OUTPUT_CAPABILITY_NOT_GRANTED");
    return (
      <article className={compact ? "agent-output-card agent-output-card-compact" : "agent-output-card"} key={output.task_id}>
        <div className="agent-output-card-topline">
          <strong>{agentDisplayNames[output.agent_id] ?? output.agent_id}</strong>
          <span className="status-badge status-muted">{agentOutputDecisionLabels[decision] ?? decision}</span>
        </div>
        <small>
          已生成 {output.output_previews.length || output.output_types.length} 项候选材料 · 可接入：
          {output.target_pages.map(targetPageLabel).join("、") || "项目产出箱"}
        </small>
        {output.agent_run_id && <small className="agent-execution-record">已执行 · {output.agent_version || output.agent_run_id}</small>}
        {primaryPreview && (
          <div className="agent-output-readable-preview">
            <strong>直接回答{output.summary_mode === "llm" ? " · 模型整理" : " · 规则整理"}</strong>
            <p>{output.researcher_answer || primaryPreview.researcher_summary || outputPreviewText(output)}</p>
            {!compact && primaryPreview.review_points?.length ? (
              <div className="agent-output-brief-list">
                <span>建议审查</span>
                <ul>{primaryPreview.review_points.map((point) => <li key={point}>{point}</li>)}</ul>
              </div>
            ) : null}
            {!compact && primaryPreview.action_items?.length ? (
              <div className="agent-output-brief-list">
                <span>下一步</span>
                <ul>{primaryPreview.action_items.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
          </div>
        )}
        {!compact && (
          <dl className="agent-output-metadata">
            <div><dt>输入</dt><dd>{output.input_refs.join("、") || "当前对话上下文"}</dd></div>
            <div><dt>依赖</dt><dd>{output.depends_on.map((item) => item.replace("agent:", "")).join("、") || "无"}</dd></div>
            <div><dt>风险</dt><dd>{output.risk_level}</dd></div>
          </dl>
        )}
        {visibleRiskFlags.map((flag) => <span className="agent-output-risk" key={flag}>{riskFlagText(flag)}</span>)}
        {!compact && output.output_previews.length > 0 && (
          <details className="agent-output-preview">
            <summary>查看结构化产物（{output.output_previews.length} 项）</summary>
            {output.output_previews.map((preview) => (
              <details className="agent-output-raw-record" key={preview.artifact_id}>
                <summary>{preview.artifact_type} · {preview.status}</summary>
                <pre>{JSON.stringify(preview.content, null, 2)}</pre>
              </details>
            ))}
          </details>
        )}
        {!compact && output.target_pages.length > 0 && (
          <label className="agent-output-target">
            <span>应用位置</span>
            <select
              value={agentOutputTargets[output.task_id] ?? output.target_pages[0]}
              onChange={(event) => setAgentOutputTargets((current) => ({
                ...current,
                [output.task_id]: event.target.value,
              }))}
            >
              {output.target_pages.map((target) => <option key={target} value={target}>{targetPageLabel(target)}</option>)}
            </select>
          </label>
        )}
        <div className="agent-output-actions">
          <button type="button" disabled={agentPlanBusy || !output.artifact_ids.length} onClick={() => void decideAgentOutput(output, "retain")}>保留</button>
          {output.agent_id === "paper_writing" ? (
            <button type="button" disabled={agentPlanBusy || !output.artifact_ids.length} onClick={() => void applyManuscriptCandidate(output)}>送入论文草稿</button>
          ) : (
            <button type="button" disabled={agentPlanBusy || !output.artifact_ids.length} onClick={() => void decideAgentOutput(output, "apply")}>应用主产物</button>
          )}
          {output.agent_id === "evidence_review" && (
            <>
            <button type="button" disabled={agentPlanBusy || !output.artifact_ids.length} onClick={() => {
              setView("audit");
              setContextTab("workspace");
              setRightPaneVisible(true);
            }}>查看证据审核</button>
            <button type="button" disabled={agentPlanBusy} onClick={() => {
              setView("knowledge");
              setContextTab("evidence");
              setRightPaneVisible(true);
            }}>打开知识库核验</button>
            </>
          )}
          {canPromoteEvidence(output) && (
            <button type="button" disabled={agentPlanBusy || !output.artifact_ids.length} onClick={() => void decideAgentOutput(output, "promote")}>申请正式证据</button>
          )}
          <button type="button" disabled={agentPlanBusy || !output.artifact_ids.length} onClick={() => void decideAgentOutput(output, "reject")}>拒绝</button>
        </div>
      </article>
    );
  };

  const renderPageMaterials = (title: string, targets: string[]) => {
    const materials = pageMaterialsFor(targets);
    return (
      <section className="output-section applied-material-section">
        <div className="output-section-heading">
          <div><h3>{title}</h3><p className="section-subtitle">仅显示研究者已应用或已提升的项目材料。</p></div>
          <span>{materials.length} 项</span>
        </div>
        {materials.length ? (
          <div className="applied-material-list">
            {materials.map((material) => (
              <article className="applied-material-card" key={material.material_id}>
                <div><strong>{agentDisplayNames[material.agent_id] ?? material.agent_id}</strong><span className={material.formalization === "formal_evidence" ? "verified-tag" : "review-tag"}>{material.formalization === "formal_evidence" ? "正式证据" : "已应用"}</span></div>
                <small>{material.artifact_type} · {material.turn_id ? `轮次 ${material.turn_id}` : "项目材料"}</small>
                <p>
                  {typeof material.content.researcher_summary === "object" && material.content.researcher_summary !== null && typeof (material.content.researcher_summary as Record<string, unknown>).summary === "string"
                    ? String((material.content.researcher_summary as Record<string, unknown>).summary)
                    : typeof material.content.researcher_summary === "string"
                      ? material.content.researcher_summary
                    : typeof material.content.title === "string"
                      ? material.content.title
                      : Object.keys(material.content).slice(0, 4).join("、") || "候选内容已写入项目材料"}
                </p>
              </article>
            ))}
          </div>
        ) : <div className="empty-output"><span className="empty-symbol">□</span><p>在产出箱选择“应用到页面”后，候选材料会出现在这里。</p></div>}
      </section>
    );
  };

  const renderFormalEvidence = () => (
    <section className="output-section formal-evidence-section">
      <div className="output-section-heading">
        <div>
          <h3>正式证据库</h3>
          <p className="section-subtitle">按稳定证据标识去重汇总；每条保留来自哪个问题和 Agent 产出的来源链。</p>
        </div>
        <span>{formalEvidence.length} 条</span>
      </div>
      {formalEvidence.length ? (
        <div className="formal-evidence-list">
          {formalEvidence.map((record) => {
            const ref = record.evidence_ref;
            const location = ref.location && typeof ref.location === "object"
              ? ref.location as Record<string, unknown>
              : null;
            const excerpt = typeof ref.excerpt === "string" ? ref.excerpt : "已核验证据片段";
            return (
              <article className="formal-evidence-card" key={record.evidence_id}>
                <div><strong>{record.evidence_id}</strong><span className="verified-tag">正式证据</span></div>
                <p>{excerpt}</p>
                <small>Chunk {String(ref.chunk_id ?? "-")} · 字符 {String(location?.char_start ?? "-")}-{String(location?.char_end ?? "-")}</small>
                <small>首次关联问题：{record.provenance[0]?.turn_id ? `轮次 ${String(record.provenance[0].turn_id)}` : "未绑定轮次"} · 已在 {record.provenance.length} 次 Agent 产出中使用</small>
              </article>
            );
          })}
        </div>
      ) : <div className="empty-output"><span className="empty-symbol">◇</span><p>已核验的证据类产物提升成功后，会在这里按证据标识汇总。</p></div>}
    </section>
  );

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
      const assistantMessageId = `assistant-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setSelectedTurnId(assistantMessageId);
      setMessages((current) => [...current, {
        id: assistantMessageId,
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
    setSelectedTurnId(null);
    setLastResponse(demoQAResponse);
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
      setSelectedTurnId(null);
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
      const next = await workflowApi.uploadControllerRawCsv(projectId, file);
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
      const next = await workflowApi.decideControllerDataPipeline(projectId, decision, decidedBy);
      setAnalysisState(next);
      setAnalysisStage(next.stage);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "数据分析审批失败");
    } finally {
      setAnalysisBusy(false);
    }
  };

  const openDataAnalysisAgentPlan = () => {
    setAnalysisError("");
    openAgentPlanner(
      "请根据当前已批准的研究方案，判断是否需要调用数据分析 Agent，并生成数据审查、处理计划、分析规格和代码草案的任务计划。",
    );
  };

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
            turn_id: turn.turn_id ?? turn.memory_id,
            mode: turn.mode ?? "discovery",
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
        setSelectedTurnId(nextMessages[nextMessages.length - 1]?.id ?? null);
        const last = turns[turns.length - 1];
        setLastResponse({
          project_id: last.project_id,
          conversation_id: last.conversation_id,
          question: last.question,
          turn_id: last.turn_id ?? last.memory_id,
          mode: last.mode ?? "discovery",
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
    setSelectedTurnId(null);
  };

  const workspaceStyle = {
    gridTemplateColumns: [
      sidebarVisible ? `${paneWidths.sidebar}px 8px` : "0px 0px",
      rightPaneVisible
        ? "minmax(420px, 1fr) 8px"
        : "minmax(0, 1fr)",
      rightPaneVisible ? `${paneWidths.output}px` : "",
    ].filter(Boolean).join(" "),
  };

  return (
    <div className={`research-app ${rightPaneVisible ? "" : "research-app-two-pane"}`} style={workspaceStyle}>
      <aside className={`research-sidebar ${sidebarVisible ? "" : "research-sidebar-hidden"}`}>
        <div className="research-brand">
          <div className="research-logo">S</div>
          <div>
            <strong>STEM-SCI</strong>
            <span>科研智能工作台</span>
          </div>
          <button
            className="header-icon-button workspace-collapse-button"
            type="button"
            title="隐藏工作区"
            onClick={() => setSidebarVisible(false)}
          >
            ←
          </button>
        </div>

        <button className="new-conversation" type="button" onClick={resetConversation}>
          <span className="ui-icon">＋</span>
          新建对话
        </button>

        <div className="sidebar-section">
          <span className="sidebar-label">工作区</span>
          <button className="sidebar-link sidebar-link-active" type="button">
            <span className="ui-icon">⌕</span>
            研究助手
          </button>
          <button className={view === "knowledge" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => { setView("knowledge"); setContextTab("evidence"); }}>
            <span className="ui-icon">▱</span>
            知识库
          </button>
          <button className={view === "codex" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => { setView("codex"); setContextTab("workspace"); }}>
            <span className="ui-icon">⌘</span>
            Codex
          </button>
          <button className={view === "analysis" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => { setView("analysis"); setContextTab("workspace"); }}>
            <span className="ui-icon">◫</span>
            数据分析
          </button>
          <button className={view === "audit" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => { setView("audit"); setContextTab("agent-work"); setRightPaneVisible(true); }}>
            <span className="ui-icon">✦</span>
            Agent 工作
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
          <button className="recent-chat" type="button" onClick={resetConversation}>
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
      {!sidebarVisible && (
        <button
          className="restore-sidebar-button"
          type="button"
          title="显示工作区"
          onClick={() => setSidebarVisible(true)}
        >
          → <span>显示工作区</span>
        </button>
      )}

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
            <article
              className={`${message.role === "user" ? "chat-message user-message" : "chat-message assistant-message"}${message.id === selectedTurnId ? " message-selected" : ""}`}
              key={message.id}
              onClick={() => {
                if (message.role === "assistant" && message.response) setSelectedTurnId(message.id);
              }}
              onKeyDown={(event) => {
                if ((event.key === "Enter" || event.key === " ") && message.role === "assistant" && message.response) {
                  event.preventDefault();
                  setSelectedTurnId(message.id);
                }
              }}
              role={message.role === "assistant" && message.response ? "button" : undefined}
              tabIndex={message.role === "assistant" && message.response ? 0 : undefined}
            >
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
                    <span className="signal-chip signal-green">
                      {message.response.mode === "formal" ? "正式证据" : "探索证据"} {message.response.citations.length} 条
                    </span>
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
            {starterAgentFeatures.map((feature) => (
              <button
                className="starter-prompt starter-agent-prompt"
                key={feature.agent}
                type="button"
                title={`体验${feature.agent} Agent：${feature.description}`}
                onClick={() => openAgentPlanner(feature.prompt)}
              >
                <strong>{feature.agent}</strong><span>{feature.description}</span>
              </button>
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
                <button
                  className="composer-tool"
                  type="button"
                  disabled={mode === "discovery" && !corpusSummary?.formal_evidence_ready}
                  title={corpusSummary?.formal_evidence_ready ? "切换正式证据或探索模式" : "正式证据尚未满足来源定位和核验条件"}
                  onClick={() => {
                    if (mode === "discovery" && !corpusSummary?.formal_evidence_ready) return;
                    setMode((current) => current === "discovery" ? "formal" : "discovery");
                  }}
                >
                  ◈ <span>{mode === "formal" ? "正式" : "探索"}</span>
                </button>
                <button
                  className="composer-tool composer-agent-tool"
                  type="button"
                  title="根据当前研究需求生成 Agent 调用计划"
                  onClick={() => openAgentPlanner()}
                >
                  ✦ <span>调用 Agent</span>
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
            <h2>{contextTab === "agent-work" ? "Agent 工作" : contextTab === "agent-plan" ? "Agent 计划" : contextTab === "agent-outputs" ? "Agent 产出箱" : contextTab === "evidence" ? "知识库证据" : view === "codex" ? "Codex" : "数据分析"}</h2>
          </div>
          <button className="header-icon-button" type="button" title="隐藏右侧面板，进入双栏模式" onClick={() => setRightPaneVisible(false)}>→</button>
        </div>
        {contextTab === "agent-work" && (
          <div className="output-content">
            <section className="output-section agent-workbench">
              <div className="output-section-heading">
                <div>
                  <span className="chat-kicker">WORK TASKS</span>
                  <h3>Agent 工作台</h3>
                  <p className="section-subtitle">先生成计划，批准后执行；所有输出先进入产出箱。</p>
                </div>
              </div>
              {agentPlan?.user_request && (
                <div className="agent-current-question">
                  <span>本轮研究问题</span>
                  <p>{agentPlan.user_request}</p>
                </div>
              )}
              <label className="agent-plan-input">
                <span>研究需求</span>
                <textarea rows={4} value={agentPlanDraft} onChange={(event) => setAgentPlanDraft(event.target.value)} placeholder="描述本轮需要完成的研究任务..." />
              </label>
              <button className="primary-inline-button full-width" type="button" disabled={agentPlanBusy || !agentPlanDraft.trim()} onClick={() => void createAgentPlan()}>
                {agentPlanBusy ? "处理中..." : "生成 Agent 计划"}
              </button>
              {agentPlans.length > 0 && (
                <div className="agent-question-history" aria-label="Agent 使用问题记录">
                  <span>Agent 使用记录</span>
                  {agentPlans.slice(0, 8).map((plan) => (
                    <button
                      key={plan.plan_id}
                      className={agentPlan?.plan_id === plan.plan_id ? "selected" : ""}
                      type="button"
                      onClick={() => selectAgentQuestion(plan)}
                    >
                      <strong>{plan.user_request}</strong>
                      <small>{plan.tasks.filter((task) => task.status === "COMPLETED").length}/{plan.tasks.length} 已完成 · {agentPlanStatusLabels[plan.status] ?? plan.status}</small>
                    </button>
                  ))}
                </div>
              )}
              {agentPlan && (
                <>
                  <div className="agent-work-plan-head">
                    <div><strong>{agentPlan.user_request}</strong><small>{agentPlan.intent_summary} · {agentPlan.planner_mode === "llm" ? "模型规划" : "受控规则规划"} · {agentPlanStatusLabels[agentPlan.status] ?? agentPlan.status}</small></div>
                    <span>{agentPlan.tasks.filter((task) => task.status === "COMPLETED").length}/{agentPlan.tasks.length} 完成</span>
                  </div>
                  <div className="agent-progress-track" aria-label="Agent 计划进度">
                    <i style={{ width: `${agentPlan.tasks.length ? Math.round(agentPlan.tasks.filter((task) => task.status === "COMPLETED").length / agentPlan.tasks.length * 100) : 0}%` }} />
                  </div>
                  <div className="agent-work-task-list">
                    {agentPlan.tasks.map((task) => {
                      const selected = selectedAgentTaskIds.includes(task.task_id);
                      const disabled = task.blocked_reason !== null || task.status === "SKIPPED";
                      return (
                        <label className={`agent-work-task ${disabled ? "agent-plan-task-disabled" : ""}`} key={task.task_id}>
                          <input type="checkbox" checked={selected} disabled={disabled || agentPlan.status !== "PENDING_APPROVAL"} onChange={() => toggleAgentTask(task.task_id)} />
                          <span><strong>{agentDisplayNames[task.agent_id] ?? task.agent_id}</strong><small>{task.reason}</small>{task.persisted_artifact_ids.length > 0 && <small>已生成 {task.persisted_artifact_ids.length} 项候选产出</small>}{task.review_note && <small>审核意见：{task.review_note}</small>}{task.error && <em>{task.error}</em>}{task.blocked_reason && <em>{task.blocked_reason}</em>}</span>
                          <b className={`agent-task-status agent-task-status-${task.status.toLowerCase()}`}>{agentTaskStatusLabels[task.status] ?? task.status}</b>
                        </label>
                      );
                    })}
                  </div>
                  {agentPlan.status === "PENDING_APPROVAL" ? (
                    <>
                      <div className="agent-execution-mode" role="group" aria-label="Agent 执行方式">
                        <button className={agentExecutionMode === "automatic" ? "selected" : ""} type="button" onClick={() => setAgentExecutionMode("automatic")}>全自动</button>
                        <button className={agentExecutionMode === "stepwise" ? "selected" : ""} type="button" onClick={() => setAgentExecutionMode("stepwise")}>逐步人工</button>
                        <small>{agentExecutionMode === "automatic" ? "按任务依赖自动执行，完成后统一审查。" : "每个 Agent 产出后暂停，确认后才继续下一步。"}</small>
                      </div>
                      <div className="agent-plan-actions">
                        <button className="secondary-inline-button" type="button" disabled={agentPlanBusy} onClick={() => void rejectAgentPlan()}>拒绝计划</button>
                        <button className="primary-inline-button" type="button" disabled={agentPlanBusy || selectedAgentTaskIds.length === 0} onClick={() => void approveAndExecuteAgentPlan()}>{agentPlanBusy ? "执行中..." : agentExecutionMode === "automatic" ? "批准并全自动执行" : "批准并执行第一项"}</button>
                      </div>
                    </>
                  ) : agentPlan.status === "WAITING_TASK_APPROVAL" ? (
                    <div className="agent-step-review">
                      <p>当前候选产出等待人工确认。确认后才会执行下一项 Agent。</p>
                      <div className="agent-plan-actions">
                        <button className="secondary-inline-button" type="button" disabled={agentPlanBusy} onClick={() => void continueStepwiseAgentPlan("rework")}>退回到对话修改</button>
                        <button className="primary-inline-button" type="button" disabled={agentPlanBusy} onClick={() => void continueStepwiseAgentPlan("approved")}>{agentPlanBusy ? "处理中..." : "确认并继续"}</button>
                      </div>
                    </div>
                  ) : agentPlan.status === "REWORK_REQUIRED" ? (
                    <div className="agent-step-review agent-step-rework">
                      <p>{agentPlan.rework_note || "当前步骤已退回。请在对话框补充修改要求，再生成新的 Agent 计划。"}</p>
                      <button className="secondary-inline-button" type="button" onClick={() => document.querySelector<HTMLTextAreaElement>(".composer-box textarea")?.focus()}>继续在对话中修改</button>
                    </div>
                  ) : null}
                  {agentPlan.risk_flags.map((flag) => <p className="workflow-control-error" key={flag}>{riskFlagText(flag)}</p>)}
                </>
              )}
              {agentPlanError && <p className="workflow-control-error" role="alert">{agentPlanError}</p>}
            </section>
            <section className="output-section agent-workbench-output">
              <div className="output-section-heading">
                <div><h3>Agent 产出</h3><p className="section-subtitle">候选输出需要人工保留或应用；证据通过核验后才可提升为正式证据。</p></div>
                <button className="plain-action" type="button" onClick={() => setAgentOutputBoxOpen((open) => !open)}>{agentOutputBoxOpen ? "收起产出" : "展开产出"}</button>
              </div>
              <div className="agent-output-scope" role="tablist" aria-label="Agent 产出范围">
                <button className={agentOutputScope === "turn" ? "selected" : ""} type="button" onClick={() => setAgentOutputScope("turn")}>当前对话轮次 {activeTurnOutputs.length}</button>
                <button className={agentOutputScope === "question" ? "selected" : ""} type="button" disabled={!agentPlan} onClick={() => setAgentOutputScope("question")}>所选问题 {selectedQuestionOutputs.length}</button>
                <button className={agentOutputScope === "project" ? "selected" : ""} type="button" onClick={() => setAgentOutputScope("project")}>项目全部 {agentOutputs.length}</button>
              </div>
              {visibleAgentOutputs.length ? (
                <div className="agent-output-list">{visibleAgentOutputs.map((output) => renderAgentOutputCard(output, !agentOutputBoxOpen))}</div>
              ) : <div className="empty-output"><span className="empty-symbol">✦</span><p>选择一条 Agent 使用问题，或执行批准的计划后在这里审查产出。</p></div>}
            </section>
            {renderPageMaterials("审查结论与修改请求", ["audit_validation"])}
            {agentOutputs.some((output) => output.agent_id === "evidence_review") && (
              <section className="output-section evidence-gate-link-section">
                <div className="output-section-heading">
                  <div>
                    <h3>证据核验与正式化</h3>
                    <p className="section-subtitle">证据 Agent 的结果先在这里审核；完成来源核验后，才能申请进入正式证据库。</p>
                  </div>
                  <span>{formalEvidence.length} 条正式证据</span>
                </div>
                <div className="workflow-control-actions">
                  <button className="secondary-inline-button" type="button" onClick={() => {
                    setView("audit");
                    setContextTab("workspace");
                    setRightPaneVisible(true);
                  }}>打开 Evidence Gate</button>
                  <button className="secondary-inline-button" type="button" onClick={() => {
                    setView("knowledge");
                    setContextTab("evidence");
                    setRightPaneVisible(true);
                  }}>查看正式证据库</button>
                </div>
              </section>
            )}
            {formalEvidence.length > 0 && renderFormalEvidence()}
          </div>
        )}

        {contextTab === "agent-plan" && (
          <div className="output-content">
            <section className="output-section agent-plan-section">
              <div className="output-section-heading">
                <div>
                  <h3>本轮调用计划</h3>
                  <p className="section-subtitle">模型只提出必要任务；勾选并批准前不会调用任何 Agent。</p>
                </div>
                <button className="plain-action" type="button" onClick={() => setAgentPlanPanelOpen((open) => !open)}>
                  {agentPlanPanelOpen ? "收起" : "展开"} · {agentPlan?.status ?? "未生成"}
                </button>
              </div>
              {agentPlanPanelOpen && (
                <>
                  <label className="agent-plan-input">
                    <span>研究需求</span>
                    <textarea rows={4} value={agentPlanDraft} onChange={(event) => setAgentPlanDraft(event.target.value)} placeholder="描述本轮希望完成的研究任务..." />
                  </label>
                  <button className="primary-inline-button full-width" type="button" disabled={agentPlanBusy || !agentPlanDraft.trim()} onClick={() => void createAgentPlan()}>
                    {agentPlanBusy ? "处理中..." : "生成调用计划"}
                  </button>
                  {agentPlans.length > 1 && (
                    <div className="agent-plan-history">
                      <span>历史计划</span>
                      {agentPlans.slice(0, 4).map((plan) => (
                        <button key={plan.plan_id} className={agentPlan?.plan_id === plan.plan_id ? "selected" : ""} type="button" onClick={() => {
                          setAgentPlan(plan);
                          setSelectedAgentTaskIds(plan.approved_task_ids.length ? plan.approved_task_ids : plan.tasks.filter((task) => task.blocked_reason === null && task.status !== "SKIPPED").map((task) => task.task_id));
                        }}>{plan.intent_summary}</button>
                      ))}
                    </div>
                  )}
                  {agentPlan && (
                    <div className="agent-plan-card">
                      <div className="agent-plan-summary">
                        <strong>{agentPlan.intent_summary}</strong>
                        <small>{agentPlan.planner_mode === "llm" ? "模型规划" : "受控规则规划"} · {agentPlan.tasks.length} 个任务</small>
                      </div>
                      {agentPlan.status === "PENDING_APPROVAL" && (
                        <div className="agent-selection-actions">
                          <button type="button" onClick={() => setSelectedAgentTaskIds(agentPlan.tasks.filter((task) => task.blocked_reason === null && task.status !== "SKIPPED").map((task) => task.task_id))}>全选可执行项</button>
                          <button type="button" onClick={() => setSelectedAgentTaskIds([])}>清空选择</button>
                        </div>
                      )}
                      <div className="agent-plan-task-list">
                        {agentPlan.tasks.map((task) => {
                          const selected = selectedAgentTaskIds.includes(task.task_id);
                          const disabled = task.blocked_reason !== null || task.status === "SKIPPED";
                          return (
                            <label className={`agent-plan-task ${disabled ? "agent-plan-task-disabled" : ""}`} key={task.task_id}>
                              <input type="checkbox" checked={selected} disabled={disabled || agentPlan.status !== "PENDING_APPROVAL"} onChange={() => toggleAgentTask(task.task_id)} />
                              <span className="agent-plan-task-copy">
                                <strong>{agentDisplayNames[task.agent_id] ?? task.agent_id}</strong>
                                <small>{task.reason}</small>
                                <span>输入：{task.input_refs.join("、") || "当前对话"}</span>
                                <span>输出：{task.expected_output_types.slice(0, 3).join("、")}</span>
                        <span>风险：{task.risk_level} · 依赖：{task.depends_on.map((item) => item.replace("agent:", "")).join("、") || "无"}</span>
                                {task.blocked_reason && <span className="workflow-control-error">{task.blocked_reason}</span>}
                              </span>
                              <span className={`agent-task-status agent-task-status-${task.status.toLowerCase()}`}>{task.status}</span>
                            </label>
                          );
                        })}
                      </div>
                      {agentPlan.status === "PENDING_APPROVAL" ? (
                        <div className="agent-plan-actions">
                          <button className="secondary-inline-button" type="button" disabled={agentPlanBusy} onClick={() => void rejectAgentPlan()}>拒绝本次计划</button>
                          <button className="primary-inline-button" type="button" disabled={agentPlanBusy || selectedAgentTaskIds.length === 0} onClick={() => void approveAndExecuteAgentPlan()}>{agentPlanBusy ? "执行中..." : "批准选中项并执行"}</button>
                        </div>
                      ) : <div className="agent-plan-status-note"><span>计划状态</span><strong>{agentPlanStatusLabels[agentPlan.status] ?? agentPlan.status}</strong></div>}
                      {agentPlan.risk_flags.map((flag) => <p className="workflow-control-error" key={flag}>{riskFlagText(flag)}</p>)}
                    </div>
                  )}
                  {agentPlanError && <p className="workflow-control-error" role="alert">{agentPlanError}</p>}
                </>
              )}
            </section>
          </div>
        )}

        {contextTab === "agent-outputs" && (
          <div className="output-content">
            <section className="output-section agent-output-section">
              <div className="output-section-heading">
                <div><h3>Agent 产出箱</h3><p className="section-subtitle">候选材料不会自动进入正式证据或专业页面。</p></div>
                <button className="plain-action" type="button" onClick={() => setAgentOutputBoxOpen((open) => !open)}>{agentOutputBoxOpen ? "收起" : "展开"}</button>
              </div>
              <div className="agent-output-scope" role="tablist" aria-label="产出范围">
                <button className={agentOutputScope === "turn" ? "selected" : ""} type="button" onClick={() => setAgentOutputScope("turn")}>当前轮次 {activeTurnOutputs.length}</button>
                <button className={agentOutputScope === "project" ? "selected" : ""} type="button" onClick={() => setAgentOutputScope("project")}>项目全部 {agentOutputs.length}</button>
              </div>
              {agentOutputBoxOpen && (agentOutputScope === "turn" ? activeTurnOutputs : agentOutputs).length ? (
                <div className="agent-output-list">{(agentOutputScope === "turn" ? activeTurnOutputs : agentOutputs).map((output) => renderAgentOutputCard(output))}</div>
              ) : agentOutputBoxOpen ? <div className="empty-output"><span className="empty-symbol">✦</span><p>批准计划并执行后，当前轮次的 Agent 输出会出现在这里。</p></div> : null}
            </section>
          </div>
        )}

        {view === "knowledge" && contextTab === "evidence" && (
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
              <div className="output-section-heading">
                <div>
                  <h3>{activeResponse?.mode === "formal" ? "本轮正式证据" : "本轮探索证据"}</h3>
                  <p className="section-subtitle">
                    {selectedTurnResponse ? "当前显示所选回答轮次的证据" : "当前回答轮次的证据"}
                  </p>
                </div>
                <span>{citations.length} 条</span>
              </div>
              <div className="evidence-list">
                {citations.map((citation, index) => (
                  <button
                    className="evidence-item"
                    type="button"
                    key={`${activeResponse?.turn_id ?? activeResponse?.memory_ref ?? "turn"}-${index}-${citation.canonical_chunk_id}`}
                    onClick={() => setSelectedCitation(citation)}
                  >
                    <div className="evidence-item-topline">
                      <span className="citation-number">{citation.citation_index || index + 1}</span>
                      <span className={isFormalCitation(citation) ? "verified-tag" : "review-tag"}>
                        {citationStatusLabel(citation)}
                      </span>
                    </div>
                    <strong>{citation.paper_title}</strong>
                    <p>{citation.excerpt}</p>
                    <small>
                      {citation.source_filename} · Chunk {citation.chunk_index} · {citationPageLabel(citation)}
                    </small>
                  </button>
                ))}
              </div>
            </section>
            {renderFormalEvidence()}
            {renderPageMaterials("候选证据与证据矩阵", ["knowledge_evidence", "evidence_gate"])}
            <section className="output-section compact-section">
              <div className="output-section-heading">
                <h3>知识库状态</h3>
                <span className={corpusSummary?.discovery_ready ? "ready-text" : "review-tag"}>
                  {corpusSummary?.formal_evidence_ready ? "正式证据可用" : corpusSummary?.discovery_ready ? "发现模式可用" : "资源缺失"}
                </span>
              </div>
              <div className="corpus-stats">
                <div><strong>{corpusSummary?.paper_count ?? "—"}</strong><small>篇论文</small></div>
                <div><strong>{corpusSummary?.vector_chunk_count ?? "—"}</strong><small>文本块</small></div>
                <div><strong>{citations.length}</strong><small>本轮证据</small></div>
              </div>
              {corpusSummary?.risk_flags.length ? (
                <p className="workflow-control-error">{corpusSummary.risk_flags.join("；")}</p>
              ) : null}
            </section>
          </div>
        )}

        {view === "codex" && contextTab === "workspace" && (
          <div className="output-content">
            <section className="codex-hero">
              <span className="codex-symbol">⌘</span>
              <h3>Agent 协作工作区</h3>
              <p>先根据当前研究需求生成调用计划，获得许可后再执行 Agent。输出会保留在项目产出箱中。</p>
              <button
                className="primary-inline-button"
                type="button"
                onClick={() => openAgentPlanner()}
              >
                使用当前问题规划 <span>→</span>
              </button>
            </section>
            {renderPageMaterials("研究方案、写作与代码候选", ["workspace", "research_questions", "research_design", "data_collection", "codex", "paper_editor"])}
            <section className="output-section">
              <div className="output-section-heading"><h3>运行环境</h3><span className="review-tag">开发模式</span></div>
              <div className="runtime-list">
                <div><span>代码提供方</span><strong>{runtimeStatus.coding_provider}</strong></div>
                <div><span>Codex CLI</span><strong>{runtimeStatus.codex_available ? "可用" : runtimeStatus.codex_reason ?? "未配置"}</strong></div>
                <div><span>SPSS</span><strong>{runtimeStatus.spss_available ? "可用" : runtimeStatus.spss_reason ?? "未配置"}</strong></div>
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>最近代码任务</h3><span>0</span></div>
              <div className="empty-output"><span className="empty-symbol">⌘</span><p>在对话中描述你的分析需求，Codex 会先生成代码草案。</p></div>
            </section>
          </div>
        )}

        {view === "analysis" && contextTab === "workspace" && (
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
                    <button className="secondary-inline-button" type="button" disabled={analysisBusy} onClick={openDataAnalysisAgentPlan}>
                      用计划调用数据分析 Agent
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
            {renderPageMaterials("数据处理与分析计划", ["data_analysis", "codex"])}
            {analysisError && <p className="upload-error" role="alert">{analysisError}</p>}
          </div>
        )}

        {view === "audit" && contextTab === "workspace" && (
          <div className="output-content">
            <section className="output-section evidence-control-section">
              <div className="output-section-heading">
                <div>
                  <h3>Evidence Gate</h3>
                  <p className="section-subtitle">上传来源并逐条核验后，才能通过证据审查。</p>
                </div>
                <span>{evidenceRows.filter((item) => item.evidence.verification_status === "source_verified" || item.evidence.verification_status === "human_verified").length} 条已核验</span>
              </div>
              <div className="workflow-control-actions">
                <button className="secondary-inline-button" disabled={evidenceBusy || !projectId} type="button" onClick={() => evidenceInputRef.current?.click()}>
                  {evidenceBusy ? "处理中..." : "上传 PDF / TXT"}
                </button>
                <button className="secondary-inline-button" disabled={evidenceBusy || !projectId} type="button" onClick={() => void searchProjectEvidence()}>
                  刷新证据
                </button>
                <input
                  ref={evidenceInputRef}
                  className="visually-hidden"
                  type="file"
                  accept=".pdf,.txt,.md,.json,application/pdf,text/plain,application/json"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void uploadEvidenceSource(file);
                  }}
                />
              </div>
              {evidenceRows.length > 0 && (
                <div className="evidence-control-list">
                  {evidenceRows.map((item) => {
                    const verified = item.evidence.verification_status === "source_verified" || item.evidence.verification_status === "human_verified";
                    return (
                      <div className="evidence-control-row" key={item.evidence.evidence_id}>
                        <div>
                          <strong>{item.evidence.excerpt.slice(0, 90)}{item.evidence.excerpt.length > 90 ? "..." : ""}</strong>
                          <small>{item.evidence.verification_status}</small>
                        </div>
                        <button className={verified ? "verified-tag" : "review-tag"} disabled={verified || evidenceBusy} type="button" onClick={() => void verifyProjectEvidence(item.evidence.evidence_id)}>
                          {verified ? "已核验" : "核验来源"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
              {evidenceError && <p className="workflow-control-error" role="alert">{evidenceError}</p>}
            </section>
            {evidenceGateOutputs.length > 0 && (
              <section className="output-section evidence-control-section">
                <div className="output-section-heading">
                  <div>
                    <h3>本轮 Agent 证据候选</h3>
                    <p className="section-subtitle">这里显示本轮证据 Agent 的实际产出；核验通过后可申请写入正式证据库。</p>
                  </div>
                  <span>{evidenceGateOutputs.length} 个 Agent 结果</span>
                </div>
                <div className="agent-output-list">
                  {evidenceGateOutputs.map((output) => renderAgentOutputCard(output))}
                </div>
              </section>
            )}
            <section className="output-section workflow-control-section">
              <div className="output-section-heading">
                <h3>科研工作流</h3>
                <span className="workflow-stage-code">{workflow?.current_stage ?? "未启动"}</span>
              </div>
              {!auth?.access_token ? (
                <p className="workflow-control-note">登录后可生成 Agent 调用计划，并在批准后完成数据审批。</p>
              ) : (
                <div className="workflow-control-body">
                  <div className="workflow-state-row">
                    <span>当前阶段</span>
                    <strong>{workflow?.current_stage ?? "等待生成 Agent 计划"}</strong>
                  </div>
                  <div className="workflow-control-note workflow-control-agent-note">
                    固定顺序调度已停用。请先在当前对话生成 Agent 计划，勾选需要的任务后再批准执行。
                    <button className="secondary-inline-button" type="button" onClick={() => openAgentPlanner()}>
                      打开 Agent 计划
                    </button>
                  </div>
                  {workflow?.data_pipeline && (
                    <div className="workflow-state-row">
                      <span>数据管线</span>
                      <strong>{dataPipelineLabels[workflow.data_pipeline.stage] ?? workflow.data_pipeline.stage}</strong>
                    </div>
                  )}

                  {workflow?.data_pipeline?.stage === "WAITING_RAW_DATA" ? (
                    <div className="workflow-control-actions">
                      <button className="primary-inline-button" disabled={workflowBusy} type="button" onClick={() => rawCsvInputRef.current?.click()}>
                        {workflowBusy ? "审查中..." : "上传原始 CSV"}
                      </button>
                      <input
                        ref={rawCsvInputRef}
                        className="visually-hidden"
                        type="file"
                        accept=".csv,text/csv"
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) void uploadRawCsv(file);
                        }}
                      />
                    </div>
                  ) : workflow?.data_pipeline?.pending_approval ? (
                    <div className="workflow-control-actions">
                      <button className="primary-inline-button" disabled={workflowBusy} type="button" onClick={() => void decideDataPipeline("approved")}>通过数据 Gate</button>
                      <button className="secondary-inline-button" disabled={workflowBusy} type="button" onClick={() => void decideDataPipeline("rejected")}>退回</button>
                    </div>
                  ) : workflow?.pending_approval_ref ? (
                    <p className="workflow-control-note">这是历史固定流程遗留的审批记录；新的研究任务请使用 Agent 计划执行。</p>
                  ) : null}
                  {workflow?.data_pipeline?.rework_reason && <p className="workflow-control-error">{workflow.data_pipeline.rework_reason}</p>}
                </div>
              )}
              {workflowError && <p className="workflow-control-error" role="alert">{workflowError}</p>}
            </section>
            <section className="audit-summary">
              <div className="audit-summary-icon">✓</div>
              <div><strong>研究链路正在审查</strong><p>当前回答已关联证据，正式发布前仍需检查数据和引用。</p></div>
            </section>
            {renderPageMaterials("审查结论与修改请求", ["audit_validation"])}
            <section className="output-section">
              <div className="output-section-heading">
                <h3>六个 Agent</h3>
                <span>
                  {agentRows.filter(([, agentId]) => {
                    const status = workflow ? workflowAgentStatus(agentId, workflow) : agentStatus(workflowSnapshot, agentId);
                    return status === "进行中" || status === "待审批" || status === "等待审批";
                  }).length} / 6 活跃
                </span>
              </div>
              <div className="agent-list">
                {agentRows.map(([index, agentId, name, description]) => {
                  const status = workflow ? workflowAgentStatus(agentId, workflow) : agentStatus(workflowSnapshot, agentId);
                  return (
                  <div className="agent-row" key={index}>
                    <span className="agent-index">{index}</span>
                    <span><strong>{name}</strong><small>{description}</small></span>
                    <span className={status === "进行中" || status === "待审批" || status === "等待审批" ? "agent-status active" : "agent-status"}>{status}</span>
                  </div>
                  );
                })}
              </div>
            </section>
            <section className="output-section">
              <div className="output-section-heading"><h3>本轮审查</h3><span>{activeResponse?.risk_flags.length ?? 0} 项提醒</span></div>
              <div className="review-list">
                {(activeResponse?.risk_flags ?? []).map((flag) => <div className="review-item" key={flag}><span>!</span><p>{flag}</p></div>)}
              </div>
              {workflowSnapshot?.pending_approval_ref && (
                <div className="audit-pending-note">
                  <strong>当前存在 Human Gate</strong>
                  <p>
                    {workflowSnapshot.last_route_decision?.selected_route ?? "当前 Agent"} 已生成候选结果，
                    需要研究者在研究流程中确认后才能继续。
                  </p>
                </div>
              )}
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
              <div><dt>回答引用序号</dt><dd>{selectedCitation.citation_index || "未提供"}</dd></div>
              <div><dt>Chunk</dt><dd>{selectedCitation.canonical_chunk_id}</dd></div>
              <div><dt>论文标识</dt><dd>{selectedCitation.canonical_paper_id}</dd></div>
              <div><dt>DOI</dt><dd>{selectedCitation.normalized_doi ?? "未提供"}</dd></div>
              <div><dt>证据状态</dt><dd>{citationStatusLabel(selectedCitation)}</dd></div>
              <div><dt>来源定位</dt><dd>{selectedCitation.source_locator_method ?? "UNRESOLVED"}</dd></div>
              <div><dt>PDF 页码</dt><dd>{citationPageLabel(selectedCitation)}</dd></div>
              <div><dt>字符范围</dt><dd>{selectedCitation.char_start != null && selectedCitation.char_end != null ? `${selectedCitation.char_start}-${selectedCitation.char_end}` : "待补充"}</dd></div>
            </dl>
            <p className="drawer-note">
              {isFormalCitation(selectedCitation)
                ? "这条材料已通过来源定位和核验，可以进入正式证据链。"
                : "这条材料目前只能用于探索，正式模式下还需要来源定位和核验。"}
            </p>
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

      {!auth && !demoMode && (
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
