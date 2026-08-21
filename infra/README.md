# Infrastructure

The deployment bundle lives under `compose/` and `docker/`.

## Backend deployment

1. Create a local `.env` from `compose/.env.example`.
2. Set `NEO4J_PASSWORD`.
3. Set `VECTOR_KB_HOST_ROOT` to the existing `vector_kb` directory.
4. Set `PDF_ROOT_HOST_ROOT` to the directory containing the 122 source PDFs.
5. Add `DASHSCOPE_API_KEY` and `STEM_SCI_LLM_API_KEY` only when the corresponding
   runtime is needed.
6. Start the stack from the repository root:

```powershell
docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.yml up -d --build
```

The API is available at `http://localhost:8000`. Neo4j is reachable by the
backend over the private Compose network; the frontend should only call the
FastAPI API. The backend health endpoint is `/api/v1/health`.

The local corpus remains discovery-ready only when all mounted files pass the
manifest hash and count checks. Formal evidence remains fail-closed until a
verified page/character locator index is published.
