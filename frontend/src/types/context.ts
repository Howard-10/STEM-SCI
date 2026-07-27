export type Status = "demo_seed" | "model_generated_unverified" | "source_verified" | "human_verified";
export interface Source { source_id: string; filename: string; sha256: string; imported_at: string; verification_status: Status }
export interface SearchResult { evidence: { evidence_id: string; source_id: string; chunk_id: string; excerpt: string; verification_status: Status; location: { heading?: string } }; score: number }
export interface Bundle { context_id: string; evidence_refs: SearchResult["evidence"][]; estimated_tokens: number; context_hash: string; verification_summary: Record<string, number> }
