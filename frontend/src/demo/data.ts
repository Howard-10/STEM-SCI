import type { QAAnswerResponse } from "../api/qa";
import type {
  AgentCapability,
  AgentResult,
  ApprovalRequest,
  PlanningRun,
  ResearchState,
  RouteDecision,
  RuntimeStatus,
  WorkflowRun,
  WorkflowState,
} from "../api/workflow";
import type {
  Bundle,
  GraphCandidate,
  SharedCorpusSummary,
  SharedRetrievalResponse,
} from "../types/context";

export const demoCorpus: SharedCorpusSummary = {
  corpus_id: "physics_stem_v1",
  corpus_version: "v1",
  access_mode: "internal_read_only",
  paper_count: 122,
  vector_chunk_count: 1788,
  discovery_ready: true,
  formal_evidence_ready: false,
  risk_flags: ["formal_locator_index_unavailable"],
};

export const demoCitations: QAAnswerResponse["citations"] = [
  {
    paper_title: "Generative AI scaffolding for physics modeling",
    source_filename: "physics_ai_scaffolding_2024.pdf",
    canonical_paper_id: "paper-physics-ai-2024",
    canonical_chunk_id: "chunk-physics-ai-2024-028",
    chunk_index: 28,
    excerpt: "分层提示、模型解释反馈和逐步撤除支架，有助于学习者形成对模型假设与变量关系的显式解释。",
    normalized_doi: "10.0000/physics-ai-scaffolding",
    source_type: "chunk",
  },
  {
    paper_title: "Model-based reasoning in teacher physics education",
    source_filename: "teacher-model-reasoning-2023.pdf",
    canonical_paper_id: "paper-teacher-model-2023",
    canonical_chunk_id: "chunk-teacher-model-2023-061",
    chunk_index: 61,
    excerpt: "前测、后测和迁移任务可以共同衡量师范生将物理概念迁移到新建模情境的能力。",
    normalized_doi: "10.0000/teacher-model-reasoning",
    source_type: "chunk",
  },
  {
    paper_title: "Learning analytics for computational STEM instruction",
    source_filename: "computational-stem-learning-2022.pdf",
    canonical_paper_id: "paper-computational-stem-2022",
    canonical_chunk_id: "chunk-computational-stem-2022-014",
    chunk_index: 14,
    excerpt: "研究设计需要预先明确主要结果变量、协变量和稳健性检查，避免在看到结果后改变分析口径。",
    normalized_doi: "10.0000/computational-stem-learning",
    source_type: "chunk",
  },
];

export const demoQAResponse: QAAnswerResponse = {
  project_id: "physics-ai-demo",
  conversation_id: "conversation-demo-001",
  question: "如何设计师范生 Python 物理建模研究？",
  rewritten_query: "师范生 Python 物理建模 生成式 AI 分层支架 研究设计",
  route: {
    route: "hybrid_search",
    reason: "需要结合共享论文库的全文证据与图谱导航结果",
    recommended_agent: "ResearchDesignAgent",
  },
  answer:
    "建议采用前测、后测与迁移测验相结合的准实验设计。实验组使用生成式 AI 分层支架，对照组使用常规教学材料。主要结果变量可以包括 Python 物理建模任务评分、模型解释质量和迁移测验得分，并将前测成绩作为协变量。研究设计生成后，应先经过人工审批，再进入数据分析计划。",
  citations: demoCitations,
  retrieval_status: "READY",
  retrieval_trace_ref: "retrieval://physics_stem_v1/demo-trace-001",
  context_bundle_ref: "context://demo-physics-ai",
  memory_ref: "memory://conversation-demo-001",
  risk_flags: ["演示数据中的页码定位仅用于界面展示", "正式结论仍需人工核验来源"],
  answer_mode: "llm",
  confidence: 0.86,
  needs_follow_up: true,
  follow_up_question: "是否要把这个研究设计转换成可审批的实验方案？",
  tool_calls: ["hybrid_search", "workflow_agent"],
  workflow_action: {
    action: "PROPOSAL_ONLY",
    project_id: "physics-ai-demo",
    message: "研究设计 Agent 可以生成实验方案候选，提交后等待人工审批。",
    current_stage: "RESEARCH_QUESTION_APPROVED",
    selected_agent: "ResearchDesignAgent",
    approval_required: true,
    confirmation_required: true,
    approval_request_id: "approval-demo-research-design",
    approval_request: {
      request_id: "approval-demo-research-design",
      artifact_ref: "artifact://physics-ai-demo/study-protocol-candidate",
      approval_type: "study_protocol",
      reason: "研究设计候选需要研究者确认",
      risk_summary: "主要结果变量和对照组设置需要人工确认",
    },
    workflow_state: null,
    artifacts: [],
    next_available_actions: ["查看研究设计候选", "批准并推进", "退回修改"],
  },
};

const demoCandidates: GraphCandidate[] = [
  {
    canonical_paper_id: "paper-physics-ai-2024",
    graph_paper_id: "Generative AI scaffolding for physics modeling",
    navigation_score: 0.92,
    matched_facets: ["AI scaffolding", "physics modeling"],
    supporting_edge_refs: ["edge:topic:physics-modeling"],
    source_status: "model_generated_unverified",
  },
  {
    canonical_paper_id: "paper-teacher-model-2023",
    graph_paper_id: "Model-based reasoning in teacher physics education",
    navigation_score: 0.84,
    matched_facets: ["teacher education", "transfer"],
    supporting_edge_refs: ["edge:topic:teacher-modeling"],
    source_status: "model_generated_unverified",
  },
];

export const demoRetrieval: SharedRetrievalResponse = {
  project_id: "physics-ai-demo",
  corpus_id: "physics_stem_v1",
  requested_mode: "discovery",
  retrieval_status: "READY",
  degraded_mode: null,
  candidate_papers: demoCandidates,
  chunk_hits: demoCitations.map((citation, index) => ({
    canonical_chunk_id: citation.canonical_chunk_id,
    canonical_paper_id: citation.canonical_paper_id,
    source_filename: citation.source_filename,
    paper_title: citation.paper_title,
    normalized_doi: citation.normalized_doi,
    chunk_index: citation.chunk_index,
    section_hint: index === 0 ? "Scaffolding design" : "Research methods",
    excerpt: citation.excerpt,
    dense_rank: index + 1,
    sparse_rank: index + 1,
    rrf_score: 0.94 - index * 0.08,
    locator_status: index === 1 ? "UNRESOLVED" : "RESOLVED",
    retrieval_modalities: index === 0 ? ["dense", "sparse", "graph_navigation"] : ["dense", "sparse"],
  })),
  retrieval_trace: {
    query_normalized: "师范生 Python 物理建模 生成式 AI 分层支架 研究设计",
    retrieval_mode: "HYBRID_GRAPH_GUIDED",
    graph_available: true,
    dense_available: true,
    sparse_available: true,
  },
  risk_flags: ["图谱候选仅用于导航，不构成正式证据"],
  manifest_refs: ["manifest:physics_stem_v1:v1"],
};

export const demoBundle: Bundle = {
  context_id: "context-demo-physics-ai",
  project_id: "physics-ai-demo",
  task_ref: "demo-research-design",
  query: "师范生 Python 物理建模 生成式 AI 分层支架 研究设计",
  evidence_refs: demoCitations.map((citation, index) => ({
    evidence_id: `demo-evidence-${index + 1}`,
    project_id: "physics-ai-demo",
    source_id: citation.source_filename,
    chunk_id: citation.canonical_chunk_id,
    excerpt: citation.excerpt,
    location: {
      chunk_index: citation.chunk_index,
      char_start: 0,
      char_end: citation.excerpt.length,
      page_start: index + 2,
      page_end: index + 2,
    },
    verification_status: index === 0 ? "source_verified" : "demo_seed",
    canonical_paper_id: citation.canonical_paper_id,
    canonical_chunk_id: citation.canonical_chunk_id,
    corpus_id: "physics_stem_v1",
    retrieval_modalities: ["dense", "sparse"],
  })),
  source_refs: demoCitations.map((citation) => citation.source_filename),
  estimated_tokens: 680,
  token_budget: 3000,
  context_hash: "demo-context-hash",
  verification_summary: { source_verified: 1, demo_seed: 2 },
  context_mode: "discovery",
  corpus_refs: ["physics_stem_v1"],
  retrieval_strategy: "hybrid",
  retrieval_trace_ref: "retrieval://physics_stem_v1/demo-trace-001",
  retrieval_risk_flags: ["演示数据中的页码定位仅用于界面展示"],
  manifest_refs: ["manifest:physics_stem_v1:v1"],
};

export const demoResearchState: ResearchState = {
  project_id: "physics-ai-demo",
  current_stage: "WAITING_HUMAN",
  rework_target_agent: null,
  rework_reason: null,
  rework_trigger_refs: [],
  task_status: { planning: "DONE", approval: "WAITING_HUMAN" },
  task_ledger: ["task://physics-ai-demo/planning", "task://physics-ai-demo/evidence-review"],
  progress_ledger: ["planning completed", "evidence review candidate generated"],
  evidence_refs: ["evidence://demo-evidence-1", "evidence://demo-evidence-2"],
  context_bundle_refs: ["context-demo-physics-ai"],
  execution_run_refs: [],
  artifact_refs: [
    "candidate://physics-ai-demo/EvidenceMatrixCandidate",
    "candidate://physics-ai-demo/StudyProtocolCandidate",
  ],
  data_asset_refs: [],
  protocol_refs: ["protocol://physics-ai-demo/study-protocol"],
  research_test_result_refs: [],
  risk_profile_refs: ["risk://physics-ai-demo/initial"],
  route_decision_refs: ["route://physics-ai-demo/demo-001"],
  agent_run_refs: ["agent-run://physics-ai-demo/evidence-review"],
  approval_request_refs: ["approval-demo-research-design"],
  budget_state_ref: null,
  recent_rounds: ["evidence_review -> research_design"],
  short_memory_summary: "研究对象为师范生，重点关注建模能力、解释质量和迁移表现。",
  long_memory_refs: ["memory://physics-ai-demo/research-intent"],
  risk_flags: ["主要结果变量仍需人工确认", "私有论文索引尚未完成"],
  unresolved_questions: ["是否采用自然班准实验设计？"],
  error_log: [],
};

const demoRoute: RouteDecision = {
  decision_id: "route-demo-001",
  project_id: "physics-ai-demo",
  current_stage: "WAITING_HUMAN",
  selected_route: "ResearchDesignAgent",
  reason: "用户问题要求把检索证据转化为可审批的研究设计",
  required_context: ["shared_evidence", "research_intent"],
  required_tools: ["hybrid_search", "evidence_context_build"],
  decision_scope: "STAGE",
  risk_level: "MEDIUM",
  triggered_rules: ["research_design_request"],
  final_decider: "controller",
  policy_version: "controller-v1",
  created_at: "2026-08-23T08:00:00Z",
};

export const demoWorkflowState: WorkflowState = {
  project_id: "physics-ai-demo",
  current_stage: "WAITING_HUMAN",
  pending_approval_ref: "approval-demo-research-design",
  last_agent_run_id: "agent-run://physics-ai-demo/evidence-review",
  last_route_decision: demoRoute,
  research_state: demoResearchState,
};

export const demoApproval: ApprovalRequest = {
  request_id: "approval-demo-research-design",
  artifact_ref: "candidate://physics-ai-demo/StudyProtocolCandidate",
  approval_type: "study_protocol",
  reason: "研究设计候选需要研究者确认",
  risk_summary: "主要结果变量、分组方式和迁移测验设置需要人工确认。",
};

const demoAgentResult: AgentResult = {
  agent_run_id: "agent-run://physics-ai-demo/evidence-review",
  agent_id: "evidence_review",
  agent_version: "demo-v1",
  candidate_artifact_refs: demoResearchState.artifact_refs,
  evidence_refs: demoResearchState.evidence_refs,
  tool_requests: [],
  approval_requests: [demoApproval.request_id],
  risk_flags: demoResearchState.risk_flags,
  unresolved_questions: demoResearchState.unresolved_questions,
  recommendations: ["补充同类准实验研究", "确认迁移测验评分量表"],
  confidence: 0.82,
  created_at: "2026-08-23T08:00:00Z",
};

export const demoAgents: AgentCapability[] = [
  "mentor_planning",
  "evidence_review",
  "research_design",
  "data_analysis",
  "paper_writing",
  "independent_review",
].map((agentId) => ({
  agent_id: agentId,
  supported_task_types: ["research_planning", "evidence_review", "bounded_recommendation"],
  allowed_tool_capabilities: ["hybrid_search", "evidence_context_build"],
  allowed_output_types: ["candidate_artifact", "recommendation", "risk_profile"],
  forbidden_actions: ["approve", "freeze_data", "execute_code", "release"],
  read_only_global_state: true,
}));

export const demoRuntime: RuntimeStatus = {
  coding_provider: "deterministic",
  codex_available: false,
  codex_reason: "CODEX_PROVIDER_NOT_SELECTED",
  spss_available: false,
  spss_reason: "SPSS_EXECUTABLE_NOT_CONFIGURED",
};

export const demoPlanningRun: PlanningRun = {
  workflow_state: demoWorkflowState,
  agent_result: demoAgentResult,
  approval_request: demoApproval,
  route_decision: demoRoute,
};

export const demoWorkflowRun: WorkflowRun = {
  workflow_state: demoWorkflowState,
  agent_result: demoAgentResult,
  approval_request: demoApproval,
  route_decision: demoRoute,
};

export const demoExecutionRows = [
  {
    operator_id: "shared_literature_search",
    status: "SUCCEEDED",
    created_at: "2026-08-23T08:02:00Z",
    finished_at: "2026-08-23T08:02:03Z",
  },
  {
    operator_id: "evidence_context_build",
    status: "SUCCEEDED",
    created_at: "2026-08-23T08:03:00Z",
    finished_at: "2026-08-23T08:03:02Z",
  },
];

export const demoRouteRows = [demoRoute];
