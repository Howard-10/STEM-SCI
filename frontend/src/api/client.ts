import type {
  Bundle,
  EvidenceDetail,
  SearchResult,
  Source,
  SourceChunk,
} from "../types/context";
import { isApiError } from "../types/context";

const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

function query(values: Record<string, string>): string {
  return new URLSearchParams(values).toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(isApiError(payload) ? payload.error.message : "Request failed");
  }
  return payload as T;
}

export const api = {
  listSources: (projectId: string) => request<Source[]>(`/sources?${query({ project_id: projectId })}`),
  getSource: (projectId: string, sourceId: string) =>
    request<Source>(`/sources/${sourceId}?${query({ project_id: projectId })}`),
  getChunks: (projectId: string, sourceId: string) =>
    request<SourceChunk[]>(`/sources/${sourceId}/chunks?${query({ project_id: projectId })}`),
  importSource: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("project_id", projectId);
    body.append("file", file);
    return request<Source>("/sources/import", { method: "POST", body });
  },
  search: (projectId: string, queryText: string) =>
    request<SearchResult[]>("/evidence/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ project_id: projectId, query: queryText }),
    }),
  getEvidence: (projectId: string, evidenceId: string) =>
    request<EvidenceDetail>(`/evidence/${evidenceId}?${query({ project_id: projectId })}`),
  verifySource: (projectId: string, evidenceId: string, verifiedBy: string, note: string) =>
    request(`/evidence/${evidenceId}/verify-source?${query({
      project_id: projectId,
      verified_by: verifiedBy,
      verification_note: note,
    })}`, { method: "POST" }),
  buildBundle: (projectId: string, queryText: string, tokenBudget: number) =>
    request<Bundle>("/context/build", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        task_ref: "frontend-context-task",
        query: queryText,
        token_budget: tokenBudget,
      }),
    }),
  getBundle: (projectId: string, contextId: string) =>
    request<Bundle>(`/context/${contextId}?${query({ project_id: projectId })}`),
};
