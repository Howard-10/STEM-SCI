"""Bounded journal-style revision and LaTeX handoff for an existing English draft."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stem_sci.agents.writing_pipeline.models import AtomicClaimGraph, LanguageCode, ManuscriptDraft
from stem_sci.latex import LatexGenerateRequest, LatexGenerateResponse, LatexService

from .loader import JournalProfileLoader
from .models import (
    ArticleTypeRecommendation,
    DraftJournalValidation,
    SemanticAssessmentResponse,
)
from .validator import semantic_rule_keys, validate_journal_draft

print("JOURNAL_REVISION_FILE:", __file__)

if TYPE_CHECKING:
    from stem_sci.agents.runtime import StructuredGenerator


class RevisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevisionStatus(StrEnum):
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"


class RevisedSection(RevisionModel):
    name: str = Field(min_length=1)
    text: str = Field(min_length=1)


class RevisedSectionsResponse(RevisionModel):
    sections: list[RevisedSection]
    change_summary: list[str]

    @field_validator("sections", mode="before")
    @classmethod
    def accept_mapping_in_tests(cls, value: object) -> object:
        if isinstance(value, dict):
            return [{"name": name, "text": text} for name, text in value.items()]
        return value

    @field_validator("change_summary", mode="before")
    @classmethod
    def accept_single_change_summary(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value

    def section_map(self) -> dict[str, str]:
        return {section.name: section.text for section in self.sections}


class ArticleTypeRecommendationModelResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    recommended_type: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class JournalStyleRevisionRequest(RevisionModel):
    target_journal: str = Field(min_length=1)
    article_type: str | None = None
    methodology: str | None = None
    draft: ManuscriptDraft
    claim_graph: AtomicClaimGraph
    compile_pdf: bool = False


class ArticleTypeRecommendationRequest(RevisionModel):
    target_journal: str = Field(min_length=1)
    draft: ManuscriptDraft


class JournalStyleRevisionReport(RevisionModel):
    status: RevisionStatus
    target_journal: str
    article_type: str | None = None
    methodology: str | None = None
    applied_layers: list[str] = Field(default_factory=list)
    layer_warnings: list[str] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)
    safety_findings: list[str] = Field(default_factory=list)
    generation_error: str | None = None


class JournalStyleRevisionResult(RevisionModel):
    draft: ManuscriptDraft
    candidate_draft: ManuscriptDraft | None = None
    report: JournalStyleRevisionReport
    journal_validation: DraftJournalValidation | None = None
    latex: LatexGenerateResponse | None = None
    recommendation: ArticleTypeRecommendation | None = None
    generation_metadata_refs: list[str] = Field(default_factory=list)


class JournalRevisionUnavailableError(RuntimeError):
    pass


_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%?(?![\w.])")
_CITATION = re.compile(r"\[[0-9,;\- ]+\]|\([^()]{1,80},\s*20\d{2}[a-z]?\)|10\.\d{4,9}/\S+", re.IGNORECASE)
_CLAIM_ID = re.compile(r"\bclaim(?:[_:\-][a-z0-9_.:\-]+|\s+id\s*[:=]\s*[a-z0-9_.:\-]+)", re.IGNORECASE)
_CAUSAL = ("causes", "caused", "leads to", "led to", "results in", "resulted in", "proves", "demonstrates that")
_RESULT_DIRECTIONS = (
    "increased",
    "decreased",
    "higher than",
    "lower than",
    "positive association",
    "negative association",
    "positive relationship",
    "negative relationship",
    "no association",
    "no difference",
)
_RESULT_ASSERTIONS = ("we found", "our findings show", "results show", "results indicate", "significant effect")

_IEEE_SOURCE_FIDELITY_PROMPT = """
IEEE Transactions on Education source-fidelity constraint:
The source manuscript is the sole source of study-specific facts. IEEE journal patterns and article-type
patterns are writing and organizational guidance only; they are not evidence and must never be used to
invent or infer missing research content. If a detail expected by an IEEE rule or observed pattern is absent,
leave it absent and allow journal validation to report it as missing or incomplete. This applies especially
to the Application article type: do not infer a study design from the article type.

Do not invent or infer participants, sample sizes, demographics, study designs, quasi-experimental designs,
procedures, instruments, datasets, numerical values, percentages, statistical tests, p-values, effect sizes,
citations, references, research questions, hypotheses, findings, result directions, or causal conclusions.
When methodology is null, do not infer quantitative, qualitative, experimental, or quasi-experimental
methodology. You may only rephrase existing content, improve academic wording, reorganize existing content,
reduce redundancy, improve transitions, and clarify statements already supported by the source manuscript.
STYLE IS NOT EVIDENCE.
""".strip()

_IEEE_FINAL_SOURCE_POLICY = """
FINAL NON-NEGOTIABLE SOURCE POLICY

The source manuscript is the sole source of study-specific facts.

All journal rules, article-type patterns, methodology patterns, and general writing patterns above are subordinate to this policy.

They are guidance for organizing and rewriting information that already exists in the source manuscript. They are NOT instructions to fill missing research content.

If any pattern above asks for information that is absent from the source manuscript, SKIP that requirement in the revised manuscript.

Do NOT create or infer:

- research questions
- hypotheses
- participants
- sample sizes
- demographics
- study designs
- procedures
- instruments
- datasets
- numerical values
- percentages
- statistical tests
- p-values
- effect sizes
- citations
- references
- findings
- result directions
- causal conclusions

Never invent content merely to make the manuscript appear compliant with IEEE Transactions on Education.

Missing information must remain missing and may later be reported by journal validation.

You may only:

- rephrase existing content
- reorganize existing content
- improve academic wording
- improve clarity
- reduce redundancy
- improve transitions

Before returning the answer, verify that every study-specific fact in the revised manuscript is supported by the source manuscript.

If a requested journal pattern conflicts with this policy, THIS POLICY WINS.
""".strip()

_IEEE_OUTPUT_FORMAT_PROMPT = """

OUTPUT FORMAT REQUIREMENTS:

Return JSON only.
Do not return Markdown.
Do not return explanations before or after the JSON.

The response MUST contain exactly these top-level fields:

{
  "sections": [
    {
      "name": "original section name",
      "text": "revised section text"
    }
  ],
  "change_summary": [
    "brief description of a valid revision"
  ]
}

Rules:
- "sections" must be a non-empty array.
- Every section must contain a non-empty "name" and non-empty "text".
- Sections may be renamed, added, removed, merged, or split when this improves journal fit; preserve the manuscript facts.
- Return the complete revised section set, including any intentional section changes.
- "change_summary" must always be present and must be an array of strings.
- Do not add any other top-level fields.
- Do not put validation findings, warnings, missing-information notes, or explanations inside the JSON
  unless the existing schema explicitly supports them.
- Missing research information must simply remain missing in the revised text; do not invent it and do
  not create new output fields for it.
""".strip()


_IEEE_TOP_LEVEL_SECTION_PRESERVATION_PROMPT = """
TOP-LEVEL SECTION PRESERVATION

Preserve every top-level manuscript section from the source manuscript.

Do not:
- delete a top-level section;
- add a new top-level section;
- merge two top-level sections;
- move the contents of one top-level section into another and remove the original section;
- rename a top-level section, except existing accepted normalization such as Methods/Methodology if the backend already handles it.

For IEEE structured abstracts:
Contribution, Background, Intended Outcomes, Application Design, and Findings are labels INSIDE the Abstract only.

They must not replace, absorb, rename, or remove the manuscript's top-level:
Methods, Results, Discussion, or other sections.

If the source contains a Methods section, the revised response MUST still contain that Methods section.

Return exactly one revised section for every original top-level section.
""".strip()


def _joined_sections(sections: dict[str, str]) -> str:
    return "\n".join(sections.values())


def _section_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


_SECTION_MATCH_ALIASES = {
    "method": "methods",
    "methods": "methods",
    "methodology": "methods",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
}


def _section_match_key(name: str) -> str:
    key = _section_key(name)
    return _SECTION_MATCH_ALIASES.get(key, key)


def _find_matching_section(
    llm_sections: list[RevisedSection],
    target: str,
    used: set[int],
) -> int | None:
    for index, section in enumerate(llm_sections):
        if index in used:
            continue
        if _section_match_key(section.name) == target:
            return index
    return None


def _map_revised_sections(
    draft: ManuscriptDraft,
    llm_sections: list[RevisedSection],
) -> dict[str, str]:
    """Rebuild revised sections using the source manuscript's top-level structure.

    Top-level section names and order are backend-owned metadata; the model only
    supplies candidate revised text. For each original section, match a model section
    by normalized name (with simple aliases for matching only); use its text when
    found, otherwise keep the original text. Model sections that do not correspond to
    any original top-level section are ignored, so the final section set is always
    exactly the source draft's.
    """
    result: dict[str, str] = {}
    used: set[int] = set()
    for original_name, original_text in draft.sections.items():
        index = _find_matching_section(
            llm_sections,
            _section_match_key(original_name),
            used,
        )
        if index is not None:
            used.add(index)
            result[original_name] = llm_sections[index].text
        else:
            result[original_name] = original_text
    return result


def revision_safety_findings(
    original: ManuscriptDraft,
    revised_sections: dict[str, str],
) -> list[str]:
    findings: list[str] = []
    original_text = _joined_sections(original.sections)
    revised_text = _joined_sections(revised_sections)
    added_numbers = sorted(set(_NUMBER.findall(revised_text)) - set(_NUMBER.findall(original_text)))
    if added_numbers:
        findings.append("NEW_NUMERIC_LITERAL:" + ",".join(added_numbers))
    added_citations = sorted(set(_CITATION.findall(revised_text)) - set(_CITATION.findall(original_text)))
    if added_citations:
        findings.append("NEW_CITATION:" + ",".join(added_citations))
    original_lower = original_text.casefold()
    revised_lower = revised_text.casefold()
    added_causal = [phrase for phrase in _CAUSAL if phrase in revised_lower and phrase not in original_lower]
    if added_causal:
        findings.append("STRONGER_CAUSAL_LANGUAGE:" + ",".join(added_causal))
    added_directions = [phrase for phrase in _RESULT_DIRECTIONS if phrase in revised_lower and phrase not in original_lower]
    if added_directions:
        findings.append("NEW_RESULT_DIRECTION:" + ",".join(added_directions))
    added_result_assertions = [
        phrase for phrase in _RESULT_ASSERTIONS if phrase in revised_lower and phrase not in original_lower
    ]
    if added_result_assertions:
        findings.append("NEW_RESULT_ASSERTION:" + ",".join(added_result_assertions))
    added_claim_ids = sorted(set(_CLAIM_ID.findall(revised_text)) - set(_CLAIM_ID.findall(original_text)))
    if added_claim_ids:
        findings.append("NEW_CLAIM_ID:" + ",".join(added_claim_ids))
    if not revised_sections or any(not body.strip() for body in revised_sections.values()):
        findings.append("EMPTY_REVISED_SECTION")
    return findings


_BLOCKING_FINDINGS = {
    "MODEL_OUTPUT_INVALID",
    "EMPTY_REVISED_SECTION",
}


def _finding_code(finding: str) -> str:
    return finding.split(":", 1)[0]


def _markdown_content(draft: ManuscriptDraft) -> tuple[str, str, str, list[str]]:
    title = "Revised manuscript"
    abstract = ""
    keywords: list[str] = []
    blocks: list[str] = []
    for name, body in draft.sections.items():
        normalized = re.sub(r"[^a-z]", "", name.casefold())
        if normalized == "title":
            title = body.strip() or title
        elif normalized == "abstract":
            abstract = body
        elif normalized in {"keyword", "keywords"}:
            keywords = [item.strip() for item in re.split(r"[,;]", body) if item.strip()]
        else:
            blocks.append(f"# {name}\n\n{body}")
    return title, abstract, "\n\n".join(blocks), keywords


class JournalStyleRevisionService:
    def __init__(self, *, generator: StructuredGenerator | None, model: str | None, loader: JournalProfileLoader | None = None, latex_service: LatexService | None = None) -> None:
        if (generator is None) != (model is None):
            raise ValueError("generator and model must be configured together")
        self.generator = generator
        self.model = model
        self.loader = loader or JournalProfileLoader()
        self.latex_service = latex_service or LatexService()

    def recommend_article_type(self, request: ArticleTypeRecommendationRequest) -> ArticleTypeRecommendation:
        from stem_sci.agents.runtime import StructuredGenerationError

        profile = self.loader.load_journal_profile(request.target_journal)
        if len(profile.article_types) == 1:
            return ArticleTypeRecommendation(target_journal=profile.journal.name, recommended_type=profile.article_types[0], allowed_types=profile.article_types, rationale="The selected journal profile defines one supported article type.", requires_confirmation=False)
        if self.generator is None or self.model is None:
            raise JournalRevisionUnavailableError("article-type recommendation requires a configured LLM")
        try:
            result = self.generator.generate(
                system_prompt=(
                    "Recommend exactly one configured journal scholarship type from manuscript evidence. "
                    "Do not revise the manuscript. Return JSON with exactly two fields: recommended_type "
                    "and rationale. recommended_type must exactly match one allowed type."
                ),
                user_prompt=json.dumps({"target_journal": profile.journal.name, "allowed_types": profile.article_types, "sections": request.draft.sections}, ensure_ascii=False, sort_keys=True),
                response_model=ArticleTypeRecommendationModelResponse,
                model=self.model,
                prompt_version="journal-type-recommendation-v1",
            )
        except StructuredGenerationError as error:
            raise JournalRevisionUnavailableError(
                "article-type recommendation did not return a valid structured response"
            ) from error
        model_response = result.parsed_output
        assert isinstance(model_response, ArticleTypeRecommendationModelResponse)
        if model_response.recommended_type not in profile.article_types:
            raise ValueError("model recommended an article type absent from the journal profile")
        return ArticleTypeRecommendation(
            target_journal=profile.journal.name,
            recommended_type=model_response.recommended_type,
            allowed_types=profile.article_types,
            rationale=model_response.rationale,
            requires_confirmation=True,
        )

    def revise(self, request: JournalStyleRevisionRequest, _revision_feedback: str | None = None, _revision_attempt: int = 0) -> JournalStyleRevisionResult:
        from stem_sci.agents.runtime import StructuredGenerationError

        if request.draft.language is not LanguageCode.EN_US:
            raise ValueError("journal-style revision currently accepts only the English draft")
        if request.draft.project_id != request.claim_graph.project_id:
            raise ValueError("draft and claim graph project ids do not match")
        profile = self.loader.load_journal_profile(request.target_journal)
        if request.article_type is None and len(profile.article_types) > 1:
            recommendation = self.recommend_article_type(ArticleTypeRecommendationRequest(target_journal=request.target_journal, draft=request.draft))
            print("RETURN_BRANCH: requires_confirmation")
            print("FINAL_REVISION_STATUS:", "REQUIRES_CONFIRMATION")
            print("FINAL_SAFETY_FINDINGS:", ["ARTICLE_TYPE_CONFIRMATION_REQUIRED"])
            return JournalStyleRevisionResult(
                draft=request.draft,
                report=JournalStyleRevisionReport(status=RevisionStatus.REQUIRES_CONFIRMATION, target_journal=profile.journal.name, methodology=request.methodology, safety_findings=["ARTICLE_TYPE_CONFIRMATION_REQUIRED"]),
                recommendation=recommendation,
            )
        constraints = self.loader.resolve_writing_constraints(request.target_journal, request.article_type, methodology=request.methodology)
        if self.generator is None or self.model is None:
            raise JournalRevisionUnavailableError("journal-style revision requires a configured LLM")
        layers = constraints.style_layers
        applied_layers = [name for name in layers.get("precedence", []) if isinstance(name, str) and bool(layers.get(name))]
        warnings = [str(item) for item in layers.get("warnings", [])] if isinstance(layers.get("warnings"), list) else []
        ieee_constraint = (
            _IEEE_SOURCE_FIDELITY_PROMPT
            if constraints.target_journal == "IEEE Transactions on Education"
            else ""
        )
        revision_prompt = json.dumps(
            {
                "draft_sections": request.draft.sections,
                "claim_graph": request.claim_graph.model_dump(mode="json"),
                "constraints": constraints.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if ieee_constraint:
            revision_prompt += f"\n\n{_IEEE_FINAL_SOURCE_POLICY}\n\n{_IEEE_OUTPUT_FORMAT_PROMPT}"
        if _revision_feedback:
            revision_prompt += f"\n\nREVISION FEEDBACK FROM PREVIOUS CHECK (attempt {_revision_attempt}):\n{_revision_feedback}\nFix only the reported issues and return the complete revised JSON."
        try:
            response = self.generator.generate(
                system_prompt=(
                    "Professionally revise the supplied English research manuscript to follow the configured "
                    "journal style. Preserve every scientific claim, number, citation, result direction, and "
                    "causal strength. Do not invent evidence. Return each revised section as an object with "
                    "exactly name and text fields, plus a concise change_summary. Sections may change when needed for journal fit."
                    " Do not add or alter numbers, percentages, sample sizes, dates, citations, statistical values, result directions, causal claims, study details, or conclusions. Do not expand missing information with plausible details. If a style rule conflicts with source fidelity, preserve the source and skip the style change. Return JSON only.\n\n"
                    + ieee_constraint
                ),
                user_prompt=revision_prompt,
                response_model=RevisedSectionsResponse,
                model=self.model,
                prompt_version="journal-style-revision-v1",
            )
        except StructuredGenerationError as error:
            if _revision_attempt < 2:
                return self.revise(
                    request,
                    _revision_feedback=f"MODEL_OUTPUT_INVALID: {error.provider_error}. Return valid JSON matching the requested schema.",
                    _revision_attempt=_revision_attempt + 1,
                )
            print("RETURN_BRANCH: structured_generation_error")
            print("FINAL_REVISION_STATUS:", "REJECTED")
            print("FINAL_SAFETY_FINDINGS:", ["MODEL_OUTPUT_INVALID"])
            return JournalStyleRevisionResult(
                draft=request.draft,
                report=JournalStyleRevisionReport(
                    status=RevisionStatus.REJECTED,
                    target_journal=constraints.target_journal,
                    article_type=constraints.article_type,
                    methodology=request.methodology,
                    applied_layers=applied_layers,
                    layer_warnings=warnings,
                    safety_findings=["MODEL_OUTPUT_INVALID"],
                    generation_error=str(error.provider_error),
                ),
            )
        revised = response.parsed_output
        assert isinstance(revised, RevisedSectionsResponse)
        raw_revised_sections = revised.section_map()
        safety_findings = revision_safety_findings(request.draft, raw_revised_sections)
        blocking_safety_findings = [
            finding for finding in safety_findings
            if _finding_code(finding) in _BLOCKING_FINDINGS
        ]
        if blocking_safety_findings:
            if _revision_attempt < 2:
                return self.revise(
                    request,
                    _revision_feedback="; ".join(blocking_safety_findings),
                    _revision_attempt=_revision_attempt + 1,
                )
            print("RETURN_BRANCH: safety_rejection")
            print("FINAL_REVISION_STATUS:", "REJECTED")
            print("FINAL_SAFETY_FINDINGS:", safety_findings)
            return JournalStyleRevisionResult(
                draft=request.draft,
                report=JournalStyleRevisionReport(
                    status=RevisionStatus.REJECTED,
                    target_journal=constraints.target_journal,
                    article_type=constraints.article_type,
                    methodology=request.methodology,
                    applied_layers=applied_layers,
                    layer_warnings=warnings,
                    safety_findings=safety_findings,
                ),
                candidate_draft=request.draft.model_copy(update={"sections": raw_revised_sections}),
            )

        revised_sections = raw_revised_sections
        print("ORIGINAL:", list(request.draft.sections.keys()))
        print("LLM RAW:", [s.name for s in revised.sections])
        print("FINAL MAPPED:", list(revised_sections.keys()))
        revised_draft = request.draft.model_copy(update={"sections": revised_sections})
        configured_rules = [{"section": section, "rule_type": rule_type, "rule": rule} for section, rule_type, rule in sorted(semantic_rule_keys(constraints), key=str)]
        try:
            assessment_result = self.generator.generate(
                system_prompt=(
                    "Assess every supplied journal rule against the revised manuscript. For avoid rules, PASS "
                    "means the prohibited behavior is absent. Do not invent or omit rules. Return JSON only "
                    "with exactly one top-level field named assessments. assessments must be an array; every "
                    "item must contain exactly section, rule_type, rule, status, and explanation. Copy section, "
                    "rule_type, and rule exactly from configured_rules. status must be PASS, FAIL, or NOT_CHECKED. "
                    "Use NOT_CHECKED when the manuscript does not provide enough evidence to assess a rule."
                ),
                user_prompt=json.dumps({"sections": revised_sections, "configured_rules": configured_rules}, ensure_ascii=False, sort_keys=True),
                response_model=SemanticAssessmentResponse,
                model=self.model,
                prompt_version="journal-style-validation-v1",
            )
        except StructuredGenerationError:
            # Journal validation is a compliance report, not a safety gate. If the semantic
            # assessment cannot run, keep the safety-approved revision and surface a warning.
            validation_warnings = [*warnings, "journal validation failed"]
            title, abstract, content, keywords = _markdown_content(revised_draft)
            template_id = str(constraints.template.get("template_id") or "generic-article")
            latex = self.latex_service.generate(
                LatexGenerateRequest(
                    template_id=template_id,
                    title=title,
                    abstract=abstract,
                    content=content,
                    keywords=keywords,
                    compile_pdf=request.compile_pdf,
                )
            )
            print("RETURN_BRANCH: validation_failure")
            print("FINAL_REVISION_STATUS:", "APPLIED")
            print("FINAL_SAFETY_FINDINGS:", [])
            return JournalStyleRevisionResult(
                draft=revised_draft,
                report=JournalStyleRevisionReport(
                    status=RevisionStatus.APPLIED,
                    target_journal=constraints.target_journal,
                    article_type=constraints.article_type,
                    methodology=request.methodology,
                    applied_layers=applied_layers,
                    layer_warnings=validation_warnings,
                    change_summary=revised.change_summary,
                    safety_findings=safety_findings,
                ),
                latex=latex,
                generation_metadata_refs=[
                    f"llm-metadata://{request.draft.project_id}/{response.request_id}"
                ],
            )
        assessment = assessment_result.parsed_output
        assert isinstance(assessment, SemanticAssessmentResponse)
        validation = validate_journal_draft(revised_draft, constraints.target_journal, constraints.article_type, assessment, loader=self.loader, methodology=request.methodology)
        if validation.status.value != "PASS":  # noqa: SIM102
            if _revision_attempt < 2:
                validation_feedback = "; ".join(f.message for f in validation.findings) or "JOURNAL_VALIDATION_FAILED"
                return self.revise(
                    request,
                    _revision_feedback=f"JOURNAL_VALIDATION_FAILED: {validation_feedback}",
                    _revision_attempt=_revision_attempt + 1,
                )
        print("RETURN_BRANCH: journal_validation_warning")
        print("FINAL_REVISION_STATUS:", "APPLIED")
        validation_warnings = [*warnings, "Journal validation did not pass; review the findings below."] + [f.message for f in validation.findings]
        title, abstract, content, keywords = _markdown_content(revised_draft)
        template_id = str(constraints.template.get("template_id") or "generic-article")
        latex = self.latex_service.generate(LatexGenerateRequest(template_id=template_id, title=title, abstract=abstract, content=content, keywords=keywords, compile_pdf=request.compile_pdf))
        return JournalStyleRevisionResult(
            draft=revised_draft,
            report=JournalStyleRevisionReport(
                status=RevisionStatus.APPLIED,
                target_journal=constraints.target_journal,
                article_type=constraints.article_type,
                methodology=request.methodology,
                applied_layers=applied_layers,
                layer_warnings=validation_warnings,
                safety_findings=safety_findings,
                change_summary=revised.change_summary,
            ),
            journal_validation=validation,
            latex=latex,
            generation_metadata_refs=[f"llm-metadata://{request.draft.project_id}/{response.request_id}"],
        )
        metadata_refs = [
            f"llm-metadata://{request.draft.project_id}/{response.request_id}",
            f"llm-metadata://{request.draft.project_id}/{assessment_result.request_id}",
        ]
        title, abstract, content, keywords = _markdown_content(revised_draft)
        template_id = str(constraints.template.get("template_id") or "generic-article")
        latex = self.latex_service.generate(LatexGenerateRequest(template_id=template_id, title=title, abstract=abstract, content=content, keywords=keywords, compile_pdf=request.compile_pdf))
        print("RETURN_BRANCH: applied")
        print("FINAL_REVISION_STATUS:", "APPLIED")
        print("FINAL_SAFETY_FINDINGS:", [])
        return JournalStyleRevisionResult(
            draft=revised_draft,
            report=JournalStyleRevisionReport(status=RevisionStatus.APPLIED, target_journal=constraints.target_journal, article_type=constraints.article_type, methodology=request.methodology, applied_layers=applied_layers, layer_warnings=warnings, change_summary=revised.change_summary, safety_findings=safety_findings),
            journal_validation=validation,
            latex=latex,
            generation_metadata_refs=metadata_refs,
        )
