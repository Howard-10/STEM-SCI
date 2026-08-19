"""Restricted subprocess runner for local candidate analysis."""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .models import PythonExecutionRequest, PythonExecutionResult, SandboxStatus


class PythonSandbox:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def run(self, request: PythonExecutionRequest) -> PythonExecutionResult:
        try:
            self._validate_script(request.script)
        except ValueError as error:
            return PythonExecutionResult(status=SandboxStatus.BLOCKED, error_code=str(error))
        for path in request.input_paths:
            try:
                path.resolve().relative_to(self.project_root)
            except ValueError:
                return PythonExecutionResult(status=SandboxStatus.BLOCKED, error_code="PROJECT_SCOPE_VIOLATION")
            if not path.is_file():
                return PythonExecutionResult(status=SandboxStatus.BLOCKED, error_code="INPUT_NOT_FOUND")
        with tempfile.TemporaryDirectory(prefix=f"stem-sci-{request.project_id}-") as temp:
            work = Path(temp)
            for source in request.input_paths:
                destination = work / source.name
                shutil.copyfile(source, destination)
            script_path = work / "run.py"
            script_path.write_text(request.script, encoding="utf-8")
            env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONNOUSERSITE": "1",
            }
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", str(script_path)],
                    cwd=work,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=request.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                return PythonExecutionResult(status=SandboxStatus.TIMED_OUT, error_code="TIMEOUT", stdout=self._text(error.stdout))
            stdout = completed.stdout[: request.max_output_bytes]
            stderr = completed.stderr[: request.max_output_bytes]
            if completed.returncode != 0:
                if "NETWORK_DISABLED" in stderr:
                    return PythonExecutionResult(status=SandboxStatus.BLOCKED, error_code="NETWORK_DISABLED", stdout=stdout, stderr=stderr)
                return PythonExecutionResult(status=SandboxStatus.FAILED, error_code="EXECUTION_FAILED", stdout=stdout, stderr=stderr)
            try:
                value = json.loads(stdout.strip())
            except json.JSONDecodeError:
                return PythonExecutionResult(status=SandboxStatus.FAILED, error_code="OUTPUT_NOT_JSON", stdout=stdout, stderr=stderr)
            if not isinstance(value, dict):
                return PythonExecutionResult(status=SandboxStatus.FAILED, error_code="OUTPUT_SCHEMA_INVALID", stdout=stdout, stderr=stderr)
            return PythonExecutionResult(status=SandboxStatus.SUCCEEDED, json_output=value, stdout=stdout, stderr=stderr)

    @staticmethod
    def _text(value: bytes | str | None) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value or ""

    @staticmethod
    def _validate_script(script: str) -> None:
        try:
            tree = ast.parse(script)
        except SyntaxError as error:
            raise ValueError("SCRIPT_INVALID") from error
        blocked_modules = {"socket", "urllib", "http", "requests", "ftplib", "subprocess"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                if names & blocked_modules:
                    raise ValueError("NETWORK_DISABLED")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in blocked_modules:
                raise ValueError("NETWORK_DISABLED")

