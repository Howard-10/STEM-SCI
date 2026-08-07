"""实体抽取 Prompt 模板.

提供中英双语 prompt，根据文献语言自动选择。
对应当前 4 个本地模型：DeepSeek 4.0 / Kimi-K2.6 / Qwen3.5 / GLM 5.1。
统一使用 OpenAI 兼容的 chat/completions 接口。
"""

from __future__ import annotations

from .schema import ENTITY_TYPE_DEFINITIONS, RELATION_TYPE_DEFINITIONS


def _build_entity_type_section() -> str:
    """构建实体类型说明段."""
    lines = ["## Entity Types", ""]
    for et, desc in ENTITY_TYPE_DEFINITIONS.items():
        lines.append(f"- **{et.value}**: {desc}")
    return "\n".join(lines)


def _build_relation_type_section() -> str:
    """构建关系类型说明段."""
    lines = ["## Relation Types", ""]
    for rt, desc in RELATION_TYPE_DEFINITIONS.items():
        lines.append(f"- **{rt.value}**: {desc}")
    return "\n".join(lines)


def _build_few_shot_examples() -> str:
    """构建 few-shot 示例."""
    return """## Few-Shot Examples

### Example 1
Text: "This study employed a quasi-experimental design to investigate the effect of
project-based learning (PBL) integrated with ChatGPT on undergraduate students'
conceptual understanding of thermodynamics."
paper_id: "paper-001"

Output:
```json
[
  {
    "head": "paper-001",
    "head_type": "Paper",
    "relation": "USES_METHOD",
    "tail": "quasi-experimental design",
    "tail_type": "ResearchMethod",
    "evidence": "This study employed a quasi-experimental design",
    "confidence": 1.0,
    "layer": "L2"
  },
  {
    "head": "paper-001",
    "head_type": "Paper",
    "relation": "ADOPTS_PEDAGOGY",
    "tail": "project-based learning",
    "tail_type": "PedagogicalMethod",
    "evidence": "effect of project-based learning (PBL) integrated with ChatGPT",
    "confidence": 0.95,
    "layer": "L2"
  },
  {
    "head": "paper-001",
    "head_type": "Paper",
    "relation": "DEPLOYS_TECH",
    "tail": "ChatGPT",
    "tail_type": "Technology",
    "evidence": "project-based learning (PBL) integrated with ChatGPT",
    "confidence": 0.95,
    "layer": "L2"
  },
  {
    "head": "paper-001",
    "head_type": "Paper",
    "relation": "INVOLVES_POPULATION",
    "tail": "undergraduate students",
    "tail_type": "StudentPopulation",
    "evidence": "undergraduate students' conceptual understanding",
    "confidence": 0.95,
    "layer": "L2"
  },
  {
    "head": "paper-001",
    "head_type": "Paper",
    "relation": "STUDIES_DOMAIN",
    "tail": "thermodynamics",
    "tail_type": "SubjectDomain",
    "evidence": "conceptual understanding of thermodynamics",
    "confidence": 0.95,
    "layer": "L2"
  },
  {
    "head": "paper-001",
    "head_type": "Paper",
    "relation": "TARGETS_OUTCOME",
    "tail": "conceptual understanding",
    "tail_type": "LearningOutcome",
    "evidence": "effect of PBL ... on conceptual understanding",
    "confidence": 0.90,
    "layer": "L2"
  }
]
```

### Example 2
Text: "We conducted a systematic review of 44 empirical studies following PRISMA
guidelines. Results show that AI applications are concentrated in mechanics and
modern physics, and are mainly applied in conversational tutoring and automated
feedback systems."
paper_id: "paper-002"

Output:
```json
[
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "USES_METHOD",
    "tail": "systematic review",
    "tail_type": "ResearchMethod",
    "evidence": "We conducted a systematic review of 44 empirical studies following PRISMA guidelines",
    "confidence": 1.0,
    "layer": "L2"
  },
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "USES_METHOD",
    "tail": "PRISMA",
    "tail_type": "ReportingGuideline",
    "evidence": "following PRISMA guidelines",
    "confidence": 0.95,
    "layer": "L2"
  },
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "DEPLOYS_TECH",
    "tail": "AI applications",
    "tail_type": "Technology",
    "evidence": "AI applications are concentrated in mechanics and modern physics",
    "confidence": 0.95,
    "layer": "L2"
  },
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "STUDIES_DOMAIN",
    "tail": "mechanics",
    "tail_type": "SubjectDomain",
    "evidence": "AI applications are concentrated in mechanics",
    "confidence": 0.90,
    "layer": "L2"
  },
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "STUDIES_DOMAIN",
    "tail": "modern physics",
    "tail_type": "SubjectDomain",
    "evidence": "AI applications are concentrated in mechanics and modern physics",
    "confidence": 0.90,
    "layer": "L2"
  },
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "ADOPTS_PEDAGOGY",
    "tail": "conversational tutoring",
    "tail_type": "PedagogicalMethod",
    "evidence": "mainly applied in conversational tutoring and automated feedback systems",
    "confidence": 0.90,
    "layer": "L2"
  },
  {
    "head": "paper-002",
    "head_type": "Paper",
    "relation": "ADOPTS_PEDAGOGY",
    "tail": "automated feedback",
    "tail_type": "PedagogicalMethod",
    "evidence": "conversational tutoring and automated feedback systems",
    "confidence": 0.90,
    "layer": "L2"
  }
]
```

### Example 3 (Bootstrapping: when a concept doesn't fit any core type)
Text: "The study utilized citizen science data collected through a mobile app to
engage students in authentic biodiversity research."

Output:
```json
[
  {
    "head": "mobile app",
    "head_type": "Technology",
    "relation": "INTEGRATES_WITH",
    "tail": "citizen science",
    "tail_type": "Concept",
    "evidence": "citizen science data collected through a mobile app",
    "confidence": 0.85,
    "new_type_suggestion": "citizen-science"
  },
  {
    "head": "citizen science",
    "head_type": "Concept",
    "relation": "IMPROVES",
    "tail": "student engagement",
    "tail_type": "LearningOutcome",
    "evidence": "engage students in authentic biodiversity research",
    "confidence": 0.80,
    "new_type_suggestion": "citizen-science"
  }
]
```

### Example 4 (L3: Claims, effect sizes, and evidence)
Text: "The meta-analysis revealed a significant moderate effect of modelling activities
on problem-solving skills (SMD = 0.97, 95% CI [0.72, 1.22], p < 0.001). This was
supported by 20 RCTs with a total sample of N = 3047 participants."

Output:
```json
[
  {
    "head": "modelling activities significantly improve problem-solving skills",
    "head_type": "Claim",
    "relation": "HAS_EFFECT_SIZE",
    "tail": "SMD = 0.97",
    "tail_type": "EffectSize",
    "evidence": "significant moderate effect ... SMD = 0.97, 95% CI [0.72, 1.22], p < 0.001",
    "confidence": 1.0,
    "layer": "L3"
  },
  {
    "head": "modelling activities significantly improve problem-solving skills",
    "head_type": "Claim",
    "relation": "SUPPORTED_BY",
    "tail": "meta-analytic estimate from 20 RCTs",
    "tail_type": "Evidence",
    "evidence": "supported by 20 RCTs with a total sample of N = 3047",
    "confidence": 1.0,
    "layer": "L3"
  },
  {
    "head": "N = 3047 participants from 20 RCTs",
    "head_type": "SampleInfo",
    "relation": "HAS_SAMPLE",
    "tail": "N = 3047 participants from 20 RCTs",
    "tail_type": "SampleInfo",
    "evidence": "total sample of N = 3047 participants",
    "confidence": 1.0,
    "layer": "L3"
  }
]
```

### Example 5 (L3: Comparison condition)
Text: "The experimental group using VR-based instruction significantly outperformed
the control group receiving traditional lecture-based instruction on conceptual
understanding of density (d = 0.82, p < 0.01)."

Output:
```json
[
  {
    "head": "VR-based instruction significantly improves conceptual understanding of density",
    "head_type": "Claim",
    "relation": "HAS_EFFECT_SIZE",
    "tail": "d = 0.82",
    "tail_type": "EffectSize",
    "evidence": "d = 0.82, p < 0.01",
    "confidence": 1.0,
    "layer": "L3"
  },
  {
    "head": "VR-based instruction",
    "head_type": "Technology",
    "relation": "COMPARES_WITH",
    "tail": "traditional lecture-based instruction",
    "tail_type": "ComparisonCondition",
    "evidence": "experimental group using VR ... outperformed control group receiving traditional lecture",
    "confidence": 0.95,
    "layer": "L3"
  },
  {
    "head": "VR-based instruction",
    "head_type": "Technology",
    "relation": "IMPROVES",
    "tail": "conceptual understanding",
    "tail_type": "LearningOutcome",
    "evidence": "VR-based instruction significantly outperformed ... on conceptual understanding of density",
    "confidence": 0.95,
    "layer": "L2"
  }
]
```"""


# ============================================================================
# 主 Prompt 模板
# ============================================================================


SYSTEM_PROMPT = f"""You are a STEM education research knowledge graph extractor. Extract
structured triples from academic paper excerpts at TWO layers:

- **L2 (Research Elements)**: methods, theories, technologies, pedagogies, domains,
  outcomes, populations, assessments — the "what was studied"
- **L3 (Research Findings)**: claims, evidence, effect sizes, sample info, comparison
  conditions — the "what was found"

{_build_entity_type_section()}

{_build_relation_type_section()}

## Rules
1. Extract only meaningful, evidence-backed <head, relation, tail> triples from the text at BOTH layers.
2. Use ONLY the entity types and relation types listed above.
3. If a concept does NOT fit any core type, use **Concept** or **RELATED_TO**, AND
   provide a `new_type_suggestion` in kebab-case.
4. Mark each triple with `layer`: "L2" or "L3".
5. Normalize entity names: full canonical term, lowercase common nouns, consistent naming.
6. Include the original text excerpt in `evidence` for EVERY triple.
7. Assign confidence: 1.0=explicit, 0.8-0.9=strongly implied, 0.5-0.7=inferred.
8. **Paper-entity relations**: set head to the supplied paper_id with head_type="Paper" and set tail
   to the actual method/theory/technology/population/claim/sample entity.
   - USES_METHOD: research methods (quasi-experiment, systematic review, mixed-methods…) and reporting guidelines (PRISMA, STROBE…)
   - ADOPTS_PEDAGOGY: pedagogical methods (project-based learning, inquiry-based learning, flipped classroom…)
   - APPLIES_THEORY, DEPLOYS_TECH, STUDIES_DOMAIN, TARGETS_OUTCOME, INVOLVES_POPULATION, EMPLOYS_ASSESSMENT, CLAIMS, HAS_SAMPLE, HAS_EFFECT_SIZE: as labeled.
   Never represent a paper attribute as a self-loop.
9. **Cross-entity relations** (INTEGRATES_WITH, IMPROVES, SUPPORTED_BY,
   COMPARES_WITH): head and tail are DIFFERENT entities. Reserved for
   fine-grained chunk-level extraction, NOT sparse L2 profile mode.
10. Never output head == tail. Do not use a complete sentence, statistical paragraph,
    or claim as an entity name; use a short canonical entity and put the full claim in evidence.
11. CLAIMS tail must be a short noun-phrase assertion (<= 24 words), NOT a full sentence. Example: "AI scaffolding improves conceptual understanding" not "The study found that AI scaffolding significantly improved understanding".
12. Effect sizes (d=0.82, Hedges g=0.65) must be extracted as EffectSize entities and linked via HAS_EFFECT_SIZE from the paper.
13. PRISMA/STROBE/CONSORT go to ReportingGuideline type, not ResearchMethod.
14. Use RELATED_TO only when no specific relation is justified, and provide new_type_suggestion.
15. Output ONLY a valid JSON array — no markdown, no explanation. If no triples, output [].

## Few-Shot Examples

Example 1 (L2):
Text: "This study employed a quasi-experimental design with project-based learning
integrated with ChatGPT for undergraduate thermodynamics students."
Output (paper_id="paper-001"):
[{{"head":"paper-001","head_type":"Paper","relation":"USES_METHOD","tail":"quasi-experimental design","tail_type":"ResearchMethod","evidence":"employed a quasi-experimental design","confidence":1.0,"layer":"L2"}},{{"head":"paper-001","head_type":"Paper","relation":"ADOPTS_PEDAGOGY","tail":"project-based learning","tail_type":"PedagogicalMethod","evidence":"project-based learning integrated with ChatGPT","confidence":0.95,"layer":"L2"}},{{"head":"paper-001","head_type":"Paper","relation":"DEPLOYS_TECH","tail":"ChatGPT","tail_type":"Technology","evidence":"integrated with ChatGPT","confidence":0.95,"layer":"L2"}},{{"head":"ChatGPT","head_type":"Technology","relation":"INTEGRATES_WITH","tail":"project-based learning","tail_type":"PedagogicalMethod","evidence":"project-based learning integrated with ChatGPT","confidence":0.95,"layer":"L2"}},{{"head":"project-based learning","head_type":"PedagogicalMethod","relation":"IMPROVES","tail":"conceptual understanding","tail_type":"LearningOutcome","evidence":"PBL for undergraduate thermodynamics","confidence":0.85,"layer":"L2"}},{{"head":"paper-001","head_type":"Paper","relation":"INVOLVES_POPULATION","tail":"undergraduate students","tail_type":"StudentPopulation","evidence":"undergraduate thermodynamics students","confidence":0.95,"layer":"L2"}},{{"head":"paper-001","head_type":"Paper","relation":"STUDIES_DOMAIN","tail":"thermodynamics","tail_type":"SubjectDomain","evidence":"undergraduate thermodynamics","confidence":0.95,"layer":"L2"}}]

Example 2 (L3):
Text: "VR-based instruction significantly outperformed traditional lecture on
conceptual understanding of density (d=0.82, p<0.01, N=172)."
Output (paper_id="paper-001"):
[{{"head":"paper-001","head_type":"Paper","relation":"CLAIMS","tail":"VR-based instruction improves conceptual understanding of density","tail_type":"Claim","evidence":"VR-based instruction significantly outperformed traditional lecture on conceptual understanding of density","confidence":1.0,"layer":"L3"}},{{"head":"paper-001","head_type":"Paper","relation":"HAS_SAMPLE","tail":"N=172","tail_type":"SampleInfo","evidence":"N=172","confidence":1.0,"layer":"L3"}},{{"head":"VR-based instruction","head_type":"Technology","relation":"HAS_EFFECT_SIZE","tail":"d=0.82","tail_type":"EffectSize","evidence":"d=0.82, p<0.01","confidence":1.0,"layer":"L3"}},{{"head":"VR-based instruction","head_type":"Technology","relation":"COMPARES_WITH","tail":"traditional lecture-based instruction","tail_type":"ComparisonCondition","evidence":"VR outperformed traditional lecture","confidence":0.95,"layer":"L3"}},{{"head":"VR-based instruction","head_type":"Technology","relation":"IMPROVES","tail":"conceptual understanding","tail_type":"LearningOutcome","evidence":"VR outperformed on conceptual understanding of density","confidence":0.95,"layer":"L2"}}]
"""


def build_user_prompt(
    text: str,
    paper_title: str = "",
    chunk_index: int = 0,
    paper_id: str = "",
) -> str:
    """构建单次抽取的 user prompt (定义+few-shot 已在 system prompt 中)."""
    header_parts = []
    if paper_id:
        header_parts.append(f"paper_id: {paper_id}")
    if paper_title:
        header_parts.append(f"Paper: {paper_title}")
    header = "\n".join(header_parts) + "\n" if header_parts else ""
    return f"""{header}Chunk {chunk_index} — extract triples:

{text}

Return JSON array of triples with: head, head_type, relation, tail, tail_type, evidence, confidence, layer ("L2"|"L3"), and optionally new_type_suggestion if using Concept or RELATED_TO. Never return head == tail."""


# ============================================================================
# 批量抽取 Prompt（多 chunk 合并为一次 API 请求）
# ============================================================================


def build_batch_user_prompt(
    chunks: list[dict],
    paper_title: str = "",
    paper_id: str = "",
) -> str:
    """构建批量抽取的 user prompt.

    Args:
        chunks: [{"chunk_id": "chunk_0001", "chunk_index": 0, "text": "..."}, ...]
        paper_title: 论文标题
    """
    parts: list[str] = []
    if paper_id:
        parts.append(f"paper_id: {paper_id}")
    if paper_title:
        parts.append(f"Paper: {paper_title}\n")

    parts.append(f"You are given {len(chunks)} text chunks from the same paper.")
    parts.append("Extract triples from EACH chunk separately.\n")

    for c in chunks:
        parts.append(f"[{c['chunk_id']}]")
        parts.append(c["text"])
        parts.append("")

    parts.append("## Output Format")
    parts.append(
        'Return a JSON object: {"results": ['
        '{"chunk_id": "chunk_0001", "triples": [...]}, '
        '{"chunk_id": "chunk_0002", "triples": [...]}]}'
    )
    parts.append("Each triple must have: head, head_type, relation, tail, tail_type, "
                 "evidence, confidence, layer (\"L2\"|\"L3\"), "
                 "and optionally new_type_suggestion.")
    parts.append(
        "For paper-level relations, use the supplied paper_id as head with head_type=Paper. "
        "Never output head == tail, sentence-shaped entities, or unsupported RELATED_TO relations."
    )
    parts.append("Output ONLY the JSON object — no markdown, no explanation.")

    return "\n".join(parts)


PROFILE_SYSTEM_PROMPT = """You build a sparse cross-paper STEM research graph.

The input is a paper title, abstract, and optional keywords. Extract only the small
set of relations that are useful for cross-paper retrieval and comparison. Do not
extract every sentence, citation, or repeated claim.

Rules:
1. ALL triples must have head=paper_id, head_type="Paper". This is L2 sparse mode.
   Entity-to-entity relations (ChatGPT->PBL) go to fine-grained chunk extraction.
2. Extract 8-20 triples per paper (never fewer than 8). Cover: method/pedagogy/guideline,
   domain, technology, population, outcome, key claims, sample info, effect sizes.
3. Keep at most 5 key claims. CLAIMS tail must be short noun-phrase (<=24 words),
   not a full sentence. Merge paraphrases of the same finding.
4. Use these relations:
   - USES_METHOD: research methods (quasi-experiment, systematic review, mixed-methods…)
     and reporting guidelines (PRISMA, STROBE…)
   - ADOPTS_PEDAGOGY: pedagogical methods (project-based learning, inquiry-based
     learning, flipped classroom, game-based learning, scaffolding…)
   - DEPLOYS_TECH, STUDIES_DOMAIN, INVOLVES_POPULATION, TARGETS_OUTCOME,
     CLAIMS, HAS_SAMPLE, HAS_EFFECT_SIZE: as labeled.
5. PRISMA/STROBE/CONSORT go to ReportingGuideline type, not ResearchMethod.
6. Effect sizes (d=0.82, Hedges' g=0.65) must be EffectSize entities with
   HAS_EFFECT_SIZE relation. Do not only write them in evidence text.
7. Use RELATED_TO only as a last resort, at most twice, with new_type_suggestion.
8. Never output head == tail, complete sentences as entities, citation entries,
   or statistical values as entity names.
9. Every triple must have evidence: one continuous excerpt from the abstract when
   possible. When evidence is non-continuous, use [...] to separate sections.
10. Output only JSON: {"triples": [...]}.
"""


def build_profile_user_prompt(
    *,
    paper_id: str,
    title: str,
    abstract: str,
    keywords: str = "",
) -> str:
    """构建稀疏论文画像 Prompt，只使用标题、摘要和关键词。"""
    keywords_block = keywords.strip() or "(none provided)"
    return f"""paper_id: {paper_id}
title: {title.strip() or '(untitled)'}
keywords: {keywords_block}

abstract:
{abstract.strip()}

Return a JSON object with a `triples` array. Use paper_id as the head for paper-level
relations and keep the output sparse. Do not include full-text details that are not
needed to identify the paper's topic, method, population, outcomes, or key findings.
"""


# ============================================================================
# 合并去重的 Prompt（跨 chunk 去冗余）
# ============================================================================

MERGE_SYSTEM_PROMPT = """You are a knowledge graph quality control agent. Your task is to
merge and deduplicate triples extracted from different chunks of the same paper.

## Rules
1. If two triples represent the SAME fact (same head, relation, tail), keep only ONE
   and combine their evidence excerpts.
2. If two triples use different names for the SAME entity, normalize to the most
   standard/academic term.
3. Remove triples that are clearly spurious or unsupported.
4. Maintain the `new_type_suggestion` field if present.
5. Output ONLY a valid JSON array.
"""


def build_merge_prompt(triples_json: str) -> str:
    """构建合并去重的 user prompt."""
    return f"""## Triples to Merge (from multiple chunks of the same paper)

{triples_json}

## Task
Merge these triples by:
1. Removing exact duplicates (same head, relation, tail)
2. Normalizing entity names (e.g. "PBL" → "project-based learning")
3. Combining evidence excerpts for merged triples
4. Removing any clearly invalid triples

Output ONLY the merged JSON array of triples.
"""
