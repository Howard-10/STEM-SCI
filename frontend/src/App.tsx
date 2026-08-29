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
  type WorkflowState,
  type ControllerWorkflowState,
  type DataPipelineState,
  type RuntimeStatus,
  type WorkflowTimeline,
} from "./api/workflow";
import { answerWorkflowQuestion, artifactLabels, buildWorkflowConversation, dataAnalysisClarificationsComplete, designClarificationsComplete, evidenceClarificationsComplete, findLatestWorkflowReport, formatDataAnalysisClarificationFeedback, formatDesignClarificationFeedback, formatEvidenceClarificationFeedback, formatMentorPlanningReport, formatWorkflowArtifact, formatReviewClarificationFeedback, getDataAnalysisClarificationStatus, getPlanningClarificationStatus, isPlanningClarification, planningClarificationsComplete, reviewClarificationsComplete, workflowProjectIdValid, writingClarificationsComplete, formatWritingClarificationFeedback, type DataAnalysisClarificationAnswers, type DesignClarificationAnswers, type EvidenceClarificationAnswers, type PlanningClarificationAnswers, type ReviewClarificationAnswers, type WritingClarificationAnswers } from "./workflow/conversation";
import { api } from "./api/client";
import type { SearchResult, SharedCorpusSummary } from "./types/context";
import { demoBundle, demoQAResponse, demoRuntime } from "./demo/data";
import { demoDocumentContents, demoDocumentsByProject, demoProjects } from "./demo/projectHub";

type WorkspaceView = "knowledge" | "codex" | "analysis" | "audit";
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
  const [rightPaneVisible, setRightPaneVisible] = useState(true);
  const [paneWidths, setPaneWidths] = useState<PaneWidths>({ sidebar: 246, output: 374 });
  const [draggingPane, setDraggingPane] = useState<"sidebar" | "output" | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState("");
  const [workflowTimeline, setWorkflowTimeline] = useState<WorkflowTimeline | null>(null);
  const [workflowFeedback, setWorkflowFeedback] = useState("");
  const [planningAnswers, setPlanningAnswers] = useState<PlanningClarificationAnswers>({ population: "", context: "", intervention: "", comparator: "", outcome: "" });
  const [evidenceAnswers, setEvidenceAnswers] = useState<EvidenceClarificationAnswers>({ goal: "", timeRange: "", sources: "", preferences: "", outputs: "" });
  const [designAnswers, setDesignAnswers] = useState<DesignClarificationAnswers>({ designType: "", samplePlan: "", timepoints: "", analysisModel: "", ethics: "" });
  const [designClarificationsSubmitted, setDesignClarificationsSubmitted] = useState(false);
  const [dataAnalysisAnswers, setDataAnalysisAnswers] = useState<DataAnalysisClarificationAnswers>({ dataSource: "", variables: "", missingData: "", mode: "", privacy: "" });
  const [dataAnalysisClarificationsSubmitted, setDataAnalysisClarificationsSubmitted] = useState(false);
  const [writingAnswers, setWritingAnswers] = useState<WritingClarificationAnswers>({ scope: "", languages: "", format: "", boundary: "" });
  const [writingClarificationsSubmitted, setWritingClarificationsSubmitted] = useState(false);
  const [reviewAnswers, setReviewAnswers] = useState<ReviewClarificationAnswers>({ scope: "", focus: "", threshold: "" });
  const [reviewClarificationsSubmitted, setReviewClarificationsSubmitted] = useState(false);
  const [evidenceRows, setEvidenceRows] = useState<SearchResult[]>([]);
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const [corpusSummary, setCorpusSummary] = useState<SharedCorpusSummary | null>(null);

  useEffect(() => {
    if (!auth?.access_token || !projectId) return;
    void workflowApi.getTimeline(projectId).then(setWorkflowTimeline).catch(() => setWorkflowTimeline(null));
  }, [auth?.access_token, projectId]);

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
  const mentorApprovalBlocked = workflowTimeline?.workflow_state.last_route_decision?.selected_route === "mentor_planning"
    && !getPlanningClarificationStatus(findLatestWorkflowReport(workflowTimeline, "mentor_planning")?.artifacts ?? []).complete;

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
    void api.listSharedCorpora().then((corpora) => {
      if (mounted) setCorpusSummary(corpora[0] ?? null);
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

  const reloadWorkflowTimeline = async () => {
    if (!auth?.access_token || !projectId) {
      setWorkflowTimeline(null);
      return;
    }
    try {
      setWorkflowTimeline(await workflowApi.getTimeline(projectId));
    } catch {
      setWorkflowTimeline(null);
    }
  };

  const submitWorkflowFeedback = async (agentId: string, action: "rerun" | "pause") => {
    if (!workflowTimeline || !workflowFeedback.trim()) return;
    if (!workflowProjectIdValid(projectId)) {
      setWorkflowError("当前未选择研究项目，请先在项目列表中选择项目。");
      return;
    }
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: agentId,
        stage: workflowTimeline.workflow_state.current_stage,
        action,
        feedback: workflowFeedback.trim(),
      });
      setWorkflow(result.workflow_state);
      setWorkflowFeedback("");
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法保存阶段反馈");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitPlanningClarifications = async () => {
    if (!planningClarificationsComplete(planningAnswers)) return;
    setWorkflowFeedback([
      `研究对象：${planningAnswers.population}`,
      `研究场景：${planningAnswers.context}`,
      `干预与对照：${planningAnswers.intervention} vs ${planningAnswers.comparator}`,
      `主要指标：${planningAnswers.outcome}`,
    ].join("；"));
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: "mentor_planning",
        stage: workflowTimeline?.workflow_state.current_stage ?? "WAITING_HUMAN",
        action: "rerun",
        feedback: [
          `研究对象：${planningAnswers.population}`,
          `研究场景：${planningAnswers.context}`,
          `干预与对照：${planningAnswers.intervention} vs ${planningAnswers.comparator}`,
          `主要指标：${planningAnswers.outcome}`,
        ].join("；"),
      });
      setWorkflow(result.workflow_state);
      setPlanningAnswers({ population: "", context: "", intervention: "", comparator: "", outcome: "" });
      setWorkflowFeedback("");
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法提交导师规划补充信息");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitEvidenceClarifications = async () => {
    if (!workflowTimeline || !evidenceClarificationsComplete(evidenceAnswers)) return;
    if (!workflowProjectIdValid(projectId)) {
      setWorkflowError("当前未选择研究项目，请先在项目列表中选择项目。");
      return;
    }
    const feedback = formatEvidenceClarificationFeedback(evidenceAnswers);
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: "evidence_review",
        stage: workflowTimeline.workflow_state.current_stage,
        action: "rerun",
        feedback,
      });
      setWorkflow(result.workflow_state);
      setEvidenceAnswers({ goal: "", timeRange: "", sources: "", preferences: "", outputs: "" });
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法提交证据检索条件");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitDesignClarifications = async () => {
    if (!workflowTimeline || !designClarificationsComplete(designAnswers) || !workflowProjectIdValid(projectId)) return;
    const feedback = formatDesignClarificationFeedback(designAnswers);
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: "research_design",
        stage: workflowTimeline.workflow_state.current_stage,
        action: "rerun",
        feedback,
      });
      setWorkflow(result.workflow_state);
      setDesignAnswers({ designType: "", samplePlan: "", timepoints: "", analysisModel: "", ethics: "" });
      setDesignClarificationsSubmitted(true);
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法提交研究设计条件");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitDataAnalysisClarifications = async () => {
    if (!workflowTimeline || !dataAnalysisClarificationsComplete(dataAnalysisAnswers) || !workflowProjectIdValid(projectId)) return;
    const feedback = formatDataAnalysisClarificationFeedback(dataAnalysisAnswers);
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: "data_analysis",
        stage: workflowTimeline.workflow_state.current_stage,
        action: "rerun",
        feedback,
      });
      setWorkflow(result.workflow_state);
      setDataAnalysisClarificationsSubmitted(true);
      setDataAnalysisAnswers({ dataSource: "", variables: "", missingData: "", mode: "", privacy: "" });
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法提交数据分析条件");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitWritingClarifications = async () => {
    if (!workflowTimeline || !writingClarificationsComplete(writingAnswers) || !workflowProjectIdValid(projectId)) return;
    const feedback = formatWritingClarificationFeedback(writingAnswers);
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: "paper_writing",
        stage: workflowTimeline.workflow_state.current_stage,
        action: "rerun",
        feedback,
      });
      setWorkflow(result.workflow_state);
      setWritingClarificationsSubmitted(true);
      setWritingAnswers({ scope: "", languages: "", format: "", boundary: "" });
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法提交论文写作条件");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitReviewClarifications = async () => {
    if (!workflowTimeline || !reviewClarificationsComplete(reviewAnswers) || !workflowProjectIdValid(projectId)) return;
    const feedback = formatReviewClarificationFeedback(reviewAnswers);
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.submitFeedback(projectId, {
        agent_id: "independent_review",
        stage: workflowTimeline.workflow_state.current_stage,
        action: "rerun",
        feedback,
      });
      setWorkflow(result.workflow_state);
      setReviewClarificationsSubmitted(true);
      setReviewAnswers({ scope: "", focus: "", threshold: "" });
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法提交独立审查条件");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitWorkflowFeedbackAndContinue = async (agentId: string) => {
    if (!workflowTimeline || !workflowFeedback.trim()) return;
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      await workflowApi.submitFeedback(projectId, {
        agent_id: agentId,
        stage: workflowTimeline.workflow_state.current_stage,
        action: "pause",
        feedback: workflowFeedback.trim(),
      });
      if (workflowTimeline.workflow_state.pending_approval_ref) {
        await workflowApi.approve(projectId, "approved", auth?.user.username ?? "researcher");
      }
      const next = await workflowApi.runNext(projectId);
      setWorkflow(next.workflow_state);
      setWorkflowFeedback("");
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法保存意见并继续流程");
    } finally {
      setWorkflowBusy(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    setWorkflowError("");
    if (!auth?.access_token || !projectId) {
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

  const startWorkflow = async () => {
    if (!activeProject || workflowBusy) return;
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.startProject({
        project_id: projectId,
        research_intent: activeProject.research_direction || activeProject.title,
      });
      setWorkflow(result.workflow_state);
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "研究流程启动失败");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const runNextWorkflowStage = async () => {
    if (!workflowProjectIdValid(projectId)) {
      setWorkflowError("当前未选择研究项目，请先在项目列表中选择项目。");
      return;
    }
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      const result = await workflowApi.runNext(projectId);
      setWorkflow(result.workflow_state);
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "无法调度下一阶段");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const decideWorkflow = async (decision: "approved" | "rejected") => {
    if (!workflowProjectIdValid(projectId)) {
      setWorkflowError("当前未选择研究项目，请先在项目列表中选择项目。");
      return;
    }
    if (decision === "approved" && workflowTimeline?.workflow_state.last_route_decision?.selected_route === "mentor_planning") {
      const mentorReport = findLatestWorkflowReport(workflowTimeline, "mentor_planning");
      if (mentorReport) {
        const status = getPlanningClarificationStatus(mentorReport.artifacts);
        if (!status.complete) {
          setWorkflowError(`请先补充：${status.missing.join("、")}，再通过候选方案。`);
          return;
        }
      }
    }
    if (decision === "approved" && workflowTimeline?.workflow_state.last_route_decision?.selected_route === "independent_review" && !reviewClarificationsSubmitted) {
      setWorkflowError("请先填写独立审查范围、重点和发布门槛，再通过候选方案。");
      return;
    }
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      await workflowApi.approve(projectId, decision, auth?.user.username ?? "researcher");
      await refreshWorkflow();
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "流程审批失败");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const uploadRawCsv = async (file: File) => {
    setWorkflowBusy(true);
    setWorkflowError("");
    try {
      await workflowApi.uploadRawCsv(projectId, file);
      await refreshWorkflow();
      await reloadWorkflowTimeline();
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
      await reloadWorkflowTimeline();
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : "数据 Gate 审批失败");
    } finally {
      setWorkflowBusy(false);
    }
  };

  const submitQuestion = async (value = question) => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
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
      const workflowCommand = /^(确定|确认|同意|开始|继续|通过|下一步|进入下一阶段|开始进行导师规划|确认规划|确认方案|通过候选方案|调度下一 ?Agent)[。！!。 ]*$/iu.test(trimmed);
      const workflowState = workflow ?? workflowTimeline?.workflow_state;
      if (workflowCommand && auth?.access_token && activeProject) {
        if (workflowState?.pending_approval_ref) {
          if (workflowTimeline?.workflow_state.last_route_decision?.selected_route === "mentor_planning") {
            const mentorReport = findLatestWorkflowReport(workflowTimeline, "mentor_planning");
            if (mentorReport) {
              const status = getPlanningClarificationStatus(mentorReport.artifacts);
              if (!status.complete) {
                setMessages((current) => [...current, { id: `assistant-planning-required-${Date.now()}`, role: "assistant", content: `请先补充导师规划信息：${status.missing.join("、")}。填写下方澄清卡并点击“提交并重新规划”，完成后才能通过候选方案。` }]);
                return;
              }
            }
          }
          await workflowApi.approve(projectId, "approved", auth.user.username);
          await refreshWorkflow();
          await reloadWorkflowTimeline();
          setMessages((current) => [...current, {
            id: `assistant-workflow-approved-${Date.now()}`,
            role: "assistant",
            content: "当前阶段成果已确认。请再次输入“继续”或点击“调度下一 Agent”进入下一阶段。",
          }]);
          return;
        }
        if (workflowState) {
          const next = await workflowApi.runNext(projectId);
          setWorkflow(next.workflow_state);
          await reloadWorkflowTimeline();
          setMessages((current) => [...current, {
            id: `assistant-workflow-next-${Date.now()}`,
            role: "assistant",
            content: "已开始下一阶段 Agent 调度，完成后将生成可审核的阶段报告。",
          }]);
          return;
        }
        const planning = await workflowApi.startProject({
          project_id: projectId,
          research_intent: activeProject.research_direction || activeProject.title,
        });
        setWorkflow(planning.workflow_state);
        setWorkflowTimeline(await workflowApi.getTimeline(projectId));
        setMessages((current) => [...current, {
          id: `assistant-workflow-start-${Date.now()}`,
          role: "assistant",
          content: "已开始导师规划。请审核研究边界、问题树与可行性方案。",
        }]);
        return;
      }
      let targetProjectId = projectId;
      if (!activeProject) {
        if (!auth?.access_token) throw new Error("请先登录并创建研究项目");
        const created = await authApi.createProject(auth.access_token, {
          title: "未命名研究项目",
          research_direction: trimmed,
          abstract: null,
        });
        targetProjectId = created.project_id;
        setProjects((current) => [created, ...current.filter((item) => item.project_id !== created.project_id)]);
        setProjectId(created.project_id);
        const planning = await workflowApi.startProject({
          project_id: created.project_id,
          research_intent: trimmed,
        });
        setWorkflow(planning.workflow_state);
        setWorkflowTimeline(await workflowApi.getTimeline(created.project_id));
        setMessages((current) => [...current, {
          id: `assistant-workflow-${Date.now()}`,
          role: "assistant",
          content: "已根据你的研究思路启动项目工作流。请先审核导师规划的研究边界、问题树与可行性方案。",
        }]);
        return;
      }
      if (auth?.access_token && !workflow) {
        const planning = await workflowApi.startProject({
          project_id: targetProjectId,
          research_intent: trimmed,
        });
        setWorkflow(planning.workflow_state);
        setWorkflowTimeline(await workflowApi.getTimeline(targetProjectId));
        setMessages((current) => [...current, {
          id: `assistant-workflow-${Date.now()}`,
          role: "assistant",
          content: "已根据你的研究思路启动项目工作流。请先审核导师规划的研究边界、问题树与可行性方案。",
        }]);
        return;
      }
      const pendingMentor = workflowTimeline?.workflow_state.pending_approval_ref
        && workflowTimeline.agent_runs.some((run) => run.agent_id === "mentor_planning");
      if (pendingMentor && isPlanningClarification(trimmed)) {
        const feedbackResult = await workflowApi.submitFeedback(projectId, {
          agent_id: "mentor_planning",
          stage: workflowTimeline.workflow_state.current_stage,
          action: "rerun",
          feedback: trimmed,
        });
        if (feedbackResult.workflow_state) setWorkflow(feedbackResult.workflow_state);
        await reloadWorkflowTimeline();
        setMessages((current) => [...current, {
          id: `assistant-planning-rerun-${Date.now()}`,
          role: "assistant",
          content: "已收到你的补充信息，正在据此重新生成导师规划。新的研究边界、问题树和可行性方案生成后会再次请你审核。",
        }]);
        return;
      }
      const workflowAnswer = workflowTimeline && answerWorkflowQuestion(trimmed, workflowTimeline);
      if (workflowAnswer) {
        setMessages((current) => [...current, {
          id: `assistant-workflow-answer-${Date.now()}`,
          role: "assistant",
          content: workflowAnswer,
        }]);
        return;
      }
      const response = auth?.access_token
        ? await authApi.projectChatAnswer(auth.access_token, {
          project_id: targetProjectId,
          question: trimmed,
          mode,
          conversation_id: conversationId,
          allow_llm: true,
          top_k: 8,
          token_budget: 3000,
        })
        : await qaApi.answer({
          project_id: targetProjectId,
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
          <button className={view === "analysis" ? "sidebar-link sidebar-link-active" : "sidebar-link"} type="button" onClick={() => setView("analysis")}>
            <span className="ui-icon">◫</span>
            数据分析
          </button>
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
          {workflowTimeline && buildWorkflowConversation(workflowTimeline).map((item, index) => (
            item.kind === "workflow-route" ? (
              <article className="chat-message assistant-message workflow-conversation-card" key="workflow-route">
                <div className="assistant-mark">S</div>
                <div className="message-body">
                  <div className="message-meta">STEM-SCI <span>·</span> 项目执行路线</div>
                  <p>工作流会在每个阶段完成后暂停，等待你的审核与决定。</p>
                  <ol>{item.steps.map((step) => <li key={step.agentId}><strong>{step.name}</strong>：{step.task}</li>)}</ol>
                </div>
              </article>
            ) : (
              <article className="chat-message assistant-message workflow-conversation-card" key={`workflow-${item.agentId}-${index}`}>
                <div className="assistant-mark">S</div>
                <div className="message-body">
                  <div className="message-meta">STEM-SCI <span>·</span> {item.agentName} 阶段报告</div>
                  <p>{item.pendingApproval ? "本阶段已完成，等待你审核候选成果。" : "已保留本阶段运行记录。"}</p>
                  {item.agentId === "mentor_planning" && item.artifacts.length ? (
                    <section className="workflow-artifact-text mentor-planning-summary">
                      <p>{formatMentorPlanningReport(item.artifacts)}</p>
                    </section>
                  ) : item.artifacts.length ? item.artifacts.map((artifact, artifactIndex) => (
                    <section className="workflow-artifact-text" key={`${artifact.artifactType}-${artifactIndex}`}>
                      <h4>{artifactLabels[artifact.artifactType] ?? artifact.artifactType}</h4>
                      <p>{formatWorkflowArtifact(artifact.artifactType, artifact.body)}</p>
                    </section>
                  )) : <p>输出内容不可用。</p>}
                  {item.pendingApproval && item.agentId === "mentor_planning" && (() => {
                    const status = getPlanningClarificationStatus(item.artifacts);
                    return <section className="planning-clarification-card">
                      <div className="planning-clarification-heading"><strong>导师规划确认</strong><span className={status.complete ? "clarification-complete" : "clarification-pending"}>{status.complete ? "信息已完整" : `${status.missing.length} 项待补充`}</span></div>
                      <p>请补充关键研究条件。提交后系统会重新生成导师规划，再开放审批。</p>
                      <div className="planning-clarification-grid">
                        {["研究对象", "研究场景", "干预与对照", "主要指标"].map((label) => <span className={status.missing.includes(label) ? "clarification-item missing" : "clarification-item"} key={label}><i />{label}<small>{status.missing.includes(label) ? "待补充" : "已识别"}</small></span>)}
                      </div>
                    </section>;
                  })()}
                  {item.pendingApproval && <div className="workflow-control-actions">
                    <button className="primary-inline-button" disabled={workflowBusy || (item.agentId === "mentor_planning" && !getPlanningClarificationStatus(item.artifacts).complete) || (item.agentId === "research_design" && !designClarificationsSubmitted) || (item.agentId === "data_analysis" && !dataAnalysisClarificationsSubmitted) || (item.agentId === "paper_writing" && !writingClarificationsSubmitted) || (item.agentId === "independent_review" && !reviewClarificationsSubmitted)} type="button" onClick={() => void decideWorkflow("approved")}>通过候选方案</button>
                    <button className="secondary-inline-button" disabled={workflowBusy} type="button" onClick={() => void decideWorkflow("rejected")}>退回</button>
                  </div>}
                  {item.isLatest && !item.pendingApproval && (workflow ?? workflowTimeline?.workflow_state) && !["VERIFIED", "RELEASED", "BLOCKED", "REWORK"].includes((workflow ?? workflowTimeline?.workflow_state)?.current_stage ?? "") && <div className="workflow-control-actions">
                    <button className="primary-inline-button" disabled={workflowBusy} type="button" onClick={() => void runNextWorkflowStage()}>{workflowBusy ? "调度中..." : "继续下一 Agent"}</button>
                  </div>}
                  {item.pendingApproval && item.agentId === "mentor_planning" ? <section className="planning-clarification-form">
                    <div className="planning-form-grid">
                      <label><span>研究对象</span><input value={planningAnswers.population} onChange={(event) => setPlanningAnswers((current) => ({ ...current, population: event.target.value }))} placeholder="例如：大一物理师范生" /></label>
                      <label><span>研究场景</span><input value={planningAnswers.context} onChange={(event) => setPlanningAnswers((current) => ({ ...current, context: event.target.value }))} placeholder="例如：大学物理力学实验课" /></label>
                      <label><span>干预方法</span><input value={planningAnswers.intervention} onChange={(event) => setPlanningAnswers((current) => ({ ...current, intervention: event.target.value }))} placeholder="例如：分层 AI 支架" /></label>
                      <label><span>对照条件</span><input value={planningAnswers.comparator} onChange={(event) => setPlanningAnswers((current) => ({ ...current, comparator: event.target.value }))} placeholder="例如：常规提示" /></label>
                      <label className="planning-form-wide"><span>主要指标</span><input value={planningAnswers.outcome} onChange={(event) => setPlanningAnswers((current) => ({ ...current, outcome: event.target.value }))} placeholder="例如：物理建模迁移得分" /></label>
                    </div>
                    <div className="planning-form-footer"><span>四项填写完整后将重新生成导师规划。</span><button type="button" disabled={workflowBusy || !planningClarificationsComplete(planningAnswers)} onClick={() => void submitPlanningClarifications()}>提交并重新规划</button></div>
                  </section> : item.pendingApproval && item.agentId === "evidence_review" ? <section className="planning-clarification-form evidence-clarification-form">
                    <div className="planning-clarification-heading"><strong>证据检索确认</strong><span className="clarification-pending">确认后重新检索</span></div>
                    <p>导师规划中的研究对象、场景、干预和指标已自动带入。请补充本轮检索范围，系统会据此筛选、核验并整理证据。</p>
                    <div className="planning-form-grid">
                      <label className="planning-form-wide"><span>检索目标 <em>必填</em></span><input value={evidenceAnswers.goal} onChange={(event) => setEvidenceAnswers((current) => ({ ...current, goal: event.target.value }))} placeholder="例如：验证分层 AI 支架是否改善迁移得分" /></label>
                      <label><span>文献范围 <em>必填</em></span><input value={evidenceAnswers.timeRange} onChange={(event) => setEvidenceAnswers((current) => ({ ...current, timeRange: event.target.value }))} placeholder="例如：2020-2026，中英文期刊" /></label>
                      <label><span>证据来源 <em>必填</em></span><input value={evidenceAnswers.sources} onChange={(event) => setEvidenceAnswers((current) => ({ ...current, sources: event.target.value }))} placeholder="例如：平台知识库与已上传 PDF" /></label>
                      <label><span>筛选偏好 <small>可选</small></span><input value={evidenceAnswers.preferences} onChange={(event) => setEvidenceAnswers((current) => ({ ...current, preferences: event.target.value }))} placeholder="例如：优先物理教育实证研究" /></label>
                      <label><span>期望产出 <small>可选</small></span><input value={evidenceAnswers.outputs ?? ""} onChange={(event) => setEvidenceAnswers((current) => ({ ...current, outputs: event.target.value }))} placeholder="例如：证据矩阵、研究空白" /></label>
                    </div>
                    <div className="planning-form-footer"><span>填写三项必填信息后，才会重新执行证据检索。</span><button type="button" disabled={workflowBusy || !evidenceClarificationsComplete(evidenceAnswers)} onClick={() => void submitEvidenceClarifications()}>确认并重新检索</button></div>
                  </section> : item.pendingApproval && item.agentId === "research_design" ? <section className="planning-clarification-form design-clarification-form">
                    <div className="planning-clarification-heading"><strong>研究设计确认</strong><span className="clarification-pending">确认后生成方案</span></div>
                    <p>研究对象、场景、干预、对照、指标和证据已自动继承。请确认研究设计的实施条件，系统将生成研究协议、测量方案和预注册分析计划。</p>
                    <div className="planning-form-grid">
                      <label><span>研究设计 <em>必填</em></span><input value={designAnswers.designType} onChange={(event) => setDesignAnswers((current) => ({ ...current, designType: event.target.value }))} placeholder="例如：平行随机对照" /></label>
                      <label><span>样本与招募 <em>必填</em></span><input value={designAnswers.samplePlan} onChange={(event) => setDesignAnswers((current) => ({ ...current, samplePlan: event.target.value }))} placeholder="例如：招募大一物理师范生" /></label>
                      <label><span>测量时间点 <em>必填</em></span><input value={designAnswers.timepoints} onChange={(event) => setDesignAnswers((current) => ({ ...current, timepoints: event.target.value }))} placeholder="例如：基线、干预后、迁移任务" /></label>
                      <label><span>统计模型 <em>必填</em></span><input value={designAnswers.analysisModel} onChange={(event) => setDesignAnswers((current) => ({ ...current, analysisModel: event.target.value }))} placeholder="例如：线性混合模型" /></label>
                      <label className="planning-form-wide"><span>伦理与排除规则 <em>必填</em></span><input value={designAnswers.ethics} onChange={(event) => setDesignAnswers((current) => ({ ...current, ethics: event.target.value }))} placeholder="例如：已确认课程伦理要求，并采用预注册技术失败排除规则" /></label>
                    </div>
                    <div className="planning-form-footer"><span>五项填写完整后，才会重新生成研究设计。</span><button type="button" disabled={workflowBusy || !designClarificationsComplete(designAnswers)} onClick={() => void submitDesignClarifications()}>确认并重新生成</button></div>
                  </section> : item.pendingApproval && item.agentId === "data_analysis" ? <section className="planning-clarification-form analysis-clarification-form">
                    <div className="planning-clarification-heading"><strong>数据分析确认</strong><span className="clarification-pending">确认后建立数据管道</span></div>
                    <p>研究方案、预注册分析计划和结果指标已自动继承。请确认数据文件、变量、缺失值、分析模式和隐私规则；确认后才能上传 CSV 并开始数据审查。</p>
                    <div className="planning-form-grid">
                      <label className="planning-form-wide"><span>数据来源 <em>必填</em></span><input value={dataAnalysisAnswers.dataSource} onChange={(event) => setDataAnalysisAnswers((current) => ({ ...current, dataSource: event.target.value }))} placeholder="例如：大学物理实验课程 CSV" /></label>
                      <label><span>必需变量 <em>必填</em></span><input value={dataAnalysisAnswers.variables} onChange={(event) => setDataAnalysisAnswers((current) => ({ ...current, variables: event.target.value }))} placeholder="例如：group, transfer_score" /></label>
                      <label><span>缺失值处理 <em>必填</em></span><input value={dataAnalysisAnswers.missingData} onChange={(event) => setDataAnalysisAnswers((current) => ({ ...current, missingData: event.target.value }))} placeholder="例如：按预注册规则处理" /></label>
                      <label><span>分析模式 <em>必填</em></span><input value={dataAnalysisAnswers.mode} onChange={(event) => setDataAnalysisAnswers((current) => ({ ...current, mode: event.target.value }))} placeholder="例如：Python 单引擎" /></label>
                      <label><span>隐私规则 <em>必填</em></span><input value={dataAnalysisAnswers.privacy} onChange={(event) => setDataAnalysisAnswers((current) => ({ ...current, privacy: event.target.value }))} placeholder="例如：去标识化，不含直接身份信息" /></label>
                    </div>
                    <div className="planning-form-footer"><span>五项填写完整后，才会生成分析规格并开放审批。</span><button type="button" disabled={workflowBusy || !dataAnalysisClarificationsComplete(dataAnalysisAnswers)} onClick={() => void submitDataAnalysisClarifications()}>确认并生成分析规格</button></div>
                  </section> : item.pendingApproval && item.agentId === "paper_writing" ? <section className="planning-clarification-form writing-clarification-form">
                    <div className="planning-clarification-heading"><strong>论文写作确认</strong><span className="clarification-pending">确认后生成双语稿</span></div>
                    <p>研究方案、证据矩阵和已验证结果会自动继承。请确认写作范围、语言、目标格式和主张边界；系统将生成论文大纲、双语草稿和引用映射。</p>
                    <div className="planning-form-grid">
                      <label><span>写作范围 <em>必填</em></span><input value={writingAnswers.scope} onChange={(event) => setWritingAnswers((current) => ({ ...current, scope: event.target.value }))} placeholder="例如：完整研究论文" /></label>
                      <label><span>语言版本 <em>必填</em></span><input value={writingAnswers.languages} onChange={(event) => setWritingAnswers((current) => ({ ...current, languages: event.target.value }))} placeholder="例如：中文和英文" /></label>
                      <label><span>目标格式 <em>必填</em></span><input value={writingAnswers.format} onChange={(event) => setWritingAnswers((current) => ({ ...current, format: event.target.value }))} placeholder="例如：教育技术类期刊" /></label>
                      <label><span>主张边界 <em>必填</em></span><input value={writingAnswers.boundary} onChange={(event) => setWritingAnswers((current) => ({ ...current, boundary: event.target.value }))} placeholder="例如：结果只引用已验证结果卡" /></label>
                    </div>
                    <div className="planning-form-footer"><span>四项填写完整后，才会生成论文候选稿。</span><button type="button" disabled={workflowBusy || !writingClarificationsComplete(writingAnswers)} onClick={() => void submitWritingClarifications()}>确认并生成论文稿</button></div>
                  </section> : item.pendingApproval && item.agentId === "independent_review" ? <section className="planning-clarification-form review-clarification-form">
                    <div className="planning-clarification-heading"><strong>独立审查确认</strong><span className="clarification-pending">确认后形成发布建议</span></div>
                    <p>研究协议、证据引用和论文草稿将以只读方式交给审查 Agent。请明确本轮审查边界，系统会生成问题、修改请求和总体建议。</p>
                    <div className="planning-form-grid">
                      <label className="planning-form-wide"><span>审查范围 <em>必填</em></span><input value={reviewAnswers.scope} onChange={(event) => setReviewAnswers((current) => ({ ...current, scope: event.target.value }))} placeholder="例如：完整发布前审查" /></label>
                      <label className="planning-form-wide"><span>审查重点 <em>必填</em></span><input value={reviewAnswers.focus} onChange={(event) => setReviewAnswers((current) => ({ ...current, focus: event.target.value }))} placeholder="例如：引用、方法、可复现性和主张边界" /></label>
                      <label className="planning-form-wide"><span>发布门槛 <em>必填</em></span><input value={reviewAnswers.threshold} onChange={(event) => setReviewAnswers((current) => ({ ...current, threshold: event.target.value }))} placeholder="例如：发现重大问题则退回，全部通过后允许申请发布" /></label>
                    </div>
                    <div className="planning-form-footer"><span>三项填写完整后，才会生成独立审查报告。</span><button type="button" disabled={workflowBusy || !reviewClarificationsComplete(reviewAnswers)} onClick={() => void submitReviewClarifications()}>确认并执行审查</button></div>
                  </section> : item.pendingApproval && <div className="workflow-feedback-actions">
                    <textarea value={workflowFeedback} onChange={(event) => setWorkflowFeedback(event.target.value)} placeholder={item.agentId === "mentor_planning" ? "请填写：研究对象、研究场景、干预与对照、主要指标..." : "补充你的研究思路或修改意见..."} rows={3} />
                    <button type="button" disabled={workflowBusy || !workflowFeedback.trim()} onClick={() => void submitWorkflowFeedback(item.agentId, "pause")}>保存意见并暂停</button>
                    <button type="button" disabled={workflowBusy || !workflowFeedback.trim()} onClick={() => void submitWorkflowFeedbackAndContinue(item.agentId)}>保存意见并继续</button>
                    <button type="button" disabled={workflowBusy || !workflowFeedback.trim()} onClick={() => void submitWorkflowFeedback(item.agentId, "rerun")}>{item.agentId === "mentor_planning" ? "提交并重新规划" : "基于意见重新执行当前 Agent"}</button>
                  </div>}
                  {workflowError && <p className="workflow-control-error" role="alert">{workflowError}</p>}
                </div>
              </article>
            )
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
            <h2>{view === "knowledge" ? "知识库" : view === "codex" ? "Codex 工作区" : view === "analysis" ? "数据分析" : "数据审查"}</h2>
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
              <div className="output-section-heading">
                <h3>知识库状态</h3>
                <span className={corpusSummary?.discovery_ready ? "ready-text" : "review-tag"}>
                  {corpusSummary?.formal_evidence_ready ? "正式证据可用" : corpusSummary?.discovery_ready ? "发现模式可用" : "资源缺失"}
                </span>
              </div>
              <div className="corpus-stats">
                <div><strong>{corpusSummary?.paper_count ?? "—"}</strong><small>篇论文</small></div>
                <div><strong>{corpusSummary?.vector_chunk_count ?? "—"}</strong><small>文本块</small></div>
                <div><strong>{demoBundle.evidence_refs.length}</strong><small>本轮证据</small></div>
              </div>
              {corpusSummary?.risk_flags.length ? (
                <p className="workflow-control-error">{corpusSummary.risk_flags.join("；")}</p>
              ) : null}
            </section>
          </div>
        )}

        {view === "codex" && (
          <div className="output-content">
            <section className="codex-hero">
              <span className="codex-symbol">⌘</span>
              <h3>面向研究的代码工作区</h3>
              <p>在当前项目中编写、解释和审查 Python 分析代码。代码执行仍然需要经过数据审查和人工确认。</p>
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
            </section>
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

        {view === "audit" && (
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
            <section className="output-section workflow-control-section">
              <div className="output-section-heading">
                <h3>科研工作流</h3>
                <span className="workflow-stage-code">{workflow?.current_stage ?? "未启动"}</span>
              </div>
              {!auth?.access_token ? (
                <p className="workflow-control-note">登录后可启动六 Agent 工作流并完成数据审批。</p>
              ) : !workflow ? (
                <button className="primary-inline-button" disabled={workflowBusy} type="button" onClick={() => void startWorkflow()}>
                  {workflowBusy ? "启动中..." : "启动工作流"}
                </button>
              ) : (
                <div className="workflow-control-body">
                  <div className="workflow-state-row">
                    <span>当前阶段</span>
                    <strong>{workflow.current_stage}</strong>
                  </div>
                  {workflow.data_pipeline && (
                    <div className="workflow-state-row">
                      <span>数据管线</span>
                      <strong>{dataPipelineLabels[workflow.data_pipeline.stage] ?? workflow.data_pipeline.stage}</strong>
                    </div>
                  )}

                  {workflow.data_pipeline?.stage === "WAITING_RAW_DATA" ? (
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
                  ) : workflow.data_pipeline?.pending_approval ? (
                    <div className="workflow-control-actions">
                      <button className="primary-inline-button" disabled={workflowBusy} type="button" onClick={() => void decideDataPipeline("approved")}>通过数据 Gate</button>
                      <button className="secondary-inline-button" disabled={workflowBusy} type="button" onClick={() => void decideDataPipeline("rejected")}>退回</button>
                    </div>
                  ) : workflow.pending_approval_ref ? (
                    <div className="workflow-control-actions">
                      <button className="primary-inline-button" disabled={workflowBusy || mentorApprovalBlocked} type="button" onClick={() => void decideWorkflow("approved")}>通过候选方案</button>
                      <button className="secondary-inline-button" disabled={workflowBusy} type="button" onClick={() => void decideWorkflow("rejected")}>退回</button>
                    </div>
                  ) : workflow.current_stage !== "VERIFIED" && workflow.current_stage !== "BLOCKED" && workflow.current_stage !== "REWORK" ? (
                    <button className="primary-inline-button" disabled={workflowBusy} type="button" onClick={() => void runNextWorkflowStage()}>
                      {workflowBusy ? "调度中..." : "调度下一 Agent"}
                    </button>
                  ) : null}
                  {workflow.data_pipeline?.rework_reason && <p className="workflow-control-error">{workflow.data_pipeline.rework_reason}</p>}
                </div>
              )}
              {workflowError && <p className="workflow-control-error" role="alert">{workflowError}</p>}
            </section>
            <section className="audit-summary">
              <div className="audit-summary-icon">✓</div>
              <div><strong>研究链路正在审查</strong><p>当前回答已关联证据，正式发布前仍需检查数据和引用。</p></div>
            </section>
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
              <div className="output-section-heading"><h3>本轮审查</h3><span>{lastResponse.risk_flags.length} 项提醒</span></div>
              <div className="review-list">
                {lastResponse.risk_flags.map((flag) => <div className="review-item" key={flag}><span>!</span><p>{flag}</p></div>)}
              </div>
              {workflowSnapshot?.pending_approval_ref && (
                <div className="audit-pending-note">
                  <strong>当前存在 Human Gate</strong>
                  <p>
                    {workflowSnapshot.last_route_decision?.selected_route ?? "当前 Agent"} 已生成候选结果，
                    需要研究者在研究流程中确认后才能进入下一阶段。
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
