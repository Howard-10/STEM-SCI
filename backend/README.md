# STEM-SCI backend

This directory contains the Phase 1 Python backend and six specialist-Agent capability framework.

From this directory, install development dependencies with `python -m pip install -e ".[dev]"` and run `ruff check src tests`, `mypy src`, and `pytest`. To enable the optional FAISS + DashScope query path for the declared shared corpus, install `python -m pip install -e ".[hybrid-retrieval]"`; keep `DASHSCOPE_API_KEY` only in the local environment.

The six Agents now produce typed, proposal-only research artifacts: planning and design candidates, bounded evidence packages, analysis specifications, claim-safe manuscript candidates, and independent review findings. Agents never approve a protocol, change project stage, mutate data, freeze data, execute code, or create statistical numbers.

The backend includes a narrow deterministic CSV/Python-only demonstration pipeline for data processing, freezing, Controller-owned code specification compilation, hashed code artifacts, static code review, development-restricted code execution, result validation, and result cards. It also contains a fail-closed Codex CLI provider, SPSS syntax/adapter contracts, and cross-engine validation contracts. It does not yet include a production container sandbox, a locally usable Codex CLI integration, a verified IBM SPSS runtime, long-term memory, a complete Microsoft GraphRAG stack, or a LangGraph workflow.

The main boundaries are:

- `stem_sci.agents`: six role contracts, structured candidate builders, optional typed GPT rationale, and deterministic safety fallbacks.
- `stem_sci.controller`: routing, approval gates, REWORK, and review-finding feedback.
- `stem_sci.context`: project-scoped evidence and ContextBundle assembly.
- `stem_sci.operators`: structured ToolRequest dispatch and explicit unsupported runs.
- `stem_sci.coding`: code-spec compilation, deterministic development template, optional Codex CLI provider, code-review gate, and local restricted sandbox.
- `stem_sci.statistics`: Python execution contracts, SPSS batch adapter/syntax template, single-engine validation, and cross-engine comparison.
- `stem_sci.artifacts` and `stem_sci.provenance`: versioned audit and lineage stores.
- `stem_sci.knowledge`: read-only shared-corpus identity, manifest checks, real BM25 rebuild,
  optional FAISS query retrieval, and graph-guided candidate navigation. Graph triples are not
  formal evidence and never contribute a score to RRF.

## Physics-STEM hybrid retrieval

`physics_stem_v1` declares a 122-paper shared corpus, 1,788 local text chunks and a 944-triple
paper-level navigation graph. The local assets remain ignored by Git; their hashes are verified
against `data/catalogs/physics_stem/physics_stem_v1.manifest.json` before use.

`STEM_SCI_CONTEXT_PROVIDER=local` remains the default. Set it to `hybrid` only on an internal
machine with the declared local assets and query-embedding credential. The hybrid provider is
fail-closed for Controller-facing formal contexts until a verified page/character locator index
and source-verified EvidenceQuotes are available. Discovery search may degrade explicitly to
local BM25 when FAISS or the embedding dependency is unavailable; it never calls this degraded
mode GraphRAG or cross-engine retrieval. The implemented graph capability is deliberately
lightweight: it uses model-generated-unverified paper-level triples only to navigate candidate
papers, then retrieves original text chunks. It is not community/global search, automatic
claim verification, or a substitute for source verification.

## GPT configuration

Real GPT calls are opt-in for mentor planning, research design, evidence review, and paper writing. Configure `STEM_SCI_LLM_PROVIDER=gpt`, a GPT-compatible `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and the per-run `STEM_SCI_MAX_LLM_CALLS` budget. Keep `STEM_SCI_LLM_API_KEY` in the local environment only. Automated tests inject `FakeLLMProvider` and do not access the network.

## Research-code execution configuration

`STEM_SCI_CODEX_COMMAND` defaults to `codex`. The Codex provider uses non-interactive read-only generation and accepts only a schema/plan specification, never the frozen-data rows. Its output remains a candidate until CodeReviewGate and human approval allow it to execute.

Set `STEM_SCI_SPSS_EXECUTABLE` to the licensed IBM SPSS Statistics batch executable when it is available. Without it, the adapter reports a blocked SPSS Run; a Python-only result remains `SINGLE_ENGINE` and cannot be represented as cross-engine verified. See `docs/reports/RESEARCH_EXECUTION_MVP_STATUS.md` for the current execution evidence and development-sandbox limitations.
