export type ProjectStage =
  | "INTAKE"
  | "SCOPED"
  | "SEARCH_PROTOCOL_APPROVED"
  | "EVIDENCE_READY"
  | "RESEARCH_QUESTION_APPROVED"
  | "STUDY_PROTOCOL_APPROVED"
  | "DATA_READY"
  | "ANALYZED"
  | "DRAFTED"
  | "VERIFIED"
  | "RELEASED"
  | "REWORK"
  | "BLOCKED"
  | "WAITING_HUMAN"
  | "FAILED";

export interface AgentCapability {
  agent_id: string;
  supported_task_types: string[];
  allowed_tool_capabilities: string[];
  allowed_output_types: string[];
  forbidden_actions: string[];
  read_only_global_state: boolean;
}

export type AgentPlanStatus =
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "RUNNING"
  | "COMPLETED"
  | "PARTIAL"
  | "REJECTED"
  | "BLOCKED"
  | "WAITING_TASK_APPROVAL"
  | "REWORK_REQUIRED";

export type AgentExecutionMode = "automatic" | "stepwise";

export type AgentTaskStatus =
  | "PLANNED"
  | "WAITING_DEPENDENCY"
  | "SKIPPED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "BLOCKED";

export interface AgentTaskPlan {
  task_id: string;
  agent_id: string;
  task_type: string;
  reason: string;
  input_refs: string[];
  required_context: string[];
  depends_on: string[];
  expected_output_types: string[];
  risk_level: string;
  approval_required: boolean;
  status: AgentTaskStatus;
  blocked_reason: string | null;
  agent_run_id: string | null;
  output_refs: string[];
  persisted_artifact_ids: string[];
  evidence_refs: string[];
  risk_flags: string[];
  unresolved_questions: string[];
  error: string | null;
  review_note: string | null;
}

export interface AgentExecutionPlan {
  plan_id: string;
  project_id: string;
  conversation_id: string | null;
  turn_id: string | null;
  user_request: string;
  conversation_context: string[];
  intent_summary: string;
  status: AgentPlanStatus;
  tasks: AgentTaskPlan[];
  source_context_refs: string[];
  risk_flags: string[];
  unresolved_questions: string[];
  planner_mode: string;
  execution_mode: AgentExecutionMode;
  pending_review_task_id: string | null;
  rework_note: string | null;
  approved_task_ids: string[];
  approved_by: string | null;
  approved_at: string | null;
  executed_at: string | null;
  created_at: string;
}

export interface AgentOutputSummary {
  plan_id: string;
  task_id: string;
  project_id: string;
  user_request: string | null;
  conversation_id: string | null;
  turn_id: string | null;
  agent_id: string;
  task_type: string;
  status: AgentTaskStatus;
  input_refs: string[];
  depends_on: string[];
  risk_level: string;
  output_types: string[];
  artifact_ids: string[];
  artifact_refs: string[];
  evidence_refs: string[];
  output_previews: AgentOutputPreview[];
  risk_flags: string[];
  unresolved_questions: string[];
  decision: string;
  target_pages: string[];
  error: string | null;
  agent_run_id?: string | null;
  agent_version?: string | null;
  primary_artifact_id?: string | null;
  researcher_answer?: string;
  summary_mode?: "llm" | "deterministic" | string;
}

export interface AgentOutputPreview {
  artifact_id: string;
  artifact_type: string;
  status: string;
  content: Record<string, unknown>;
  researcher_summary?: string;
  review_points?: string[];
  action_items?: string[];
  summary_mode?: "llm" | "deterministic" | string;
}

export interface AgentPageMaterial {
  material_id: string;
  project_id: string;
  plan_id: string;
  task_id: string;
  agent_id: string;
  artifact_id: string;
  artifact_type: string;
  target: string;
  conversation_id: string | null;
  turn_id: string | null;
  formalization: string;
  applied_by: string;
  applied_at: string;
  content: Record<string, unknown>;
}

export interface FormalEvidenceRecord {
  project_id: string;
  evidence_id: string;
  artifact_id: string;
  plan_id: string;
  task_id: string;
  agent_id: string;
  conversation_id: string | null;
  turn_id: string | null;
  promoted_by: string;
  promoted_at: string;
  evidence_ref: Record<string, unknown>;
  provenance: Array<Record<string, unknown>>;
}

export interface ApprovalRequest {
  request_id: string;
  artifact_ref: string;
  approval_type: string;
  reason: string;
  risk_summary: string;
}

export interface RouteDecision {
  decision_id: string;
  project_id: string;
  current_stage: ProjectStage;
  selected_route: string;
  reason: string;
  required_context: string[];
  required_tools: string[];
  decision_scope: string;
  risk_level: string;
  triggered_rules: string[];
  final_decider: string;
  policy_version: string;
  created_at: string;
}

export interface AgentResult {
  agent_run_id: string;
  agent_id: string;
  agent_version: string;
  candidate_artifact_refs: string[];
  evidence_refs: string[];
  tool_requests: ToolRequest[];
  approval_requests: string[];
  risk_flags: string[];
  unresolved_questions: string[];
  recommendations: string[];
  confidence: number | null;
  created_at: string;
}

export interface ToolRequest {
  request_id: string;
  capability: string;
  input_refs: string[];
  required_output_types: string[];
  reason: string;
}

export interface ResearchState {
  project_id: string;
  current_stage: ProjectStage;
  rework_target_agent: string | null;
  rework_reason: string | null;
  rework_trigger_refs: string[];
  task_status: Record<string, string>;
  task_ledger: string[];
  progress_ledger: string[];
  evidence_refs: string[];
  context_bundle_refs: string[];
  execution_run_refs: string[];
  artifact_refs: string[];
  data_asset_refs: string[];
  protocol_refs: string[];
  research_test_result_refs: string[];
  risk_profile_refs: string[];
  route_decision_refs: string[];
  agent_run_refs: string[];
  approval_request_refs: string[];
  budget_state_ref: string | null;
  recent_rounds: string[];
  short_memory_summary: string | null;
  long_memory_refs: string[];
  risk_flags: string[];
  unresolved_questions: string[];
  error_log: string[];
}

export interface WorkflowState {
  project_id: string;
  current_stage: ProjectStage;
  pending_approval_ref: string | null;
  last_agent_run_id: string | null;
  last_route_decision: RouteDecision | null;
  research_state: ResearchState | null;
  data_pipeline?: DataPipelineState | null;
  data_pipeline_package_ref?: string | null;
}

export interface PlanningRun {
  workflow_state: WorkflowState;
  agent_result: AgentResult;
  approval_request: ApprovalRequest;
  route_decision: RouteDecision | null;
}

export interface WorkflowRun {
  workflow_state: WorkflowState;
  agent_result: AgentResult;
  approval_request: ApprovalRequest;
  route_decision: RouteDecision;
}

export interface RuntimeStatus {
  coding_provider: string;
  codex_available: boolean;
  codex_reason: string | null;
  spss_available: boolean;
  spss_reason: string | null;
}

export type DataPipelineStage =
  | "WAITING_RAW_DATA"
  | "WAITING_PROCESSING_APPROVAL"
  | "REWORK"
  | "WAITING_FREEZE_APPROVAL"
  | "WAITING_EXECUTION_APPROVAL"
  | "ANALYZED"
  | "BLOCKED";

export interface DataPipelineApproval {
  request_id: string;
  approval_type: string;
  artifact_ref: string;
  reason: string;
}

export interface DataPipelineState {
  project_id: string;
  stage: DataPipelineStage;
  preregistered_plan_ref: string;
  preregistration_approval_ref: string;
  code_artifact_ref: string | null;
  code_specification_ref: string | null;
  code_review_ref: string | null;
  spss_code_artifact_ref: string | null;
  spss_execution_run_ref: string | null;
  result_consistency_report_ref: string | null;
  raw_dataset: Record<string, unknown> | null;
  data_audit_report: {
    passed: boolean;
    missing_required_variables: string[];
    risk_flags: string[];
  } | null;
  processed_dataset: Record<string, unknown> | null;
  frozen_dataset: Record<string, unknown> | null;
  executable_plan: {
    analysis_mode: "PYTHON_ONLY" | "SPSS_PYTHON_DUAL";
    executable_plan_id: string;
  } | null;
  validation_report: {
    passed: boolean;
    execution_run_refs: string[];
  } | null;
  statistical_result_card: {
    result_id: string;
    execution_status: string;
    values: Record<string, number>;
  } | null;
  pending_approval: DataPipelineApproval | null;
  rework_reason: string | null;
  blocked_target_ids: string[];
}

export interface ControllerWorkflowState {
  project_id: string;
  current_stage: string;
  pending_approval_ref: string | null;
  last_route_decision: RouteDecision | null;
  data_pipeline: DataPipelineState | null;
  research_state: ResearchState | null;
}
const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await authenticatedRequest<T>(path, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (error) {
    if (!demoMode) throw error;
    return demoWorkflowFallback<T>(path, init);
  }
}

function demoWorkflowFallback<T>(path: string, init?: RequestInit): T {
  if (path === "/workflow/runtime") return demoRuntime as T;
  if (path === "/workflow/agents") return demoAgents as T;
  if (path.endsWith("/workflow/plans") && init?.method === "POST") {
    demoAgentPlan = {
      ...demoAgentPlan,
      status: "PENDING_APPROVAL",
      user_request: init?.body ? JSON.parse(String(init.body)).user_request ?? demoAgentPlan.user_request : demoAgentPlan.user_request,
    };
    return demoAgentPlan as T;
  }
  if (path.includes("/workflow/plans/") && path.endsWith("/approve") && init?.method === "POST") {
    const body = init?.body ? JSON.parse(String(init.body)) as { decision?: string; selected_task_ids?: string[] } : {};
    demoAgentPlan = {
      ...demoAgentPlan,
      status: body.decision === "approved" ? "APPROVED" : "REJECTED",
      approved_task_ids: body.selected_task_ids ?? demoAgentPlan.tasks.map((task) => task.task_id),
      tasks: demoAgentPlan.tasks.map((task) => ({
        ...task,
        status: body.decision === "approved" ? task.status : "SKIPPED",
      })),
    };
    return demoAgentPlan as T;
  }
  if (path.includes("/workflow/plans/") && path.endsWith("/execute") && init?.method === "POST") {
    demoAgentPlan = {
      ...demoAgentPlan,
      status: "COMPLETED",
      executed_at: new Date().toISOString(),
      tasks: demoAgentPlan.tasks.map((task) => ({
        ...task,
        status: "COMPLETED",
        agent_run_id: `${task.agent_id}-demo-run`,
        output_refs: task.expected_output_types.map((type) => `candidate://${task.agent_id}/${type}`),
        persisted_artifact_ids: [`artifact-${task.agent_id}-demo`],
      })),
    };
    return demoAgentPlan as T;
  }
  if (path.endsWith("/workflow/agent-outputs") || path.includes("/workflow/plans/") && path.endsWith("/outputs")) return demoAgentOutputs as T;
  if (path.endsWith("/workflow/page-materials")) return [] as T;
  if (path.includes("/workflow/artifacts/") && path.endsWith("/decision") && init?.method === "POST") {
    return { ok: true, decision: "retain", formalization: "project_material" } as T;
  }
  if (path.startsWith("/workflow/projects/") && path.endsWith("/data-pipeline/raw")) {
    demoPipelineState = {
      ...demoPipelineState,
      stage: "WAITING_PROCESSING_APPROVAL",
      raw_dataset: {
        dataset_id: "raw-demo-upload",
        version: 1,
        sha256: "demo-upload",
      },
      data_audit_report: {
        passed: true,
        missing_required_variables: [],
        risk_flags: [],
      },
      pending_approval: {
        request_id: "data-approval-demo-processing",
        approval_type: "data_processing",
        artifact_ref: "processing-plan-candidate://demo",
        reason: "请确认数据处理计划后继续。",
      },
    };
    return demoPipelineState as T;
  }
  if (path.startsWith("/workflow/projects/") && path.endsWith("/data-pipeline/decide")) {
    const body = typeof init?.body === "string"
      ? JSON.parse(init.body) as { decision?: string }
      : {};
    const transitions: Record<string, DataPipelineStage> = {
      data_processing: "WAITING_FREEZE_APPROVAL",
      data_freeze: "WAITING_EXECUTION_APPROVAL",
      analysis_execution: "ANALYZED",
    };
    const approvalType = demoPipelineState.pending_approval?.approval_type ?? "data_processing";
    const nextStage = body.decision === "approved"
      ? transitions[approvalType] ?? "ANALYZED"
      : "REWORK";
    demoPipelineState = {
      ...demoPipelineState,
      stage: nextStage,
      pending_approval: nextStage === "ANALYZED" || nextStage === "REWORK"
        ? null
        : {
          request_id: `data-approval-demo-${nextStage.toLowerCase()}`,
          approval_type: nextStage === "WAITING_FREEZE_APPROVAL" ? "data_freeze" : "analysis_execution",
          artifact_ref: `candidate://demo/${nextStage}`,
          reason: "请确认下一阶段操作后继续。",
        },
      processed_dataset: nextStage === "WAITING_EXECUTION_APPROVAL" || nextStage === "ANALYZED"
        ? { ref: "dataset://processed-demo/1" }
        : demoPipelineState.processed_dataset,
      frozen_dataset: nextStage === "WAITING_EXECUTION_APPROVAL" || nextStage === "ANALYZED"
        ? { ref: "dataset://frozen-demo/1" }
        : demoPipelineState.frozen_dataset,
      executable_plan: nextStage === "WAITING_EXECUTION_APPROVAL" || nextStage === "ANALYZED"
        ? { analysis_mode: "PYTHON_ONLY", executable_plan_id: "demo-plan" }
        : demoPipelineState.executable_plan,
      validation_report: nextStage === "ANALYZED"
        ? { passed: true, execution_run_refs: ["execution://demo-python"] }
        : demoPipelineState.validation_report,
      statistical_result_card: nextStage === "ANALYZED"
        ? {
          result_id: "demo-result-card",
          execution_status: "execution_verified",
          values: { analysis_sample_size: 48, transfer_mean_difference_group_2_minus_group_1: 0.42 },
        }
        : demoPipelineState.statistical_result_card,
    };
    return demoPipelineState as T;
  }
  if (path.startsWith("/workflow/projects/") && path.endsWith("/data-pipeline/start")) {
    demoPipelineState = {
      ...demoPipelineState,
      stage: "WAITING_RAW_DATA",
      project_id: path.split("/")[3] || demoPipelineState.project_id,
    };
    return demoPipelineState as T;
  }
  if (path.startsWith("/workflow/projects/") && !path.includes("/data-pipeline/")) {
    return {
      project_id: path.split("/")[3] || "physics-ai-demo",
      current_stage: demoPipelineState.stage === "WAITING_RAW_DATA" ? "DATA_READY" : "STUDY_PROTOCOL_APPROVED",
      pending_approval_ref: demoPipelineState.pending_approval?.request_id ?? null,
      last_route_decision: null,
      data_pipeline: demoPipelineState,
      research_state: demoWorkflowState.research_state,
    } as T;
  }
  if (path.includes("/executions")) return demoExecutionRows as T;
  if (path.includes("/routes")) return demoRouteRows as T;
  if (path.includes("/artifacts") || path.includes("/artifact-contents") || path.includes("/agent-runs")) {
    return demoWorkflowState.research_state?.artifact_refs.map((artifact_ref) => ({ artifact_ref, status: "CANDIDATE" })) as T;
  }
  if (path.endsWith("/approve") && init?.method === "POST") return demoResearchState as T;
  if (path.endsWith("/next") && init?.method === "POST") return demoWorkflowRun as T;
  if ((path.includes("/projects/") && path.endsWith("/workflow")) || path.includes("/workflow/projects/")) {
    if (init?.method === "POST") return demoPlanningRun as T;
    return demoWorkflowState as T;
  }
  return demoWorkflowState as T;
}

let demoPipelineState: DataPipelineState = {
  project_id: "physics-ai-demo",
  stage: "WAITING_RAW_DATA",
  preregistered_plan_ref: "prereg-plan://physics-ai-demo/v1",
  preregistration_approval_ref: "approval://physics-ai-demo/prereg-v1",
  code_artifact_ref: null,
  code_specification_ref: null,
  code_review_ref: null,
  spss_code_artifact_ref: null,
  spss_execution_run_ref: null,
  result_consistency_report_ref: null,
  raw_dataset: null,
  data_audit_report: null,
  processed_dataset: null,
  frozen_dataset: null,
  executable_plan: null,
  validation_report: null,
  statistical_result_card: null,
  pending_approval: null,
  rework_reason: null,
  blocked_target_ids: [],
};

let demoAgentPlan: AgentExecutionPlan = {
  plan_id: "plan-demo-001",
  project_id: "physics-ai-demo",
  conversation_id: "conversation-demo",
  turn_id: "turn-demo-017",
  user_request: "根据当前证据设计一个师范生 Python 物理建模实验",
  conversation_context: [],
  intent_summary: "本轮将处理：文献证据、研究设计",
  status: "PENDING_APPROVAL",
  tasks: [
    {
      task_id: "task-evidence-demo",
      agent_id: "evidence_review",
      task_type: "synthesize_evidence",
      reason: "检索、筛选和组织与当前问题相关的来源证据。",
      input_refs: ["context://demo"],
      required_context: ["context://demo"],
      depends_on: [],
      expected_output_types: ["PaperCardCollection", "EvidenceMatrixCandidate", "ResearchGapReport"],
      risk_level: "HIGH",
      approval_required: true,
      status: "PLANNED",
      blocked_reason: null,
      agent_run_id: null,
      output_refs: [],
      persisted_artifact_ids: [],
      evidence_refs: [],
      risk_flags: ["FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION"],
      unresolved_questions: [],
      error: null,
      review_note: null,
    },
    {
      task_id: "task-design-demo",
      agent_id: "research_design",
      task_type: "draft_study_protocol",
      reason: "把研究目标转换为变量、测量方案和可审批研究设计。",
      input_refs: ["context://demo"],
      required_context: ["context://demo"],
      depends_on: ["agent:evidence_review"],
      expected_output_types: ["Estimand", "StudyProtocolCandidate", "MeasurementPlan"],
      risk_level: "MEDIUM",
      approval_required: true,
      status: "WAITING_DEPENDENCY",
      blocked_reason: null,
      agent_run_id: null,
      output_refs: [],
      persisted_artifact_ids: [],
      evidence_refs: [],
      risk_flags: [],
      unresolved_questions: [],
      error: null,
      review_note: null,
    },
  ],
  source_context_refs: ["context://demo"],
  risk_flags: ["FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION"],
  unresolved_questions: [],
  planner_mode: "capability_rules",
  execution_mode: "automatic",
  pending_review_task_id: null,
  rework_note: null,
  approved_task_ids: [],
  approved_by: null,
  approved_at: null,
  executed_at: null,
  created_at: new Date().toISOString(),
};

const demoAgentOutputs: AgentOutputSummary[] = [
  {
    plan_id: "plan-demo-001",
    task_id: "task-evidence-demo",
    project_id: "physics-ai-demo",
    user_request: "根据当前证据设计一个师范生 Python 物理建模实验",
    conversation_id: "conversation-demo",
    turn_id: "turn-demo-017",
    agent_id: "evidence_review",
    task_type: "synthesize_evidence",
    status: "COMPLETED",
    input_refs: ["conversation-turn://conversation-demo/turn-demo-017"],
    depends_on: [],
    risk_level: "HIGH",
    output_types: ["PaperCardCollection", "EvidenceMatrixCandidate"],
    artifact_ids: ["artifact-evidence_review-demo"],
    artifact_refs: ["candidate://evidence_review/PaperCardCollection"],
    evidence_refs: ["evd_demo_001"],
    output_previews: [],
    risk_flags: ["FORMAL_EVIDENCE_REQUIRES_SOURCE_VERIFICATION"],
    unresolved_questions: [],
    decision: "candidate",
    target_pages: ["knowledge_evidence", "evidence_gate"],
    error: null,
  },
];

export const workflowApi = {
  getRuntime() {
    return request<RuntimeStatus>("/workflow/runtime");
  },
  startProject(input: { project_id: string; research_intent: string; run_id?: string }) {
    return request<PlanningRun>(`/projects/${encodeURIComponent(input.project_id)}/workflow`, {
      method: "POST",
      // Project ID is part of the path. The authenticated project endpoint
      // intentionally rejects unknown body fields.
      body: JSON.stringify({ research_intent: input.research_intent, run_id: input.run_id }),
    });
  },
  getProject(projectId: string) {
    return request<WorkflowState>(`/projects/${encodeURIComponent(projectId)}/workflow`);
  },
  getControllerProject(projectId: string) {
    return request<ControllerWorkflowState>(
      `/workflow/projects/${encodeURIComponent(projectId)}`,
    );
  },
  approve(projectId: string, decision: string, decidedBy: string) {
    return request<ResearchState>(`/projects/${encodeURIComponent(projectId)}/workflow/approve`, {
      method: "POST",
      body: JSON.stringify({ decision, decided_by: decidedBy }),
    });
  },
  uploadControllerRawCsv(projectId: string, file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<DataPipelineState>(
      `/workflow/projects/${encodeURIComponent(projectId)}/data-pipeline/raw`,
      { method: "POST", body },
    );
  },
  decideControllerDataPipeline(projectId: string, decision: "approved" | "rejected", decidedBy: string) {
    return request<DataPipelineState>(
      `/workflow/projects/${encodeURIComponent(projectId)}/data-pipeline/decide`,
      {
        method: "POST",
        body: JSON.stringify({ decision, decided_by: decidedBy }),
      },
    );
  },
  listAgents() {
    return request<AgentCapability[]>("/workflow/agents");
  },
  createAgentPlan(input: {
    project_id: string;
    user_request: string;
    conversation_id?: string;
    turn_id?: string;
    context_refs?: string[];
    conversation_context?: string[];
  }) {
    return request<AgentExecutionPlan>(
      `/projects/${encodeURIComponent(input.project_id)}/workflow/plans`,
      {
        method: "POST",
        body: JSON.stringify(input),
      },
    );
  },
  listAgentPlans(projectId: string) {
    return request<AgentExecutionPlan[]>(
      `/projects/${encodeURIComponent(projectId)}/workflow/plans`,
    );
  },
  approveAgentPlan(
    projectId: string,
    planId: string,
    decision: "approved" | "rejected",
    decidedBy: string,
    selectedTaskIds?: string[],
    executionMode: AgentExecutionMode = "automatic",
  ) {
    return request<AgentExecutionPlan>(
      `/projects/${encodeURIComponent(projectId)}/workflow/plans/${encodeURIComponent(planId)}/approve`,
      {
        method: "POST",
        body: JSON.stringify({
          decision,
          decided_by: decidedBy,
          selected_task_ids: selectedTaskIds,
          execution_mode: executionMode,
        }),
      },
    );
  },
  executeAgentPlan(projectId: string, planId: string) {
    return request<AgentExecutionPlan>(
      `/projects/${encodeURIComponent(projectId)}/workflow/plans/${encodeURIComponent(planId)}/execute`,
      { method: "POST" },
    );
  },
  continueAgentPlan(
    projectId: string,
    planId: string,
    decision: "approved" | "rework",
    decidedBy: string,
    note?: string,
  ) {
    return request<AgentExecutionPlan>(
      `/projects/${encodeURIComponent(projectId)}/workflow/plans/${encodeURIComponent(planId)}/continue`,
      {
        method: "POST",
        body: JSON.stringify({ decision, decided_by: decidedBy, note }),
      },
    );
  },
  listAgentOutputs(
    projectId: string,
    filters: { planId?: string; conversationId?: string; turnId?: string } = {},
  ) {
    const query = new URLSearchParams();
    if (filters.planId) query.set("plan_id", filters.planId);
    if (filters.conversationId) query.set("conversation_id", filters.conversationId);
    if (filters.turnId) query.set("turn_id", filters.turnId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<AgentOutputSummary[]>(
      `/projects/${encodeURIComponent(projectId)}/workflow/agent-outputs${suffix}`,
    );
  },
  listPlanOutputs(projectId: string, planId: string) {
    return request<AgentOutputSummary[]>(
      `/projects/${encodeURIComponent(projectId)}/workflow/plans/${encodeURIComponent(planId)}/outputs`,
    );
  },
  listAgentPageMaterials(
    projectId: string,
    filters: { target?: string; conversationId?: string; turnId?: string } = {},
  ) {
    const query = new URLSearchParams();
    if (filters.target) query.set("target", filters.target);
    if (filters.conversationId) query.set("conversation_id", filters.conversationId);
    if (filters.turnId) query.set("turn_id", filters.turnId);
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<AgentPageMaterial[]>(
      `/projects/${encodeURIComponent(projectId)}/workflow/page-materials${suffix}`,
    );
  },
  listFormalEvidence(projectId: string) {
    return request<FormalEvidenceRecord[]>(
      `/projects/${encodeURIComponent(projectId)}/workflow/formal-evidence`,
    );
  },
  decideAgentOutput(
    projectId: string,
    artifactId: string,
    decision: "retain" | "reject" | "apply" | "promote",
    decidedBy: string,
    target?: string,
  ) {
    return request<Record<string, unknown>>(
      `/projects/${encodeURIComponent(projectId)}/workflow/artifacts/${encodeURIComponent(artifactId)}/decision`,
      {
        method: "POST",
        body: JSON.stringify({ decision, decided_by: decidedBy, target }),
      },
    );
  },
  applyAgentManuscript(projectId: string, artifactId: string) {
    return request<{ document_id: string }>(
      `/projects/${encodeURIComponent(projectId)}/workflow/artifacts/${encodeURIComponent(artifactId)}/apply-to-manuscript`,
      { method: "POST" },
    );
  },
  listExecutions(projectId: string) {
    return request<Array<Record<string, unknown>>>(`/workflow/projects/${encodeURIComponent(projectId)}/executions`);
  },
  listArtifacts(projectId: string) {
    return request<Array<Record<string, unknown>>>(`/workflow/projects/${encodeURIComponent(projectId)}/artifacts`);
  },
  listArtifactContents(projectId: string) {
    return request<Array<Record<string, unknown>>>(`/workflow/projects/${encodeURIComponent(projectId)}/artifact-contents`);
  },
  listAgentRuns(projectId: string) {
    return request<Array<Record<string, unknown>>>(`/workflow/projects/${encodeURIComponent(projectId)}/agent-runs`);
  },
  listRoutes(projectId: string) {
    return request<Array<Record<string, unknown>>>(`/workflow/projects/${encodeURIComponent(projectId)}/routes`);
  },
  uploadRawCsv(projectId: string, file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<DataPipelineState>(`/projects/${encodeURIComponent(projectId)}/workflow/data-pipeline/raw`, {
      method: "POST", body,
    });
  },
  decideDataPipeline(projectId: string, decision: "approved" | "rejected", decidedBy: string) {
    return request<DataPipelineState>(`/projects/${encodeURIComponent(projectId)}/workflow/data-pipeline/decide`, {
      method: "POST", body: JSON.stringify({ decision, decided_by: decidedBy }),
    });
  },
};
import {
  demoAgents,
  demoApproval,
  demoExecutionRows,
  demoPlanningRun,
  demoResearchState,
  demoRouteRows,
  demoRuntime,
  demoWorkflowRun,
  demoWorkflowState,
} from "../demo/data";
import { authenticatedRequest } from "./auth";
