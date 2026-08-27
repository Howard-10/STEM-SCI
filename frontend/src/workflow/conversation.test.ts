import { describe, expect, it } from "vitest";

import { buildWorkflowConversation } from "./conversation";

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
});
