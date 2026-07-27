# Context and Knowledge MVP Implementation Report

## Implemented scope

The MVP provides a local frontend-to-backend chain for Markdown, TXT, and JSON import; SHA256 de-duplication; SQLite persistence; deterministic chunking; traceable EvidenceItem search; source verification; and token-budgeted ContextBundle assembly. It uses no network retrieval, embeddings, LLM, GraphRAG, or external statistical service.

## Architecture and storage

`backend/src/stem_sci/context/` owns the context models and `ContextService`. SQLite stores source documents, chunks, evidence items, verification records, and bundles. Original uploads reside under configurable `.stem_sci/uploads/`, which is ignored by Git. Bundles contain excerpt-level EvidenceRef objects and IDs, never source-file bodies.

## API and frontend

The FastAPI application serves health, source import/list/detail/chunks, evidence search/detail/source-verification, and context build/detail endpoints under `/api/v1`. `contracts/openapi/context-mvp.openapi.json` is generated from the application. The React/Vite workspace provides source upload, search, source verification, and bundle display with a configurable `VITE_API_BASE_URL`.

## Safety and limits

Only `source_verified` can be set through the verification endpoint; `human_verified` is not exposed. Unsupported files, oversized files, duplicate hashes, and missing verification metadata are rejected. Demo assets are explicitly fictional `demo_seed` material. No user uploads, databases, caches, secrets, or build output are committed.

## Validation and demo

Automated tests cover duplicate SHA handling, rejected file types, source-to-chunk evidence traceability, source verification, budget-bound bundles, persistence, and API flow. Demo: start the backend, open the Vite frontend, import an item from `data/demo`, search a phrase, mark the evidence `source_verified`, build a ContextBundle, then inspect its source/chunk IDs and context hash.

## Not implemented

PDF/OCR, vector search, Chroma, Neo4j, GraphRAG, online retrieval, LLM calls, full Controller/Agent workflows, user authentication, real research data, and human approval workflows remain outside this MVP.
