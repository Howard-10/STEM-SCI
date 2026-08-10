"""Independent-review Agent role boundary."""

from typing import Literal

from stem_sci.core.enums import DecisionScope

from .base import BaseAgent
from .contracts import ReviewFinding, ReviewReport, RevisionRequest
from .reviewer_contracts import (
    CitationReviewInput,
    GeneralReviewOutcome,
    MethodReviewInput,
    PedagogyReviewInput,
    ReproducibilityReviewInput,
    ReproducibilityReviewOutcome,
    ReviewArbiterInput,
    ReviewArbiterOutcome,
    ReviewCriterion,
)


class IndependentReviewAgent(BaseAgent):
    agent_id = "independent_review"
    supported_task_types = (
        "review_citations",
        "review_method",
        "review_reproducibility",
        "review_pedagogy",
        "review_arbitration",
    )
    allowed_tool_capabilities = ()
    allowed_output_types = ("ReviewFinding", "RevisionRequest", "ReviewReport")

    def review_reproducibility(
        self, review_input: ReproducibilityReviewInput
    ) -> ReproducibilityReviewOutcome:
        """Compare manuscript numbers to immutable result-card values only."""

        cards = {card.ref: card for card in review_input.statistical_result_cards}
        findings = []
        revisions = []
        for claim in review_input.numeric_claims:
            card = cards.get(claim.result_card_ref)
            expected = card.values.get(claim.result_key) if card is not None else None
            if expected is not None and abs(claim.reported_value - expected) <= review_input.tolerance:
                continue
            finding_id = f"finding://reproducibility/{claim.claim_ref}"
            findings.append(
                ReviewFinding(
                    finding_id=finding_id,
                    reviewer_type="reproducibility",
                    artifact_ref=review_input.manuscript_ref,
                    severity="major",
                    category="claim",
                    description=(
                        "The manuscript number is missing from, or differs from, its "
                        "referenced StatisticalResultCard."
                    ),
                    evidence_refs=[claim.result_card_ref],
                    suggested_action="Return the manuscript artifact for a traceable numeric revision.",
                    decision_scope=DecisionScope.ARTIFACT,
                    blocked_target_ids=[review_input.manuscript_ref],
                )
            )
            revisions.append(
                RevisionRequest(
                    revision_id=f"revision://reproducibility/{claim.claim_ref}",
                    artifact_ref=review_input.manuscript_ref,
                    required_changes=[
                        f"Reconcile {claim.result_key} with {claim.result_card_ref}."
                    ],
                    blocking=True,
                    triggered_by_refs=[finding_id],
                )
            )
        overall: Literal["PASS", "MAJOR_REVISION"] = "PASS" if not findings else "MAJOR_REVISION"
        report = ReviewReport(
            review_report_id=f"review-report://reproducibility/{review_input.manuscript_ref}",
            finding_refs=[finding.finding_id for finding in findings],
            revision_request_refs=[request.revision_id for request in revisions],
            overall_recommendation=overall,
        )
        return ReproducibilityReviewOutcome(
            findings=findings,
            revision_requests=revisions,
            report=report,
        )

    def review_citations(self, review_input: CitationReviewInput) -> GeneralReviewOutcome:
        """Reject unsupported or insufficiently verified citations, read-only."""

        findings: list[ReviewFinding] = []
        revisions: list[RevisionRequest] = []
        for item in review_input.citations:
            verified = item.verification_status in {"source_verified", "human_verified"}
            valid = verified and item.supports_claim and item.context_adequate and item.source_chunk_ref
            if valid:
                continue
            finding_id = f"finding://citation/{item.claim_ref}"
            reasons: list[str] = []
            if not verified:
                reasons.append("evidence is not source-verified")
            if not item.supports_claim:
                reasons.append("evidence does not support the linked claim")
            if not item.context_adequate:
                reasons.append("citation context is inadequate")
            if item.source_chunk_ref is None:
                reasons.append("source chunk reference is missing")
            findings.append(
                ReviewFinding(
                    finding_id=finding_id,
                    reviewer_type="citation",
                    artifact_ref=review_input.manuscript_ref,
                    severity="major",
                    category="citation",
                    description="; ".join(reasons),
                    evidence_refs=[item.evidence_ref],
                    suggested_action="Replace or verify the citation before release.",
                    decision_scope=DecisionScope.ARTIFACT,
                    blocked_target_ids=[review_input.manuscript_ref],
                )
            )
            revisions.append(
                RevisionRequest(
                    revision_id=f"revision://citation/{item.claim_ref}",
                    artifact_ref=review_input.manuscript_ref,
                    required_changes=[f"Repair citation support for {item.claim_ref}."],
                    blocking=True,
                    triggered_by_refs=[finding_id],
                )
            )
        return self._general_outcome("citation", review_input.manuscript_ref, findings, revisions)

    def review_method(self, review_input: MethodReviewInput) -> GeneralReviewOutcome:
        """Review protocol/design/estimand alignment without changing them."""

        return self._review_criteria("method", review_input.protocol_ref, review_input.criteria)

    def review_pedagogy(self, review_input: PedagogyReviewInput) -> GeneralReviewOutcome:
        """Review educational-intervention and transfer-measurement logic only."""

        return self._review_criteria("pedagogy", review_input.study_protocol_ref, review_input.criteria)

    def arbitrate(self, review_input: ReviewArbiterInput) -> ReviewArbiterOutcome:
        """Aggregate read-only findings into a recommendation, never a release."""

        severities = {finding.severity.lower() for finding in review_input.findings}
        scopes = {finding.decision_scope for finding in review_input.findings}
        if "critical" in severities or scopes.intersection(
            {DecisionScope.STAGE, DecisionScope.PROJECT}
        ):
            overall: Literal["PASS", "MINOR_REVISION", "MAJOR_REVISION", "BLOCK"] = "BLOCK"
        elif "major" in severities:
            overall = "MAJOR_REVISION"
        elif "minor" in severities:
            overall = "MINOR_REVISION"
        else:
            overall = "PASS"
        return ReviewArbiterOutcome(
            report=ReviewReport(
                review_report_id=f"review-arbiter://{review_input.reviewed_artifact_ref}",
                finding_refs=[finding.finding_id for finding in review_input.findings],
                overall_recommendation=overall,
            )
        )

    def _review_criteria(
        self,
        reviewer_type: str,
        reviewed_artifact_ref: str,
        criteria: list[ReviewCriterion],
    ) -> GeneralReviewOutcome:
        findings: list[ReviewFinding] = []
        revisions: list[RevisionRequest] = []
        for criterion in criteria:
            if criterion.passed:
                continue
            finding_id = f"finding://{reviewer_type}/{criterion.criterion_id}"
            target_ids = criterion.blocked_target_ids or [criterion.artifact_ref]
            findings.append(
                ReviewFinding(
                    finding_id=finding_id,
                    reviewer_type=reviewer_type,
                    artifact_ref=criterion.artifact_ref,
                    severity=criterion.severity,
                    category=criterion.category,
                    description=criterion.description,
                    evidence_refs=criterion.evidence_refs,
                    suggested_action=f"Return {criterion.artifact_ref} for a traceable revision.",
                    decision_scope=criterion.decision_scope,
                    blocked_target_ids=target_ids,
                )
            )
            revisions.append(
                RevisionRequest(
                    revision_id=f"revision://{reviewer_type}/{criterion.criterion_id}",
                    artifact_ref=criterion.artifact_ref,
                    required_changes=[criterion.description],
                    blocking=criterion.severity in {"major", "critical"},
                    triggered_by_refs=[finding_id],
                )
            )
        return self._general_outcome(reviewer_type, reviewed_artifact_ref, findings, revisions)

    @staticmethod
    def _general_outcome(
        reviewer_type: str,
        reviewed_artifact_ref: str,
        findings: list[ReviewFinding],
        revisions: list[RevisionRequest],
    ) -> GeneralReviewOutcome:
        if any(finding.severity == "critical" for finding in findings):
            overall: Literal["PASS", "MINOR_REVISION", "MAJOR_REVISION", "BLOCK"] = "BLOCK"
        elif any(finding.severity == "major" for finding in findings):
            overall = "MAJOR_REVISION"
        elif findings:
            overall = "MINOR_REVISION"
        else:
            overall = "PASS"
        return GeneralReviewOutcome(
            findings=findings,
            revision_requests=revisions,
            report=ReviewReport(
                review_report_id=f"review-report://{reviewer_type}/{reviewed_artifact_ref}",
                finding_refs=[finding.finding_id for finding in findings],
                revision_request_refs=[revision.revision_id for revision in revisions],
                overall_recommendation=overall,
            ),
        )
