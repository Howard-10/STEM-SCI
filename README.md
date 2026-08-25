# STEM-SCI

STEM-SCI is a traceable research-agent system for STEM programming education experiments within education research. The repository uses a frontend/backend Monorepo layout.

Current status: the Phase 1 six-Agent workflow framework is implemented. It includes Controller routing, approval gates, REWORK and review-finding feedback, project-scoped Context MVP integration, structured Operator requests, SQLite audit persistence, and a React workflow workspace. Agent internals and real external providers remain intentionally unimplemented.

## Context MVP local development

The Context MVP accepts Markdown, TXT, JSON, and text-extractable PDF files under a required `project_id`. Its default upload limit is 50 MB and can be changed with `STEM_SCI_MAX_UPLOAD_BYTES`. Scanned or image-only PDFs require a later OCR capability and are rejected clearly in this MVP. Its default CORS allowlist is limited to `http://localhost:5173` and `http://127.0.0.1:5173`; configure `STEM_SCI_CORS_ORIGINS` as a comma-separated allowlist for another local frontend origin. Do not use a wildcard CORS origin. Copy the root `.env.example` for the available local settings.

## Physics-STEM retrieval status

The repository now also contains a bounded, read-only shared-corpus retrieval layer. Its local assets cover 122 Physics-STEM papers, 1,788 paragraph-level text chunks, and a 944-triple paper-level sparse relation graph. The graph only navigates toward candidate papers; paragraph retrievers locate original-text candidates; graph scores do not affect text RRF scores. Every graph triple remains `model_generated_unverified` and cannot be cited as a formal research fact.

The shared corpus is accessed through `/api/v1/corpora`, `/api/v1/retrieval/search`, and `/api/v1/context/hybrid-build`. Discovery mode is usable when declared assets are available. Formal mode is intentionally fail-closed until the project publishes a verified chunk-to-PDF locator index and source-verifies the relevant excerpts. This is a light graph-guided hybrid retrieval implementation, not the full Microsoft GraphRAG community/global-search stack.

## Repository layout

- `backend/`: Python package, backend tests, and backend development configuration.
- `frontend/`: reserved frontend source, public assets, and frontend engineering boundary.
- `contracts/`: reserved API and shared schema contracts.
- `docs/`: project architecture, decisions, tracks, and authoritative planning materials.
- `data/`: local demo-data boundary; formal research data must not be committed.
- `infra/`: reserved Docker and Compose infrastructure configuration.

## Workflow framework

The workflow entry point is the Controller-backed API. The six role boundaries live under `backend/src/stem_sci/agents/`; routing, approval, and REWORK policy live under `backend/src/stem_sci/controller/`. Candidate artifacts, Agent runs, route decisions, approvals, and Operator runs are stored as project-scoped references. A rejected approval or structured `ReviewFinding` returns the project to a mapped Agent without allowing an Agent to mutate workflow state directly.

Run the backend checks from `backend/` with `python -m pytest -q`, `python -m ruff check src tests`, and `python -m mypy src`. Run the frontend checks from `frontend/` with `npm.cmd run typecheck` and `npm.cmd run build`.

The root-level planning materials are retained as project references and are not application source code.

## Optional GPT runtime

The evidence-review and paper-writing pipelines use a provider interface and default to offline `FakeLLMProvider` in CI. For a local GPT run, set `STEM_SCI_LLM_PROVIDER=gpt`, `STEM_SCI_LLM_BASE_URL`, `STEM_SCI_LLM_MODEL`, `STEM_SCI_LLM_TIMEOUT_SECONDS`, and `STEM_SCI_MAX_LLM_CALLS` from the root `.env.example`. Set `STEM_SCI_LLM_API_KEY` only in the local shell or an ignored `.env.local`; never commit it or place it in prompts, logs, or artifact bodies.
