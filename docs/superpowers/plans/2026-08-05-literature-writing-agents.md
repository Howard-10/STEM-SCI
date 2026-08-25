# Literature Review and Paper Writing Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement bounded-corpus evidence synthesis and bilingual manuscript drafting from a shared `AtomicClaimGraph`, using configurable GPT calls without changing the six-Agent Controller topology.

**Architecture:** Keep `EvidenceReviewAgent` and `PaperWritingAgent` as Controller-facing adapters. Each adapter invokes a typed internal pipeline and persists versioned artifact content plus references. A shared structured GPT runtime validates every response before it becomes a candidate artifact; the Controller remains the only owner of workflow state, approvals, budgets, and REWORK.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, `httpx`, SQLite, pytest, mypy, Ruff, React/Vite unchanged.

## Global Constraints

- Use the existing `AgentInput`, `AgentResult`, `ToolRequest`, `ApprovalRequest`, `ReviewFinding`, `ArtifactRef`, `AgentRunRecord`, and `ResearchState` contracts unless a task explicitly extends them.
- Use GPT through a Provider interface; never import a vendor SDK from an Agent pipeline.
- Read only project-scoped verified evidence and versioned artifact references; never expose a database connection or the whole local database to a model.
- Keep `evidence_review` routed from `ProjectStage.SCOPED` and `paper_writing` routed from `ProjectStage.ANALYZED`.
- Agent code must not mutate `ResearchState.current_stage`, approve artifacts, freeze datasets, modify result values, or publish manuscripts.
- Every model response must be parsed into a declared Pydantic model before persistence.
- `RESULT` claims require a validated result reference; literature claims require evidence references; unsupported claims are rejected or marked incomplete.
- Chinese and English manuscripts must share claim IDs, evidence references, numbers, conclusion strength, and limitations.
- API keys are loaded from environment variables only and never committed, logged, or written to artifacts.
- CI uses a Fake GPT Provider. Real GPT calls are opt-in smoke tests and are never required for the default test suite.
- Do not add online retrieval, GraphRAG, vector search, nested Agents, publication automation, or a new workflow stage in this plan.

---

## File Map

| Area | Files | Responsibility |
|---|---|---|
| GPT runtime | `backend/src/stem_sci/agents/runtime/` | Provider protocol, HTTP client, structured parsing, prompt versions |
| Evidence pipeline | `backend/src/stem_sci/agents/evidence_pipeline/` | Context, PaperCard, screening, matrix, gaps, bounded synthesis |
| Writing pipeline | `backend/src/stem_sci/agents/writing_pipeline/` | Claim graph, outline, bilingual rendering, consistency checks |
| Artifact content | `backend/src/stem_sci/artifacts/content_store.py` | Project-scoped content bodies and hashes behind artifact refs |
| Controller | `backend/src/stem_sci/controller/` | Context assembly, LLM budget, Agent injection, audit references |
| Contracts | `backend/src/stem_sci/agents/`, `backend/src/stem_sci/core/` | Capability lists, claim relations, run metadata, statuses |
| Tests | `backend/tests/test_*_agents.py`, `backend/tests/test_llm_runtime.py` | Unit, invariant, integration, and Fake Provider coverage |
| Configuration | `.env.example`, `backend/pyproject.toml` | Non-secret GPT settings and runtime HTTP dependency |

---

### Task 1: Add the GPT structured-generation runtime

**Files:**
- Create: `backend/src/stem_sci/agents/runtime/__init__.py`
- Create: `backend/src/stem_sci/agents/runtime/provider.py`
- Create: `backend/src/stem_sci/agents/runtime/structured_generator.py`
- Create: `backend/src/stem_sci/agents/runtime/prompt_registry.py`
- Modify: `backend/src/stem_sci/controller/budget/budget_manager.py`
- Modify: `backend/src/stem_sci/provenance/models.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_llm_runtime.py`

**Interfaces:**
- Consumes: `STEM_SCI_LLM_PROVIDER`, `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_API_KEY`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and `STEM_SCI_MAX_LLM_CALLS`.
- Produces: `LLMProvider`, `GPTProvider`, `FakeLLMProvider`, `GenerationResult`, `StructuredGenerator`, `PromptRegistry`, and `BudgetManager.consume_llm()`.

- [ ] **Step 1: Write failing Provider and budget tests**

```python
def test_structured_generator_parses_fake_gpt_response() -> None:
    provider = FakeLLMProvider(responses=[{"value": "ok"}])
    result = StructuredGenerator(provider).generate(
        system_prompt="Return JSON.", user_prompt="value",
        response_model=ValueModel, model="gpt-test", prompt_version="test-v1",
    )
    assert result.parsed_output.value == "ok"
    assert result.retry_count == 0


def test_budget_rejects_llm_call_after_limit() -> None:
    budget = BudgetManager(BudgetState(max_llm_calls=1))
    budget.consume_llm()
    with pytest.raises(ValueError, match="llm budget exceeded"):
        budget.consume_llm()


def test_invalid_structured_response_is_retried_then_fails() -> None:
    provider = FakeLLMProvider(responses=[{"bad": True}, {"bad": True}])
    with pytest.raises(StructuredGenerationError):
        StructuredGenerator(provider, max_retries=1).generate(
            system_prompt="Return JSON.", user_prompt="value",
            response_model=ValueModel, model="gpt-test", prompt_version="test-v1",
        )
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run from `backend/`:

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_llm_runtime.py -q
```

Expected: collection or import failures because the runtime interfaces do not exist.

- [ ] **Step 3: Add the runtime contracts and implementation**

Implement these public shapes:

```python
class GenerationResult(BaseModel):
    parsed_output: BaseModel
    model: str
    prompt_version: str
    request_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    response_hash: str
    retry_count: int = 0


class LLMProvider(Protocol):
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        model: str,
        prompt_version: str,
    ) -> GenerationResult: ...
```

`GPTProvider` uses `httpx.Client`, sends a JSON request to the configured GPT-compatible chat endpoint, requests structured output, parses the response without logging the API key or full prompt, and raises typed transport, response, and schema errors. `FakeLLMProvider` returns predetermined payloads and exposes a call counter. Add `BudgetState.can_use_llm()` and `consume_llm()` with retrieval-style accounting. Add optional LLM metadata references to `AgentRunRecord` without storing prompts or response bodies. Add `httpx>=0.27,<1` to runtime dependencies.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_llm_runtime.py -q
python -m ruff check src tests
python -m mypy src
```

Expected: focused tests pass, Ruff and Mypy report no errors.

- [ ] **Step 5: Commit the runtime**

```powershell
git add backend/src/stem_sci/agents/runtime backend/src/stem_sci/controller/budget/budget_manager.py backend/src/stem_sci/provenance/models.py backend/pyproject.toml backend/tests/test_llm_runtime.py
git commit -m "feat(agents): add structured GPT provider runtime"
```

### Task 2: Add project-scoped artifact content and evidence context contracts

**Files:**
- Create: `backend/src/stem_sci/artifacts/content_store.py`
- Create: `backend/src/stem_sci/agents/evidence_pipeline/__init__.py`
- Create: `backend/src/stem_sci/agents/evidence_pipeline/models.py`
- Create: `backend/src/stem_sci/agents/evidence_pipeline/validators.py`
- Modify: `backend/src/stem_sci/artifacts/__init__.py`
- Test: `backend/tests/test_agent_content_store.py`
- Test: `backend/tests/test_evidence_models.py`

**Interfaces:**
- Consumes: `ArtifactRef`, `EvidenceRef`, `ContextBundle`, and runtime `GenerationResult`.
- Produces: `ArtifactContent`, `SQLiteArtifactContentStore`, `EvidenceReviewContext`, `CorpusCoverageReport`, `ScreeningDecision`, `PaperCard`, `EvidenceMatrixRow`, `EvidenceConflictMap`, `ResearchGapReport`, `BoundedEvidenceSynthesis`, `EvidenceSufficiencyReport`, and `EvidenceReviewPackage`.

- [ ] **Step 1: Write failing content-store and evidence-contract tests**

```python
def test_content_store_is_project_scoped_and_versioned(tmp_path: Path) -> None:
    store = SQLiteArtifactContentStore(tmp_path / "workflow.db")
    content = ArtifactContent(
        project_id="physics-demo", artifact_id="paper-card-1", version=1,
        artifact_type="PaperCard", schema_version="v1", body={"title": "A"},
    )
    store.put(content)
    assert store.get("physics-demo", "paper-card-1", 1) == content
    assert store.get("other-project", "paper-card-1", 1) is None


def test_evidence_context_rejects_unverified_evidence() -> None:
    context = EvidenceReviewContext(
        project_id="physics-demo", context_bundle_ref="context://1",
        evidence_refs=[unverified_ref], source_refs=[], research_scope="scope",
    )
    with pytest.raises(ValueError, match="verified"):
        validate_evidence_context(context)
```

- [ ] **Step 2: Run focused tests and confirm they fail**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_agent_content_store.py tests/test_evidence_models.py -q
```

Expected: import or missing-model failures.

- [ ] **Step 3: Implement content storage and typed evidence models**

`ArtifactContent` has `project_id`, `artifact_id`, positive `version`, `artifact_type`, `schema_version`, JSON-compatible `body`, `content_hash`, and `created_at`. Compute `content_hash` from canonical JSON and reject writes whose supplied hash does not match. Implement in-memory and SQLite stores with `put`, `get`, `list_versions`, and `list_project` methods matching the existing `ArtifactStore` style.

`EvidenceReviewContext` contains `project_id`, `context_bundle_ref`, `research_scope`, `evidence_refs`, `source_refs`, inclusion criteria, exclusion criteria, corpus time boundary, and `context_hash`. `EvidenceReviewPackage` contains `status`, typed outputs, `used_evidence_refs`, risk flags, unresolved questions, and generation metadata. Every evidence model carries project-scoped evidence references. Reject cross-project evidence and verification statuses outside the context allow-list before a pipeline starts.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_agent_content_store.py tests/test_evidence_models.py -q
python -m ruff check src tests
python -m mypy src
```

- [ ] **Step 5: Commit the evidence contracts**

```powershell
git add backend/src/stem_sci/artifacts backend/src/stem_sci/agents/evidence_pipeline backend/tests/test_agent_content_store.py backend/tests/test_evidence_models.py
git commit -m "feat(agents): add evidence context and content store"

### Task 3: Implement the bounded-corpus evidence pipeline

**Files:**
- Create: `backend/src/stem_sci/agents/evidence_pipeline/stages.py`
- Create: `backend/src/stem_sci/agents/evidence_pipeline/pipeline.py`
- Create: `backend/src/stem_sci/agents/evidence_pipeline/prompts/__init__.py`
- Create: `backend/src/stem_sci/agents/evidence_pipeline/prompts/v1.py`
- Modify: `backend/src/stem_sci/agents/evidence.py`
- Modify: `backend/src/stem_sci/agents/contracts.py`
- Test: `backend/tests/test_evidence_pipeline.py`

**Interfaces:**
- Consumes: `EvidenceReviewContext`, `StructuredGenerator`, PaperCard models, and source chunks from the context bundle.
- Produces: `EvidenceReviewPipeline.run(context, agent_input) -> EvidenceReviewPackage` and an `EvidenceReviewAgent.run_with_context(...)` adapter returning the existing `AgentResult`.

- [ ] **Step 1: Write failing stage and invariant tests**

```python
def test_evidence_pipeline_marks_gap_as_corpus_limited() -> None:
    package = make_pipeline(fake_responses).run(context, agent_input)
    assert package.research_gap.limit_text.startswith("在当前限定语料中")


def test_evidence_pipeline_drops_claim_without_evidence_ref() -> None:
    package = make_pipeline(response_with_unknown_ref).run(context, agent_input)
    assert "INVALID_EVIDENCE_REFERENCE" in package.risk_flags
    context_ids = {item.evidence_id for item in context.evidence_refs}
    assert all(ref in context_ids for ref in package.used_evidence_refs)


def test_evidence_agent_capability_lists_pipeline_outputs() -> None:
    capability = EvidenceReviewAgent.capability()
    assert "BoundedEvidenceSynthesis" in capability.allowed_output_types
    assert "EvidenceSufficiencyReport" in capability.allowed_output_types
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_evidence_pipeline.py -q
```

Expected: missing pipeline or model failures.

- [ ] **Step 3: Implement the six evidence stages**

Implement these typed functions in `stages.py`:

```python
def audit_corpus(context: EvidenceReviewContext) -> CorpusCoverageReport: ...
def screen_sources(context: EvidenceReviewContext, report: CorpusCoverageReport) -> list[ScreeningDecision]: ...
def extract_paper_cards(context: EvidenceReviewContext, included: list[ScreeningDecision], generator: StructuredGenerator) -> list[PaperCard]: ...
def build_evidence_matrix(context: EvidenceReviewContext, cards: list[PaperCard], generator: StructuredGenerator) -> list[EvidenceMatrixRow]: ...
def analyze_conflicts_and_gaps(rows: list[EvidenceMatrixRow], generator: StructuredGenerator) -> tuple[EvidenceConflictMap, ResearchGapReport]: ...
def synthesize_bounded_evidence(context: EvidenceReviewContext, rows: list[EvidenceMatrixRow], conflicts: EvidenceConflictMap, gaps: ResearchGapReport, generator: StructuredGenerator) -> BoundedEvidenceSynthesis: ...
```

Prompts must require source-backed fields, explicit empty values for unsupported details, and corpus-limited gap language. Stop before synthesis if the context has no permitted evidence; return `EvidenceSufficiencyReport` and risk flags instead of a strong synthesis. The pipeline calls stages in order, validates every response, deduplicates references, calculates deterministic coverage metrics, and returns typed outputs, risks, unresolved questions, and generation metadata. Extend `EvidenceReviewAgent.allowed_output_types` for every package output. In the MVP, local evidence is read from `ContextBundle` and no blocked online operator is requested automatically.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_evidence_pipeline.py tests/test_agents.py -q
python -m ruff check src tests
python -m mypy src
```

- [ ] **Step 5: Commit the evidence pipeline**

```powershell
git add backend/src/stem_sci/agents/evidence.py backend/src/stem_sci/agents/contracts.py backend/src/stem_sci/agents/evidence_pipeline backend/tests/test_evidence_pipeline.py backend/tests/test_agents.py
git commit -m "feat(agents): implement bounded evidence review pipeline"
```

### Task 4: Connect evidence context and content artifacts to Controller audit

**Files:**
- Modify: `backend/src/stem_sci/context/provider.py`
- Modify: `backend/src/stem_sci/controller/router.py`
- Modify: `backend/src/stem_sci/controller/__init__.py`
- Modify: `backend/src/stem_sci/provenance/models.py`
- Modify: `backend/src/stem_sci/api.py`
- Modify: `backend/scripts/export_openapi.py` output contract
- Test: `backend/tests/test_evidence_controller_integration.py`
- Test: `backend/tests/test_audit_persistence.py`

**Interfaces:**
- Consumes: `EvidenceReviewPipeline`, `EvidenceReviewContext`, `ArtifactContentStore`, and the existing `ContextProvider`.
- Produces: Controller-created evidence context, persisted typed artifact bodies, and read-only project audit access.

- [ ] **Step 1: Write failing Controller integration tests**

```python
def test_controller_persists_evidence_package_content(tmp_path: Path) -> None:
    controller = make_controller(tmp_path, fake_provider)
    planning = controller.start_planning(make_planning_request("evidence-integration"))
    controller.resume_approval("evidence-integration", planning.approval_request, decision="approved", decided_by="r")
    result = controller.run_next("evidence-integration")
    assert result.route_decision.selected_route == "evidence_review"
    assert result.workflow_state.research_state is not None
    assert result.workflow_state.research_state.artifact_refs
    assert content_store.list_project("evidence-integration")
```

- [ ] **Step 2: Run the focused integration test and confirm it fails**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_evidence_controller_integration.py -q
```

Expected: the current Controller constructs only a generic `ContextBundle` and does not persist typed Agent content.

- [ ] **Step 3: Wire the Controller without changing the route topology**

Build `EvidenceReviewContext` from the existing project-scoped `ContextBundle`, inject the pipeline and content store into `AgentDispatcher`/`ResearchController`, persist each package item as `ArtifactContent` plus `ArtifactRef`, and keep `ResearchState` reference-only. Add LLM metadata references to `_record_audit`; never persist prompts or API keys. Add a read-only content endpoint only if the existing audit response cannot expose project-scoped content safely.

- [ ] **Step 4: Regenerate and verify the OpenAPI contract**

```powershell
cd backend
$env:PYTHONPATH="src"
python scripts/export_openapi.py
python -c "import json; from pathlib import Path; from stem_sci.api import app; assert json.loads(Path('../contracts/openapi/context-mvp.openapi.json').read_text(encoding='utf-8')) == app.openapi(); print('OpenAPI matches app')"
```

- [ ] **Step 5: Run integration checks and commit**

```powershell
python -m pytest tests/test_evidence_controller_integration.py tests/test_audit_persistence.py -q
python -m ruff check src tests
python -m mypy src
git add backend/src/stem_sci/context/provider.py backend/src/stem_sci/controller backend/src/stem_sci/provenance backend/src/stem_sci/api.py backend/scripts/export_openapi.py contracts/openapi/context-mvp.openapi.json backend/tests/test_evidence_controller_integration.py backend/tests/test_audit_persistence.py
git commit -m "feat(workflow): persist evidence agent artifacts"
```

### Task 5: Add AtomicClaimGraph and bilingual writing contracts

**Files:**
- Create: `backend/src/stem_sci/agents/writing_pipeline/__init__.py`
- Create: `backend/src/stem_sci/agents/writing_pipeline/models.py`
- Create: `backend/src/stem_sci/agents/writing_pipeline/validators.py`
- Create: `backend/src/stem_sci/agents/writing_pipeline/bilingual.py`
- Modify: `backend/src/stem_sci/core/claims.py`
- Test: `backend/tests/test_writing_models.py`
- Test: `backend/tests/test_bilingual_consistency.py`

**Interfaces:**
- Consumes: `AtomicClaim`, `ClaimType`, `ArtifactContent`, evidence refs, method refs, and validated result refs.
- Produces: `WritingContextBundle`, `AtomicClaimNode`, `ClaimRelation`, `AtomicClaimGraph`, `ManuscriptOutline`, `ManuscriptDraft`, `BilingualConsistencyReport`, and `WritingSufficiencyReport`.

- [ ] **Step 1: Write failing claim and bilingual invariant tests**

```python
def test_result_claim_requires_validated_result_ref() -> None:
    claim = AtomicClaimNode(
        claim_id="claim-1", text="结果显示……", claim_type=ClaimType.RESULT,
        evidence_refs=[], result_card_ref=None, section_target="results",
    )
    with pytest.raises(ValueError, match="validated result"):
        validate_claim_node(claim, context)


def test_bilingual_report_blocks_numeric_mismatch() -> None:
    report = compare_bilingual_drafts(chinese_draft("n=64"), english_draft("n=65"), claim_graph)
    assert report.status == "BLOCKED"
    assert "BILINGUAL_MISMATCH" in report.risk_flags
```

- [ ] **Step 2: Run focused tests and confirm they fail**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_writing_models.py tests/test_bilingual_consistency.py -q
```

Expected: missing writing model and validator failures.

- [ ] **Step 3: Implement the writing contracts and validators**

Define these exact relations:

```python
class ClaimRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    INTERPRETS = "INTERPRETS"
    QUALIFIES = "QUALIFIES"
    LIMITS = "LIMITS"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"
```

`WritingContextBundle` includes approved scope, evidence refs, PaperCards, EvidenceMatrix, approved protocol, validated result cards, interpretation boundaries, review findings, output language, and a context hash. `AtomicClaimGraph` validates one and only one `ClaimType` per node, rejects cross-project references, and exposes a `result_claims` view for validation. `ManuscriptOutline` binds section IDs to allowed claim IDs. `ManuscriptDraft` carries language, section bodies, claim IDs, content hash, and status. `WritingPackage` contains `claim_graph`, Chinese and English drafts, `consistency`, `sufficiency`, risk flags, and generation metadata. `compare_bilingual_drafts` compares claim IDs, citations, extracted numeric literals, result direction, causal-strength markers, and limitation coverage, returning `PASS` or `BLOCKED` with explicit findings.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_writing_models.py tests/test_bilingual_consistency.py -q
python -m ruff check src tests
python -m mypy src
```

- [ ] **Step 5: Commit the writing contracts**

```powershell
git add backend/src/stem_sci/core/claims.py backend/src/stem_sci/agents/writing_pipeline backend/tests/test_writing_models.py backend/tests/test_bilingual_consistency.py
git commit -m "feat(agents): add atomic claim and bilingual writing contracts"

### Task 6: Implement the staged bilingual writing pipeline

**Files:**
- Create: `backend/src/stem_sci/agents/writing_pipeline/stages.py`
- Create: `backend/src/stem_sci/agents/writing_pipeline/pipeline.py`
- Create: `backend/src/stem_sci/agents/writing_pipeline/prompts/__init__.py`
- Create: `backend/src/stem_sci/agents/writing_pipeline/prompts/v1.py`
- Modify: `backend/src/stem_sci/agents/writing.py`
- Modify: `backend/src/stem_sci/agents/contracts.py`
- Test: `backend/tests/test_writing_pipeline.py`

**Interfaces:**
- Consumes: `WritingContextBundle`, `StructuredGenerator`, `AtomicClaimGraph`, and Fake GPT responses.
- Produces: `PaperWritingPipeline.run(context, agent_input) -> WritingPackage` and `PaperWritingAgent.run_with_context(...) -> AgentResult`.

- [ ] **Step 1: Write failing staged-pipeline tests**

```python
def test_writing_pipeline_uses_one_claim_graph_for_both_languages() -> None:
    package = make_writing_pipeline(fake_responses).run(context, agent_input)
    assert package.chinese.claim_ids == package.english.claim_ids
    assert package.chinese.citation_refs == package.english.citation_refs
    assert package.consistency.status == "PASS"


def test_writing_pipeline_never_invents_results() -> None:
    package = make_writing_pipeline(resultless_responses).run(context_without_results, agent_input)
    assert package.sufficiency.status == "INCOMPLETE"
    assert not package.claim_graph.result_claims
    assert "INCOMPLETE_RESULT_INPUT" in package.risk_flags


def test_writing_agent_capability_exposes_bilingual_outputs() -> None:
    output_types = set(PaperWritingAgent.capability().allowed_output_types)
    assert {"ManuscriptDraftZh", "ManuscriptDraftEn", "BilingualConsistencyReport"} <= output_types
```

- [ ] **Step 2: Run focused tests and confirm they fail**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_writing_pipeline.py -q
```

Expected: missing pipeline and adapter behavior.

- [ ] **Step 3: Implement the six writing stages**

Implement these typed functions in `stages.py`:

```python
def audit_writing_inputs(context: WritingContextBundle) -> WritingSufficiencyReport: ...
def build_claim_graph(context: WritingContextBundle, generator: StructuredGenerator) -> AtomicClaimGraph: ...
def build_manuscript_outline(context: WritingContextBundle, graph: AtomicClaimGraph, generator: StructuredGenerator) -> ManuscriptOutline: ...
def render_manuscript(language: Literal["zh-CN", "en-US"], context: WritingContextBundle, graph: AtomicClaimGraph, outline: ManuscriptOutline, generator: StructuredGenerator) -> ManuscriptDraft: ...
def validate_manuscript(draft: ManuscriptDraft, graph: AtomicClaimGraph, context: WritingContextBundle) -> list[str]: ...
def check_bilingual_consistency(chinese: ManuscriptDraft, english: ManuscriptDraft, graph: AtomicClaimGraph) -> BilingualConsistencyReport: ...
```

The pipeline audits first, builds one claim graph, creates one outline, renders Chinese and English independently from that graph, validates each draft, and only then compares them. It must not create a `RESULT` claim without a validated result card; incomplete sections remain explicit in `WritingSufficiencyReport`. Prompt templates prohibit new citations, DOI values, sample sizes, statistics, or analyses not present in context.

Update `PaperWritingAgent` to accept an injected pipeline while retaining the existing deterministic `run()` contract for scaffold tests. Its `run_with_context` adapter converts the typed package into candidate refs, evidence refs, risk flags, unresolved questions, and recommendations without changing workflow authority.

- [ ] **Step 4: Run focused tests and static checks**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_writing_pipeline.py tests/test_agents.py -q
python -m ruff check src tests
python -m mypy src
```

- [ ] **Step 5: Commit the writing pipeline**

```powershell
git add backend/src/stem_sci/agents/writing.py backend/src/stem_sci/agents/contracts.py backend/src/stem_sci/agents/writing_pipeline backend/tests/test_writing_pipeline.py backend/tests/test_agents.py
git commit -m "feat(agents): implement bilingual paper writing pipeline"
```

### Task 7: Connect writing context, persistence, and Controller routing

**Files:**
- Modify: `backend/src/stem_sci/controller/router.py`
- Modify: `backend/src/stem_sci/controller/store.py`
- Modify: `backend/src/stem_sci/controller/__init__.py`
- Modify: `backend/src/stem_sci/api.py`
- Modify: `backend/src/stem_sci/provenance/models.py`
- Modify: `contracts/openapi/context-mvp.openapi.json` via export script
- Test: `backend/tests/test_writing_controller_integration.py`
- Test: `backend/tests/test_workflow_api.py`

**Interfaces:**
- Consumes: approved evidence artifacts, approved study protocol refs, validated result refs, `PaperWritingPipeline`, and `ArtifactContentStore`.
- Produces: a Controller-created `WritingContextBundle`, persisted bilingual artifact package, existing `ANALYZED -> paper_writing` route, and read-only audit records.

- [ ] **Step 1: Write failing Controller writing tests**

```python
def test_analyzed_project_dispatches_writing_with_verified_inputs(tmp_path: Path) -> None:
    controller = make_controller_with_approved_analysis(tmp_path, fake_provider)
    result = controller.run_next("writing-demo")
    assert result.route_decision.selected_route == "paper_writing"
    assert "ManuscriptDraftZh" in content_types_for("writing-demo")
    assert "ManuscriptDraftEn" in content_types_for("writing-demo")


def test_controller_keeps_writing_incomplete_when_results_are_missing(tmp_path: Path) -> None:
    controller = make_controller_with_missing_results(tmp_path, fake_provider)
    result = controller.run_next("writing-no-results")
    assert "INCOMPLETE_RESULT_INPUT" in result.agent_result.risk_flags
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_writing_controller_integration.py -q
```

Expected: current Controller does not build a writing context or persist writing package content.

- [ ] **Step 3: Implement writing context assembly and persistence**

At the `ANALYZED` route, resolve only approved protocol refs, validated result refs, evidence refs, and prior review feedback from project-scoped stores. Build `WritingContextBundle` with a deterministic context hash. Inject the writing pipeline and content store, persist each output as `ArtifactContent` plus `ArtifactRef`, and record generation metadata in `AgentRunRecord`. Keep route, approval type `manuscript`, and REWORK behavior unchanged.

- [ ] **Step 4: Expose and verify read-only audit access**

Add only project-scoped read endpoints required to inspect typed writing content; reject cross-project IDs and never return API keys or raw Provider prompts. Regenerate OpenAPI and assert the checked-in contract equals `app.openapi()`.

- [ ] **Step 5: Run integration checks and commit**

```powershell
python -m pytest tests/test_writing_controller_integration.py tests/test_workflow_api.py tests/test_audit_persistence.py -q
python -m ruff check src tests
python -m mypy src
python scripts/export_openapi.py
git add backend/src/stem_sci/controller backend/src/stem_sci/api.py backend/src/stem_sci/provenance contracts/openapi/context-mvp.openapi.json backend/tests/test_writing_controller_integration.py backend/tests/test_workflow_api.py backend/tests/test_audit_persistence.py
git commit -m "feat(workflow): connect bilingual writing artifacts"
```

### Task 8: Add configuration, security checks, and Fake GPT end-to-end coverage

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `backend/README.md`
- Create: `backend/tests/test_agent_end_to_end.py`
- Create: `backend/tests/test_llm_secret_safety.py`
- Modify: `.gitignore` only if the existing rules do not ignore `.env` and `.env.local`

**Interfaces:**
- Consumes: all runtime, evidence, writing, content-store, and Controller components from Tasks 1-7.
- Produces: documented GPT configuration, a Fake GPT six-stage end-to-end test, and secret-leak regression checks.

- [ ] **Step 1: Write failing end-to-end and secret-safety tests**

```python
def test_fake_gpt_runs_evidence_then_bilingual_writing() -> None:
    project = run_fake_project_with_verified_evidence_and_results()
    assert project.evidence_package.status == "READY"
    assert project.writing_package.consistency.status == "PASS"


def test_secret_never_appears_in_generation_errors_or_audit() -> None:
    provider = provider_with_key("test-secret")
    provider.force_error("provider failed")
    with pytest.raises(LLMProviderError) as error:
        provider.generate_structured(**request)
    assert "test-secret" not in str(error.value)
```

- [ ] **Step 2: Run focused tests and confirm they fail**

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_agent_end_to_end.py tests/test_llm_secret_safety.py -q
```

Expected: missing end-to-end fixtures or security assertions.

- [ ] **Step 3: Document non-secret GPT configuration**

Add these names, without real values, to `.env.example`:

```text
STEM_SCI_LLM_PROVIDER=gpt
STEM_SCI_LLM_BASE_URL=https://api.openai.com/v1
STEM_SCI_LLM_MODEL=<set-for-local-deployment>
STEM_SCI_LLM_TIMEOUT_SECONDS=60
STEM_SCI_MAX_LLM_CALLS=12
```

Document that `STEM_SCI_LLM_API_KEY` is set only in the local environment and CI uses `FakeLLMProvider`. Do not put a key, token, or example secret into `.env.example`, README, tests, or fixtures.

- [ ] **Step 4: Run the complete verification suite**

```powershell
cd backend
$env:PYTHONPATH="src"
python -m pytest -q
python -m ruff check src tests
python -m mypy src
cd ..\frontend
npm.cmd run typecheck
npm.cmd run build
```

Expected: all existing and new backend tests pass, Mypy and Ruff are clean, and the existing frontend typecheck/build remain green.

- [ ] **Step 5: Commit configuration and end-to-end coverage**

```powershell
cd ..
git add .env.example README.md backend/README.md backend/tests/test_agent_end_to_end.py backend/tests/test_llm_secret_safety.py
git commit -m "test(agents): verify GPT-backed agent workflow"

### Task 9: Manual GPT smoke test and release review

**Files:**
- No source changes unless a verified smoke-test failure requires a targeted fix.
- Read: `.env.example`, `docs/superpowers/specs/2026-08-05-literature-writing-agents-design.md`

**Interfaces:**
- Consumes: a locally configured GPT API key and model, Fake GPT suite, and read-only workflow/audit APIs.
- Produces: a local smoke-test record outside Git and a final release decision.

- [ ] **Step 1: Configure local-only variables without committing them**

Set `STEM_SCI_LLM_API_KEY` in the shell or an ignored `.env.local`. Do not echo the value, include it in a command argument captured by shell history, or add it to Git.

- [ ] **Step 2: Run one bounded evidence synthesis smoke test**

Use a project containing only verified local evidence, set `STEM_SCI_MAX_LLM_CALLS=12`, and run the evidence route. Verify that every factual field has a project-scoped evidence reference and that audit metadata contains no prompt or key contents.

- [ ] **Step 3: Run one bilingual manuscript smoke test**

Use a project containing an approved protocol and validated result cards. Verify that both drafts share claim IDs, citations, numeric values, and limitation coverage, and that `BilingualConsistencyReport.status` is `PASS`.

- [ ] **Step 4: Run final release gates**

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

Expected: all automated checks pass; only explicitly ignored local configuration and the pre-existing internal plan directory remain outside the commit.

- [ ] **Step 5: Review the branch before pushing**

```powershell
git diff origin/main...HEAD --stat
git log --oneline --decorate -12
```

Push only the feature branch after review; do not push directly to `main`.

---

## Self-Review Checklist

- [x] Design requirements map to Tasks 1-9: GPT runtime, bounded evidence review, artifact content, bilingual writing, Controller integration, audit, budgets, tests, and smoke checks.
- [x] Every task names exact files, interfaces, focused tests, commands, and a commit boundary.
- [x] No task introduces online retrieval, a nested Agent topology, or an unapproved workflow stage.
- [x] `EvidenceReviewContext`, `WritingContextBundle`, `AtomicClaimGraph`, `ManuscriptDraft`, and `BilingualConsistencyReport` are defined before downstream tasks consume them.
- [x] The plan never requires a real API key in source, tests, fixtures, or CI.
- [x] The plan contains no placeholder markers or unspecified error-handling steps.
- [x] Existing scaffold behavior remains covered by current Agent, Controller, persistence, and frontend test commands.
```
```
```
