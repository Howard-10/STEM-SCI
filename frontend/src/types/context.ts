export type VerificationStatus =
  | "demo_seed"
  | "model_generated_unverified"
  | "source_verified"
  | "human_verified";

export interface SourceLocation {
  chunk_index: number;
  char_start: number;
  char_end: number;
  heading?: string | null;
}

export interface Source {
  source_id: string;
  project_id: string;
  filename: string;
  media_type: string;
  sha256: string;
  imported_at: string;
  verification_status: VerificationStatus;
}

export interface SourceChunk {
  chunk_id: string;
  project_id: string;
  source_id: string;
  text: string;
  location: SourceLocation;
}

export interface EvidenceRef {
  evidence_id: string;
  project_id: string;
  source_id: string;
  chunk_id: string;
  excerpt: string;
  location: SourceLocation;
  verification_status: VerificationStatus;
}

export interface EvidenceDetail extends EvidenceRef {
  relation: string;
  verification_note?: string | null;
  verified_by?: string | null;
  verified_at?: string | null;
}

export interface SearchResult {
  evidence: EvidenceRef;
  score: number;
}

export interface Bundle {
  context_id: string;
  project_id: string;
  task_ref: string;
  query: string;
  evidence_refs: EvidenceRef[];
  source_refs: string[];
  estimated_tokens: number;
  token_budget: number;
  context_hash: string;
  verification_summary: Record<string, number>;
}

interface ApiErrorResponse {
  error: { code: string; message: string };
}

export function isApiError(value: unknown): value is ApiErrorResponse {
  return typeof value === "object" && value !== null && "error" in value;
}
