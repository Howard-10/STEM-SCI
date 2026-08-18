"""Deterministic structural audit and model-specific eligibility evaluation."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from stem_sci.core.enums import DecisionScope, GateDecision
from stem_sci.core.models import DomainModel, GateResult
from stem_sci.research_data.canonical import read_csv_rows
from stem_sci.research_data.models import (
    FrozenDatasetRef,
    ModelEligibilityManifest,
    ModelEligibilityRecord,
    ParticipantEligibilityManifest,
    ParticipantEligibilityRecord,
)


REQUIRED_COLUMNS = frozenset(
    {
        "participant_id",
        "group",
        "task_sequence",
        "task_id",
        "analysis_role",
        "measurement_period",
        "baseline_score",
        "physics_modeling_score",
        "transfer_score",
        "prompt_dependency_q1",
        "prompt_dependency_q2",
        "prompt_dependency_q3",
        "prompt_dependency_q4",
        "prompt_dependency_q5",
        "prompt_dependency_q6",
    }
)
PROMPT_COLUMNS = tuple(f"prompt_dependency_q{index}" for index in range(1, 7))
DIRECT_IDENTIFIER_COLUMNS = frozenset({"name", "email", "phone", "address", "id_number"})


class StructuralDataAuditReport(DomainModel):
    report_id: str
    project_id: str
    frozen_dataset_ref: str
    passed: bool
    risk_flags: list[str]
    missing_columns: list[str]
    decision_scope: DecisionScope
    blocked_target_ids: list[str]
    participant_eligibility_manifest: ParticipantEligibilityManifest | None = None


@dataclass(frozen=True)
class AuditRows:
    header: list[str]
    rows: list[dict[str, str]]


class StructuralDataAuditor:
    """Validate research-design shape only, never outcome completeness."""

    policy_version = "structural-data-audit-v1"

    def audit(self, frozen_dataset: FrozenDatasetRef) -> StructuralDataAuditReport:
        try:
            header, rows = read_csv_rows(Path(frozen_dataset.content_uri).read_bytes())
        except (OSError, UnicodeDecodeError, ValueError):
            return self._failure(frozen_dataset, ["FROZEN_CSV_UNREADABLE"], [])
        flags: list[str] = []
        missing_columns = sorted(REQUIRED_COLUMNS.difference(header))
        if missing_columns:
            flags.append("REQUIRED_COLUMNS_MISSING")
        if DIRECT_IDENTIFIER_COLUMNS.intersection(value.lower() for value in header):
            flags.append("UNSANITIZED_DIRECT_IDENTIFIER")
        if missing_columns or flags:
            return self._failure(frozen_dataset, flags, missing_columns)
        by_participant: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            participant_id = row["participant_id"].strip()
            if not participant_id:
                flags.append("PARTICIPANT_ID_EMPTY")
                continue
            by_participant[participant_id].append(row)
        records: list[ParticipantEligibilityRecord] = []
        for participant_id, participant_rows in sorted(by_participant.items()):
            participant_flags = self._participant_structure_flags(participant_rows)
            if participant_flags:
                flags.extend(participant_flags)
            records.append(
                ParticipantEligibilityRecord(
                    participant_id=participant_id,
                    study_inclusion_status="eligible" if not participant_flags else "ineligible",
                    rule_ids=sorted(set(participant_flags)),
                )
            )
        passed = not flags
        manifest = ParticipantEligibilityManifest(
            manifest_id=f"participant-eligibility-{uuid4().hex}",
            project_id=frozen_dataset.project_id,
            frozen_dataset_ref=frozen_dataset.ref,
            frozen_dataset_sha256=frozen_dataset.canonical_content_sha256,
            records=records or [ParticipantEligibilityRecord(
                participant_id="__none__", study_inclusion_status="ineligible", rule_ids=["NO_ROWS"]
            )],
        )
        return StructuralDataAuditReport(
            report_id=f"structural-audit-{uuid4().hex}",
            project_id=frozen_dataset.project_id,
            frozen_dataset_ref=frozen_dataset.ref,
            passed=passed,
            risk_flags=sorted(set(flags)),
            missing_columns=[],
            decision_scope=DecisionScope.TASK if passed else DecisionScope.ARTIFACT,
            blocked_target_ids=[] if passed else [frozen_dataset.ref],
            participant_eligibility_manifest=manifest,
        )

    @staticmethod
    def _participant_structure_flags(rows: list[dict[str, str]]) -> list[str]:
        flags: list[str] = []
        groups = {row["group"].strip() for row in rows}
        if len(groups) != 1 or not groups.issubset({"ai_scaffold", "static_prompt"}):
            flags.append("GROUP_NOT_CONSTANT_OR_INVALID")
        sequences = {row["task_sequence"].strip() for row in rows}
        if len(sequences) != 1 or not sequences.issubset({"AB", "BA"}):
            flags.append("TASK_SEQUENCE_NOT_CONSTANT_OR_INVALID")
        baseline = {row["baseline_score"].strip() for row in rows}
        if len(baseline) != 1 or not _finite(next(iter(baseline), "")):
            flags.append("BASELINE_NOT_CONSTANT_OR_NONFINITE")
        repeated = [row for row in rows if row["analysis_role"].strip() == "repeated_modeling"]
        transfer = [row for row in rows if row["analysis_role"].strip() == "transfer"]
        if len(repeated) != 2 or len(transfer) != 1 or len(rows) != 3:
            flags.append("AB_C_RECORD_STRUCTURE_INVALID")
            return flags
        task_period = {(row["task_id"].strip(), row["measurement_period"].strip()) for row in repeated}
        sequence = next(iter(sequences), "")
        expected = {("A", "period1"), ("B", "period2")} if sequence == "AB" else {
            ("B", "period1"), ("A", "period2")
        }
        if task_period != expected:
            flags.append("TASK_SEQUENCE_PERIOD_MAPPING_INVALID")
        c_row = transfer[0]
        if c_row["task_id"].strip() != "C" or c_row["measurement_period"].strip():
            flags.append("TRANSFER_RECORD_INVALID")
        if any(row["task_id"].strip() not in {"A", "B"} for row in repeated):
            flags.append("REPEATED_TASK_INVALID")
        flags.extend(StructuralDataAuditor._optional_measurement_flags(rows))
        return flags

    @staticmethod
    def _optional_measurement_flags(rows: list[dict[str, str]]) -> list[str]:
        """Reject malformed values while leaving outcome *missingness* to models.

        A blank score or dependency item is not a dataset-wide structural
        failure: eligibility determines which approved model may use that
        participant.  A nonblank nonnumeric value, however, makes the data
        artifact ill-typed and cannot safely be interpreted as missing.
        """

        flags: list[str] = []
        for row in rows:
            for column in ("physics_modeling_score", "transfer_score"):
                value = row[column].strip()
                if value and not _finite(value):
                    flags.append("OUTCOME_VALUE_NONFINITE")
            for column in PROMPT_COLUMNS:
                value = row[column].strip()
                if value and not _scale_1_to_5(value):
                    flags.append("PROMPT_ITEM_OUT_OF_RANGE")
        return flags

    @staticmethod
    def _failure(
        frozen_dataset: FrozenDatasetRef, flags: list[str], missing_columns: list[str]
    ) -> StructuralDataAuditReport:
        return StructuralDataAuditReport(
            report_id=f"structural-audit-{uuid4().hex}",
            project_id=frozen_dataset.project_id,
            frozen_dataset_ref=frozen_dataset.ref,
            passed=False,
            risk_flags=flags,
            missing_columns=missing_columns,
            decision_scope=DecisionScope.ARTIFACT,
            blocked_target_ids=[frozen_dataset.ref],
        )


class ModelEligibilityEvaluator:
    """Build independent model eligibility manifests from a structurally valid dataset."""

    policy_version = "model-eligibility-v1"

    def evaluate(
        self,
        *,
        frozen_dataset: FrozenDatasetRef,
        participant_manifest: ParticipantEligibilityManifest,
        model_id: str,
        minimum_group_size: int = 24,
        minimum_group_sequence_size: int = 12,
    ) -> ModelEligibilityManifest:
        if model_id not in {"primary_lmm", "transfer_ancova", "prompt_dependency_lmm"}:
            raise ValueError("unsupported model eligibility id")
        _, rows = read_csv_rows(Path(frozen_dataset.content_uri).read_bytes())
        rows_by_participant: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            rows_by_participant[row["participant_id"]].append(row)
        study_eligible = {
            record.participant_id
            for record in participant_manifest.records
            if record.study_inclusion_status == "eligible"
        }
        records: list[ModelEligibilityRecord] = []
        eligible_rows: list[dict[str, str]] = []
        for participant_id in sorted(rows_by_participant):
            participant_rows = rows_by_participant[participant_id]
            rules = [] if participant_id in study_eligible else ["STUDY_INCLUSION_FAILED"]
            if not rules:
                rules = self._model_rules(model_id, participant_rows)
            eligible = not rules
            records.append(ModelEligibilityRecord(participant_id=participant_id, eligible=eligible, rule_ids=rules))
            if eligible:
                eligible_rows.extend(self._model_rows(model_id, participant_rows))
        participants = {
            row["participant_id"]: (row["group"], row["task_sequence"])
            for row in eligible_rows
        }
        group_counts = Counter(group for group, _ in participants.values())
        sequence_counts = Counter(f"{group}:{sequence}" for group, sequence in participants.values())
        task_period_counts = Counter(
            f"{row['task_id']}:{row['measurement_period']}" for row in eligible_rows
        )
        coverage = (
            all(group_counts[group] >= minimum_group_size for group in ("ai_scaffold", "static_prompt"))
            and all(
                sequence_counts[f"{group}:{sequence}"] >= minimum_group_sequence_size
                for group in ("ai_scaffold", "static_prompt")
                for sequence in ("AB", "BA")
            )
        )
        return ModelEligibilityManifest(
            manifest_id=f"model-eligibility-{model_id}-{uuid4().hex}",
            project_id=frozen_dataset.project_id,
            model_id=cast(Literal["primary_lmm", "transfer_ancova", "prompt_dependency_lmm"], model_id),
            source_frozen_dataset_ref=frozen_dataset.ref,
            source_dataset_sha256=frozen_dataset.canonical_content_sha256,
            participant_eligibility_manifest_ref=participant_manifest.ref,
            records=records,
            group_counts=dict(sorted(group_counts.items())),
            sequence_counts=dict(sorted(sequence_counts.items())),
            task_period_row_counts=dict(sorted(task_period_counts.items())),
            passed_minimum_coverage=coverage,
            minimum_group_size=minimum_group_size,
            minimum_group_sequence_size=minimum_group_sequence_size,
        )

    @staticmethod
    def _model_rows(model_id: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        if model_id == "transfer_ancova":
            return [row for row in rows if row["task_id"] == "C"]
        return [row for row in rows if row["task_id"] in {"A", "B"}]

    @staticmethod
    def _model_rules(model_id: str, rows: list[dict[str, str]]) -> list[str]:
        if model_id == "primary_lmm":
            values = [row["physics_modeling_score"] for row in rows if row["task_id"] in {"A", "B"}]
            return [] if len(values) == 2 and all(_finite(value) for value in values) else ["PRIMARY_OUTCOME_INCOMPLETE"]
        if model_id == "transfer_ancova":
            values = [row["transfer_score"] for row in rows if row["task_id"] == "C"]
            return [] if len(values) == 1 and _finite(values[0]) else ["TRANSFER_OUTCOME_INCOMPLETE"]
        values = [row[column] for row in rows if row["task_id"] in {"A", "B"} for column in PROMPT_COLUMNS]
        return [] if len(values) == 12 and all(_scale_1_to_5(value) for value in values) else ["PROMPT_DEPENDENCY_INCOMPLETE"]


def structural_gate(report: StructuralDataAuditReport) -> GateResult:
    return GateResult(
        gate_id="StructuralDataAuditGate",
        gate_version="v1.0",
        project_id=report.project_id,
        artifact_id=report.frozen_dataset_ref,
        decision=GateDecision.PASS if report.passed else GateDecision.REWORK,
        decision_scope=report.decision_scope,
        blocked_target_ids=report.blocked_target_ids,
        risk_flags=report.risk_flags,
        missing_fields=report.missing_columns,
        next_action="Evaluate model eligibility." if report.passed else "Repair the data artifact.",
        created_at=datetime.now(UTC),
    )


def _finite(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


def _scale_1_to_5(value: str) -> bool:
    return _finite(value) and 1.0 <= float(value) <= 5.0
