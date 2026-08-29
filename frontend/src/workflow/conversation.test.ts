import { describe, expect, it } from "vitest";

import { answerWorkflowQuestion, buildWorkflowConversation, dataAnalysisClarificationsComplete, designClarificationsComplete, evidenceClarificationsComplete, findLatestWorkflowReport, formatDataAnalysisClarificationFeedback, formatDesignClarificationFeedback, formatEvidenceClarificationFeedback, formatMentorPlanningReport, formatReviewClarificationFeedback, formatWritingClarificationFeedback, formatWorkflowArtifact, getDataAnalysisClarificationStatus, getPlanningClarificationStatus, isPlanningClarification, planningClarificationsComplete, reviewClarificationsComplete, writingClarificationsComplete, workflowProjectIdValid } from "./conversation";

describe("buildWorkflowConversation", () => {
  it("builds the six-agent route and mentor report from persisted records", () => {
    const items = buildWorkflowConversation({
      project_id: "project-1",
      research_intent: "AI physics STEM",
      workflow_state: { pending_approval_ref: "approval-1" },
      pending_approval: { approval_type: "research_scope", reason: "请审核研究范围" },
      agent_runs: [{ agent_run_id: "planning-1", agent_id: "mentor_planning", started_at: "2026-08-27T00:00:00Z", output_artifact_refs: [] }],
      artifact_contents: [{ artifact_id: "planning-1:artifact:0", artifact_type: "ResearchScopeCandidate", body: { research_boundary: "师范生物理建模" } }],
      routes: [],
      feedback: [],
    });

    const route = items[0];
    const report = items[1];
    expect(route).toMatchObject({ kind: "workflow-route", currentAgent: "mentor_planning" });
    expect(report).toMatchObject({ kind: "workflow-report", agentId: "mentor_planning", pendingApproval: true });
    if (route?.kind !== "workflow-route" || report?.kind !== "workflow-report") throw new Error("unexpected timeline item");
    expect(route.steps).toHaveLength(6);
    expect(report.artifacts[0]).toMatchObject({ artifactType: "ResearchScopeCandidate" });
    expect(report.approvalReason).toBe("请审核研究范围");
  });

  it("does not crash when a timeline response omits arrays", () => {
    expect(buildWorkflowConversation({
      workflow_state: { pending_approval_ref: null },
      agent_runs: undefined as never,
      artifact_contents: undefined as never,
    })).toHaveLength(1);
  });

  it("resolves artifact contents referenced by content URI", () => {
    const items = buildWorkflowConversation({
      workflow_state: { pending_approval_ref: null },
      pending_approval: null,
      agent_runs: [{ agent_run_id: "planning-2", agent_id: "mentor_planning", started_at: "2026-08-27T00:00:00Z", output_artifact_refs: ["artifact-content://project-1/planning-2:artifact:0/1"] }],
      artifact_contents: [{ artifact_id: "planning-2:artifact:0", artifact_type: "ResearchScopeCandidate", body: { research_boundary: "scope" } }],
    });
    expect(items[1]).toMatchObject({ kind: "workflow-report", artifacts: [{ artifactType: "ResearchScopeCandidate" }] });
  });

  it("answers mentor planning questions from the current workflow artifacts", () => {
    const answer = answerWorkflowQuestion("导师规划的研究边界和可行性是什么？", {
      workflow_state: { pending_approval_ref: "approval-1" },
      pending_approval: { reason: "请审核" },
      agent_runs: [{ agent_run_id: "planning-2", agent_id: "mentor_planning", started_at: "2026-08-27T00:00:00Z", output_artifact_refs: [] }],
      artifact_contents: [
        { artifact_id: "planning-2:artifact:0", artifact_type: "ResearchScopeCandidate", body: { in_scope: ["AI物理教育"], out_of_scope: ["医学"] } },
        { artifact_id: "planning-2:artifact:1", artifact_type: "FeasibilityReport", body: { status: "CANDIDATE_FEASIBLE", required_confirmations: ["确认伦理要求"] } },
      ],
    });
    expect(answer).toContain("研究边界");
    expect(answer).toContain("AI物理教育");
    expect(answer).toContain("确认伦理要求");
  });

  it("formats mentor artifacts as readable report text instead of raw JSON", () => {
    const text = formatWorkflowArtifact("ResearchQuestionTree", {
      primary_question: "AI 支架如何影响物理建模？",
      secondary_questions: ["是否改善迁移能力？", "哪些学生受益？"],
      out_of_scope_questions: ["医学诊断"],
    });
    expect(text).toContain("核心研究问题：AI 支架如何影响物理建模？");
    expect(text).toContain("次级问题：");
    expect(text).toContain("1. 是否改善迁移能力？");
    expect(text).not.toContain("primary_question");
  });

  it("turns planner placeholders into focused user questions", () => {
    const text = formatMentorPlanningReport([
      { artifactType: "ResearchContractCandidate", body: { topic: "AI 物理建模", population: "目标研究人群（待确认）", context: "教育或科研应用场景（待确认）", intervention: "研究意图中描述的干预、方法或技术", comparator: "常规方法或基线条件（待确认）", outcomes: ["主要研究目标指标（待确认）"] } },
      { artifactType: "FeasibilityReport", body: { required_confirmations: ["Confirm ethics and data-governance requirements."] } },
    ]);
    expect(text).toContain("为了继续研究设计，请补充或确认");
    expect(text).toContain("研究对象");
    expect(text).not.toContain("目标研究人群（待确认）");
    expect(text).not.toContain("ResearchContractCandidate");
  });

  it("recognizes a user field clarification as planner feedback", () => {
    expect(isPlanningClarification("研究对象：华东师范大学物理师范生；研究场景：大学物理实验课程")).toBe(true);
    expect(isPlanningClarification("请检索 AI 物理教育的论文")).toBe(false);
    expect(isPlanningClarification("我希望面向大一物理师范生，在力学实验课比较分层 AI 支架与常规提示")).toBe(true);
  });

  it("keeps candidate approval blocked while planning fields are unresolved", () => {
    const status = getPlanningClarificationStatus([
      { artifactType: "ResearchContractCandidate", body: { population: "目标研究人群（待确认）", context: "大学物理课", intervention: "分层 AI 支架", comparator: "常规提示", outcomes: ["建模迁移得分"] } },
    ]);
    expect(status.complete).toBe(false);
    expect(status.missing).toEqual(["研究对象"]);
  });

  it("requires all four structured planning answers before resubmission", () => {
    expect(planningClarificationsComplete({ population: "物理师范生", context: "力学实验课", intervention: "AI 支架", comparator: "常规提示", outcome: "迁移得分" })).toBe(true);
    expect(planningClarificationsComplete({ population: "物理师范生", context: "", intervention: "AI 支架", comparator: "常规提示", outcome: "迁移得分" })).toBe(false);
  });

  it("uses the latest mentor report when planning has been rerun", () => {
    const timeline = {
      workflow_state: { pending_approval_ref: "approval-2" }, pending_approval: null,
      agent_runs: [
        { agent_run_id: "planning-1", agent_id: "mentor_planning", started_at: "2026-08-27T00:00:00Z", output_artifact_refs: [] },
        { agent_run_id: "planning-2", agent_id: "mentor_planning", started_at: "2026-08-27T01:00:00Z", output_artifact_refs: [] },
      ],
      artifact_contents: [
        { artifact_id: "planning-1:artifact:0", artifact_type: "ResearchContractCandidate", body: { population: "目标研究人群（待确认）" } },
        { artifact_id: "planning-2:artifact:0", artifact_type: "ResearchContractCandidate", body: { population: "物理师范生", context: "实验课", intervention: "AI 支架", comparator: "常规提示", outcomes: ["迁移得分"] } },
      ],
    };
    expect(getPlanningClarificationStatus(findLatestWorkflowReport(timeline, "mentor_planning")?.artifacts ?? []).complete).toBe(true);
  });

  it("requires an evidence search goal, scope, and source before rerunning", () => {
    expect(evidenceClarificationsComplete({ goal: "", timeRange: "2020-2026", sources: "平台知识库", preferences: "" })).toBe(false);
    expect(evidenceClarificationsComplete({ goal: "验证干预效果", timeRange: "2020-2026", sources: "平台知识库", preferences: "优先实证研究" })).toBe(true);
  });

  it("serializes evidence clarification answers into readable workflow feedback", () => {
    const feedback = formatEvidenceClarificationFeedback({
      goal: "验证分层 AI 支架是否改善迁移得分",
      timeRange: "2020-2026",
      sources: "平台知识库与已上传 PDF",
      preferences: "优先物理教育实证研究",
      outputs: "证据矩阵、研究空白",
    });
    expect(feedback).toContain("检索目标：验证分层 AI 支架是否改善迁移得分");
    expect(feedback).toContain("文献范围：2020-2026");
    expect(feedback).toContain("证据来源：平台知识库与已上传 PDF");
    expect(feedback).not.toContain("[object Object]");
  });

  it("hides internal evidence references from the user-facing report", () => {
    const text = formatWorkflowArtifact("VerifiedEvidenceRef", {
      verification_status: "model_generated_unverified",
      verified: false,
      risk_flags: ["formal_locator_index_unavailable", "SOURCE_REVIEW_REQUIRED"],
    });
    expect(text).toContain("待人工核验");
    expect(text).toContain("当前仅支持探索性检索");
    expect(text).not.toContain("formal_locator_index_unavailable");
    expect(text).not.toContain("verification_status");
  });

  it("formats evidence coverage and paper cards without internal field names", () => {
    const coverage = formatWorkflowArtifact("CorpusCoverageReport", {
      source_count: 3,
      evidence_count: 12,
      covered_topics: ["Python 物理建模"],
      missing_topics: [],
    });
    const card = formatWorkflowArtifact("PaperCard", {
      title: "Python modeling in physics education",
      main_findings: ["建模任务提升了迁移表现"],
      limitations: ["样本来自单一课程"],
    });
    expect(coverage).toContain("已找到 3 个来源、12 条证据");
    expect(coverage).not.toContain("source_count");
    expect(card).toContain("Python modeling in physics education");
    expect(card).toContain("建模任务提升了迁移表现");
    expect(card).not.toContain("main_findings");
  });

  it("uses the operator shapes for screened papers and extracted paper cards", () => {
    const screened = formatWorkflowArtifact("ScreenedPaperSet", {
      decision: "INCLUDE",
      source_refs: ["source-a", "source-b"],
      evidence_refs: ["evidence-1", "evidence-2", "evidence-3"],
    });
    const extracted = formatWorkflowArtifact("PaperCard", {
      cards: [{ title: "A physics modeling study", main_findings: ["Finding one"] }],
    });
    expect(screened).toContain("已完成初筛，涉及 2 个来源、3 条证据");
    expect(extracted).toContain("已整理 1 篇文献卡片");
    expect(extracted).toContain("A physics modeling study");
    expect(extracted).not.toContain("verification_status");
  });

  it("rejects empty project ids before building workflow URLs", () => {
    expect(workflowProjectIdValid("")).toBe(false);
    expect(workflowProjectIdValid("project-53f8045541c4466b")).toBe(true);
  });

  it("requires core design decisions before rerunning research design", () => {
    expect(designClarificationsComplete({ designType: "", samplePlan: "课程学生", timepoints: "前测、后测", analysisModel: "线性混合模型", ethics: "已确认" })).toBe(false);
    expect(designClarificationsComplete({ designType: "平行随机对照", samplePlan: "课程学生", timepoints: "前测、后测", analysisModel: "线性混合模型", ethics: "已确认" })).toBe(true);
  });

  it("serializes design clarification answers", () => {
    const feedback = formatDesignClarificationFeedback({ designType: "平行随机对照", samplePlan: "招募大一物理师范生", timepoints: "基线、干预后、迁移任务", analysisModel: "线性混合模型", ethics: "已确认课程伦理要求" });
    expect(feedback).toContain("研究设计：平行随机对照");
    expect(feedback).toContain("样本与招募：招募大一物理师范生");
    expect(feedback).not.toContain("[object Object]");
  });

  it("requires analysis rules rather than a duplicate textual data source", () => {
    expect(dataAnalysisClarificationsComplete({ variables: "group, transfer_score", missingData: "完整案例分析", mode: "Python", privacy: "去标识化" })).toBe(true);
    expect(dataAnalysisClarificationsComplete({ variables: "", missingData: "完整案例分析", mode: "Python", privacy: "去标识化" })).toBe(false);
  });

  it("serializes data analysis clarification answers", () => {
    const feedback = formatDataAnalysisClarificationFeedback({ variables: "group, transfer_score", missingData: "按预注册规则处理", mode: "Python", privacy: "去标识化且拒绝直接身份信息" });
    expect(feedback).not.toContain("数据来源：");
    expect(feedback).toContain("必需变量：group, transfer_score");
    expect(feedback).toContain("分析模式：Python");
  });

  it("detects whether an analysis specification has been confirmed", () => {
    expect(getDataAnalysisClarificationStatus([
      { artifactType: "DataAuditSpecification", body: { required_variables: ["group", "transfer_score"] } },
      { artifactType: "AnalysisReadinessReport", body: { status: "READY" } },
    ]).complete).toBe(false);
    expect(getDataAnalysisClarificationStatus([
      { artifactType: "DataAnalysisPreAnalysisPackage", body: { source: "controller-narrow-csv-mvp" } },
    ]).complete).toBe(true);
  });

  it("requires writing scope, language, format, and claim boundary", () => {
    expect(writingClarificationsComplete({ scope: "", languages: "中英文", format: "期刊论文", boundary: "仅使用已核验证据" })).toBe(false);
    expect(writingClarificationsComplete({ scope: "完整研究论文", languages: "中英文", format: "期刊论文", boundary: "仅使用已核验证据" })).toBe(true);
  });

  it("serializes writing clarification answers", () => {
    const feedback = formatWritingClarificationFeedback({ scope: "完整研究论文", languages: "中文和英文", format: "教育技术类期刊", boundary: "结果只引用已验证结果卡" });
    expect(feedback).toContain("写作范围：完整研究论文");
    expect(feedback).toContain("语言版本：中文和英文");
    expect(feedback).toContain("主张边界：结果只引用已验证结果卡");
  });

  it("requires review scope and release threshold before rerunning independent review", () => {
    expect(reviewClarificationsComplete({ scope: "", focus: "引用、方法和可复现性", threshold: "发现重大问题则退回" })).toBe(false);
    expect(reviewClarificationsComplete({ scope: "完整发布前审查", focus: "引用、方法和可复现性", threshold: "发现重大问题则退回" })).toBe(true);
  });

  it("serializes review clarification answers", () => {
    const feedback = formatReviewClarificationFeedback({ scope: "完整发布前审查", focus: "引用、方法和可复现性", threshold: "发现重大问题则退回" });
    expect(feedback).toContain("审查范围：完整发布前审查");
    expect(feedback).toContain("审查重点：引用、方法和可复现性");
  });

  it("formats independent review findings and report artifacts", () => {
    expect(formatWorkflowArtifact("ReviewFinding", {
      severity: "major",
      category: "citation",
      description: "引用缺少原文定位",
      suggested_action: "补充页码或段落",
    })).toContain("严重程度：major");
    expect(formatWorkflowArtifact("RevisionRequest", {
      required_changes: ["补充原文定位"],
      blocking: true,
    })).toContain("必须修改内容");
    expect(formatWorkflowArtifact("ReviewReport", {
      overall_recommendation: "MAJOR_REVISION",
      finding_refs: ["finding://1"],
      revision_request_refs: ["revision://1"],
    })).toContain("总体建议：MAJOR_REVISION");
  });
});
