# Conversational Workflow Design

## Goal

Replace black-box workflow dispatch with a conversational research workflow. The user must see the full six-agent route before execution, receive a readable report after every agent run, and explicitly choose whether to continue, provide context for later stages, rerun the current agent, or pause.

## Scope

This feature changes workflow presentation and user control. It does not relax Controller-owned approvals, evidence gates, data-processing approvals, manuscript gates, or agent permissions.

## User Experience

### Workflow Start

When a user starts a workflow from a project with a research direction, the chat thread appends a project route message before the first agent is run. The route names all six agents in their actual order:

1. Mentor Planning: research scope, question tree, feasibility proposal.
2. Evidence Review: retrieval, source verification, evidence matrix.
3. Research Design: variables, sample, methods, ethics and preregistration proposal.
4. Data Analysis: data requirements, analysis plan, executable code proposal and result checks.
5. Paper Writing: evidence-backed manuscript package and citation mapping.
6. Independent Review: reproducibility, risk and release recommendation.

The route message also identifies the current agent and explains that the workflow waits for user direction after every completed stage.

### Stage Report

After a Controller run, the chat thread appends a stage report derived from persisted workflow state, AgentRunRecord entries, ArtifactContent entries, route decisions and pending approvals. A report contains:

- Agent name, completion status and project stage.
- The assigned task and inputs used for the run.
- Human-readable outputs, grouped by artifact type.
- Key findings, evidence references, risks and unresolved questions.
- The next planned agent and its expected output.
- Any mandatory Controller approval or blocking condition.

Artifact content is shown only from persisted records. The frontend does not invent a report when a stored output is absent; it explicitly says that the output is unavailable.

### User Decisions

Each stage report provides four explicit commands:

- Continue to the next agent: dispatch the existing Controller next-stage endpoint only when no mandatory approval blocks progression.
- Save feedback and continue: persist the user feedback as a project workflow note, include it in later agent context, then dispatch the next permitted stage.
- Rerun the current agent with feedback: persist the feedback, mark the current stage for rework and invoke the Controller rerun path for the selected agent. The original run remains traceable.
- Pause workflow: persist the report and feedback without dispatching another agent. Resuming later returns to the same stage.

Mandatory controller approval remains a separate decision. At approval stages, the chat action card shows the approval reason and only exposes the existing approve/reject actions; it does not offer an unsafe bypass.

### Right-side Agent Summary

The existing six-agent progress panel remains. It reflects Controller state and AgentRunRecord status, while the chat is the detailed execution record. Selecting an agent in the summary scrolls to that agent's latest stage report when one exists.

## Architecture

### Backend

Add a workflow timeline/read-model endpoint scoped to a project. It returns the persisted route, ordered agent runs, artifact contents, pending approval and user feedback records needed to reconstruct a conversation after refresh.

Add an authenticated endpoint to record stage feedback. The endpoint accepts a project ID, current agent ID, feedback text and action (`continue`, `rerun`, or `pause`). It stores a traceable event, adds the feedback to the project context used by subsequent work, and delegates all progression to the existing Controller. It rejects invalid stage/action combinations and never performs direct state mutation outside Controller paths.

Reuse existing artifact, run, route and approval stores. Introduce a small event/note record only if current persistence does not carry user feedback with agent and stage provenance.

### Frontend

Extend the chat message model with workflow route, stage report and action-card variants. Load the timeline whenever the project changes and after every workflow command. Render structured content in the existing chat thread rather than a second dashboard.

The start-workflow action appends the route message, calls the existing start endpoint and appends the Mentor Planning report. The continue, feedback and rerun actions call the new workflow feedback command or existing Controller command as appropriate, then reload the timeline.

Use concise research-operational styling consistent with the existing workspace: readable structured sections, expandable artifact content, stable action buttons and explicit blocked/approval states. Do not replace the six-agent summary panel.

## Data and Safety Rules

- Every report maps to stored artifacts and run records.
- User feedback includes author, timestamp, project, stage and agent provenance.
- A rerun retains previous output and creates a distinct subsequent run.
- A pause never changes workflow stage.
- Continue and rerun respect verified-evidence, approval, data and manuscript gates.
- Missing artifacts, missing run records and API failures are displayed as explicit status, not silently treated as completed work.

## Acceptance Criteria

1. Starting a workflow creates a chat route message with all six agents and their tasks.
2. Mentor Planning completion shows stored planning artifacts and a status report in chat.
3. Every subsequent completed agent produces an equivalent report without exposing raw internal logs as the primary interface.
4. The user can continue, save feedback, rerun with feedback or pause at each non-approval stage.
5. Approval stages present approval/reject controls and cannot be bypassed through the conversation actions.
6. Refreshing the project restores the workflow route, reports, feedback and latest action state from persisted backend data.
7. The right-side six-agent progress display remains accurate and is synchronized with the conversation timeline.
8. Backend and frontend tests cover normal progression, rerun provenance, pause behavior, blocked approval and timeline restoration.
