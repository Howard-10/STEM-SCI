# Physics STEM paper identity catalog

`paper_identity_map.json` is the bridge between the local vector knowledge base and the published sparse paper graph.

Each record maps one stable `paper_id` to its title, DOI, source filename, journal, year, vector-chunk count, and matching method. It contains no PDF or full-text chunk content.

The current catalog covers 122 papers. 120 records match by exact filename; 2 match through normalized DOI because their collection serial numbers differ between the two local artifacts.

## Formal evidence locator

`locator.json` maps all 1,788 canonical vector chunks to the 122 original PDFs without storing full text. The current build resolves all chunks: 1,744 unique whitespace-normalized matches are `source_verified`; 44 aggressive normalized matches remain `model_generated_unverified` until human review. Runtime readiness validates the locator hash, schema/counts, and every referenced PDF SHA256 before enabling Formal mode.

Rebuild after any PDF or vector metadata change:

```powershell
python backend/scripts/build_physics_stem_locator.py --pdf-root "<local-pdf-root>" --update-manifest
```