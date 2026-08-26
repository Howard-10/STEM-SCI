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
  page_start?: number | null;
  page_end?: number | null;
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
  canonical_paper_id?: string | null;
  canonical_chunk_id?: string | null;
  pdf_relative_path?: string | null;
  corpus_id?: string | null;
  retrieval_modalities?: string[];
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
  context_mode?: "local" | "discovery" | "formal";
  corpus_refs?: string[];
  retrieval_strategy?: "local_keyword" | "hybrid";
  retrieval_trace_ref?: string | null;
  retrieval_risk_flags?: string[];
  manifest_refs?: string[];
}

export type SharedContextMode = "discovery" | "formal";
export type RetrievalMode =
  | "HYBRID_GRAPH_GUIDED"
  | "HYBRID_DENSE_SPARSE"
  | "SPARSE_ONLY"
  | "DENSE_ONLY"
  | "UNAVAILABLE";

export interface SharedCorpusSummary {
  corpus_id: string;
  corpus_version: string;
  access_mode: "internal_read_only" | "project_private";
  paper_count: number;
  vector_chunk_count: number;
  discovery_ready: boolean;
  formal_evidence_ready: boolean;
  risk_flags: string[];
}

export interface GraphCandidate {
  canonical_paper_id: string;
  graph_paper_id: string;
  navigation_score: number;
  matched_facets: string[];
  supporting_edge_refs: string[];
  source_status: "model_generated_unverified";
}

export interface SharedChunkHit {
  canonical_chunk_id: string;
  canonical_paper_id: string;
  source_filename: string;
  paper_title: string;
  normalized_doi?: string | null;
  chunk_index: number;
  section_hint?: string | null;
  excerpt: string;
  dense_rank?: number | null;
  sparse_rank?: number | null;
  rrf_score: number;
  locator_status: "RESOLVED" | "UNRESOLVED";
  pdf_relative_path?: string | null;
  pdf_sha256?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  verification_status?: VerificationStatus;
  retrieval_modalities: Array<"dense" | "sparse" | "graph_navigation">;
}

export interface SharedRetrievalResponse {
  project_id: string;
  corpus_id: string;
  requested_mode: SharedContextMode;
  retrieval_status: "READY" | "DEGRADED" | "UNAVAILABLE";
  degraded_mode?: RetrievalMode | null;
  candidate_papers: GraphCandidate[];
  chunk_hits: SharedChunkHit[];
  retrieval_trace: {
    query_normalized: string;
    retrieval_mode: RetrievalMode;
    graph_available: boolean;
    dense_available: boolean;
    sparse_available: boolean;
  };
  risk_flags: string[];
  manifest_refs: string[];
}

interface ApiErrorResponse {
  error: { code: string; message: string };
}

export function isApiError(value: unknown): value is ApiErrorResponse {
  return typeof value === "object" && value !== null && "error" in value;
}
