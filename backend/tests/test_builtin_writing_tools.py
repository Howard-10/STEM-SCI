from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.writing import manuscript_renderer_en


def test_manuscript_renderer_returns_candidate_without_approval() -> None:
    result = manuscript_renderer_en.execute(project_id="project-a", graph_ref="graph-1", outline_ref="outline-1")
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.value["candidate"]
    assert "approved" not in result.value
