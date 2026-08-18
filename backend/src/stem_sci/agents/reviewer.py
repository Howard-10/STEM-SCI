"""Independent-review Agent role boundary."""

from datetime import UTC, datetime
from typing import Literal

from stem_sci.core.enums import DecisionScope
from stem_sci.coding.compiler import CodeSpecificationCompiler

from .base import BaseAgent
from .contracts import AgentInput, AgentResult, CandidateArtifact, ReviewFinding, ReviewReport, RevisionRequest
from .reviewer_contracts import (
    CitationReviewInput,
    GeneralReviewOutcome,
    MethodReviewInput,
    ManuscriptTraceabilityReviewInput,
    PedagogyReviewInput,
    ReproducibilityReviewInput,
    ReproducibilityReviewOutcome,
    ReviewArbiterInput,
    ReviewArbiterOutcome,
    ReviewPacket,
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

    def as_agent_result(
        self,
        agent_input: AgentInput,
        outcome: GeneralReviewOutcome | ReproducibilityReviewOutcome,
    ) -> AgentResult:
        """Adapt read-only review output into Controller-persistable candidates.

        This method is deliberately one-way: it exposes findings and revision
        requests but cannot apply any requested change or alter workflow state.
        """

        allowed = set(agent_input.allowed_output_types)
        artifacts: list[CandidateArtifact] = []
        for finding in outcome.findings:
            if "ReviewFinding" in allowed:
                artifacts.append(self._artifact(agent_input.task_ref, "ReviewFinding", finding.finding_id, finding))
        for request in outcome.revision_requests:
            if "RevisionRequest" in allowed:
                artifacts.append(
                    self._artifact(agent_input.task_ref, "RevisionRequest", request.revision_id, request)
                )
        if "ReviewReport" in allowed:
            artifacts.append(
                self._artifact(
                    agent_input.task_ref,
                    "ReviewReport",
                    outcome.report.review_report_id,
                    outcome.report,
                )
            )
        risk_flags = []
        if outcome.report.overall_recommendation != "PASS":
            risk_flags.append("REVIEW_REQUIRES_CONTROLLER_ROUTE")
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version="phase1-structured-review-v1",
            candidate_artifact_refs=[artifact.candidate_ref for artifact in artifacts],
            candidate_artifacts=artifacts,
            evidence_refs=list(
                dict.fromkeys(
                    ref for finding in outcome.findings for ref in finding.evidence_refs
                )
            ),
            risk_flags=risk_flags,
            unresolved_questions=[
                request.required_changes[0] for request in outcome.revision_requests
            ],
            recommendations=[
                "Controller must interpret decision_scope and route any revision; the reviewer is read-only."
            ],
            confidence=1.0 if outcome.report.overall_recommendation == "PASS" else 0.5,
            created_at=datetime.now(UTC),
        )

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

    def review_execution_packet(self, packet: ReviewPacket) -> GeneralReviewOutcome:
        """Audit immutable execution identity without rerunning or changing anything."""

        reasons: list[str] = []
        manifest = packet.reproducibility_manifest
        if manifest.code_artifact_sha256 != packet.code_artifact.sha256:
            reasons.append("CodeArtifact hash differs from ReproducibilityManifest")
        if manifest.analysis_dataset_sha256 != packet.analysis_dataset.canonical_content_sha256:
            reasons.append("AnalysisDataset hash differs from ReproducibilityManifest")
        code_spec_hash = CodeSpecificationCompiler.fingerprint(packet.code_specification)
        if manifest.code_spec_sha256 != code_spec_hash:
            reasons.append("CodeSpecification hash differs from ReproducibilityManifest")
        if packet.code_artifact.source_specification_sha256 != code_spec_hash:
            reasons.append("CodeArtifact is not bound to the supplied CodeSpecification")
        if packet.execution_run.operator_run_id not in packet.validation_report.execution_run_refs:
            reasons.append("ExecutionRun is absent from ResultValidationReport")
        if any(
            card.execution_run_ref != packet.execution_run.operator_run_id
            for card in packet.statistical_result_cards
        ):
            reasons.append("StatisticalResultCard is not bound to the supplied ExecutionRun")
        if packet.execution_run.status.value != "SUCCEEDED":
            reasons.append("ExecutionRun did not succeed")
        if not packet.validation_report.passed:
            reasons.append("ResultValidationReport did not pass")
        if not reasons:
            return self._general_outcome("reproducibility", packet.code_artifact.ref, [], [])
        finding = ReviewFinding(
            finding_id=f"finding://execution-packet/{packet.code_artifact.artifact_id}",
            reviewer_type="reproducibility",
            artifact_ref=packet.code_artifact.ref,
            severity="critical",
            category="execution_provenance",
            description="; ".join(reasons),
            evidence_refs=[packet.code_specification.ref, packet.analysis_dataset.ref, manifest.ref],
            suggested_action="Controller must stop release and obtain a new verified execution package.",
            decision_scope=DecisionScope.STAGE,
            blocked_target_ids=[packet.code_artifact.ref],
        )
        revision = RevisionRequest(
            revision_id=f"revision://execution-packet/{packet.code_artifact.artifact_id}",
            artifact_ref=packet.code_artifact.ref,
            required_changes=reasons,
            blocking=True,
            triggered_by_refs=[finding.finding_id],
        )
        return self._general_outcome("reproducibility", packet.code_artifact.ref, [finding], [revision])

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

    def review_traceability(
        self, review_input: ManuscriptTraceabilityReviewInput
    ) -> GeneralReviewOutcome:
        """Audit claim links without judging scientific truth or editing a manuscript."""

        evidence_by_id = {item.evidence_id: item for item in review_input.evidence_refs}
        result_refs = {card.ref for card in review_input.validated_result_cards}
        findings: list[ReviewFinding] = []
        revisions: list[RevisionRequest] = []
        for claim in review_input.claim_graph.nodes:
            reasons: list[str] = []
            if claim.claim_type.value == "LITERATURE":
                if not claim.evidence_refs:
                    reasons.append("literature claim has no evidence reference")
                for ref in claim.evidence_refs:
                    evidence = evidence_by_id.get(ref)
                    if evidence is None:
                        reasons.append(f"evidence reference {ref} is absent from the review package")
                    elif evidence.verification_status.value not in {
                        "source_verified",
                        "human_verified",
                    }:
                        reasons.append(f"evidence reference {ref} is not formally verified")
            elif claim.claim_type.value == "RESULT" and claim.result_card_ref not in result_refs:
                reasons.append("RESULT claim lacks a project-scoped validated StatisticalResultCard")
            elif claim.claim_type.value == "METHOD" and claim.method_ref not in set(
                review_input.approved_study_protocol_refs
            ):
                reasons.append("METHOD claim lacks an approved study protocol reference")
            elif claim.claim_type.value == "INTERPRETATION":
                if claim.interpretation_boundary_ref is None:
                    reasons.append("INTERPRETATION claim lacks an interpretation boundary")
                if claim.human_approval_ref is None:
                    reasons.append("INTERPRETATION claim lacks human approval")
            if not reasons:
                continue
            finding_id = f"finding://traceability/{claim.claim_id}"
            findings.append(
                ReviewFinding(
                    finding_id=finding_id,
                    reviewer_type="traceability",
                    artifact_ref=review_input.manuscript_ref,
                    severity="major",
                    category="claim_traceability",
                    description="; ".join(reasons),
                    evidence_refs=claim.evidence_refs,
                    suggested_action="Repair claim references before independent release review.",
                    decision_scope=DecisionScope.ARTIFACT,
                    blocked_target_ids=[review_input.manuscript_ref],
                )
            )
            revisions.append(
                RevisionRequest(
                    revision_id=f"revision://traceability/{claim.claim_id}",
                    artifact_ref=review_input.manuscript_ref,
                    required_changes=reasons,
                    blocking=True,
                    triggered_by_refs=[finding_id],
                )
            )
        return self._general_outcome("traceability", review_input.manuscript_ref, findings, revisions)

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

    @staticmethod
    def _artifact(
        task_ref: str,
        artifact_type: str,
        artifact_id: str,
        body: ReviewFinding | RevisionRequest | ReviewReport,
    ) -> CandidateArtifact:
        safe_id = artifact_id.replace("://", "-").replace("/", "-")
        return CandidateArtifact(
            candidate_ref=f"candidate://independent_review/{task_ref}/{safe_id}/{artifact_type}",
            artifact_type=artifact_type,
            schema_version="v1",
            body=body.model_dump(mode="json"),
        )
