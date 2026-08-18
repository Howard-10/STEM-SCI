# STEM-SCI Workflow Framework

The repository uses a Controller-mediated six-Agent architecture. Agents never call one another directly and never mutate global workflow state. They receive a versioned `AgentInput`, return a validated `AgentResult`, and communicate tool needs through structured `ToolRequest` objects.

The Controller selects a route from the current stage and policy state, records a `RouteDecision`, dispatches one role, merges only references into `ResearchState`, and pauses at a human gate. Rejected approvals enter `REWORK`. Review findings provide a second routing signal and can target the mentor, evidence, design, analysis, or writing role.

The framework is intentionally provider-neutral. Context, Operator, artifact, provenance, and verification interfaces are usable without claiming that external retrieval, statistical execution, or code execution has succeeded.
