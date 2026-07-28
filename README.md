# STEM-SCI

STEM-SCI is a traceable research-agent system for STEM programming education experiments within education research. The repository uses a frontend/backend Monorepo layout.

Current status: Phase 0 passed; Phase 1 includes a local, project-scoped Context MVP. This repository intentionally contains no production agent, statistical, sandbox, GraphRAG, or external-provider implementation yet.

## Context MVP local development

The Context MVP accepts Markdown, TXT, and JSON under a required `project_id`. Its default CORS allowlist is limited to `http://localhost:5173` and `http://127.0.0.1:5173`; configure `STEM_SCI_CORS_ORIGINS` as a comma-separated allowlist for another local frontend origin. Do not use a wildcard CORS origin. Copy the root `.env.example` for the available local settings.

## Repository layout

- `backend/`: Python package, backend tests, and backend development configuration.
- `frontend/`: reserved frontend source, public assets, and frontend engineering boundary.
- `contracts/`: reserved API and shared schema contracts.
- `docs/`: project architecture, decisions, tracks, and authoritative planning materials.
- `data/`: local demo-data boundary; formal research data must not be committed.
- `infra/`: reserved Docker and Compose infrastructure configuration.

The root-level planning materials are retained as project references and are not application source code.
