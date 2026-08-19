from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.analysis import data_freeze_request_builder, result_validation_checker


def test_result_validation_checker_blocks_unvalidated_result() -> None:
    result = result_validation_checker.execute(project_id="project-a", execution_ref="execution-1", validation_refs=[])
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "RESULT_NOT_VALIDATED"


def test_data_freeze_request_builder_is_candidate_only() -> None:
    result = data_freeze_request_builder.execute(project_id="project-a", dataset_ref="dataset-1")
    assert result.output_type == "DataFreezeRequest"
    assert not result.approved
