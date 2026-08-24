import type { QAAnswerResponse, QAContextMode } from "./qa";

const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";
const storageKey = "stem_sci_auth_state";

export type UserProfile = {
  user_id: string;
  username: string;
  email: string;
  display_name?: string | null;
  created_at: string;
};

export type AuthState = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserProfile;
};

export type ApiResearchProject = {
  project_id: string;
  owner_user_id: string;
  title: string;
  research_direction: string;
  abstract?: string | null;
  status: "active" | "archived";
  role: "owner" | "editor" | "viewer";
  created_at: string;
  updated_at: string;
};

export type ApiProjectDocument = {
  document_id: string;
  project_id: string;
  title: string;
  document_type: "manuscript" | "reference" | "dataset" | "protocol" | "note";
  format: "markdown" | "text" | "pdf" | "docx" | "csv";
  status: "active" | "archived";
  current_version: number;
  current_sha256: string;
  size_bytes: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type ApiConversationSummary = {
  conversation_id: string;
  project_id: string;
  title: string;
  last_question: string;
  last_answer_preview: string;
  turn_count: number;
  created_at: string;
  updated_at: string;
};

export type ApiMemoryTurn = {
  memory_id: string;
  conversation_id: string;
  project_id: string;
  question: string;
  rewritten_query: string;
  answer: string;
  route: string;
  citations: Array<{
    paper_title: string;
    source_filename: string;
    canonical_paper_id: string;
    canonical_chunk_id: string;
    chunk_index: number;
    excerpt: string;
    normalized_doi: string | null;
    source_type: "chunk" | "paper";
  }>;
  retrieval_trace_ref: string | null;
  created_at: string;
};

export type ApiDocumentVersion = {
  document_id: string;
  project_id: string;
  version: number;
  format: ApiProjectDocument["format"];
  content: string;
  sha256: string;
  size_bytes: number;
  storage_ref: string;
  change_note: string | null;
  created_by: string;
  created_at: string;
};

export class ApiRequestError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "request_failed") {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

export function readStoredAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(storageKey);
    return raw ? (JSON.parse(raw) as AuthState) : null;
  } catch {
    return null;
  }
}

export function saveAuth(auth: AuthState) {
  localStorage.setItem(storageKey, JSON.stringify(auth));
}

export function clearAuth() {
  localStorage.removeItem(storageKey);
}

function errorDetails(payload: unknown) {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: { code?: string; message?: string } }).error;
    return {
      code: error?.code ?? "request_failed",
      message: error?.message ?? "请求失败",
    };
  }
  return { code: "request_failed", message: "请求失败" };
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json; charset=utf-8");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${base}${path}`, { ...init, headers });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const details = errorDetails(payload);
    throw new ApiRequestError(details.message, response.status, details.code);
  }
  return payload as T;
}

export const authApi = {
  register(input: { username: string; email: string; password: string; display_name?: string | null }) {
    return request<AuthState>("/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  login(input: { login: string; password: string }) {
    return request<AuthState>("/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  refresh(refreshToken: string) {
    return request<AuthState>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  },
  me(token: string) {
    return request<UserProfile>("/auth/me", {}, token);
  },
  logout(token: string) {
    return request<{ status: string }>("/auth/logout", { method: "POST" }, token);
  },
  listProjects(token: string) {
    return request<ApiResearchProject[]>("/projects", {}, token);
  },
  createProject(
    token: string,
    input: { project_id?: string; title: string; research_direction: string; abstract?: string | null },
  ) {
    return request<ApiResearchProject>("/projects", {
      method: "POST",
      body: JSON.stringify(input),
    }, token);
  },
  listDocuments(token: string, projectId: string) {
    return request<ApiProjectDocument[]>(`/projects/${encodeURIComponent(projectId)}/documents`, {}, token);
  },
  getDocument(token: string, projectId: string, documentId: string) {
    return request<ApiProjectDocument>(
      `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`,
      {},
      token,
    );
  },
  createDocument(
    token: string,
    projectId: string,
    input: {
      title: string;
      document_type: ApiProjectDocument["document_type"];
      format: ApiProjectDocument["format"];
      content: string;
      change_note?: string | null;
    },
  ) {
    return request<ApiProjectDocument>(`/projects/${encodeURIComponent(projectId)}/documents`, {
      method: "POST",
      body: JSON.stringify(input),
    }, token);
  },
  saveDocumentVersion(token: string, projectId: string, documentId: string, content: string, changeNote: string) {
    return request<ApiDocumentVersion>(`/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions`, {
      method: "POST",
      body: JSON.stringify({ content, change_note: changeNote }),
    }, token);
  },
  getDocumentVersion(token: string, projectId: string, documentId: string, version: number) {
    return request<ApiDocumentVersion>(
      `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/versions/${version}`,
      {},
      token,
    );
  },
  projectChatAnswer(
    token: string,
    input: {
      project_id: string;
      question: string;
      mode?: QAContextMode;
      conversation_id?: string | null;
      top_k?: number;
      token_budget?: number;
      allow_llm?: boolean;
    },
  ) {
    return request<QAAnswerResponse>(`/projects/${encodeURIComponent(input.project_id)}/chat/answer`, {
      method: "POST",
      body: JSON.stringify({
        project_id: input.project_id,
        question: input.question,
        mode: input.mode ?? "discovery",
        conversation_id: input.conversation_id ?? null,
        top_k: input.top_k ?? 8,
        token_budget: input.token_budget ?? 3000,
        allow_llm: input.allow_llm ?? true,
      }),
    }, token);
  },
  listConversations(token: string, projectId: string) {
    return request<ApiConversationSummary[]>(
      `/projects/${encodeURIComponent(projectId)}/conversations`,
      {},
      token,
    );
  },
  listConversationTurns(token: string, projectId: string, conversationId: string) {
    return request<ApiMemoryTurn[]>(
      `/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/turns`,
      {},
      token,
    );
  },
};
