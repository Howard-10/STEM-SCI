# STEM-SCI backend

This directory contains the Phase 1 Python backend and six specialist-Agent capability framework.

From this directory, install development dependencies with `python -m pip install -e ".[dev]"` and run `ruff check src tests`, `mypy src`, and `pytest`. To enable the optional FAISS + DashScope query path for the declared shared corpus, install `python -m pip install -e ".[hybrid-retrieval]"`; keep `DASHSCOPE_API_KEY` only in the local environment.

The six Agents now produce typed, proposal-only research artifacts: planning and design candidates, bounded evidence packages, analysis specifications, claim-safe manuscript candidates, and independent review findings. Agents never approve a protocol, change project stage, mutate data, freeze data, execute code, or create statistical numbers.

The backend includes a narrow deterministic CSV/Python-only demonstration pipeline for data processing, freezing, Controller-owned code specification compilation, hashed code artifacts, static code review, development-restricted code execution, result validation, and result cards. It also contains a fail-closed Codex CLI provider, SPSS syntax/adapter contracts, and cross-engine validation contracts. It does not yet include a production container sandbox, a locally usable Codex CLI integration, a verified IBM SPSS runtime, long-term memory, or a complete Microsoft GraphRAG stack.

The main boundaries are:

- `stem_sci.agents`: six role contracts, structured candidate builders, optional typed GPT rationale, and deterministic safety fallbacks.
- `stem_sci.controller`: routing, approval gates, REWORK, and review-finding feedback.
- `stem_sci.controller.langgraph_workflow`: LangGraph `StateGraph` orchestration with `MemorySaver`, human `interrupt` approval, `Command(resume=...)`, thread checkpoint recovery, six-Agent routing, and explicit result-validation status.
- `stem_sci.context`: project-scoped evidence and ContextBundle assembly.
- `stem_sci.operators`: structured ToolRequest dispatch and explicit unsupported runs.
- `stem_sci.coding`: code-spec compilation, deterministic development template, optional Codex CLI provider, code-review gate, and local restricted sandbox.
- `stem_sci.statistics`: Python execution contracts, SPSS batch adapter/syntax template, single-engine validation, and cross-engine comparison.
- `stem_sci.artifacts` and `stem_sci.provenance`: versioned audit and lineage stores.
- `stem_sci.knowledge`: read-only shared-corpus identity, manifest checks, real BM25 rebuild, optional FAISS query retrieval, and graph-guided candidate navigation. Graph triples are not formal evidence and never contribute a score to RRF.

## Physics-STEM hybrid retrieval

`physics_stem_v1` declares a 122-paper shared corpus, 1,788 local text chunks and a 944-triple paper-level navigation graph. The local assets remain ignored by Git; their hashes are verified against `data/catalogs/physics_stem/physics_stem_v1.manifest.json` before use.

`STEM_SCI_CONTEXT_PROVIDER=local` remains the default. Set it to `hybrid` only on an internal machine with the declared local assets and query-embedding credential. The hybrid provider is fail-closed unless the declared page/character locator index, PDF hashes, and source-verified EvidenceQuotes pass runtime validation. Discovery search may degrade explicitly to local BM25 when FAISS or the embedding dependency is unavailable; it never calls this degraded mode GraphRAG or cross-engine retrieval. The implemented graph capability is deliberately lightweight: it uses model-generated-unverified paper-level triples only to navigate candidate papers, then retrieves original text chunks. It is not community/global search, automatic claim verification, or a substitute for source verification.

For local workflow development only, set `STEM_SCI_ALLOW_UNVERIFIED_FORMAL_EVIDENCE=true` to let retrieved shared-corpus chunks pass through the formal workflow while retaining `model_generated_unverified` status and a visible risk flag. Keep it unset or `false` for production; strict configuration rejects this switch.

The workflow literature operators are wired to the shared knowledge service: `literature_search` persists an `EvidenceSet`, `paper_screening` persists a `ScreenedPaperSet`, and `paper_extraction` persists a `PaperCard`. `source_verification` completes only when the corpus has verified locator-backed evidence; otherwise it persists a review-required traceability report and keeps the evidence unverified.

## LangGraph six-Agent workflow

`LangGraphWorkflow` is the executable graph entry point. LangGraph owns node transitions, checkpointed human pauses, and `Command(resume=...)`; `ResearchController` remains responsible for artifact persistence, permissions, approvals, REWORK, and audit. The six-Agent order is `mentor_planning -> evidence_review -> research_design -> data_analysis -> paper_writing -> independent_review`.

```python
from stem_sci.controller import LangGraphWorkflow, PlanningRequest
workflow = LangGraphWorkflow()
state = workflow.start(PlanningRequest(project_id="demo", research_intent="scope"))
state = workflow.resume("demo", decision="approved", decided_by="researcher")
```

The same `thread_id` must be used when resuming. A six-Agent chain ending at `VERIFIED` is reported as `AGENT_CHAIN_COMPLETE_REQUIRES_DATA_VALIDATION` until the Controller-owned data pipeline has a passed validation report and statistical result card.

## Local verification

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m mypy src
python -m pytest -q
python -m pytest -q tests/test_langgraph_workflow.py
```

## GPT configuration

Real GPT calls are opt-in for mentor planning, research design, evidence review, and paper writing. Configure `STEM_SCI_LLM_PROVIDER=gpt`, a GPT-compatible `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and the per-run `STEM_SCI_MAX_LLM_CALLS` budget. Keep `STEM_SCI_LLM_API_KEY` in the local environment only. Automated tests inject `FakeLLMProvider` and do not access the network.

## Conversational QA

The user-facing QA chain is exposed separately from the six-agent workflow:

```text
POST /api/v1/qa/answer
```

It performs transparent query expansion, graph-guided hybrid retrieval, `ContextBundle`
assembly, optional GPT-compatible answer synthesis, citations, and SQLite conversation
memory. When an LLM key is configured, the router can use bounded function calls for
`graph_search`, `vector_search`, `hybrid_search`, `paper_lookup`, `workflow_agent`, and
`external_paper_search`, then synthesize a final answer from the returned tool results.
Without an LLM key it returns a deterministic evidence summary and keeps the same
retrieval/memory trace. `workflow_agent` is proposal-only and cannot mutate workflow state.

The response includes `tool_calls` so the frontend can show which retrieval path was
selected without exposing provider credentials or internal database connections.

For DeepSeek-compatible chat completions, set:

```text
STEM_SCI_LLM_PROVIDER=gpt
STEM_SCI_LLM_BASE_URL=https://api.deepseek.com
STEM_SCI_LLM_MODEL=deepseek-chat
STEM_SCI_LLM_API_KEY=<local-secret>
STEM_SCI_LLM_RESPONSE_FORMAT=auto
```

The vector query side still uses `DASHSCOPE_API_KEY` and the declared
`text-embedding-v3` corpus index. Set both keys only in the local shell or an ignored
`.env.local`; never commit them.

When the vector files and PDFs are stored outside the repository, point the backend at
them without copying them into Git:

```text
STEM_SCI_VECTOR_KB_ROOT=C:\path\to\vector_kb
STEM_SCI_PDF_ROOT=C:\path\to\literature_pdfs
```

<<<<<<< HEAD
=======
To rebuild the page/character locator after replacing the local PDF batch, run this
from the repository root. The command updates only traceability metadata and the
manifest hash; it never copies PDF files into Git:

```powershell
python -m pip install -e "backend[hybrid-retrieval]"
$env:STEM_SCI_VECTOR_KB_ROOT="C:\path\to\vector_kb"
python backend/scripts/build_physics_stem_locator.py `
  --pdf-root "C:\path\to\literature_pdfs" `
  --update-manifest
```

The locator keeps exact whitespace-normalized matches as `source_verified`.
Aggressively normalized matches remain `model_generated_unverified` until a person
checks the original PDF, so they are excluded from formal evidence.

>>>>>>> origin/main
To use the imported Neo4j sparse graph instead of the JSON graph artifact:

```text
STEM_SCI_GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7688
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<local-neo4j-password>
NEO4J_DATABASE=neo4j
NEO4J_PROJECT_ID=stem-sci
```

`STEM_SCI_GRAPH_BACKEND=auto` is the default. It tries Neo4j when configured and
falls back to the checked-in JSON graph when Neo4j is unavailable. Use `neo4j` when
you want a failed connection to be visible instead of silently degrading.

## Research-code execution configuration

The API loads the repository root `.env` (and `.env.local`) before constructing
the Controller, so these settings also apply when uvicorn is started from
`backend`. `STEM_SCI_CODEX_COMMAND` defaults to `codex`. `STEM_SCI_CODING_PROVIDER` defaults to
`deterministic`; set it to `codex` only after a locally executable and authenticated
Codex CLI is available. The Codex provider uses non-interactive read-only generation
and accepts only a schema/plan specification, never the frozen-data rows. Its output
remains a candidate until CodeReviewGate and human approval allow it to execute.

Set `STEM_SCI_SPSS_EXECUTABLE` to the licensed IBM SPSS Statistics batch executable when it is available. A `SPSS_PYTHON_DUAL` data-pipeline run now invokes Python and the SPSS adapter and compares their normalized outputs. Without SPSS, the adapter reports a blocked SPSS Run; it never silently downgrades to Python-only. A Python-only result remains `SINGLE_ENGINE` and cannot be represented as cross-engine verified. The read-only `/api/v1/workflow/runtime` endpoint reports provider availability without exposing executable paths. See `docs/reports/RESEARCH_EXECUTION_MVP_STATUS.md` for the current execution evidence and development-sandbox limitations.
