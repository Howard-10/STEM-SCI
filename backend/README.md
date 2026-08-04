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
