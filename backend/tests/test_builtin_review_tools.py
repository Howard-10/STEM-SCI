from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.review import revision_request_builder


def test_revision_request_is_proposal_only() -> None:
    result = revision_request_builder.execute(project_id="project-a", findings=["finding-1"])
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.value["proposal_only"]
