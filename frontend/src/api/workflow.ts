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

const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${base}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const message = typeof payload === "object" && payload !== null && "error" in payload
        ? String((payload as { error?: { message?: string } }).error?.message ?? "请求失败")
        : "请求失败";
      throw new Error(message);
    }
    return payload as T;
  } catch (error) {
    if (!demoMode) throw error;
    return demoWorkflowFallback<T>(path, init);
  }
}

function demoWorkflowFallback<T>(path: string, init?: RequestInit): T {
  if (path === "/workflow/runtime") return demoRuntime as T;
  if (path === "/workflow/agents") return demoAgents as T;
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

export const workflowApi = {
  getRuntime() {
    return request<RuntimeStatus>("/workflow/runtime");
  },
  startProject(input: { project_id: string; research_intent: string; run_id?: string }) {
    return request<PlanningRun>(`/projects/${encodeURIComponent(input.project_id)}/workflow`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  getProject(projectId: string) {
    return request<WorkflowState>(`/projects/${encodeURIComponent(projectId)}/workflow`);
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
