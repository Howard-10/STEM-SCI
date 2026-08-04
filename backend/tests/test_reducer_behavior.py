from stem_sci.core.enums import TaskStatus
from stem_sci.core.reducers import merge_references
from stem_sci.core.state import ResearchState


def test_reducer_deduplicates_references_and_merges_status() -> None:
    state = ResearchState(project_id="reducer-demo")
    merged = merge_references(
        state,
        artifact_refs=["artifact://1", "artifact://1"],
        task_status={"planning": TaskStatus.DONE},
    )
    assert merged.artifact_refs == ["artifact://1"]
    assert merged.task_status["planning"] is TaskStatus.DONE
