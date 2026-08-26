export type QAContextMode = "discovery" | "formal";

export interface QAWorkflowAction {
  action:
    | "STARTED"
    | "STATUS"
    | "NEXT_AGENT"
    | "APPROVAL_READY"
    | "PROPOSAL_ONLY"
    | "UNAVAILABLE";
  project_id: string;
  message: string;
  current_stage: string | null;
  selected_agent: string | null;
  approval_required: boolean;
  confirmation_required: boolean;
  approval_request_id: string | null;
  approval_request: Record<string, unknown> | null;
  workflow_state: Record<string, unknown> | null;
  artifacts: Array<Record<string, unknown>>;
  next_available_actions: string[];
}

export interface QAAnswerResponse {
  project_id: string;
  conversation_id: string;
  question: string;
  rewritten_query: string;
  route: {
    route: string;
    reason: string;
    recommended_agent: string | null;
  };
  answer: string;
  citations: Array<{
    paper_title: string;
    source_filename: string;
    canonical_paper_id: string;
    canonical_chunk_id: string;
    chunk_index: number;
    excerpt: string;
    normalized_doi: string | null;
    pdf_relative_path?: string | null;
    source_type: "chunk" | "paper";
  }>;
  retrieval_status: string;
  retrieval_trace_ref: string | null;
  context_bundle_ref: string | null;
  memory_ref: string | null;
  risk_flags: string[];
  answer_mode: "llm" | "fallback";
  confidence: number;
  needs_follow_up: boolean;
  follow_up_question: string | null;
  tool_calls: string[];
  workflow_action: QAWorkflowAction | null;
}

const base = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
import { demoQAResponse } from "../demo/data";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${base}${path}`, {
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const message =
        typeof payload === "object" && payload !== null && "error" in payload
          ? String((payload as { error?: { message?: string } }).error?.message ?? "请求失败")
          : "请求失败";
      throw new Error(message);
    }
    return payload as T;
  } catch (error) {
    if (demoMode && path === "/qa/answer") return demoQAResponse as T;
    throw error;
  }
}

export const qaApi = {
  answer(input: {
    project_id: string;
    question: string;
    mode?: QAContextMode;
    conversation_id?: string;
    context_bundle_ref?: string;
    top_k?: number;
    token_budget?: number;
    allow_llm?: boolean;
  }) {
    return request<QAAnswerResponse>("/qa/answer", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
};
