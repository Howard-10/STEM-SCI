from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.research_design import estimand_validator, protocol_schema_validator


def test_estimand_validator_rejects_missing_outcome() -> None:
    result = estimand_validator.execute(project_id="project-a", payload={"exposure": "x"})
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "INVALID_ESTIMAND"


def test_protocol_schema_validator_is_candidate_report_only() -> None:
    result = protocol_schema_validator.execute(project_id="project-a", protocol={"name": "draft"})
    assert result.output_type == "StudyProtocolValidationReport"
    assert not result.approved
