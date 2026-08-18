# STEM-SCI Workflow Framework Implementation

## Scope

This report records the Phase 1 framework boundary. It does not claim that the six Agents can independently complete a real research project. Agent-specific reasoning and external execution providers remain future work.

## Implemented architecture

```text
Research intent
  -> Mentor planning Agent
  -> human approval
  -> Evidence review Agent
  -> human approval
  -> Research design Agent
  -> human approval
  -> Data analysis Agent
  -> human approval
  -> Paper writing Agent
  -> Independent review Agent
```

The Controller is the only component allowed to advance `ResearchState.current_stage`. Agent results are candidates and may contain evidence references, structured `ToolRequest` objects, risks, unresolved questions, and approval requests.

## Feedback and governance

- Rejected approvals enter `REWORK` and map to a target Agent.
- Structured `ReviewFinding.category` can route a method, evidence, analysis, contribution, or writing issue to the corresponding Agent.
- ContextBundle and evidence references are project-scoped and retained in state as references.
- Operator capabilities that do not have an implementation are recorded as `BLOCKED`; unknown capabilities are recorded as `FAILED`.
- Workflow snapshots, approvals, candidate artifacts, Agent runs, route decisions, and Operator runs use SQLite-backed stores in local development.

## Repository boundaries

- Agent role contracts: `backend/src/stem_sci/agents/`
- Controller and policy: `backend/src/stem_sci/controller/`
- Evidence Context MVP: `backend/src/stem_sci/context/`
- Operator and audit contracts: `backend/src/stem_sci/operators/`, `backend/src/stem_sci/artifacts/`, `backend/src/stem_sci/provenance/`
- Workflow API and workspace: `backend/src/stem_sci/api.py`, `frontend/src/`
- API transport contract: `contracts/openapi/context-mvp.openapi.json`

## Verification

The Phase 1 backend suite has no skipped tests and covers Agent contracts, Controller routing, approval idempotency, REWORK feedback, Context integration, Operator records, persistence, and framework invariants. Frontend typecheck and production build are also part of the release checks.

## Explicitly deferred

Real LLM calls, online literature search, GraphRAG/vector retrieval, Python/SPSS execution, data freezing, open code sandboxes, automatic manuscript publication, and production authentication/deployment are not part of this framework upload.
