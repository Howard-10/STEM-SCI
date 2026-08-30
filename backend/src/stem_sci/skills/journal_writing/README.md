# Journal writing runtime skill

This package applies YAML-defined target-journal rules and general STEM writing
patterns to the existing claim-safe manuscript pipeline. It does not retrieve
literature, parse PDFs, create PaperCards, or perform evidence retrieval.

Add a journal by placing a schema-compatible YAML file in `profiles/`. Canonical
names, aliases, article types, sections, style emphasis, format rules, and asset
paths must remain in YAML rather than Python code.

