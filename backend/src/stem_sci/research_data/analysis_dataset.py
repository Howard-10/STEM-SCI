"""Controller-owned creation of model-specific canonical AnalysisDatasets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from stem_sci.research_data.audit import PROMPT_COLUMNS
from stem_sci.research_data.canonical import canonical_csv_bytes, read_csv_rows
from stem_sci.research_data.models import (
    AnalysisDatasetRef,
    AnalysisDatasetSerializationPolicy,
    FrozenDatasetRef,
    ModelEligibilityManifest,
    ParticipantEligibilityManifest,
)
from stem_sci.utils.hash_utils import sha256_bytes


class DeterministicDataProcessor:
    """Apply approved, model-specific row selection without mutating FrozenDataset."""

    processor_version = "deterministic-analysis-dataset-v1"
    serialization_policy = AnalysisDatasetSerializationPolicy()

    def create_analysis_dataset(
        self,
        *,
        frozen_dataset: FrozenDatasetRef,
        participant_manifest: ParticipantEligibilityManifest,
        model_manifest: ModelEligibilityManifest,
        data_processing_plan_ref: str,
        analysis_dataset_specification_ref: str,
        model_specification_ref: str,
        destination_directory: Path,
    ) -> AnalysisDatasetRef:
        if model_manifest.source_frozen_dataset_ref != frozen_dataset.ref:
            raise ValueError("model eligibility manifest references another frozen dataset")
        if model_manifest.source_dataset_sha256 != frozen_dataset.canonical_content_sha256:
            raise ValueError("model eligibility manifest frozen hash does not match")
        if model_manifest.participant_eligibility_manifest_ref != participant_manifest.ref:
            raise ValueError("model eligibility manifest references another participant manifest")
        if not model_manifest.passed_minimum_coverage:
            raise ValueError("model eligibility minimum coverage did not pass")
        header, rows = read_csv_rows(Path(frozen_dataset.content_uri).read_bytes())
        eligible = {record.participant_id for record in model_manifest.records if record.eligible}
        selected = [
            row
            for row in rows
            if row["participant_id"] in eligible and self._accepts(model_manifest.model_id, row)
        ]
        output_header, output_rows = self._output_rows(model_manifest.model_id, header, selected)
        content = canonical_csv_bytes(output_header, output_rows, policy=self.serialization_policy)
        destination_directory.mkdir(parents=True, exist_ok=True)
        dataset_id = f"analysis-{model_manifest.model_id}-{uuid4().hex}"
        destination = destination_directory / f"{dataset_id}.csv"
        destination.write_bytes(content)
        included_participants = {row["participant_id"] for row in selected}
        return AnalysisDatasetRef(
            dataset_id=dataset_id,
            project_id=frozen_dataset.project_id,
            version=1,
            content_uri=str(destination),
            sha256=sha256_bytes(content),
            raw_bytes_sha256=sha256_bytes(content),
            canonical_content_sha256=sha256_bytes(content),
            created_at=datetime.now(UTC),
            source_frozen_dataset_ref=frozen_dataset.ref,
            source_dataset_sha256=frozen_dataset.canonical_content_sha256,
            data_processing_plan_ref=data_processing_plan_ref,
            analysis_dataset_specification_ref=analysis_dataset_specification_ref,
            model_specification_ref=model_specification_ref,
            participant_eligibility_manifest_ref=participant_manifest.ref,
            model_eligibility_manifest_ref=model_manifest.ref,
            included_row_count=len(output_rows),
            excluded_row_count=len(rows) - len(selected),
            included_participant_count=len(included_participants),
            serialization_policy_ref=f"serialization-policy://{self.serialization_policy.policy_id}",
        )

    @staticmethod
    def _accepts(model_id: str, row: dict[str, str]) -> bool:
        if model_id == "transfer_ancova":
            return row["task_id"] == "C"
        return row["task_id"] in {"A", "B"}

    @staticmethod
    def _output_rows(
        model_id: str, header: list[str], rows: list[dict[str, str]]
    ) -> tuple[list[str], list[dict[str, object]]]:
        if model_id != "prompt_dependency_lmm":
            return header, [dict(row) for row in rows]
        output_header = [column for column in header if column not in PROMPT_COLUMNS]
        output_header.append("prompt_dependency")
        output_rows: list[dict[str, object]] = []
        for row in rows:
            transformed: dict[str, object] = {
                column: row[column] for column in output_header if column != "prompt_dependency"
            }
            transformed["prompt_dependency"] = sum(float(row[column]) for column in PROMPT_COLUMNS) / 6
            output_rows.append(transformed)
        return output_header, output_rows
