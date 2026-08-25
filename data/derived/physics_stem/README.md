# Physics STEM sparse paper graph

`sparse_paper_graph_v2.json` is a paper-level relationship artifact generated from the 122-paper Physics STEM education corpus.

- Coverage: 122 papers and 944 triples.
- Node anchor: `paper_id`.
- Provenance bridge: `source_filename` and `data/catalogs/physics_stem/paper_identity_map.json`.
- Status: every triple is `model_generated_unverified`.

It supports navigation and exploratory analysis of relations such as research method, pedagogy, technology, subject domain, learning outcome, population, sample, and reported claims. It is not a substitute for the source papers or for human source verification.

The raw PDFs, FAISS index, BM25 index, full-text vector metadata, caches, and API credentials remain under local-only storage and are intentionally absent from Git.
