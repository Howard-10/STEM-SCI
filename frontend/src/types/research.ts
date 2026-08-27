import type { QAAnswerResponse } from "../api/qa";
import type { ApprovalRequest, ProjectStage, ResearchState, WorkflowState } from "../api/workflow";
import type { Bundle, EvidenceRef, SharedChunkHit, SharedCorpusSummary } from "./context";

export type ResearchStage =
  | "intake"
  | "scope"
  | "evidence"
  | "design"
  | "data"
  | "analysis"
  | "draft"
  | "review"
  | "release";

export type GateTone = "verified" | "pending" | "insufficient" | "approved" | "rejected" | "unknown";

export interface GateViewModel {
  kind: "evidence" | "human" | "validation";
  label: string;
  tone: GateTone;
  detail: string;
}

export interface EvidenceCoverage {
  claimLevelAvailable: boolean;
  totalClaims: number | null;
  supportedClaims: number;
  verifiedClaims: number;
  unsupportedClaims: number | null;
  coverageStatus: "complete" | "partial" | "insufficient" | "not_available";
}

export interface AgentRole {
  id: string;
  label: string;
  technicalName: string;
}

export interface StageDefinition {
  id: ResearchStage;
  label: string;
  lead: AgentRole;
  support: AgentRole[];
}

export interface ResearchArtifact {
  label: string;
  kind: string;
  technicalRef?: string;
}

export interface ResearchContextViewModel {
  projectId: string;
  stage: ResearchStage;
  stageStatus: "current" | "complete" | "waiting" | "rework" | "blocked" | "failed";
  stageDefinition: StageDefinition;
  researchState: ResearchState | null;
  workflow: WorkflowState | null;
  approval: ApprovalRequest | null;
  gates: GateViewModel[];
  artifacts: ResearchArtifact[];
}

export interface EvidenceViewModel {
  id: string;
  title: string;
  source: string;
  excerpt: string;
  doi: string | null;
  pdfPath?: string | null;
  page: string | null;
  verification: "已核验" | "待核验" | "证据不足";
  gateTone: GateTone;
  sourceType: "chunk" | "paper" | "local";
  technicalRef?: string;
}

export interface CorpusViewModel {
  summary: SharedCorpusSummary | null;
  status: string;
  detail: string;
}

export interface AnswerViewModel {
  answer: QAAnswerResponse | null;
  evidence: EvidenceViewModel[];
  coverage: EvidenceCoverage;
}

export type EvidenceInput =
  | EvidenceRef
  | SharedChunkHit
  | QAAnswerResponse["citations"][number];

export type BundleInput = Bundle | null;

export type ApiProjectStage = ProjectStage;
