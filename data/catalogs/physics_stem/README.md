# Physics STEM paper identity catalog

`paper_identity_map.json` is the bridge between the local vector knowledge base and the published sparse paper graph.

Each record maps one stable `paper_id` to its title, DOI, source filename, journal, year, vector-chunk count, and matching method. It contains no PDF or full-text chunk content.

The current catalog covers 122 papers. 120 records match by exact filename; 2 match through normalized DOI because their collection serial numbers differ between the two local artifacts.
