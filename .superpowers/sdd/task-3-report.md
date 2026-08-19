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

## Review Fixes

Implemented the scoped review fixes without changing the six-Agent route topology
or the legacy Operator fallback:

- Tool execution payloads are transient and ToolRun persistence/API expose only an allowlisted audit projection.
- READ_ONLY writes are rejected; candidate payloads require project, schema, version, and hash validation before atomic persistence, with rollback on failure and no overwrites.
- Controlled-write approvals are bound to project, Tool, version, target artifact, request context, permissions, and operation hash; idempotent requests are project-scoped and deduplicated.
- Input and executor output references use strict URI parsing and project ownership checks; only exact `context://initial` is a bootstrap exception.
- Expected timeout, execution, schema, hash, and policy failures return stable typed outcomes.
- Controller forwards approved references and explicit permissions, and only successful ToolRun IDs enter reference-only `ResearchState.execution_run_refs`.

### Verification

```text
python -m pytest tests/test_tool_gateway.py tests/test_tool_run_persistence.py -q
27 passed in 1.81s

python -m pytest tests/test_tool_gateway.py tests/test_tool_run_persistence.py tests/test_controller_agents.py tests/test_audit_persistence.py -q
35 passed in 0.46s

python -m pytest -q
178 passed in 2.57s

python -m ruff check src tests
All checks passed!

python -m mypy src
Success: no issues found in 102 source files
```
