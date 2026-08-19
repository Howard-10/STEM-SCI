# STEM-SCI backend

This directory contains the Phase 1 Python backend and six-Agent workflow framework.

From this directory, install development dependencies with `python -m pip install -e ".[dev]"` and run `ruff check src tests`, `mypy src`, and `pytest`.

The framework keeps Agent reasoning, external literature providers, formal statistical execution, data freezing, and publication authority behind explicit candidate, blocked, or failed states. Local Skill/Tool adapters and a restricted offline Python subprocess provide the implementation boundary without granting Controller authority to an Agent.

The main boundaries are:

- `stem_sci.agents`: six role contracts and deterministic scaffolds.
- `stem_sci.controller`: routing, approval gates, REWORK, and review-finding feedback.
- `stem_sci.context`: project-scoped evidence and ContextBundle assembly.
- `stem_sci.operators`: structured ToolRequest dispatch and explicit unsupported runs.
- `stem_sci.artifacts` and `stem_sci.provenance`: versioned audit and lineage stores.
- `stem_sci.skills` and `stem_sci.tools`: versioned Skill/Tool contracts, local adapters, Gateway policy enforcement, and ToolRun audit.
- `stem_sci.tools.sandbox`: restricted offline Python subprocess for candidate analysis.

## GPT configuration

Real GPT calls are opt-in. Configure `STEM_SCI_LLM_PROVIDER=gpt`, a GPT-compatible `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and the per-run `STEM_SCI_MAX_LLM_CALLS` budget. Keep `STEM_SCI_LLM_API_KEY` in the local environment only. Automated tests inject `FakeLLMProvider` and do not access the network.

`.env.local` is local-only and must remain ignored. The default Tool registry
has network disabled; external retrieval, automatic publication, dataset
freezing, and approval transitions remain Controller-owned operations.
