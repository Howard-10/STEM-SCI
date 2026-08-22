import type { QAAnswerResponse } from "../api/qa";
import type { AgentCapability, ApprovalRequest, ProjectStage, ResearchState, WorkflowState } from "../api/workflow";
import type { Bundle, EvidenceRef, SharedChunkHit, SharedCorpusSummary } from "../types/context";
import type {
  AgentRole,
  AnswerViewModel,
  BundleInput,
  CorpusViewModel,
  EvidenceCoverage,
  EvidenceInput,
  EvidenceViewModel,
  GateTone,
  GateViewModel,
  ResearchArtifact,
  ResearchContextViewModel,
  ResearchStage,
  StageDefinition,
} from "../types/research";

export const agentRoles: Record<string, AgentRole> = {
  mentor_planning: { id: "mentor_planning", label: "研究导师", technicalName: "mentor_planning" },
  evidence_review: { id: "evidence_review", label: "证据综述员", technicalName: "evidence_review" },
  research_design: { id: "research_design", label: "研究设计师", technicalName: "research_design" },
  data_analysis: { id: "data_analysis", label: "数据分析师", technicalName: "data_analysis" },
  paper_writing: { id: "paper_writing", label: "论文写作助手", technicalName: "paper_writing" },
  independent_review: { id: "independent_review", label: "独立审查员", technicalName: "independent_review" },
};

const role = (id: string) => agentRoles[id] ?? { id, label: "研究协作角色", technicalName: id };

export const stageDefinitions: StageDefinition[] = [
  { id: "intake", label: "研究接入", lead: role("mentor_planning"), support: [role("evidence_review")] },
  { id: "scope", label: "范围确认", lead: role("mentor_planning"), support: [role("evidence_review")] },
  { id: "evidence", label: "证据综述", lead: role("evidence_review"), support: [role("mentor_planning")] },
  { id: "design", label: "研究设计", lead: role("research_design"), support: [role("evidence_review")] },
  { id: "data", label: "数据准备", lead: role("data_analysis"), support: [role("research_design")] },
  { id: "analysis", label: "分析执行", lead: role("data_analysis"), support: [role("research_design")] },
  { id: "draft", label: "论文草稿", lead: role("paper_writing"), support: [role("evidence_review"), role("data_analysis")] },
  { id: "review", label: "独立审查", lead: role("independent_review"), support: [role("mentor_planning")] },
  { id: "release", label: "发布", lead: role("independent_review"), support: [role("mentor_planning")] },
];

const stageMap: Record<string, ResearchStage> = {
  INTAKE: "intake",
  SCOPED: "scope",
  SEARCH_PROTOCOL_APPROVED: "evidence",
  EVIDENCE_READY: "evidence",
  RESEARCH_QUESTION_APPROVED: "design",
  STUDY_PROTOCOL_APPROVED: "data",
  DATA_READY: "data",
  ANALYZED: "analysis",
  DRAFTED: "draft",
  VERIFIED: "review",
  RELEASED: "release",
};

const stageIndex = (id: ResearchStage) => stageDefinitions.findIndex((stage) => stage.id === id);

export function toResearchStage(stage: ProjectStage | null | undefined, routeStage?: ProjectStage | null): ResearchStage {
  return stageMap[stage ?? ""] ?? stageMap[routeStage ?? ""] ?? "intake";
}

export function stageStatus(stage: ProjectStage | null | undefined): ResearchContextViewModel["stageStatus"] {
  if (stage === "WAITING_HUMAN") return "waiting";
  if (stage === "REWORK") return "rework";
  if (stage === "BLOCKED") return "blocked";
  if (stage === "FAILED") return "failed";
  return "current";
}

function gateFromEvidence(evidence: EvidenceViewModel[]): GateViewModel {
  if (!evidence.length) return { kind: "evidence", label: "Evidence Gate", tone: "insufficient", detail: "暂无可用证据" };
  const verified = evidence.filter((item) => item.gateTone === "verified").length;
  const pending = evidence.filter((item) => item.gateTone === "pending").length;
  if (verified === evidence.length) return { kind: "evidence", label: "Evidence Gate", tone: "verified", detail: `${verified} 条证据已核验` };
  if (verified || pending) return { kind: "evidence", label: "Evidence Gate", tone: "pending", detail: `${verified} 条已核验，${pending} 条待核验` };
  return { kind: "evidence", label: "Evidence Gate", tone: "insufficient", detail: "证据不足以形成正式结论" };
}

function gateFromHuman(workflow: WorkflowState | null, approval: ApprovalRequest | null): GateViewModel {
  if (approval && workflow?.pending_approval_ref) return { kind: "human", label: "Human Gate", tone: "pending", detail: "等待研究者确认" };
  // The current API does not expose an approval decision history on WorkflowState.
  return { kind: "human", label: "Human Gate", tone: "unknown", detail: "尚无明确审批结果" };
}

function gateFromValidation(state: ResearchState | null): GateViewModel {
  if (!state) return { kind: "validation", label: "Validation Gate", tone: "pending", detail: "等待研究结果验证" };
  if (state.error_log.length > 0) return { kind: "validation", label: "Validation Gate", tone: "rejected", detail: "验证过程中存在错误" };
  // A result reference alone is not proof of successful validation.
  return { kind: "validation", label: "Validation Gate", tone: "pending", detail: "尚无明确验证成功证据" };
}

export function buildResearchContext(
  workflow: WorkflowState | null,
  approval: ApprovalRequest | null,
  evidence: EvidenceViewModel[],
): ResearchContextViewModel {
  const current = workflow?.current_stage ?? "INTAKE";
  const stage = toResearchStage(current, workflow?.last_route_decision?.current_stage);
  const definition = stageDefinitions.find((item) => item.id === stage) ?? stageDefinitions[0];
  return {
    projectId: workflow?.project_id ?? "physics-ai-demo",
    stage,
    stageStatus: stageStatus(current),
    stageDefinition: definition,
    researchState: workflow?.research_state ?? null,
    workflow,
    approval,
    gates: [gateFromEvidence(evidence), gateFromHuman(workflow, approval), gateFromValidation(workflow?.research_state ?? null)],
    artifacts: artifactViews(workflow?.research_state?.artifact_refs ?? []),
  };
}

function artifactViews(refs: string[]): ResearchArtifact[] {
  const labels: Record<string, string> = {
    SearchProtocolCandidate: "检索与纳排方案",
    EvidenceMatrixCandidate: "证据矩阵",
    PaperCardCollection: "文献卡片集",
    StudyProtocolCandidate: "研究设计候选",
    PreregisteredAnalysisPlanDraft: "统计分析计划",
    StatisticalResultCardCandidate: "统计结果卡",
    BilingualManuscriptDraft: "论文草稿",
    ReviewReport: "独立审查报告",
  };
  return refs.map((ref) => {
    const kind = ref.split("/").pop() ?? "ResearchArtifact";
    return { kind, label: labels[kind] ?? "研究候选工件", technicalRef: ref };
  });
}

export function evidenceView(item: EvidenceInput): EvidenceViewModel {
  if ("source_filename" in item) {
    const hit = item as unknown as SharedChunkHit;
    return { id: hit.canonical_chunk_id, title: hit.paper_title, source: hit.source_filename, excerpt: hit.excerpt, doi: hit.normalized_doi ?? null, page: hit.locator_status === "RESOLVED" ? "已定位" : null, verification: "待核验", gateTone: "pending", sourceType: "chunk", technicalRef: hit.canonical_chunk_id };
  }
  if ("paper_title" in item && "canonical_chunk_id" in item) {
    const citation = item as unknown as QAAnswerResponse["citations"][number];
    return { id: citation.canonical_chunk_id, title: citation.paper_title, source: citation.source_filename, excerpt: citation.excerpt, doi: citation.normalized_doi, page: null, verification: citation.source_type === "paper" ? "证据不足" : "待核验", gateTone: citation.source_type === "paper" ? "insufficient" : "pending", sourceType: citation.source_type, technicalRef: citation.canonical_chunk_id };
  }
  const evidence = item as EvidenceRef;
  const verified = evidence.verification_status === "source_verified" || evidence.verification_status === "human_verified";
  return { id: evidence.evidence_id, title: evidence.canonical_paper_id ?? evidence.source_id, source: evidence.source_id, excerpt: evidence.excerpt, doi: null, page: evidence.location.page_start ? `第 ${evidence.location.page_start} 页` : null, verification: verified ? "已核验" : "待核验", gateTone: verified ? "verified" : "pending", sourceType: "local", technicalRef: evidence.evidence_id };
}

export function buildEvidenceCoverage(evidence: EvidenceViewModel[], claimLevelAvailable = false): EvidenceCoverage {
  const supportedClaims = evidence.filter((item) => item.gateTone !== "insufficient").length;
  const verifiedClaims = evidence.filter((item) => item.gateTone === "verified").length;
  if (!claimLevelAvailable) return { claimLevelAvailable: false, totalClaims: null, supportedClaims, verifiedClaims, unsupportedClaims: null, coverageStatus: evidence.length ? "partial" : "not_available" };
  const totalClaims = evidence.length;
  return { claimLevelAvailable: true, totalClaims, supportedClaims, verifiedClaims, unsupportedClaims: totalClaims - supportedClaims, coverageStatus: supportedClaims === totalClaims ? "complete" : "partial" };
}

export function buildAnswerView(answer: QAAnswerResponse | null, bundle: BundleInput, sharedHits: SharedChunkHit[] = []): AnswerViewModel {
  const evidence = answer?.citations.map(evidenceView) ?? (bundle?.evidence_refs.map(evidenceView) ?? sharedHits.map(evidenceView));
  return { answer, evidence, coverage: buildEvidenceCoverage(evidence, false) };
}

export function buildCorpusView(summary: SharedCorpusSummary | null): CorpusViewModel {
  if (!summary) return { summary, status: "读取中", detail: "正在读取 Physics-STEM 语料状态" };
  if (!summary.discovery_ready) return { summary, status: "暂不可用", detail: "共享语料未通过完整性检查" };
  if (!summary.formal_evidence_ready) return { summary, status: "发现模式可用", detail: "正式证据仍需完成来源定位与核验" };
  return { summary, status: "正式证据可用", detail: "共享语料已具备正式引用条件" };
}

export function agentsForStage(stage: ResearchStage): { lead: AgentRole; support: AgentRole[] } {
  const definition = stageDefinitions.find((item) => item.id === stage) ?? stageDefinitions[0];
  return { lead: definition.lead, support: definition.support };
}

export function gateToneClass(tone: GateTone): string { return `gate-${tone}`; }

export function displayAgent(capability: AgentCapability | string): AgentRole {
  const id = typeof capability === "string" ? capability : capability.agent_id;
  return role(id);
}
