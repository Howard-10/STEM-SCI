from pathlib import Path

from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.analysis import PythonAnalysisSandboxTool
from stem_sci.tools.sandbox import PythonExecutionRequest, PythonSandbox


def test_python_analysis_sandbox_returns_candidate_execution(tmp_path: Path) -> None:
    request = PythonExecutionRequest(
        project_id="project-a",
        script='print("{\\\"estimate\\\": 1.5}")',
        input_paths=[],
        output_schema_ref="schema://AnalysisOutput",
    )
    result = PythonAnalysisSandboxTool(PythonSandbox(tmp_path)).execute(request)
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.value is not None
    assert result.value.output_type == "PythonExecutionCandidate"
    assert not result.value.approved


def test_python_analysis_sandbox_does_not_build_result_on_block(tmp_path: Path) -> None:
    request = PythonExecutionRequest(
        project_id="project-a",
        script="import socket; print('{}')",
        input_paths=[],
        output_schema_ref="schema://AnalysisOutput",
    )
    result = PythonAnalysisSandboxTool(PythonSandbox(tmp_path)).execute(request)
    assert result.status is ToolRunStatus.BLOCKED
    assert result.value is None
