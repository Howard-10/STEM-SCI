# STEM-SCI backend

This directory contains the Phase 1 Python backend and six-Agent workflow framework.

From this directory, install development dependencies with `python -m pip install -e ".[dev]"` and run `ruff check src tests`, `mypy src`, and `pytest`.

The framework intentionally does not implement Agent research reasoning, external literature providers, statistical execution, data freezing, or code sandboxes. Those boundaries return explicit candidate, blocked, or failed states until a later provider scope is approved.

The main boundaries are:

- `stem_sci.agents`: six role contracts and deterministic scaffolds.
- `stem_sci.controller`: routing, approval gates, REWORK, and review-finding feedback.
- `stem_sci.context`: project-scoped evidence and ContextBundle assembly.
- `stem_sci.operators`: structured ToolRequest dispatch and explicit unsupported runs.
- `stem_sci.artifacts` and `stem_sci.provenance`: versioned audit and lineage stores.

## GPT configuration

Real GPT calls are opt-in. Configure `STEM_SCI_LLM_PROVIDER=gpt`, a GPT-compatible `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and the per-run `STEM_SCI_MAX_LLM_CALLS` budget. Keep `STEM_SCI_LLM_API_KEY` in the local environment only. Automated tests inject `FakeLLMProvider` and do not access the network.
