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
        project_roots = (
            (self.project_root / request.project_id).resolve(),
            (self.project_root / "uploads" / request.project_id).resolve(),
        )
        for path in request.input_paths:
            resolved = path.resolve()
            if not any(self._within(resolved, root) for root in project_roots):
                return PythonExecutionResult(status=SandboxStatus.BLOCKED, error_code="PROJECT_SCOPE_VIOLATION")
            if not path.is_file():
                return PythonExecutionResult(status=SandboxStatus.BLOCKED, error_code="INPUT_NOT_FOUND")
        with tempfile.TemporaryDirectory(prefix=f"stem-sci-{request.project_id}-") as temp:
            work = Path(temp)
            for source in request.input_paths:
                destination = work / source.name
                shutil.copyfile(source, destination)
            script_path = work / "run.py"
            script_path.write_text(self._runner_source(request.script), encoding="utf-8")
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
                if "PROJECT_SCOPE_VIOLATION" in stderr:
                    return PythonExecutionResult(
                        status=SandboxStatus.BLOCKED,
                        error_code="PROJECT_SCOPE_VIOLATION",
                        stdout=stdout,
                        stderr=stderr,
                    )
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
    def _within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    @staticmethod
    def _runner_source(script: str) -> str:
        """Install a filesystem/network audit hook before executing user code."""
        return f"""
import os as _os
import sys as _sys
from pathlib import Path as _Path

_WORK = _Path.cwd().resolve()
_TRUSTED = tuple(_Path(item).resolve() for item in (_sys.base_prefix, _sys.prefix))

def _under(path, root):
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True

def _read_only(mode, flags):
    if isinstance(mode, str):
        return not any(char in mode for char in "wax+")
    write_flags = _os.O_WRONLY | _os.O_RDWR | _os.O_APPEND | _os.O_CREAT | _os.O_TRUNC
    return not isinstance(flags, int) or not flags & write_flags

def _audit(event, args):
    if event == "open":
        target = args[0]
        if isinstance(target, int):
            return
        candidate = _Path(target)
        if not candidate.is_absolute():
            candidate = _WORK / candidate
        candidate = candidate.resolve()
        mode = args[1] if len(args) > 1 else "r"
        flags = args[2] if len(args) > 2 else 0
        if _under(candidate, _WORK):
            return
        if _read_only(mode, flags) and any(_under(candidate, root) for root in _TRUSTED):
            return
        raise PermissionError("PROJECT_SCOPE_VIOLATION")
    if event.startswith("socket.") or event in {{"subprocess.Popen", "os.system"}}:
        raise PermissionError("NETWORK_DISABLED")

_sys.addaudithook(_audit)
exec(compile({script!r}, "<stem-sci-analysis>", "exec"), {{"__name__": "__main__"}})
"""

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
        blocked_modules = {
            "socket", "urllib", "http", "requests", "ftplib", "subprocess", "importlib",
        }
        unsafe_modules = {"ctypes", "cffi", "multiprocessing", "mmap"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                if names & blocked_modules:
                    raise ValueError("NETWORK_DISABLED")
                if names & unsafe_modules:
                    raise ValueError("SCRIPT_UNSAFE")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in blocked_modules:
                raise ValueError("NETWORK_DISABLED")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in unsafe_modules:
                raise ValueError("SCRIPT_UNSAFE")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"__import__", "eval", "exec", "compile"}:
                raise ValueError("SCRIPT_UNSAFE")
