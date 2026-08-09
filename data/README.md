# Data boundary

`demo/` is reserved for safe, synthetic demonstration data. Raw, processed, frozen, or identifiable research data must not be committed to this repository.

The repository may additionally contain lightweight, shareable research metadata:

- `catalogs/`: bibliographic catalogs and stable identity mappings. These files must not contain source full text.
- `derived/`: versioned, derived research artifacts such as a sparse paper graph. Each artifact must state its source-verification status and must not be treated as a source of final research claims by itself.

The following remain local-only and are ignored by Git: PDFs, full-text chunk metadata, vector indexes, caches, API keys, and research datasets under `data/local/`, `data/raw/`, `data/processed/`, or `data/frozen/`.
