# Local Physics STEM vector knowledge-base tool

This is the standalone query tool for the local 122-paper hybrid retrieval index. It combines DashScope `text-embedding-v3` semantic retrieval with BM25 keyword retrieval and Reciprocal Rank Fusion.

The index assets are intentionally not stored in Git because they include generated binary indexes and full-text chunk metadata. Place them locally at:

```text
data/local/vector_kb/vectordb/
├── index.faiss
├── bm25.pkl
└── metadata.json
```

Configure a local `tools/vector_kb/.env` from `.env.example`, install the requirements, then run:

```powershell
python tools/vector_kb/query.py "generative AI scaffolding in physics education"
```

Set `STEM_SCI_VECTOR_DB_DIR` when the vector assets are stored elsewhere. The tool verifies that the FAISS index size equals the metadata count before searching; rebuild or correct the index if that validation fails.

Use `data/catalogs/physics_stem/paper_identity_map.json` to map returned vector metadata (`filename` or `doi`) to the sparse graph's `paper_id`.
