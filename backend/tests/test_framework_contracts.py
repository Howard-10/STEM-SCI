from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stem_sci.artifacts.lineage_writer import InMemoryLineageWriter, LineageEdge
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.controller.approvals import ApprovalInterrupt, approval_idempotency_key
from stem_sci.controller.policy.rule_policy import RouteRule, RulePolicy
from stem_sci.core.events import EventType, ResearchEvent
from stem_sci.core.ledgers import LedgerEntry, append_ledger_entry
from stem_sci.statistics.models import (
    AnalysisPlan,
    ExecutionStatus,
    ResultValidationReport,
    StatisticalResultCard,
    ValidationMode,
)
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.utils.hash_utils import sha256_text
from stem_sci.utils.ids import new_id
from stem_sci.utils.validators import require_nonempty, require_reference
from stem_sci.verification.models import ResearchTestResult
from stem_sci.verification.rubric_registry import ResearchRubric, RubricRegistry
from stem_sci.verification.test_runner import ResearchTestRunner


def test_candidate_execution_contracts_are_reference_only() -> None:
    spec = CodeSpecification(
        specification_id="code-spec-1",
        language="python",
        entrypoint="analysis.main",
        input_refs=["dataset://raw/1"],
        output_types=["StatisticalResultCard"],
    )
    artifact = CodeArtifact(
        artifact_id="code-1",
        project_id="contracts-demo",
        specification_ref=spec.ref,
        content_uri="code://code-1",
        sha256="a" * 64,
        created_at=datetime.now(UTC),
    )
    plan = AnalysisPlan(
        plan_id="analysis-1",
        project_id="contracts-demo",
        mode="PYTHON_ONLY",
        primary_outcomes=["transfer_score"],
        model_spec_refs=["model://main"],
    )
    assert artifact.specification_ref == spec.ref
    assert plan.status == "candidate"


def test_statistics_and_verification_outputs_require_traceable_refs() -> None:
    result = StatisticalResultCard(
        result_id="result-1",
        project_id="contracts-demo",
        execution_run_ref="operator-run-1",
        analysis_plan_ref="analysis-1",
        validation_report_ref="validation-1",
        execution_status=ExecutionStatus.EXECUTION_VERIFIED,
        deterministic_parser_version="result-parser-v1",
        values={"estimate": 0.2},
    )
    report = ResultValidationReport(
        report_id="validation-1",
        project_id="contracts-demo",
        analysis_mode=AnalysisMode.PYTHON_ONLY,
        validation_mode=ValidationMode.SINGLE_ENGINE,
        execution_run_refs=["operator-run-1"],
        input_integrity_passed=True,
        model_integrity_passed=True,
        numeric_output_integrity_passed=True,
        passed=False,
        finding_refs=["finding://1"],
    )
    test_result = ResearchTestResult(
        test_result_id="test-1",
        project_id="contracts-demo",
        target_ref=result.ref,
        passed=False,
        status="blocked",
        message="Execution provider unavailable.",
        created_at=datetime.now(UTC),
    )
    assert report.execution_status is ExecutionStatus.GENERATED
    assert test_result.status == "blocked"


def test_events_ledgers_rules_and_approval_are_structured() -> None:
    event = ResearchEvent(
        event_id="event-1",
        project_id="contracts-demo",
        event_type=EventType.RISK_FLAGGED,
        subject_ref="project://contracts-demo",
        payload={"risk": "missing_evidence"},
        created_at=datetime.now(UTC),
    )
    ledger = append_ledger_entry([], LedgerEntry(entry_id="entry-1", message="started"))
    policy = RulePolicy([RouteRule(rule_id="risk", trigger="missing_evidence", target_agent="evidence_review")])
    interrupt = ApprovalInterrupt(
        request_id="approval-1", project_id="contracts-demo", scope="PROJECT", reason="review"
    )
    assert event.event_type is EventType.RISK_FLAGGED
    assert ledger[0].message == "started"
    assert policy.resolve("missing_evidence").target_agent == "evidence_review"
    assert approval_idempotency_key(interrupt, "approved") == "resume:approval-1:approved"


def test_rubric_registry_and_stable_utilities() -> None:
    registry = RubricRegistry()
    rubric = ResearchRubric(rubric_id="rubric-1", version="v1", criteria=["schema"])
    registry.register(rubric)
    assert registry.get("rubric-1", "v1") == rubric
    assert sha256_text("stem") == sha256_text("stem")
    assert new_id("event").startswith("event-")
    with pytest.raises(ValidationError):
        CodeSpecification(specification_id="bad", language="", entrypoint="x")


def test_lineage_validation_and_research_test_adapter_are_available() -> None:
    writer = InMemoryLineageWriter()
    edge = LineageEdge(source_ref="agent-run://1", target_ref="artifact://1", relation="produced")
    writer.put(edge)
    result = ResearchTestRunner().run(target_ref="artifact://1", rubric_ref="rubric://v1")
    assert writer.list_edges("artifact://1") == [edge]
    assert result.status == "blocked"
    assert require_nonempty("value", "field") == "value"
    assert require_reference("artifact://1", "artifact") == "artifact://1"
    with pytest.raises(ValueError):
        require_reference("wrong://1", "artifact")
