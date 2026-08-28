import { describe, expect, it } from "vitest";

import { answerWorkflowQuestion, buildWorkflowConversation, formatMentorPlanningReport, formatWorkflowArtifact, getPlanningClarificationStatus, isPlanningClarification, planningClarificationsComplete } from "./conversation";

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
});
