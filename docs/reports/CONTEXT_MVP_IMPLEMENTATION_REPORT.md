# Context and Knowledge MVP Implementation Report

## Implemented scope

The Context MVP is a local, project-scoped frontend/backend workflow for Markdown, TXT, JSON, and text-extractable PDF import; SHA256 de-duplication within a project; SQLite persistence; deterministic chunking; traceable evidence search; source verification; SourceChunk trace-back; and token-budgeted ContextBundle construction. It uses no network retrieval, embeddings, LLM, GraphRAG, external statistical service, Controller workflow, or Agent workflow.

## Project isolation and persistence

`SourceDocument`, `SourceChunk`, `EvidenceRef`, and `ContextBundle` each carry `project_id`. SQLite queries for lists, details, search, verification, Bundle construction, and Bundle retrieval all require the same project scope. A legacy local database without `project_id` is migrated to a `default` project on service startup; new sources use a `(project_id, sha256)` uniqueness constraint. The store remains local under configurable `STEM_SCI_STORAGE_DIR`, defaulting to `.stem_sci/`, which is ignored by Git.

## PDF import boundary

The MVP uses `pypdf` to extract text from ordinary text-based PDFs. A valid PDF follows the same source, chunk, evidence, project-isolation, and ContextBundle chain as text files. Encrypted PDFs, unreadable PDFs, and PDFs without extractable text return safe 400 errors. Image-only or scanned PDFs are not silently accepted: they require a future OCR capability.

## API safety and verification boundary

The FastAPI API uses stable `{ "error": { "code", "message" } }` error responses. The default upload limit is 50 MB and can be configured with `STEM_SCI_MAX_UPLOAD_BYTES`. Unsupported extensions, empty or oversized files, invalid UTF-8, invalid JSON, unreadable PDFs, encrypted PDFs, and PDFs without extractable text return deterministic 400 responses without filesystem paths. Invalid request schemas return 422; unexpected internal exceptions return a generic 500 response. Public uploads derive only `demo_seed` (from a machine-readable demo marker) or `model_generated_unverified`; they cannot request `human_verified`. The verification endpoint accepts only `project_id`, `verified_by`, and `verification_note`; an attempted `verification_status=human_verified` returns 400.

## CORS and frontend

The default CORS allowlist is limited to `http://localhost:5173` and `http://127.0.0.1:5173`, configurable through `STEM_SCI_CORS_ORIGINS`. Wildcard origins are not used. The React/Vite frontend uses `VITE_API_BASE_URL` and `VITE_PROJECT_ID`, with API calls centralized in `frontend/src/api/client.ts`; its Source Library accepts `.pdf` alongside Markdown, TXT, and JSON. Its four functional views are Source Library, Evidence Search, Evidence Detail with SourceChunk trace-back, and ContextBundle construction/viewing; it contains no static data mock.

## Search and ContextBundle rules

Search is deterministic Python keyword matching over project-scoped SQLite records, not GraphRAG or vector retrieval. Results sort by score descending, verification rank, source ID, then chunk index. ContextBundle construction prioritizes `human_verified`, then `source_verified`, then other allowed statuses; it accepts at most one chunk per source by default and skips candidates that exceed the token budget. Every selected evidence item preserves source ID, chunk ID, and source location.

## Demo data

All three files under `data/demo/` carry a machine-readable demo marker: `STEM_SCI_DEMO_SEED: true` in TXT/Markdown or `"stem_sci_demo_seed": true` in JSON. They are fictional material only. Uploading them through the normal API produces `demo_seed`; ordinary files, including ordinary PDFs, produce `model_generated_unverified`.

## Validation performed

Using the installed backend development environment, the following checks passed:

- `ruff check backend/src backend/tests`
- `mypy backend/src` - 60 source files, no issues
- `pytest backend/tests -q` - 18 passed, 10 intentionally skipped Phase 1 placeholder tests, one upstream TestClient deprecation warning
- `python -m compileall backend/src`
- package import of `stem_sci`
- `npm run typecheck`
- `npm run build`

An actual temporary local run started FastAPI on port 8000 and Vite on port 5173. A CORS preflight from `http://127.0.0.1:5173` returned the expected allow-origin header. The flow imported a demo Markdown as `demo_seed`, searched Evidence, opened its detail, marked it `source_verified`, built a ContextBundle, and traced its evidence back to the original SourceChunk.

A separate temporary HTTP check uploaded a real text-extractable PDF, received `application/pdf` and `model_generated_unverified`, and found its extracted text through Evidence search. Temporary PDFs, SQLite files, uploads, and server processes were deleted after both checks.

## OpenAPI contract

`contracts/openapi/context-mvp.openapi.json` is re-exported from the current FastAPI application and matches it exactly. It contains ten routes: health; source import/list/detail/chunks; evidence search/detail/verification; and context build/detail. The source document schema includes `application/pdf` as an accepted media type.

## Intentionally not implemented

OCR for scanned or image-only PDFs, online literature retrieval, embeddings, Chroma, Neo4j, GraphRAG, long-term memory, formal Literature Operators, Controller/Agent integration, human-approval workflow, authentication, SPSS/Python analysis, real research data, and external-provider integration remain out of scope for this Context MVP.
