"""Controller-owned registry for deterministic operator capabilities."""

from __future__ import annotations

from collections.abc import Iterable

from .models import OperatorSpec


class OperatorRegistry:
    def __init__(self, specs: Iterable[OperatorSpec] = ()) -> None:
        self._specs = {spec.operator_id: spec for spec in specs}

    @classmethod
    def default(cls) -> OperatorRegistry:
        runtime_capabilities = {
            "literature_search",
            "paper_screening",
            "paper_extraction",
            "source_verification",
        }
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
                operator_version=(
                    "phase2-knowledge-runtime"
                    if capability in runtime_capabilities
                    else "phase1-contract"
                ),
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
