"""Typed requests and bounded results for local Python execution."""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class SandboxStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class PythonExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1)
    script: str = Field(min_length=1, max_length=200_000)
    input_paths: list[Path] = Field(default_factory=list)
    output_schema_ref: str = Field(min_length=1)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    max_output_bytes: int = Field(default=1_000_000, gt=0, le=10_000_000)


class PythonExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: SandboxStatus
    json_output: dict[str, object] | None = None
    stdout: str = ""
    stderr: str = ""
    error_code: str | None = None
