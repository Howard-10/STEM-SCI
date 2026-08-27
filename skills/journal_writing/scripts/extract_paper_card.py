#!/usr/bin/env python3
"""Extract a structured paper card from a text-based exemplar PDF."""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    import pymupdf
except ImportError as error:  # pragma: no cover - environment-dependent message
    raise SystemExit("PyMuPDF is required: python -m pip install PyMuPDF") from error

from _pattern_utils import SKILL_ROOT, cards_dir, dump_yaml, paper_files
from pydantic import BaseModel, ConfigDict

HEADING_RE = re.compile(r"^(?:(?:(\d+(?:\.\d+)*)|([IVXLCDM]+))\.?\s+)?(.+?)\s*$", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)

CANONICAL_HEADINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("introduction", ("introduction",)),
    ("literature_review", ("literature review", "background", "related works")),
    ("theoretical_framework", ("theoretical framework", "conceptual framework")),
    ("problem_statement", ("problem statement",)),
    ("research_questions", ("research question", "research questions and significance")),
    (
        "methods",
        (
            "method",
            "methods",
            "methodology",
            "materials and methods",
            "research methods",
            "data collection and methods",
        ),
    ),
    ("results_discussion", ("findings and discussion", "results and discussion")),
    ("results", ("result", "results", "finding", "findings")),
    ("discussion", ("discussion",)),
    ("implications", ("implication", "implications")),
    ("conclusion", ("conclusion", "conclusions")),
    (
        "limitations",
        ("limitation", "limitations", "limitations and future studies", "limitations and future work", "limitations and implications"),
    ),
    ("future_work", ("future research", "recommendations for future studies")),
    ("references", ("references",)),
)


class SemanticIntroduction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opening_strategy: str | None = None
    problem_context: str | None = None
    literature_review_strategy: str | None = None
    research_gap_explicit: bool | None = None
    research_gap_position: str | None = None
    research_gap_description: str | None = None
    theoretical_framework_present: bool | None = None
    theoretical_framework_position: str | None = None
    contribution_statement_present: bool | None = None
    contribution_statement_position: str | None = None


class SemanticDiscussion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opening_strategy: str | None = None
    answers_research_questions: bool | None = None
    comparison_with_prior_research: str | None = None
    theoretical_interpretation: str | None = None
    practical_implications: str | None = None
    educational_implications: str | None = None
    limitations: str | None = None
    future_work: str | None = None
    conclusion_strategy: str | None = None


class SemanticWritingFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theory_emphasis: str | None = None
    evidence_emphasis: str | None = None
    practical_implication_emphasis: str | None = None
    educational_implication_emphasis: str | None = None


class SemanticAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    introduction: SemanticIntroduction
    discussion: SemanticDiscussion
    writing_features: SemanticWritingFeatures
    results_interpretation_level: str | None = None


def _normalize_heading(text: str) -> tuple[str | None, str, int | None]:
    compact = " ".join(text.split()).strip(" :\t")
    match = HEADING_RE.match(compact)
    if not match:
        return None, compact, None
    number, roman_number, label = match.groups()
    label_normalized = label.casefold().strip(" .:")
    level = len(number.split(".")) if number else (1 if roman_number else None)
    for canonical, aliases in CANONICAL_HEADINGS:
        if any(label_normalized == alias or label_normalized.startswith(alias + " ") for alias in aliases):
            return canonical, compact, level
    return None, compact, level


def _block_text(block: dict[str, Any]) -> tuple[str, float]:
    lines = block.get("lines")
    if not isinstance(lines, list):
        return "", 0.0
    texts: list[str] = []
    sizes: list[float] = []
    for line in lines:
        spans = line.get("spans", [])
        line_text = "".join(str(span.get("text", "")) for span in spans).strip()
        if line_text:
            texts.append(line_text)
        sizes.extend(float(span.get("size", 0.0)) for span in spans if str(span.get("text", "")).strip())
    return " ".join(texts).strip(), max(sizes, default=0.0)


def _extract_abstract(document: Any, front_text: str) -> str | None:
    structured_labels = re.compile(
        r"^(?:Abstract\s*[:—-]\s*)?(?:Contributions?|Background|Research Questions?|Methodology|Findings)\s*:",
        re.IGNORECASE,
    )
    for page in document[:2]:
        parts: list[str] = []
        found_abstract = False
        for block in page.get_text("dict", sort=True).get("blocks", []):
            text, _max_size = _block_text(block)
            if re.match(r"^Abstract\s*[:—-]", text, re.IGNORECASE):
                found_abstract = True
                parts.append(re.sub(r"^Abstract\s*[:—-]\s*", "", text, flags=re.IGNORECASE))
            elif found_abstract and structured_labels.match(text):
                parts.append(text)
        if found_abstract:
            return " ".join(" ".join(parts).split())

    abstract_match = re.search(
        r"\bAbstract\s*[:—-]\s*(.+?)(?:\n\s*(?:Index Terms|Keywords?)\s*[:—-]|\n\s*(?:1\.?|I\.)\s+Introduction\b)",
        front_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return " ".join(abstract_match.group(1).split()) if abstract_match else None


def extract_pdf(path: Path) -> dict[str, Any]:
    document = pymupdf.open(path)
    if document.needs_pass:
        raise ValueError(f"encrypted PDF requires a password: {path}")
    page_texts = [page.get_text("text", sort=True) for page in document]
    full_text = "\n".join(page_texts)
    if len(full_text.strip()) < 500:
        raise ValueError(f"PDF has no usable text layer; OCR was not attempted: {path}")

    sections: dict[str, list[str]] = {}
    section_order: list[str] = []
    current: str | None = None
    for page_index, page in enumerate(document):
        for block in page.get_text("dict", sort=True).get("blocks", []):
            text, max_size = _block_text(block)
            if not text:
                continue
            canonical, _raw_heading, level = _normalize_heading(text)
            numbered_main_heading = level == 1 and max_size >= 9.0
            unnumbered_main_heading = level is None and max_size >= 11.0
            is_main_heading = canonical is not None and (numbered_main_heading or unnumbered_main_heading)
            if is_main_heading:
                if canonical == "references":
                    current = None
                    continue
                current = canonical
                if canonical not in section_order:
                    section_order.append(canonical)
                sections.setdefault(canonical, [])
                continue
            if current:
                sections.setdefault(current, []).append(text)

    front = "\n".join(page_texts[:2])
    abstract = _extract_abstract(document, front)
    if abstract and "abstract" not in section_order:
        section_order.insert(0, "abstract")
    return {
        "metadata": document.metadata or {},
        "full_text": full_text,
        "front_text": front,
        "abstract": abstract,
        "sections": {name: "\n".join(parts).strip() for name, parts in sections.items()},
        "section_order": section_order,
    }


def _first_match(patterns: Iterable[tuple[str, str]], text: str) -> str | None:
    for label, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return label
    return None


def classify_methodology(text: str) -> str | None:
    compact = " ".join(text.split())
    if re.search(r"\b(?:instrument|scale|questionnaire) development\b|\bvalidation study\b", compact, re.IGNORECASE):
        return "instrument_development"
    if re.search(r"\b(?:randomi[sz]ed controlled|quasi[- ]experimental|experimental design)\b", compact, re.IGNORECASE):
        return "experiment"
    if re.search(r"\bmixed[- ]methods?\b|\bmixed methodology\b|\bsequential explanatory\b", compact, re.IGNORECASE):
        return "mixed_methods"
    if re.search(
        r"\bqualitative (?:study|research|approach|design)\b|\bthematic analysis\b|"
        r"\bholistic single case\b|\bmultiple case study\b|\bcase study approach\b|"
        r"\binterviews?\b.{0,240}\b(?:coding|data condensation)\b",
        compact,
        re.IGNORECASE,
    ):
        return "qualitative"
    if re.search(r"\bquantitative (?:study|research|approach|design|analysis)\b|\bpath analysis\b|\bstructural equation model", compact, re.IGNORECASE):
        return "quantitative"
    return None


def _decode_metadata_text(value: Any) -> str | None:
    decoded = str(value or "").strip()
    if not decoded:
        return None
    for _ in range(4):
        unescaped = html.unescape(decoded)
        if unescaped == decoded:
            break
        decoded = unescaped
    return " ".join(decoded.split()) or None


def _infer_title(path: Path, metadata: dict[str, Any]) -> str | None:
    metadata_title = _decode_metadata_text(metadata.get("title"))
    if metadata_title:
        return metadata_title

    document = pymupdf.open(path)
    candidates: list[tuple[float, int, str]] = []
    for page_index, page in enumerate(document[:2]):
        for block in page.get_text("dict", sort=True).get("blocks", []):
            text, max_size = _block_text(block)
            canonical, _heading, _level = _normalize_heading(text)
            if (
                max_size >= 16.0
                and text
                and canonical is None
                and not text.upper().startswith("IEEE TRANSACTIONS")
            ):
                candidates.append((max_size, page_index, text))
    if not candidates:
        return None
    largest_size = max(item[0] for item in candidates)
    title_page = min(item[1] for item in candidates if item[0] == largest_size)
    parts = [text for size, page_index, text in candidates if page_index == title_page and size >= largest_size - 0.5]
    return _decode_metadata_text(" ".join(parts))


def _method_details(text: str, methodology: str | None) -> dict[str, Any]:
    lowered = text.casefold()
    design = _first_match(
        (
            ("mixed_methods_sequential_explanatory", r"sequential explanatory"),
            ("mixed_methods", r"mixed[- ]method|mixed methodology"),
            ("holistic_single_case", r"holistic single case"),
            ("case_study", r"case study"),
            ("cross_sectional_survey", r"cross[- ]sectional"),
            ("qualitative", r"qualitative (?:study|research|approach|design)"),
            ("quantitative", r"quantitative (?:study|research|approach|design)"),
        ),
        text,
    ) or methodology
    participant_source = None
    if re.search(r"\bparticipants?\b|\bstudents?\b|\bteachers?\b|\beducators?\b", lowered):
        participant_source = "human_participants"
    explicit_artifact_source = re.search(
        r"(?:data source|data consisted of|data were drawn from).{0,180}(?:lesson plans?|documents?|artifacts?|field notes?|observations?)",
        lowered,
        re.DOTALL,
    )
    if explicit_artifact_source:
        participant_source = (
            "human_participants_and_artifact_data" if participant_source else "artifact_or_observation_data"
        )
    sampling = _first_match(
        (
            ("purposive_sampling", r"purpos(?:ive|eful) sampl"),
            ("convenience_sampling", r"convenience sampl"),
            ("random_sampling", r"random sampl"),
            ("census_sampling", r"census sampl|whole population"),
        ),
        text,
    )
    instruments = [
        label
        for label, pattern in (
            ("questionnaire", r"\bquestionnaire\b|\bsurvey instrument\b"),
            ("interview", r"\binterviews?\b"),
            ("observation", r"\bobservations?\b|observation form"),
            ("field_notes", r"field notes?"),
            ("document_or_artifact", r"lesson plans?|documents?|artifacts?"),
            ("administrative_or_enrollment_data", r"enrollment data|administrative data"),
        )
        if re.search(pattern, lowered)
    ]
    validity = [
        label
        for label, pattern in (
            ("validity", r"\bvalidity\b"),
            ("reliability", r"\breliability\b|cronbach"),
            ("trustworthiness", r"trustworthiness|member check|triangulat"),
            ("inter_rater_agreement", r"inter[- ]rater|coder agreement"),
        )
        if re.search(pattern, lowered)
    ]
    analyses = [
        label
        for label, pattern in (
            ("thematic_analysis", r"thematic analysis"),
            ("content_analysis", r"content analysis"),
            ("emergent_coding", r"emergent coding"),
            ("rasch_analysis", r"rasch"),
            ("descriptive_statistics", r"descriptive statistics|mean and standard deviation|frequenc(?:y|ies)"),
            ("inferential_statistics", r"inferential statistics|statistically significant|anova|t[- ]test"),
            ("path_analysis", r"path analysis"),
            ("structural_equation_modeling", r"structural equation model"),
        )
        if re.search(pattern, lowered)
    ]
    procedure = None
    if re.search(r"intervention|professional development program|training program", lowered):
        procedure = "intervention_or_training_procedure"
    elif re.search(r"administered the (?:survey|questionnaire)|data (?:were|was) collected", lowered):
        procedure = "data_collection_procedure"
    details_present = sum(bool(value) for value in (design, participant_source, sampling, instruments, validity, analyses))
    return {
        "research_design": design,
        "participants_or_data": participant_source,
        "sampling": sampling,
        "instruments": instruments or None,
        "procedure": procedure,
        "validity_reliability_or_trustworthiness": validity or None,
        "analysis_method": analyses or None,
        "reproducibility_detail": "substantial" if details_present >= 5 else "partial" if details_present >= 3 else None,
    }


def _reference_presence(text: str, label: str) -> str | None:
    return "present" if re.search(rf"\b{label}\s*\d+", text, flags=re.IGNORECASE) else None


def _result_details(text: str, combined_results_discussion: bool) -> dict[str, Any]:
    evidence_types = [
        label
        for label, pattern in (
            ("descriptive_statistics", r"\bmean\b|standard deviation|\bfrequency\b|\bpercentage\b"),
            ("inferential_statistics", r"statistically significant|\bp\s*[<=>]|anova|t[- ]test"),
            ("themes", r"\bthemes?\b|thematic analysis"),
            ("participant_accounts", r"participants? (?:said|reported|stated)|interview"),
        )
        if re.search(pattern, text, re.IGNORECASE)
    ]
    organization = "integrated_findings_and_discussion" if combined_results_discussion else None
    if not organization and re.search(r"\b(?:theme|construct)\s+[A-Z0-9]", text, re.IGNORECASE):
        organization = "organized_by_theme_or_construct"
    return {
        "organization": organization,
        "organized_by_research_questions": True if re.search(r"\bhow\b.+\?", text, re.IGNORECASE) else None,
        "evidence_types": evidence_types,
        "tables_usage": _reference_presence(text, "table"),
        "figures_usage": _reference_presence(text, "figure"),
        "interpretation_level": "integrated_with_results" if combined_results_discussion else None,
    }


def _position(section_order: list[str], section: str) -> str | None:
    if section not in section_order:
        return None
    index = section_order.index(section)
    if index <= 1:
        return "early_article"
    methods_index = section_order.index("methods") if "methods" in section_order else len(section_order)
    return "before_methods" if index < methods_index else "after_methods"


def _semantic_analysis(extracted: dict[str, Any], mode: str) -> tuple[SemanticAnalysis | None, bool]:
    configured = all(os.getenv(name, "").strip() for name in (
        "STEM_SCI_LLM_BASE_URL", "STEM_SCI_LLM_API_KEY", "STEM_SCI_LLM_MODEL"
    ))
    if mode == "off" or (mode == "auto" and not configured):
        return None, False
    if not configured:
        raise RuntimeError("LLM mode is required but STEM_SCI_LLM_BASE_URL/API_KEY/MODEL are incomplete")

    backend_src = SKILL_ROOT.parents[1] / "backend" / "src"
    sys.path.insert(0, str(backend_src))
    from stem_sci.agents.runtime.provider import (
        GPTProvider,  # pylint: disable=import-outside-toplevel
    )

    sections = extracted["sections"]
    evidence_text = "\n\n".join(
        f"[{name}]\n{text[:16000]}"
        for name, text in sections.items()
        if name in {
            "introduction", "literature_review", "theoretical_framework", "problem_statement",
            "research_questions", "results", "results_discussion", "discussion", "implications",
            "conclusion", "limitations", "future_work",
        }
    )
    provider = GPTProvider.from_env()
    result = provider.generate_structured(
        system_prompt=(
            "Analyze research-article rhetoric from supplied evidence only. Return concise functional labels, "
            "not quotations. A keyword alone is not evidence of a research gap, contribution, literature "
            "synthesis, or interpretation. Use null whenever evidence is insufficient."
        ),
        user_prompt=(
            "Create the semantic portion of a paper card. Distinguish explicit author claims from your own "
            "inference, and do not invent absent content.\n\n" + evidence_text[:60000]
        ),
        response_model=SemanticAnalysis,
        model=os.environ["STEM_SCI_LLM_MODEL"],
        prompt_version="journal-paper-card-v1",
    )
    return result.parsed_output, True


def build_card(path: Path, journal: str, llm_mode: str) -> tuple[dict[str, Any], bool]:
    extracted = extract_pdf(path)
    metadata = extracted["metadata"]
    front_text = extracted["front_text"]
    abstract = extracted["abstract"] or str(metadata.get("subject") or "")
    sections = extracted["sections"]
    method_text = "\n".join((abstract, sections.get("methods", "")))
    methodology = classify_methodology(method_text)
    doi_match = DOI_RE.search(front_text)
    published_match = re.search(r"Published:\s*\d{1,2}\s+\w+\s+(\d{4})", front_text, re.IGNORECASE)
    doi_value = doi_match.group(0).rstrip(".,;)") if doi_match else None
    doi_year_match = re.search(r"(?:steme|TE)\.(20\d{2})", doi_value or "", re.IGNORECASE)
    ieee_year_match = re.search(r"IEEE TRANSACTIONS ON EDUCATION[^\n]*(20\d{2})", front_text, re.IGNORECASE)
    year_match = published_match or ieee_year_match or doi_year_match
    year = int(year_match.group(1)) if year_match else None
    article_type_match = re.search(r"\n\s*(Research article|Review article|Editorial)\s*\n", front_text, re.IGNORECASE)
    section_order = extracted["section_order"]
    semantic, llm_called = _semantic_analysis(extracted, llm_mode)
    semantic_intro = semantic.introduction if semantic else None
    semantic_discussion = semantic.discussion if semantic else None
    semantic_writing = semantic.writing_features if semantic else None

    theory_heading_present = "theoretical_framework" in section_order
    rq_heading_present = "research_questions" in section_order
    structured_abstract_rq = bool(re.search(r"\bResearch Questions?\s*:", abstract, re.IGNORECASE))
    structured_abstract_contribution = bool(re.search(r"\bContributions?\s*:", abstract, re.IGNORECASE))
    method_question_count = len(re.findall(r"(?:^|\n)\s*\d+\.?\s+[^\n?]{10,}\?", sections.get("methods", "")))
    explicit_method_questions = method_question_count >= 2
    results_text = "\n".join((sections.get("results", ""), sections.get("results_discussion", "")))
    result_details = _result_details(results_text, "results_discussion" in section_order)
    if semantic and semantic.results_interpretation_level is not None:
        result_details["interpretation_level"] = semantic.results_interpretation_level

    card: dict[str, Any] = {
        "paper": {
            "title": _infer_title(path, metadata),
            "journal": journal,
            "year": year,
            "doi": doi_value,
            "article_type": article_type_match.group(1).casefold().replace(" ", "_") if article_type_match else None,
            "methodology": methodology,
        },
        "structure": {"section_order": section_order},
        "introduction": {
            "opening_strategy": semantic_intro.opening_strategy if semantic_intro else None,
            "problem_context": semantic_intro.problem_context if semantic_intro else None,
            "literature_review_strategy": semantic_intro.literature_review_strategy if semantic_intro else None,
            "research_gap": {
                "explicit": semantic_intro.research_gap_explicit if semantic_intro else None,
                "position": semantic_intro.research_gap_position if semantic_intro else None,
                "description": semantic_intro.research_gap_description if semantic_intro else None,
            },
            "theoretical_framework": {
                "present": semantic_intro.theoretical_framework_present if semantic_intro else (True if theory_heading_present else None),
                "position": semantic_intro.theoretical_framework_position if semantic_intro else _position(section_order, "theoretical_framework"),
                "separate_section": True if theory_heading_present else None,
            },
            "research_questions": {
                "present": True if rq_heading_present or explicit_method_questions or structured_abstract_rq else None,
                "position": (
                    _position(section_order, "research_questions")
                    if rq_heading_present
                    else "methods_section"
                    if explicit_method_questions
                    else "structured_abstract"
                    if structured_abstract_rq
                    else None
                ),
            },
            "contribution_statement": {
                "present": (
                    semantic_intro.contribution_statement_present
                    if semantic_intro
                    else True
                    if structured_abstract_contribution
                    else None
                ),
                "position": (
                    semantic_intro.contribution_statement_position
                    if semantic_intro
                    else "structured_abstract"
                    if structured_abstract_contribution
                    else None
                ),
            },
        },
        "methods": _method_details(method_text, methodology),
        "results": result_details,
        "discussion": {
            "opening_strategy": semantic_discussion.opening_strategy if semantic_discussion else None,
            "answers_research_questions": semantic_discussion.answers_research_questions if semantic_discussion else None,
            "comparison_with_prior_research": semantic_discussion.comparison_with_prior_research if semantic_discussion else None,
            "theoretical_interpretation": semantic_discussion.theoretical_interpretation if semantic_discussion else None,
            "practical_implications": semantic_discussion.practical_implications if semantic_discussion else None,
            "educational_implications": semantic_discussion.educational_implications if semantic_discussion else None,
            "limitations": semantic_discussion.limitations if semantic_discussion else ("separate_section" if "limitations" in section_order else None),
            "future_work": semantic_discussion.future_work if semantic_discussion else ("separate_section" if "future_work" in section_order else None),
            "conclusion_strategy": semantic_discussion.conclusion_strategy if semantic_discussion else None,
        },
        "writing_features": {
            "theory_emphasis": semantic_writing.theory_emphasis if semantic_writing else None,
            "evidence_emphasis": semantic_writing.evidence_emphasis if semantic_writing else None,
            "practical_implication_emphasis": semantic_writing.practical_implication_emphasis if semantic_writing else None,
            "educational_implication_emphasis": semantic_writing.educational_implication_emphasis if semantic_writing else None,
            "typical_argument_flow": section_order,
        },
        "evidence": {"source_type": "published_article"},
    }
    return card, llm_called


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="one exemplar PDF")
    source.add_argument("--all", action="store_true", help="process every PDF for the selected journal")
    parser.add_argument("--journal", required=True, help="journal identifier")
    parser.add_argument("--output", type=Path, help="output path; valid only with --input")
    parser.add_argument("--llm", choices=("auto", "off", "required"), default="auto")
    args = parser.parse_args()
    if args.all and args.output:
        parser.error("--output cannot be combined with --all")
    return args


def main() -> int:
    args = parse_args()
    inputs = paper_files(args.journal) if args.all else [args.input.resolve()]
    if not inputs:
        raise SystemExit(f"no PDFs found for journal: {args.journal}")
    output_dir = cards_dir(args.journal, create=True)
    llm_calls = 0
    for input_path in inputs:
        if not input_path.is_file():
            raise SystemExit(f"input PDF not found: {input_path}")
        card, llm_called = build_card(input_path, args.journal, args.llm)
        output = args.output.resolve() if args.output else output_dir / f"{input_path.stem}.yaml"
        dump_yaml(card, output)
        llm_calls += int(llm_called)
        print(f"generated {output}")
    print(f"processed={len(inputs)} llm_calls={llm_calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
