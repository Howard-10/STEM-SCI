"""Deterministic, version-aware registry for Controller-visible Tools."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ToolExecutionMode, ToolSpec


def _key(identifier: str, version: str) -> tuple[str, str]:
    return identifier, version


class ToolRegistry:
    """In-memory registry keyed by the stable ``tool_id@tool_version`` pair."""

    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[tuple[str, str], ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    @classmethod
    def default(cls) -> ToolRegistry:
        """Return the local, network-disabled Task 4 Tool catalog."""
        read_only = {
            "context_bundle_read": ("schema://ContextRef", "schema://ContextBundle"),
            "artifact_resolve": ("schema://ArtifactRef", "schema://ArtifactContent"),
            "artifact_integrity_check": ("schema://ArtifactRef", "schema://IntegrityReport"),
            "evidence_ref_validate": ("schema://EvidenceId", "schema://EvidenceRef"),
            "knowledge_base_search": ("schema://EvidenceSearchRequest", "schema://EvidenceSearchResultSet"),
            "source_chunk_reader": ("schema://SourceChunkRequest", "schema://SourceChunkCollection"),
            "source_verification_checker": ("schema://EvidenceRefCollection", "schema://VerificationReport"),
            "citation_deduplicator": ("schema://EvidenceRefCollection", "schema://EvidenceRefCollection"),
            "bounded_synthesis_validator": ("schema://BoundedEvidenceSynthesis", "schema://ValidationReport"),
        }
        candidate = {
            "paper_screening_executor": ("schema://ScreeningRequest", "schema://ScreeningLedger"),
            "paper_card_extractor": ("schema://SourceChunkCollection", "schema://PaperCardCollection"),
            "evidence_matrix_builder": ("schema://PaperCardCollection", "schema://EvidenceMatrixCandidate"),
            "evidence_conflict_detector": ("schema://EvidenceMatrixCandidate", "schema://EvidenceConflictMap"),
            "corpus_coverage_calculator": ("schema://EvidenceMatrixCandidate", "schema://CorpusCoverageReport"),
        }
        design = {name: ("schema://DesignInput", "schema://ValidationReport") for name in (
            "research_scope_validator", "feasibility_checker",
            "research_question_validator", "hypothesis_structure_checker", "estimand_validator", "causal_dag_checker", "sampling_plan_checker", "measurement_plan_checker", "protocol_schema_validator", "preregistration_consistency_checker", "intervention_protocol_linter", "quality_gate_plan_builder")}
        analysis = {name: ("schema://AnalysisInput", "schema://AnalysisCandidate") for name in (
            "dataset_catalog_read", "dataset_schema_profile", "data_quality_audit", "missingness_and_outlier_report", "data_processing_executor", "model_diagnostic_runner", "statistical_result_card_builder", "result_validation_checker", "data_freeze_request_builder", "python_analysis_sandbox")}
        writing = {name: ("schema://WritingInput", "schema://WritingCandidate") for name in (
            "writing_context_resolver", "atomic_claim_validator", "claim_evidence_mapper", "manuscript_outline_validator", "manuscript_renderer_zh", "manuscript_renderer_en", "bilingual_consistency_checker", "citation_consistency_checker", "numeric_literal_checker", "result_strength_checker", "limitation_coverage_checker", "reproducibility_statement_builder", "table_figure_narrative_builder")}
        review = {name: ("schema://ReviewInput", "schema://ReviewProposal") for name in (
            "citation_audit", "evidence_reference_audit", "method_protocol_alignment_checker", "statistical_claim_audit", "result_limitation_audit", "reproducibility_artifact_audit", "bilingual_draft_audit", "review_finding_builder", "revision_request_builder", "review_summary_builder")}
        specs = [
            ToolSpec(
                tool_id=tool_id,
                tool_version="v1",
                capability=tool_id,
                execution_mode=ToolExecutionMode.READ_ONLY,
                input_schema_ref=schemas[0],
                output_schema_ref=schemas[1],
                project_scope_required=True,
                network_policy="disabled",
                timeout_seconds=30,
            )
            for tool_id, schemas in read_only.items()
        ]
        specs.extend(
            ToolSpec(
                tool_id=tool_id,
                tool_version="v1",
                capability=tool_id,
                execution_mode=ToolExecutionMode.CANDIDATE_OUTPUT,
                input_schema_ref=schemas[0],
                output_schema_ref=schemas[1],
                project_scope_required=True,
                network_policy="disabled",
                timeout_seconds=60,
            )
            for tool_id, schemas in candidate.items()
        )
        for catalog in (design, analysis, writing, review):
            specs.extend(
                ToolSpec(tool_id=tool_id, tool_version="v1", capability=tool_id,
                         execution_mode=ToolExecutionMode.CANDIDATE_OUTPUT,
                         input_schema_ref=schemas[0], output_schema_ref=schemas[1],
                         project_scope_required=True, network_policy="disabled", timeout_seconds=60)
                for tool_id, schemas in catalog.items()
            )
        return cls(specs)

    def register(self, spec: ToolSpec) -> None:
        key = _key(spec.tool_id, spec.tool_version)
        if key in self._specs:
            raise ValueError(f"tool {spec.tool_id}@{spec.tool_version} is already registered")
        self._specs[key] = spec

    def get(self, tool_id: str, tool_version: str | None = None) -> ToolSpec:
        if tool_version is not None:
            try:
                return self._specs[(tool_id, tool_version)]
            except KeyError as exc:
                raise KeyError(f"unknown tool {tool_id}@{tool_version}") from exc

        matches = [spec for (identifier, _), spec in self._specs.items() if identifier == tool_id]
        if not matches:
            raise KeyError(f"unknown tool {tool_id}")
        if len(matches) > 1:
            raise ValueError(f"tool {tool_id} has multiple versions; version is required")
        return matches[0]

    def resolve(self, capability: str) -> list[ToolSpec]:
        """Return all versions for a capability in stable identifier order."""
        return sorted(
            (spec for spec in self._specs.values() if spec.capability == capability),
            key=lambda spec: (spec.tool_id, spec.tool_version),
        )

    def list(self) -> list[ToolSpec]:
        """Return every registered Tool in stable identifier/version order."""
        return sorted(self._specs.values(), key=lambda spec: (spec.tool_id, spec.tool_version))
