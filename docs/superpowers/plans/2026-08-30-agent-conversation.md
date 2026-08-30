# Six-Agent Conversational Workflow Implementation Plan

> **For agentic workers:** This plan records the implementation delivered on the feature branch.

**Goal:** Give each workflow Agent a role-bounded natural-language multi-turn interface that identifies missing research inputs and adapts to user corrections.

**Architecture:** A shared `AgentConversationService` stores per-project, per-conversation state and uses the configured structured LLM provider when available. The service filters updates against each Agent's allowed requirements and emits only conversational decisions; the Controller remains the sole owner of approvals and stage transitions. A project-authenticated API endpoint selects the current Agent, and the frontend routes non-command workflow messages through it.

**Tech Stack:** Python, Pydantic v2, SQLite, FastAPI, React/TypeScript, existing GPT-compatible structured provider.

## Delivered Tasks

- [x] Add strict conversation decision and draft contracts.
- [x] Add in-memory and SQLite conversation state stores.
- [x] Add role-specific required fields and Chinese label extraction for all six Agents.
- [x] Add LLM structured generation with deterministic fallback and forbidden-action boundary.
- [x] Add authenticated `/projects/{project_id}/workflow/conversation` endpoint with current-Agent inference.
- [x] Route frontend workflow chat turns to the conversational Agent endpoint while preserving approval commands.
- [x] Add service and API regression tests.
- [x] Run backend and frontend verification.

## Safety Constraints

- Conversational output cannot approve, reject, advance, freeze, execute, or publish.
- Unknown update keys are discarded.
- Missing requirements are calculated from the server-side role schema, not trusted from the model.
- Provider failures return an explicit deterministic fallback and risk flag.
