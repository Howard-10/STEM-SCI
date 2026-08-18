# STEM-SCI Agent Tools and Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a Controller-governed Skill and Tool layer for all six STEM-SCI Agents, with project isolation, typed outputs, audit records, and a restricted Python execution boundary.

**Architecture:** Skills are versioned reasoning bundles that resolve to authorized Tools. Agents emit structured `ToolRequest` objects; a Controller Gateway validates project scope, permissions, approvals, budgets, versions, and idempotency before dispatching a local Tool or sandbox Tool. The existing `operators/` package remains the low-level execution contract, while `skills/` and `tools/` become the Agent-facing layers.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLite stores, pytest, Ruff, Mypy, subprocess-based Python sandbox for the first local implementation, and existing `AgentInput`/`AgentResult`/`ResearchState` contracts.

## Global Constraints

- Keep the existing six-Agent Controller topology and human approval boundaries unchanged.
- Skills define reasoning flow and Tool composition; Tools perform concrete reads, validation, analysis, or candidate generation.
- Agents may only emit structured `ToolRequest` objects; they cannot invoke Tools directly.
- Controller Gateway is the only owner of Tool permissions, project isolation, budgets, approvals, persistence, and audit records.
- First release uses local controlled Tools; external services only receive provider interfaces and are not enabled by default.
- `READ_ONLY` Tools never write formal artifacts; `CANDIDATE_OUTPUT` Tools write only versioned candidate content and references; `CONTROLLED_WRITE` Tools require explicit Controller permission, approval reference, idempotency, and audit records.
- `ResearchState` stores references only and is never directly mutated by an Agent or Tool.
- Python and other high-risk execution runs in a restricted subprocess or container with no network, no API-key access, project-directory allowlisting, and CPU/memory/disk/time limits.
- Any cross-project reference, unauthorized Skill/Tool, invalid version, failed Schema check, failed hash check, or missing approval is rejected with a typed result.
- Expected policy and execution failures return `ToolResult(status=BLOCKED|FAILED, error_code=...)`; only programming errors and invalid registry initialization raise exceptions.
- CI and default tests use Fake Tools/Fake GPT; no external network call is required.
- API keys, full prompts, raw provider responses, and sensitive environment values never enter Git, normal logs, or artifact bodies.

---

## File Map

| Area | Files | Responsibility |
|---|---|---|
| Tool contracts | `backend/src/stem_sci/tools/models.py` | `ToolSpec`, `ToolResult`, `ToolRunRecord`, statuses and execution modes |
| Skill contracts | `backend/src/stem_sci/skills/models.py` | `SkillManifest`, bindings, risk levels and policy references |
| Registries | `backend/src/stem_sci/tools/registry.py`, `backend/src/stem_sci/skills/registry.py`, `backend/src/stem_sci/skills/resolver.py` | Versioned registration and Agent/task resolution |
| Gateway | `backend/src/stem_sci/tools/gateway.py`, `backend/src/stem_sci/tools/policies.py` | Controller-only authorization, budget, approval, scope, and dispatch boundary |
| Built-ins | `backend/src/stem_sci/tools/builtin/` | Local context, artifact, evidence, design, analysis, writing, and review Tools |
| Sandbox | `backend/src/stem_sci/tools/sandbox/python_runner.py` | Restricted Python execution and structured output collection |
| Agent bindings | `backend/src/stem_sci/agents/*`, `backend/src/stem_sci/skills/builtin.py` | Six Agent Skill manifests and capability declarations |
| Persistence | `backend/src/stem_sci/provenance/tool_run_store.py` | SQLite/in-memory ToolRun records |
| Tests | `backend/tests/test_tools_*.py`, `backend/tests/test_skills_*.py`, `backend/tests/test_agent_tool_integration.py` | Unit, policy, sandbox, and end-to-end coverage |

---

### Task 1: Add Typed Skill and Tool Contracts

**Files:**
- Create: `backend/src/stem_sci/tools/__init__.py`
- Create: `backend/src/stem_sci/tools/models.py`
- Create: `backend/src/stem_sci/skills/__init__.py`
- Create: `backend/src/stem_sci/skills/models.py`
- Modify: `backend/src/stem_sci/agents/contracts.py`
- Test: `backend/tests/test_tool_models.py`
- Test: `backend/tests/test_skill_models.py`

**Interfaces:**
- Consumes: existing `AgentInput`, `AgentResult`, `ToolRequest`, `ArtifactRef`, and `RunStatus` contracts.
- Produces: `ToolExecutionMode`, `ToolRunStatus`, `RiskLevel`, `ToolSpec`, `ToolResult`, `ToolRunRecord`, `SkillManifest`, and versioned Agent capability fields.

- [ ] **Step 1: Write failing model tests**

```python
def test_tool_spec_rejects_unknown_execution_mode() -> None:
    with pytest.raises(ValidationError):
        ToolSpec(
            tool_id="context_bundle_read",
            tool_version="v1",
            capability="context_bundle_read",
            execution_mode="INVALID",
            input_schema_ref="schema://ContextRef",
            output_schema_ref="schema://ContextBundle",
            project_scope_required=True,
            network_policy="disabled",
            timeout_seconds=10,
        )


def test_skill_manifest_requires_tool_binding() -> None:
    with pytest.raises(ValidationError):
        SkillManifest(
            skill_id="bounded_corpus_review",
            skill_version="v1",
            agent_ids=["evidence_review"],
            supported_task_types=["synthesize_evidence"],
            required_tool_ids=[],
            input_schema_refs=["schema://EvidenceReviewContext"],
            output_schema_refs=["schema://BoundedEvidenceSynthesis"],
            prompt_template_refs=["prompt://evidence-review-v1"],
            validator_refs=["validator://evidence"],
            risk_level="medium",
        )
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run from `backend/`:

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_tool_models.py tests/test_skill_models.py -q
```

Expected: import failures because the new contracts do not exist.

- [ ] **Step 3: Implement strict contracts**

Add these exact enums and fields:

```python
class ToolExecutionMode(StrEnum):
    READ_ONLY = "READ_ONLY"
    CANDIDATE_OUTPUT = "CANDIDATE_OUTPUT"
    CONTROLLED_WRITE = "CONTROLLED_WRITE"


class ToolRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ToolSpec(StrictModel):
    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    execution_mode: ToolExecutionMode
    input_schema_ref: str = Field(min_length=1)
    output_schema_ref: str = Field(min_length=1)
    required_permissions: list[str] = Field(default_factory=list)
    project_scope_required: bool = True
    network_policy: Literal["disabled", "allowlisted"] = "disabled"
    sandbox_profile: str | None = None
    timeout_seconds: int = Field(gt=0)
    retry_policy: dict[str, int] = Field(default_factory=dict)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    idempotency_policy: Literal["required", "optional", "none"] = "required"


class ToolResult(StrictModel):
    tool_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    status: ToolRunStatus
    output_artifact_refs: list[str] = Field(default_factory=list)
    output_content_refs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    error_code: str | None = None


class ToolRunRecord(ToolResult):
    agent_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    skill_ref: str = Field(min_length=1)
    request_ref: str = Field(min_length=1)
    input_artifact_refs: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

Add `SkillManifest` with `skill_id`, `skill_version`, `agent_ids`, `supported_task_types`, `required_tool_ids`, `input_schema_refs`, `output_schema_refs`, `prompt_template_refs`, `validator_refs`, and a `risk_level` literal of `low`, `medium`, or `high`. Extend `AgentInput` with backward-compatible `allowed_skill_refs` and `allowed_tool_versions`; extend `AgentCapability` with `skill_ids` and `tool_ids`.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
python -m pytest tests/test_tool_models.py tests/test_skill_models.py -q
python -m ruff check src tests
python -m mypy src
```

- [ ] **Step 5: Commit the contracts**

```powershell
git add backend/src/stem_sci/tools backend/src/stem_sci/skills backend/src/stem_sci/agents/contracts.py backend/tests/test_tool_models.py backend/tests/test_skill_models.py
git commit -m "feat(tools): add typed skill and tool contracts"
```

### Task 2: Implement Versioned Registries and Skill Resolution

**Files:**
- Create: `backend/src/stem_sci/tools/registry.py`
- Create: `backend/src/stem_sci/skills/registry.py`
- Create: `backend/src/stem_sci/skills/resolver.py`
- Modify: `backend/src/stem_sci/agents/base.py`
- Test: `backend/tests/test_tool_registry.py`
- Test: `backend/tests/test_skill_registry.py`

**Interfaces:**
- Consumes: `ToolSpec`, `SkillManifest`, `AgentCapability`, and `AgentInput` from Task 1.
- Produces: `ToolRegistry.register/get/resolve`, `SkillRegistry.register/get/list_for_agent`, and `SkillResolver.resolve_for_agent`.

- [ ] **Step 1: Write failing registry tests**

```python
def test_tool_registry_rejects_duplicate_version() -> None:
    registry = ToolRegistry([tool_spec("context_bundle_read", "v1")])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool_spec("context_bundle_read", "v1"))


def test_skill_resolver_filters_agent_and_task() -> None:
    resolver = SkillResolver(skill_registry, tool_registry)
    resolved = resolver.resolve_for_agent(
        agent_id="evidence_review",
        task_type="synthesize_evidence",
        allowed_skill_refs=["bounded_corpus_review@v1"],
    )
    assert resolved.skill_id == "bounded_corpus_review"


def test_skill_resolver_rejects_unapproved_tool_binding() -> None:
    with pytest.raises(ValueError, match="tool not registered"):
        SkillResolver(bad_skill_registry, tool_registry).resolve_for_agent(
            "evidence_review", "synthesize_evidence", ["bad-skill@v1"]
        )
```

- [ ] **Step 2: Run tests to confirm they fail**

```powershell
python -m pytest tests/test_tool_registry.py tests/test_skill_registry.py -q
```

Expected: import failures because registry and resolver modules do not exist.

- [ ] **Step 3: Implement deterministic registries**

Use these signatures:

```python
class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None: ...
    def register(self, spec: ToolSpec) -> None: ...
    def get(self, tool_id: str, tool_version: str | None = None) -> ToolSpec: ...
    def resolve(self, capability: str) -> list[ToolSpec]: ...
    def list(self) -> list[ToolSpec]: ...


class SkillRegistry:
    def __init__(self, manifests: Iterable[SkillManifest] = ()) -> None: ...
    def register(self, manifest: SkillManifest) -> None: ...
    def get(self, skill_id: str, skill_version: str | None = None) -> SkillManifest: ...
    def list_for_agent(self, agent_id: str, task_type: str) -> list[SkillManifest]: ...


class SkillResolver:
    def __init__(self, skill_registry: SkillRegistry, tool_registry: ToolRegistry) -> None: ...
    def resolve_for_agent(self, agent_id: str, task_type: str, allowed_skill_refs: list[str]) -> SkillManifest: ...
```

Use `skill_id@skill_version` and `tool_id@tool_version` as stable reference syntax. Reject duplicate `(id, version)` keys, unknown references, task mismatches, agent mismatches, and manifests containing unregistered Tools.

- [ ] **Step 4: Add six Agent capability manifests**

Add `skills/builtin.py` with one manifest per Agent family. Preserve existing capabilities and add `skill_ids`/`tool_ids` to `BaseAgent` class variables. The manifest set must include:

```text
mentor_planning: research_scope_planning@v1, research_feasibility_assessment@v1
evidence_review: bounded_corpus_review@v1, source_screening@v1, citation_grounding@v1
research_design: research_question_formulation@v1, protocol_draft_validation@v1
data_analysis: data_readiness_audit@v1, result_card_generation@v1
paper_writing: atomic_claim_graph_construction@v1, bilingual_manuscript_rendering@v1
independent_review: citation_review@v1, methodology_review@v1, reproducibility_review@v1
```

- [ ] **Step 5: Run static checks and commit**

```powershell
python -m pytest tests/test_tool_registry.py tests/test_skill_registry.py tests/test_agents.py -q
python -m ruff check src tests
python -m mypy src
git add backend/src/stem_sci/tools/registry.py backend/src/stem_sci/skills backend/src/stem_sci/agents/base.py backend/src/stem_sci/agents/*.py backend/tests/test_tool_registry.py backend/tests/test_skill_registry.py backend/tests/test_agents.py
git commit -m "feat(skills): add versioned registries and agent bindings"
```

### Task 3: Add Project-Scoped ToolRun Persistence and Controller Gateway Policies

**Files:**
- Create: `backend/src/stem_sci/provenance/tool_run_store.py`
- Create: `backend/src/stem_sci/tools/policies.py`
- Create: `backend/src/stem_sci/tools/gateway.py`
- Modify: `backend/src/stem_sci/controller/router.py`
- Modify: `backend/src/stem_sci/controller/__init__.py`
- Modify: `backend/src/stem_sci/api.py`
- Test: `backend/tests/test_tool_gateway.py`
- Test: `backend/tests/test_tool_run_persistence.py`

**Interfaces:**
- Consumes: registries/resolver from Task 2, `ArtifactStore`, `ArtifactContentStore`, `DecisionStore`, `BudgetManager`, `OperatorExecutor`, and existing `AgentRunStore`.
- Produces: `ToolExecutor` Protocol, `ToolGateway.execute`, project-scoped ToolRun storage, API injection, and audit references.

- [ ] **Step 1: Write failing policy tests**

```python
def test_gateway_rejects_cross_project_input() -> None:
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=request_with_input("artifact://project-b/source-1"),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_gateway_blocks_controlled_write_without_approval() -> None:
    result = gateway.execute(
        project_id="project-a",
        agent_id="data_analysis",
        agent_run_id="run-1",
        request=controlled_write_request,
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "APPROVAL_REQUIRED"


def test_gateway_persists_successful_candidate_output() -> None:
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=candidate_output_request,
    )
    assert result.status is ToolRunStatus.SUCCEEDED
    assert content_store.list_project("project-a")
```

- [ ] **Step 2: Run focused tests to confirm they fail**

```powershell
python -m pytest tests/test_tool_gateway.py tests/test_tool_run_persistence.py -q
```

Expected: import failures because Tool Gateway and ToolRun stores do not exist.

- [ ] **Step 3: Implement ToolRun stores**

Provide `InMemoryToolRunStore` and `SQLiteToolRunStore` with:

```python
class ToolRunStore(Protocol):
    def put(self, record: ToolRunRecord) -> ToolRunRecord: ...
    def get(self, project_id: str, tool_run_id: str) -> ToolRunRecord | None: ...
    def list_project(self, project_id: str) -> list[ToolRunRecord]: ...
```

SQLite rows must contain project ID, ToolRun ID, and canonical Pydantic JSON. Every read and list operation must filter by `project_id`.

- [ ] **Step 4: Implement gateway policy checks**

Implement these signatures:

```python
class ToolPolicyError(ValueError): ...


class ToolExecutor(Protocol):
    def execute(self, spec: ToolSpec, project_id: str, agent_id: str, agent_run_id: str, request: ToolRequest) -> ToolResult: ...


class ToolGateway:
    def execute(self, *, project_id: str, agent_id: str, agent_run_id: str, request: ToolRequest, approval_refs: Sequence[str] = ()) -> ToolResult: ...
```

The Gateway must resolve the Skill and Tool, enforce `project_scope_required`, reject unsupported network policies, require approval for `CONTROLLED_WRITE`, call `BudgetManager.consume_llm` only for model-backed Tool implementations, create a `ToolRunRecord`, and persist output only after Schema/hash checks. It must return `BLOCKED` or `FAILED` records rather than raising for expected policy and execution failures.

- [ ] **Step 5: Inject Gateway into Controller**

Add a `tool_gateway: ToolGateway | None` constructor parameter to `ResearchController`. `_execute_agent_tools` must route structured `ToolRequest` objects through the Gateway when configured and preserve the existing `OperatorExecutor` fallback for legacy operator capabilities. Store successful ToolRun IDs in `ResearchState.execution_run_refs`; store ToolRun IDs and result references in `AgentRunRecord` without prompts or sensitive outputs.

- [ ] **Step 6: Run integration tests and commit**

```powershell
python -m pytest tests/test_tool_gateway.py tests/test_tool_run_persistence.py tests/test_controller_agents.py tests/test_audit_persistence.py -q
python -m ruff check src tests
python -m mypy src
git add backend/src/stem_sci/provenance/tool_run_store.py backend/src/stem_sci/tools/policies.py backend/src/stem_sci/tools/gateway.py backend/src/stem_sci/controller backend/src/stem_sci/api.py backend/tests/test_tool_gateway.py backend/tests/test_tool_run_persistence.py backend/tests/test_controller_agents.py backend/tests/test_audit_persistence.py
git commit -m "feat(controller): add governed tool gateway"
```

### Task 4: Implement Local Read-Only and Candidate Evidence Tools

**Files:**
- Create: `backend/src/stem_sci/tools/builtin/context.py`
- Create: `backend/src/stem_sci/tools/builtin/artifacts.py`
- Create: `backend/src/stem_sci/tools/builtin/evidence.py`
- Create: `backend/src/stem_sci/tools/builtin/common.py`
- Modify: `backend/src/stem_sci/context/provider.py`
- Modify: `backend/src/stem_sci/operators/registry.py`
- Test: `backend/tests/test_builtin_context_tools.py`
- Test: `backend/tests/test_builtin_evidence_tools.py`

**Interfaces:**
- Consumes: `ContextProvider`, `ContextBundle`, `EvidenceRef`, `ArtifactStore`, `ArtifactContentStore`, and Tool Gateway contracts.
- Produces: deterministic local Tools for context, artifact integrity, knowledge-base search, source chunks, verification, screening, PaperCards, matrices, coverage, and bounded synthesis validation.

- [ ] **Step 1: Write failing read-only Tool tests**

```python
def test_knowledge_base_search_is_project_scoped() -> None:
    result = knowledge_base_search.execute(project_id="project-a", query="physics", limit=10)
    assert all(item.project_id == "project-a" for item in result.items)


def test_source_verification_checker_rejects_unverified_ref() -> None:
    result = source_verification_checker.execute(project_id="project-a", evidence_ref=unverified_ref)
    assert result.status == "BLOCKED"
    assert result.error_code == "UNVERIFIED_EVIDENCE"


def test_artifact_resolve_rejects_cross_project_reference() -> None:
    result = artifact_resolve.execute("project-a", "artifact-content://project-b/a/1")
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"
```

- [ ] **Step 2: Run tests and confirm they fail**

```powershell
python -m pytest tests/test_builtin_context_tools.py tests/test_builtin_evidence_tools.py -q
```

Expected: import failures because built-in Tool implementations do not exist.

- [ ] **Step 3: Implement context and artifact Tools**

Use these signatures:

```python
def context_bundle_read(project_id: str, context_id: str) -> ContextBundle: ...
def artifact_resolve(project_id: str, artifact_ref: str) -> ArtifactContent: ...
def artifact_integrity_check(project_id: str, artifact_ref: str) -> bool: ...
def evidence_ref_validate(project_id: str, evidence_id: str) -> EvidenceRef: ...
```

Every function must reject mismatched project IDs before reading content. Never expose a database handle, raw SQLite query, API key, or full unfiltered project database to a model.

- [ ] **Step 4: Implement evidence Tools**

Add deterministic local implementations for:

```python
knowledge_base_search(project_id, query, limit) -> EvidenceSearchResultSet
source_chunk_reader(project_id, source_id, chunk_ids) -> list[SourceChunk]
source_verification_checker(project_id, evidence_refs) -> VerificationReport
paper_screening_executor(project_id, source_refs, criteria) -> ScreeningLedger
paper_card_extractor(project_id, source_chunks) -> PaperCardCollection
evidence_matrix_builder(project_id, paper_cards) -> EvidenceMatrixCandidate
citation_deduplicator(project_id, evidence_refs) -> list[EvidenceRef]
evidence_conflict_detector(project_id, matrix) -> EvidenceConflictMap
corpus_coverage_calculator(project_id, matrix) -> CorpusCoverageReport
bounded_synthesis_validator(project_id, synthesis) -> ValidationReport
```

These Tools must preserve evidence references, verification status, and corpus-limit language. Online retrieval is explicitly out of scope.

- [ ] **Step 5: Register Tools and commit**

Register all Task 4 Tools with `READ_ONLY` or `CANDIDATE_OUTPUT` modes, `network_policy="disabled"`, project scope required, and explicit schemas. Run:

```powershell
python -m pytest tests/test_builtin_context_tools.py tests/test_builtin_evidence_tools.py tests/test_evidence_pipeline.py -q
python -m ruff check src tests
python -m mypy src
git add backend/src/stem_sci/tools/builtin backend/src/stem_sci/context/provider.py backend/src/stem_sci/operators/registry.py backend/tests/test_builtin_context_tools.py backend/tests/test_builtin_evidence_tools.py backend/tests/test_evidence_pipeline.py
git commit -m "feat(tools): add project-scoped context and evidence tools"
```

### Task 5: Add Design, Analysis, Writing, and Review Tool Adapters

**Files:**
- Create: `backend/src/stem_sci/tools/builtin/research_design.py`
- Create: `backend/src/stem_sci/tools/builtin/analysis.py`
- Create: `backend/src/stem_sci/tools/builtin/writing.py`
- Create: `backend/src/stem_sci/tools/builtin/review.py`
- Modify: `backend/src/stem_sci/tools/builtin/__init__.py`
- Modify: `backend/src/stem_sci/operators/registry.py`
- Test: `backend/tests/test_builtin_design_tools.py`
- Test: `backend/tests/test_builtin_analysis_tools.py`
- Test: `backend/tests/test_builtin_writing_tools.py`
- Test: `backend/tests/test_builtin_review_tools.py`

**Interfaces:**
- Consumes: existing research protocol models, statistics models, `AtomicClaimGraph`, manuscript drafts, evidence packages, and review contracts.
- Produces: candidate-only design/writing/review adapters and validated analysis Tool inputs for the sandbox task.

- [ ] **Step 1: Write failing design Tool tests**

```python
def test_estimand_validator_rejects_missing_outcome() -> None:
    result = estimand_validator.execute(project_id="project-a", payload={"exposure": "x"})
    assert result.status == ToolRunStatus.BLOCKED
    assert result.error_code == "INVALID_ESTIMAND"


def test_protocol_schema_validator_does_not_approve_protocol() -> None:
    result = protocol_schema_validator.execute(project_id="project-a", protocol=protocol)
    assert result.output_type == "StudyProtocolValidationReport"
    assert not result.approved
```

- [ ] **Step 2: Implement design validators**

Implement `research_question_validator`, `hypothesis_structure_checker`, `estimand_validator`, `causal_dag_checker`, `sampling_plan_checker`, `measurement_plan_checker`, `protocol_schema_validator`, `preregistration_consistency_checker`, `intervention_protocol_linter`, and `quality_gate_plan_builder`. Each returns a candidate validation report and never mutates a formal protocol.

- [ ] **Step 3: Write failing analysis Tool tests**

```python
def test_result_validation_checker_blocks_unvalidated_result() -> None:
    result = result_validation_checker.execute(project_id="project-a", execution_ref="execution-1", validation_refs=[])
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "RESULT_NOT_VALIDATED"


def test_data_freeze_request_builder_only_returns_request() -> None:
    result = data_freeze_request_builder.execute(project_id="project-a", dataset_ref="dataset-1")
    assert result.output_type == "DataFreezeRequest"
    assert result.status is ToolRunStatus.SUCCEEDED
```

- [ ] **Step 4: Implement analysis adapters**

Implement `dataset_catalog_read`, `dataset_schema_profile`, `data_quality_audit`, `missingness_and_outlier_report`, `data_processing_executor`, `model_diagnostic_runner`, `statistical_result_card_builder`, `result_validation_checker`, and `data_freeze_request_builder`. Keep processing outputs candidate-scoped; only the sandbox task may execute code. Result cards require an execution reference and validation reference.

- [ ] **Step 5: Implement writing and review adapters**

Implement these exact adapters:

```python
writing_context_resolver(project_id, context_ref) -> WritingContextBundle
atomic_claim_validator(project_id, graph) -> ValidationReport
claim_evidence_mapper(project_id, graph, evidence_refs) -> ClaimEvidenceMap
manuscript_outline_validator(project_id, outline, graph) -> ValidationReport
manuscript_renderer_zh(project_id, graph, outline) -> ManuscriptDraft
manuscript_renderer_en(project_id, graph, outline) -> ManuscriptDraft
bilingual_consistency_checker(project_id, zh, en, graph) -> BilingualConsistencyReport
citation_consistency_checker(project_id, drafts) -> ValidationReport
numeric_literal_checker(project_id, drafts) -> ValidationReport
result_strength_checker(project_id, drafts, graph) -> ValidationReport
limitation_coverage_checker(project_id, drafts, graph) -> ValidationReport
reproducibility_statement_builder(project_id, artifacts) -> ReproducibilityStatement
table_figure_narrative_builder(project_id, claims, figures) -> TableFigureNarrative

citation_audit(project_id, manuscript_ref) -> ReviewFindingSet
evidence_reference_audit(project_id, manuscript_ref) -> ReviewFindingSet
method_protocol_alignment_checker(project_id, manuscript_ref, protocol_ref) -> ReviewFindingSet
statistical_claim_audit(project_id, manuscript_ref, result_refs) -> ReviewFindingSet
result_limitation_audit(project_id, manuscript_ref) -> ReviewFindingSet
reproducibility_artifact_audit(project_id, manuscript_ref) -> ReviewFindingSet
bilingual_draft_audit(project_id, zh_ref, en_ref) -> ReviewFindingSet
review_finding_builder(project_id, findings) -> ReviewReport
revision_request_builder(project_id, findings) -> RevisionRequest
review_summary_builder(project_id, findings) -> ReviewReport
```

All writing and review outputs remain candidate artifacts or review proposals. They cannot approve, publish, or directly edit a manuscript.

- [ ] **Step 6: Register and test adapters**

```powershell
python -m pytest tests/test_builtin_design_tools.py tests/test_builtin_analysis_tools.py tests/test_builtin_writing_tools.py tests/test_builtin_review_tools.py -q
python -m ruff check src tests
python -m mypy src
git add backend/src/stem_sci/tools/builtin backend/src/stem_sci/operators/registry.py backend/tests/test_builtin_design_tools.py backend/tests/test_builtin_analysis_tools.py backend/tests/test_builtin_writing_tools.py backend/tests/test_builtin_review_tools.py
git commit -m "feat(tools): add design analysis writing and review adapters"
```

### Task 6: Implement the Restricted Python Sandbox

**Files:**
- Create: `backend/src/stem_sci/tools/sandbox/__init__.py`
- Create: `backend/src/stem_sci/tools/sandbox/models.py`
- Create: `backend/src/stem_sci/tools/sandbox/python_runner.py`
- Modify: `backend/src/stem_sci/tools/builtin/analysis.py`
- Test: `backend/tests/test_python_sandbox.py`
- Test: `backend/tests/test_analysis_sandbox_integration.py`

**Interfaces:**
- Consumes: project-scoped dataset artifact refs and sandbox policy from `ToolSpec`.
- Produces: `PythonExecutionRequest`, `PythonExecutionResult`, `PythonSandbox.run`, and `python_analysis_sandbox` Tool implementation.

- [ ] **Step 1: Write failing sandbox tests**

```python
def test_sandbox_runs_allowlisted_python_and_returns_json(tmp_path: Path) -> None:
    result = sandbox.run(PythonExecutionRequest(project_id="project-a", script="print('{\\\"value\\\": 2}')", input_paths=[], output_schema_ref="schema://AnalysisOutput"))
    assert result.status is SandboxStatus.SUCCEEDED
    assert result.json_output == {"value": 2}


def test_sandbox_rejects_network_access() -> None:
    result = sandbox.run(request_with_script("import urllib.request; urllib.request.urlopen('https://example.com')"))
    assert result.status is SandboxStatus.BLOCKED
    assert result.error_code == "NETWORK_DISABLED"


def test_sandbox_does_not_expose_api_key(monkeypatch) -> None:
    monkeypatch.setenv("STEM_SCI_LLM_API_KEY", "secret-sentinel")
    result = sandbox.run(request_with_script("import os; print(os.getenv('STEM_SCI_LLM_API_KEY'))"))
    assert "secret-sentinel" not in result.stdout
```

- [ ] **Step 2: Implement subprocess policy**

`PythonSandbox.run(request: PythonExecutionRequest) -> PythonExecutionResult` creates a temporary project-scoped directory, copies only allowlisted input artifacts, runs a sanitized interpreter environment, enforces timeout, collects stdout/stderr, validates JSON output, and deletes the temporary directory in `finally`. On Windows use `subprocess.run(..., timeout=...)` and sanitized `env`; on supported Linux runners add resource limits without making Linux-only APIs mandatory for local development.

- [ ] **Step 3: Connect analysis Tool and test**

`python_analysis_sandbox` converts successful sandbox JSON into a candidate execution/result reference and returns `BLOCKED` or `TIMED_OUT` without creating a statistical result card when execution fails.

- [ ] **Step 4: Run security tests and commit**

```powershell
python -m pytest tests/test_python_sandbox.py tests/test_analysis_sandbox_integration.py -q
python -m ruff check src tests
python -m mypy src
git add backend/src/stem_sci/tools/sandbox backend/src/stem_sci/tools/builtin/analysis.py backend/tests/test_python_sandbox.py backend/tests/test_analysis_sandbox_integration.py
git commit -m "feat(tools): add restricted python analysis sandbox"
```

### Task 7: Connect Six-Agent Skill Bindings and Tool Gateway End to End

**Files:**
- Modify: `backend/src/stem_sci/agents/base.py`
- Modify: `backend/src/stem_sci/agents/planner.py`
- Modify: `backend/src/stem_sci/agents/evidence.py`
- Modify: `backend/src/stem_sci/agents/design.py`
- Modify: `backend/src/stem_sci/agents/analysis.py`
- Modify: `backend/src/stem_sci/agents/writing.py`
- Modify: `backend/src/stem_sci/agents/reviewer.py`
- Modify: `backend/src/stem_sci/controller/router.py`
- Modify: `backend/src/stem_sci/api.py`
- Modify: `backend/src/stem_sci/provenance/models.py`
- Modify: `backend/src/stem_sci/provenance/agent_run_store.py`
- Test: `backend/tests/test_agent_tool_integration.py`
- Test: `backend/tests/test_workflow_api.py`

**Interfaces:**
- Consumes: six Agent manifests, Tool Gateway, built-in Tools, sandbox, and existing route/approval flow.
- Produces: complete Agent-to-Skill-to-Tool dispatch, read-only ToolRun API, capability output with Skill/Tool IDs, and preserved approval/REWORK semantics.

- [ ] **Step 1: Write failing integration tests**

```python
def test_evidence_agent_request_is_executed_through_gateway() -> None:
    result = controller.run_next("evidence-project")
    assert result.route_decision.selected_route == "evidence_review"
    assert tool_run_store.list_project("evidence-project")
    assert result.workflow_state.research_state is not None
    assert result.workflow_state.research_state.execution_run_refs


def test_agent_capability_exposes_skill_and_tool_ids() -> None:
    capabilities = controller.list_agent_capabilities()
    evidence = next(item for item in capabilities if item.agent_id == "evidence_review")
    assert "bounded_corpus_review@v1" in evidence.skill_ids
    assert "knowledge_base_search@v1" in evidence.tool_ids


def test_controlled_write_never_bypasses_manuscript_approval() -> None:
    result = controller.run_next("writing-project")
    assert result.workflow_state.current_stage.value == "WAITING_HUMAN"
    assert result.approval_request.approval_type == "manuscript"
```

- [ ] **Step 2: Run focused tests to confirm they fail**

```powershell
python -m pytest tests/test_agent_tool_integration.py tests/test_workflow_api.py -q
```

Expected: missing Skill/Tool capability fields, Gateway injection, and ToolRun persistence.

- [ ] **Step 3: Wire Agent manifests and Controller dispatch**

Keep the existing six route entries unchanged. Extend Agent audit handling to include ToolRun references, resolve only Skill refs supplied in `AgentInput`, and dispatch structured requests through `ToolGateway`. Retain the legacy `OperatorExecutor` path for existing scaffold capability strings until all built-in requests use the new Gateway.

- [ ] **Step 4: Add read-only project audit endpoint**

Add this endpoint:

```python
@app.get("/api/v1/workflow/projects/{project_id}/tool-runs")
def workflow_tool_runs(project_id: str) -> list[ToolRunRecord]: ...
```

Return only the requested project’s ToolRun metadata and references, never prompts, API keys, raw stdout, or raw database content.

- [ ] **Step 5: Run integration and full checks**

```powershell
python -m pytest tests/test_agent_tool_integration.py tests/test_workflow_api.py tests/test_audit_persistence.py -q
python -m ruff check src tests
python -m mypy src
python scripts/export_openapi.py
python -c "import json; from pathlib import Path; from stem_sci.api import app; assert json.loads(Path('../contracts/openapi/context-mvp.openapi.json').read_text(encoding='utf-8')) == app.openapi(); print('OpenAPI matches app')"
git add backend/src/stem_sci/agents backend/src/stem_sci/controller backend/src/stem_sci/api.py backend/src/stem_sci/provenance backend/tests/test_agent_tool_integration.py backend/tests/test_workflow_api.py backend/tests/test_audit_persistence.py contracts/openapi/context-mvp.openapi.json
git commit -m "feat(agents): connect skill and tool execution"
```

### Task 8: End-to-End, Security, Documentation, and Release Gates

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `backend/README.md`
- Create: `backend/tests/test_skill_tool_end_to_end.py`
- Create: `backend/tests/test_tool_secret_safety.py`

**Interfaces:**
- Consumes: all Skill, Tool, Gateway, sandbox, Controller, Evidence, and Writing components.
- Produces: Fake Tool/Fake GPT full workflow coverage, security regression tests, documented configuration, and release evidence.

- [ ] **Step 1: Write failing end-to-end tests**

```python
def test_fake_tools_run_all_six_agent_boundaries() -> None:
    project = run_fake_project()
    assert project.tool_runs
    assert project.evidence_package.status == "READY"
    assert project.writing_package.consistency.status == "PASS"
    assert project.review_report.overall_recommendation in {"PASS", "MINOR_REVISION"}


def test_tool_errors_never_contain_api_key_or_prompt() -> None:
    result = run_tool_with_secret("secret-sentinel", "prompt-sentinel")
    assert "secret-sentinel" not in result.error_message
    assert "prompt-sentinel" not in result.error_message
```

- [ ] **Step 2: Document configuration**

Document `STEM_SCI_LLM_PROVIDER`, `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_API_KEY`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and `STEM_SCI_MAX_LLM_CALLS`. State that `.env.local` is local-only and CI uses Fake GPT/Fake Tools. Do not add a real secret or a fake secret that resembles a live credential.

- [ ] **Step 3: Run complete verification**

```powershell
cd backend
$env:PYTHONPATH="src"
python -m pytest -q
python -m ruff check src tests
python -m mypy src
cd ..\frontend
npm.cmd run typecheck
npm.cmd run build
cd ..
git diff --check origin/main...HEAD
git status --short --branch
```

- [ ] **Step 4: Review branch and commit release evidence**

```powershell
git log --oneline --decorate -15
git diff --stat origin/main...HEAD
git commit -m "test(tools): verify six-agent skill and tool workflow"
```

The final review must confirm that the six routes, approvals, REWORK, reference-only `ResearchState`, project isolation, sandbox policy, and secret-safety checks remain intact. Push only `feature/literature-writing-agents`; do not push directly to `main`.

## Self-Review Checklist

- [x] Every design section has an implementation task: contracts, registries, Gateway, local Tools, sandbox, Agent integration, and release tests.
- [x] Every task names exact files, interfaces, focused tests, commands, and a commit boundary.
- [x] The plan preserves the existing six-Agent topology and Controller ownership.
- [x] No task enables online retrieval, GraphRAG, automatic publication, or direct Agent state mutation.
- [x] Tool execution modes, project scope, approval checks, idempotency, audit, and failure states are explicit.
- [x] Python sandbox constraints and secret-safety checks are explicit.
- [x] CI remains offline by using Fake GPT/Fake Tools.
- [x] No unresolved markers or unspecified implementation steps remain.
