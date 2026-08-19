from pathlib import Path

from stem_sci.tools.sandbox import (
    PythonExecutionRequest,
    PythonSandbox,
    SandboxStatus,
)


def _request(script: str) -> PythonExecutionRequest:
    return PythonExecutionRequest(
        project_id="project-a",
        script=script,
        input_paths=[],
        output_schema_ref="schema://AnalysisOutput",
    )


def test_sandbox_runs_allowlisted_python_and_returns_json(tmp_path: Path) -> None:
    sandbox = PythonSandbox(tmp_path)
    result = sandbox.run(_request('print("{\\\"value\\\": 2}")'))
    assert result.status is SandboxStatus.SUCCEEDED
    assert result.json_output == {"value": 2}


def test_sandbox_rejects_network_access(tmp_path: Path) -> None:
    sandbox = PythonSandbox(tmp_path)
    result = sandbox.run(
        _request("import urllib.request; urllib.request.urlopen('https://example.com')")
    )
    assert result.status is SandboxStatus.BLOCKED
    assert result.error_code == "NETWORK_DISABLED"


def test_sandbox_does_not_expose_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STEM_SCI_LLM_API_KEY", "secret-sentinel")
    result = PythonSandbox(tmp_path).run(
        _request("import os, json; print(json.dumps({'key': os.getenv('STEM_SCI_LLM_API_KEY')}))")
    )
    assert "secret-sentinel" not in result.stdout
    assert result.json_output == {"key": None}


def test_sandbox_rejects_input_outside_project(tmp_path: Path) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("x", encoding="utf-8")
    result = PythonSandbox(tmp_path / "projects").run(
        _request("print('{}')").model_copy(update={"input_paths": [outside]})
    )
    assert result.status is SandboxStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_sandbox_rejects_input_owned_by_another_project(tmp_path: Path) -> None:
    other_project = tmp_path / "uploads" / "project-b"
    other_project.mkdir(parents=True)
    secret = other_project / "secret.csv"
    secret.write_text("secret-sentinel", encoding="utf-8")

    result = PythonSandbox(tmp_path).run(
        _request("print('{}')").model_copy(update={"input_paths": [secret]})
    )

    assert result.status is SandboxStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_sandbox_blocks_script_read_of_undeclared_host_file(tmp_path: Path) -> None:
    other_project = tmp_path / "uploads" / "project-b"
    other_project.mkdir(parents=True)
    secret = other_project / "secret.txt"
    secret.write_text("secret-sentinel", encoding="utf-8")
    script = (
        "import json\n"
        f"value = open({str(secret)!r}, encoding='utf-8').read()\n"
        "print(json.dumps({'value': value}))"
    )

    result = PythonSandbox(tmp_path).run(_request(script))

    assert result.status is SandboxStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"
    assert "secret-sentinel" not in result.stdout
