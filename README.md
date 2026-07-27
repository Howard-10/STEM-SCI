# STEM-SCI

STEM-SCI is a traceable research-agent system for STEM programming education experiments within education research. The repository uses a frontend/backend Monorepo layout.

Current status: Phase 0 passed; Phase 1 scaffold only. This repository intentionally contains no production agent, statistical, sandbox, GraphRAG, or external-provider implementation yet.

## Repository layout

- `backend/`: Python package, backend tests, and backend development configuration.
- `frontend/`: reserved frontend source, public assets, and frontend engineering boundary.
- `contracts/`: reserved API and shared schema contracts.
- `docs/`: project architecture, decisions, tracks, and authoritative planning materials.
- `data/`: local demo-data boundary; formal research data must not be committed.
- `infra/`: reserved Docker and Compose infrastructure configuration.

The root-level planning materials are retained as project references and are not application source code.
