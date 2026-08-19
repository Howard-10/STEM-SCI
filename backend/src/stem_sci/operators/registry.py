"""Controller-owned registry for deterministic operator capabilities."""

from __future__ import annotations

from collections.abc import Iterable

from .models import OperatorSpec


class OperatorRegistry:
    def __init__(self, specs: Iterable[OperatorSpec] = ()) -> None:
        self._specs = {spec.operator_id: spec for spec in specs}

    @classmethod
    def default(cls) -> OperatorRegistry:
        definitions = (
            ("literature_search", "Literature Search", "SearchProtocol", "EvidenceSet"),
            ("paper_screening", "Paper Screening", "PaperSet", "ScreenedPaperSet"),
            ("paper_extraction", "Paper Extraction", "PaperRef", "PaperCard"),
            ("source_verification", "Source Verification", "EvidenceRef", "VerifiedEvidenceRef"),
            ("data_audit", "Data Audit", "RawDatasetRef", "DataAuditReport"),
            ("data_processing", "Data Processing", "DataProcessingPlan", "ProcessedDatasetRef"),
            ("data_freeze", "Data Freeze", "ProcessedDatasetRef", "FrozenDatasetRef"),
            ("coding_provider", "Coding Provider", "CodeSpecification", "CodeArtifact"),
            ("python_analysis", "Python Analysis", "ExecutableAnalysisPlan", "ExecutionRun"),
            ("spss_analysis", "SPSS Analysis", "ExecutableAnalysisPlan", "ExecutionRun"),
            ("result_validation", "Result Validation", "ExecutionRun", "ResultValidationReport"),
            ("provenance_export", "Provenance Export", "ProjectRef", "ReproducibilityPackage"),
        )
        return cls(
            OperatorSpec(
                operator_id=capability,
                operator_version="phase1-contract",
                display_name=display_name,
                capability=capability,
                input_schema_ref=f"schema://{input_type}",
                output_schema_ref=f"schema://{output_type}",
                timeout_seconds=60,
                required_permissions=["controller_dispatch"],
                supported_artifact_types=[input_type, output_type],
            )
            for capability, display_name, input_type, output_type in definitions
        )

    def register(self, spec: OperatorSpec) -> None:
        if spec.operator_id in self._specs:
            raise ValueError(f"operator already registered: {spec.operator_id}")
        self._specs[spec.operator_id] = spec

    def get(self, operator_id: str) -> OperatorSpec:
        try:
            return self._specs[operator_id]
        except KeyError as exc:
            raise ValueError(f"unknown operator: {operator_id}") from exc

    def resolve(self, capability: str) -> list[OperatorSpec]:
        return [spec for spec in self._specs.values() if spec.capability == capability]

    def list(self) -> list[OperatorSpec]:
        return sorted(self._specs.values(), key=lambda spec: spec.operator_id)

    @staticmethod
    def builtin_tool_capabilities() -> tuple[str, ...]:
        """Names of local Agent Tools kept separate from legacy operators."""
        return (
            "context_bundle_read",
            "artifact_resolve",
            "artifact_integrity_check",
            "evidence_ref_validate",
            "knowledge_base_search",
            "source_chunk_reader",
            "source_verification_checker",
            "paper_screening_executor",
            "paper_card_extractor",
            "evidence_matrix_builder",
            "citation_deduplicator",
            "evidence_conflict_detector",
            "corpus_coverage_calculator",
            "bounded_synthesis_validator",
            "research_question_validator",
            "hypothesis_structure_checker",
            "estimand_validator",
            "causal_dag_checker",
            "sampling_plan_checker",
            "measurement_plan_checker",
            "protocol_schema_validator",
            "preregistration_consistency_checker",
            "intervention_protocol_linter",
            "quality_gate_plan_builder",
            "dataset_catalog_read",
            "dataset_schema_profile",
            "data_quality_audit",
            "missingness_and_outlier_report",
            "data_processing_executor",
            "model_diagnostic_runner",
            "statistical_result_card_builder",
            "result_validation_checker",
            "data_freeze_request_builder",
            "writing_context_resolver",
            "atomic_claim_validator",
            "claim_evidence_mapper",
            "manuscript_outline_validator",
            "manuscript_renderer_zh",
            "manuscript_renderer_en",
            "bilingual_consistency_checker",
            "citation_consistency_checker",
            "numeric_literal_checker",
            "result_strength_checker",
            "limitation_coverage_checker",
            "reproducibility_statement_builder",
            "table_figure_narrative_builder",
            "citation_audit",
            "evidence_reference_audit",
            "method_protocol_alignment_checker",
            "statistical_claim_audit",
            "result_limitation_audit",
            "reproducibility_artifact_audit",
            "bilingual_draft_audit",
            "review_finding_builder",
            "revision_request_builder",
            "review_summary_builder",
        )
