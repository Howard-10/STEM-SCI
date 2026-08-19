# Task 3 Report: Governed Tool Gateway

## Status

Complete. The Controller now has a project-scoped ToolRun audit boundary while
legacy operator requests remain supported during migration.

## Implemented

- Added in-memory and SQLite `ToolRunStore` implementations with project-filtered reads.
- Added policy primitives for project scope, network policy, permissions, and controlled-write approvals.
- Added `ToolGateway` and `ToolExecutor` contracts with typed `BLOCKED`/`FAILED` outcomes.
- Added candidate payload persistence through `ArtifactContentStore` and optional `ArtifactStore` references.
- Added model-backed budget accounting without charging read-only Tools.
- Injected the Gateway into `ResearchController`; unregistered legacy capabilities fall back to `OperatorExecutor`.
- Added the project-scoped `/api/v1/workflow/projects/{project_id}/tool-runs` metadata endpoint.

## Verification

```text
Focused gateway/persistence/controller/audit tests: 14 passed
Full backend tests: 157 passed
Ruff: passed
Mypy: passed
```

ToolRun audit records contain identifiers and references only. Prompts, raw
provider responses, and sensitive environment values are not persisted.

