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

export interface WorkflowTimeline {
  project_id: string;
  research_intent: string;
  workflow_state: ControllerWorkflowState;
  agent_runs: Array<{ agent_run_id: string; agent_id: string; started_at: string; output_artifact_refs: string[] }>;
  artifact_contents: Array<{ artifact_id: string; artifact_type: string; body: Record<string, unknown> }>;
  artifacts?: Array<{ artifact_id: string; artifact_type: string; content_uri: string; version: number }>;
  routes: RouteDecision[];
  feedback: Array<{ feedback_id: string; agent_id: string; stage: string; action: "continue" | "rerun" | "pause"; feedback: string; created_by: string; created_at: string }>;
  pending_approval: { approval_type: string; reason: string; risk_summary: string } | null;
}
const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await authenticatedRequest<T>(path, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (error) {
    // Never substitute demo workflow state for an authenticated project. Doing
    // so makes a missing/unknown project look active and routes chat incorrectly.
    const hasAuth = Boolean(localStorage.getItem("stem_sci_auth_state"));
    const isProjectWorkflowRequest = path.includes("/projects/") && path.includes("/workflow");
    if (!demoMode || hasAuth || isProjectWorkflowRequest) throw error;
    return demoWorkflowFallback<T>(path, init);
  }
}

function demoWorkflowFallback<T>(path: string, init?: RequestInit): T {
  if (path === "/workflow/runtime") return demoRuntime as T;
  if (path === "/workflow/agents") return demoAgents as T;
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
  getTimeline(projectId: string) {
    return request<WorkflowTimeline>(`/projects/${encodeURIComponent(projectId)}/workflow/timeline`);
  },
  submitFeedback(projectId: string, input: { agent_id: string; stage: string; action: "continue" | "rerun" | "pause"; feedback: string }) {
    return request<{ workflow_state: WorkflowState; workflow_run: WorkflowRun | null }>(
      `/projects/${encodeURIComponent(projectId)}/workflow/feedback`,
      { method: "POST", body: JSON.stringify(input) },
    );
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
  runNext(projectId: string) {
    return request<WorkflowRun>(`/projects/${encodeURIComponent(projectId)}/workflow/next`, { method: "POST" });
  },
  runPublicNext(projectId: string) {
    return request<WorkflowRun>(
      `/workflow/projects/${encodeURIComponent(projectId)}/next`,
      { method: "POST" },
    );
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
