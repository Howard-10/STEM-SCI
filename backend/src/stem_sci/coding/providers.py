"""Controlled coding providers for research-analysis code artifacts.

The providers in this module never execute the code they produce.  They only
write a hashed candidate artifact.  A separate deterministic review gate and
research-code sandbox are required before an artifact can reach an execution
operator.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import Field

from stem_sci.coding.compiler import CodeSpecificationCompiler
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.core.models import DomainModel
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


class CodingProviderUnavailable(RuntimeError):
    """Raised when a configured coding provider is not safely callable."""


class CodeGenerationRequest(DomainModel):
    """A fully compiled request; it intentionally contains no dataset rows."""

    project_id: str = Field(min_length=1)
    specification: CodeSpecification

    def validate_project_scope(self) -> None:
        if self.specification.purpose != "research_analysis":
            raise ValueError("research coding providers accept research_analysis specifications only")
        if self.specification.project_id != self.project_id:
            raise ValueError("code specification project does not match generation request")


class CodingProvider(Protocol):
    provider_id: str
    provider_version: str

    def generate(self, request: CodeGenerationRequest) -> CodeArtifact: ...


class CodeArtifactStore:
    """Append-only local artifact storage for code, outside workflow state."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(
        self,
        *,
        project_id: str,
        specification: CodeSpecification,
        content: str,
        language: str,
        provider_id: str,
        provider_version: str,
        artifact_id: str | None = None,
    ) -> CodeArtifact:
        safe_entrypoint = Path(specification.entrypoint).name
        if safe_entrypoint != specification.entrypoint or not safe_entrypoint:
            raise ValueError("code specification entrypoint must be a safe filename")
        identifier = artifact_id or f"code-{uuid4().hex}"
        project_directory = self.root / sha256_text(project_id)[:16] / identifier
        project_directory.mkdir(parents=True, exist_ok=False)
        content_bytes = content.encode("utf-8")
        code_path = project_directory / safe_entrypoint
        code_path.write_bytes(content_bytes)
        return CodeArtifact(
            artifact_id=identifier,
            project_id=project_id,
            specification_ref=specification.ref,
            content_uri=str(code_path),
            sha256=sha256_bytes(content_bytes),
            created_at=datetime.now(UTC),
            language=language,
            provider_id=provider_id,
            provider_version=provider_version,
            source_specification_sha256=CodeSpecificationCompiler.fingerprint(specification),
        )


class DeterministicTemplateCodingProvider:
    """Generate the auditable Python template used by the first execution MVP.

    It is intentionally *not* a substitute for Codex.  It gives development
    and CI a reproducible baseline while Codex is unavailable, and makes it
    possible to verify the code-review and sandbox path without granting a
    language model authority over statistical choices.
    """

    provider_id = "deterministic_research_template"
    provider_version = "v1"

    def __init__(self, artifact_store: CodeArtifactStore) -> None:
        self.artifact_store = artifact_store

    def generate(self, request: CodeGenerationRequest) -> CodeArtifact:
        request.validate_project_scope()
        specification = request.specification
        if specification.language.lower() != "python":
            raise ValueError("the deterministic MVP provider supports Python only")
        if specification.analysis_parameters.get("model_family") != "group_mean_difference":
            raise ValueError("the deterministic MVP provider supports group_mean_difference only")
        return self.artifact_store.put(
            project_id=request.project_id,
            specification=specification,
            content=self._render(specification),
            language="python",
            provider_id=self.provider_id,
            provider_version=self.provider_version,
        )

    @staticmethod
    def _render(specification: CodeSpecification) -> str:
        outcome = specification.analysis_parameters["outcome_variable"]
        group = specification.analysis_parameters["group_variable"]
        expected_hash = specification.frozen_dataset_sha256
        return f'''# STEM_SCI_REVIEWED_TEMPLATE_V1
"""Deterministic two-group descriptive comparison generated from CodeSpecification."""
import csv
import hashlib
import json
import math
import statistics
import sys

EXPECTED_DATASET_SHA256 = "{expected_hash}"
GROUP_COLUMN = "{group}"
OUTCOME_COLUMN = "{outcome}"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: analysis.py FROZEN_DATASET OUTPUT_JSON")
    dataset_path, output_path = sys.argv[1], sys.argv[2]
    with open(dataset_path, "rb") as source:
        if hashlib.sha256(source.read()).hexdigest() != EXPECTED_DATASET_SHA256:
            raise ValueError("frozen dataset hash mismatch")
    groups: dict[str, list[float]] = {{}}
    with open(dataset_path, "r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not {{GROUP_COLUMN, OUTCOME_COLUMN}}.issubset(reader.fieldnames):
            raise ValueError("approved analysis columns are unavailable")
        for row in reader:
            if "task_id" in reader.fieldnames and (row.get("task_id") or "").strip() not in {{"C"}}:
                continue
            group = (row.get(GROUP_COLUMN) or "").strip()
            value = float(row.get(OUTCOME_COLUMN) or "")
            if not group or not math.isfinite(value):
                raise ValueError("group and outcome values must be finite and non-empty")
            groups.setdefault(group, []).append(value)
    if len(groups) != 2:
        raise ValueError("group_mean_difference requires exactly two groups")
    first_group, second_group = sorted(groups)
    first, second = groups[first_group], groups[second_group]
    first_mean, second_mean = statistics.fmean(first), statistics.fmean(second)
    payload = {{
        "parser_version": "research-python-result-v1",
        "model_family": "group_mean_difference",
        "frozen_dataset_sha256": EXPECTED_DATASET_SHA256,
        "group_labels": [first_group, second_group],
        "values": {{
            "analysis_sample_size": float(len(first) + len(second)),
            "group_1_n": float(len(first)),
            "group_1_transfer_mean": first_mean,
            "group_1_transfer_sd": statistics.stdev(first) if len(first) > 1 else 0.0,
            "group_2_n": float(len(second)),
            "group_2_transfer_mean": second_mean,
            "group_2_transfer_sd": statistics.stdev(second) if len(second) > 1 else 0.0,
            "transfer_mean_difference_group_2_minus_group_1": second_mean - first_mean,
        }},
    }}
    with open(output_path, "w", encoding="utf-8", newline="") as destination:
        json.dump(payload, destination, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    main()
'''


class DeterministicStatsmodelsTemplateProvider:
    """Persist the fixed v1.0 template identity for deterministic execution.

    The executable implementation is the Controller-owned
    ``DeterministicStatsmodelsExecutor``. This short source artifact is an
    auditable, hashed declaration of the approved template, not LLM-generated
    statistics code and not a second source of analytical decisions.
    """

    provider_id = "deterministic_research_template"
    provider_version = "v1"

    def __init__(self, artifact_store: CodeArtifactStore) -> None:
        self.artifact_store = artifact_store

    def generate(self, request: CodeGenerationRequest) -> CodeArtifact:
        request.validate_project_scope()
        specification = request.specification
        if specification.analysis_parameters.get("requires_analysis_dataset") != "true":
            raise ValueError("v1 deterministic template requires an AnalysisDataset")
        model_family = specification.analysis_parameters.get("model_family", "")
        if model_family not in CodeSpecificationCompiler.supported_v1_model_families:
            raise ValueError("unsupported deterministic statsmodels template")
        source = (
            "# STEM_SCI_DETERMINISTIC_STATSMODELS_TEMPLATE_V1\n"
            '"""Identity declaration executed only by the Controller-owned statsmodels executor."""\n'
            f'MODEL_FAMILY = "{model_family}"\n'
            f'CODE_SPECIFICATION_FINGERPRINT = "{CodeSpecificationCompiler.fingerprint(specification)}"\n'
            f'EXECUTOR_IMPLEMENTATION_SHA256 = "{specification.deterministic_template_sha256}"\n'
        )
        return self.artifact_store.put(
            project_id=request.project_id,
            specification=specification,
            content=source,
            language="python",
            provider_id=self.provider_id,
            provider_version=self.provider_version,
        )


class CodexCliCodingProvider:
    """Optional, fail-closed adapter for ``codex exec``.

    The CLI is invoked in read-only mode and receives only a compiled code
    specification, never participant data.  Its response remains a candidate
    that must pass ``CodeReviewGate`` and a human approval before execution.
    ``CodingProviderUnavailable`` is expected on machines without a usable,
    authenticated Codex CLI.
    """

    provider_id = "codex_cli"
    provider_version = "v1"

    def __init__(
        self,
        artifact_store: CodeArtifactStore,
        *,
        command: str | None = None,
        timeout_seconds: int = 90,
    ) -> None:
        self.artifact_store = artifact_store
        self.command = command or os.environ.get("STEM_SCI_CODEX_COMMAND", "codex")
        self.timeout_seconds = timeout_seconds

    def health_reason(self) -> str | None:
        resolved = self._resolve_command()
        if resolved is None:
            return "CODEX_CLI_NOT_FOUND"
        normalized = str(resolved).replace("\\", "/").lower()
        if "/windowsapps/" in normalized and normalized.endswith("/resources/codex.exe"):
            return "CODEX_DESKTOP_BINARY_NOT_CLI"
        try:
            completed = subprocess.run(
                self._command_args(resolved, ["--version"]),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except PermissionError:
            return "CODEX_CLI_ACCESS_DENIED"
        except (OSError, subprocess.TimeoutExpired):
            return "CODEX_CLI_NOT_EXECUTABLE"
        return None if completed.returncode == 0 else "CODEX_CLI_UNAVAILABLE_OR_UNAUTHENTICATED"

    def _resolve_command(self) -> str | None:
        """Resolve npm's CLI before accepting Codex Desktop's internal binary."""
        resolved = shutil.which(self.command)
        if resolved is not None:
            normalized = resolved.replace("\\", "/").lower()
            if not ("/windowsapps/" in normalized and normalized.endswith("/resources/codex.exe")):
                return resolved
        appdata = os.environ.get("APPDATA")
        if appdata:
            for name in ("codex.cmd", "codex.exe", "codex"):
                candidate = Path(appdata) / "npm" / name
                if candidate.is_file():
                    return str(candidate)
        return resolved

    @staticmethod
    def _command_args(resolved: str, args: list[str]) -> list[str]:
        if Path(resolved).suffix.lower() in {".cmd", ".bat"}:
            return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", resolved, *args]
        return [resolved, *args]

    def generate(self, request: CodeGenerationRequest) -> CodeArtifact:
        request.validate_project_scope()
        if request.specification.language.lower() != "python":
            raise ValueError("Codex MVP provider supports Python artifacts only")
        health_reason = self.health_reason()
        if health_reason is not None:
            raise CodingProviderUnavailable(health_reason)
        resolved = self._resolve_command()
        if resolved is None:  # Narrow the type after the health check for mypy.
            raise CodingProviderUnavailable("CODEX_CLI_NOT_FOUND")
        prompt = self._prompt(request.specification)
        try:
            completed = subprocess.run(
                self._command_args(
                    resolved,
                    [
                        "exec",
                        "--sandbox",
                        "read-only",
                        "--ask-for-approval",
                        "never",
                        prompt,
                    ],
                ),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodingProviderUnavailable("CODEX_CLI_EXECUTION_FAILED") from exc
        if completed.returncode != 0:
            raise CodingProviderUnavailable("CODEX_CLI_GENERATION_FAILED")
        code = self._extract_python(completed.stdout)
        if not code:
            raise CodingProviderUnavailable("CODEX_CLI_RETURNED_NO_PYTHON")
        return self.artifact_store.put(
            project_id=request.project_id,
            specification=request.specification,
            content=code,
            language="python",
            provider_id=self.provider_id,
            provider_version=self.provider_version,
        )

    @staticmethod
    def _prompt(specification: CodeSpecification) -> str:
        return (
            "Return Python source code only, with no Markdown fences. "
            "The first line must be # STEM_SCI_REVIEWED_TEMPLATE_V1. "
            "Do not execute code, access the network, use subprocess, install packages, "
            "or read any file except the dataset path passed as argv[1]. "
            "Write only the JSON path passed as argv[2]. "
            "The code must calculate exactly this approved configuration: "
            f"{specification.model_dump_json(exclude_none=True)}"
        )

    @staticmethod
    def _extract_python(output: str) -> str:
        stripped = output.strip()
        if stripped.startswith("```python") and stripped.endswith("```"):
            return stripped.removeprefix("```python").removesuffix("```").strip()
        return stripped if stripped.startswith("import ") or stripped.startswith("#") else ""
