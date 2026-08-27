---
name: journal-writing
description: Analyze STEM-education journal exemplars and apply official journal rules, observed journal patterns, methodology patterns, and general article patterns when planning or reviewing research articles.
---

# STEM Journal Writing

Treat this directory as the skill root. Preserve the distinction between evidence types and resolve conflicts in this order:

1. Official journal rules in `journals/`.
2. Observed exemplar patterns in `patterns/journals/`.
3. Methodology patterns in `patterns/methodology/`.
4. The general STEM research-article pattern in `patterns/general/`.

Observed exemplar patterns describe a sample; never present them as submission requirements. Use `null` when a paper does not provide enough evidence for a paper-card field.

For exemplar analysis, run the scripts in `scripts/`. The scripts accept both the existing `examplars/` layout and the conventional `exemplars/` layout, including flat PDFs and `papers/` subdirectories. Validate generated YAML with `scripts/validate_patterns.py` before using it.
