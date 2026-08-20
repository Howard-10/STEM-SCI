"""Static review gate for generated research-analysis code."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from stem_sci.coding.compiler import CodeSpecificationCompiler
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.core.enums import DecisionScope, GateDecision
from stem_sci.core.models import DomainModel, GateResult
from stem_sci.utils.hash_utils import sha256_bytes


class CodeReviewResult(DomainModel):
    """Review record consumed by the Controller before a sandbox run."""

    review_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    code_artifact_ref: str = Field(min_length=1)
    passed: bool
    requires_human_approval: bool
    finding_codes: list[str] = Field(default_factory=list)
    gate_result: GateResult

    @property
    def ref(self) -> str:
        return f"code-review://{self.review_id}"


class CodeReviewGate:
    """Validate provenance and a deliberately small safe-Python subset.

    Static review is a gate, not a sandbox.  Non-template Codex output is
    therefore conservatively sent to ``WAITING_HUMAN`` even if it is free of
    known prohibited constructs.  Only the inspected deterministic MVP
    template can pass automatically.
    """

    gate_id = "CodeReviewGate"
    gate_version = "research-code-v1"
    _allowed_imports = frozenset({"csv", "hashlib", "json", "math", "statistics", "sys"})
    _forbidden_names = frozenset(
        {
            "__import__",
            "compile",
            "eval",
            "exec",
            "getattr",
            "globals",
            "input",
            "locals",
            "open",
            "setattr",
            "system",
        }
    )
    _forbidden_imports = frozenset(
        {
            "asyncio",
            "ctypes",
            "http",
            "multiprocessing",
            "os",
            "pathlib",
            "requests",
            "shutil",
            "socket",
            "subprocess",
            "urllib",
        }
    )

    def review(
        self,
        *,
        review_id: str,
        specification: CodeSpecification,
        artifact: CodeArtifact,
    ) -> CodeReviewResult:
        findings: list[str] = []
        if specification.purpose != "research_analysis":
            findings.append("SPECIFICATION_NOT_RESEARCH_ANALYSIS")
        if specification.project_id != artifact.project_id:
            findings.append("PROJECT_SCOPE_MISMATCH")
        if artifact.specification_ref != specification.ref:
            findings.append("SPECIFICATION_REFERENCE_MISMATCH")
        if artifact.language.lower() != specification.language.lower():
            findings.append("LANGUAGE_MISMATCH")
        if artifact.source_specification_sha256 != CodeSpecificationCompiler.fingerprint(specification):
            findings.append("SPECIFICATION_FINGERPRINT_MISMATCH")

        content = self._read_verified_content(artifact, findings)
        if content:
            # A comment is never a trust boundary.  Only the Controller-owned
            # deterministic provider may use ``open`` for its fixed argv input
            # and output paths. Any Codex candidate remains subject to the
            # generic no-file-access rule, regardless of source comments.
            controller_template = (
                artifact.provider_id == "deterministic_research_template"
                and artifact.provider_version == "v1"
            )
            codex_candidate = artifact.provider_id == "codex_cli"
            findings.extend(
                self._static_findings(
                    content,
                    allow_open=controller_template or codex_candidate,
                    require_controlled_open=codex_candidate,
                )
            )

        blocking = bool(findings)
        requires_human = not blocking and artifact.provider_id != "deterministic_research_template"
        decision = (
            GateDecision.BLOCKED
            if blocking
            else GateDecision.WAITING_HUMAN
            if requires_human
            else GateDecision.PASS
        )
        gate = GateResult(
            gate_id=self.gate_id,
            gate_version=self.gate_version,
            project_id=artifact.project_id,
            artifact_id=artifact.artifact_id,
            decision=decision,
            decision_scope=DecisionScope.ARTIFACT,
            blocked_target_ids=[artifact.ref] if blocking else [],
            risk_flags=findings,
            next_action=(
                "Reject or regenerate the code artifact."
                if blocking
                else "Obtain human approval before executing non-template generated code."
                if requires_human
                else "Allow the Controller to submit the artifact to ResearchCodeSandbox."
            ),
            created_at=datetime.now(UTC),
        )
        return CodeReviewResult(
            review_id=review_id,
            project_id=artifact.project_id,
            code_artifact_ref=artifact.ref,
            passed=not blocking,
            requires_human_approval=requires_human,
            finding_codes=findings,
            gate_result=gate,
        )

    @staticmethod
    def _read_verified_content(artifact: CodeArtifact, findings: list[str]) -> str:
        path = Path(artifact.content_uri)
        try:
            content = path.read_bytes()
        except OSError:
            findings.append("CODE_ARTIFACT_UNAVAILABLE")
            return ""
        if sha256_bytes(content) != artifact.sha256:
            findings.append("CODE_ARTIFACT_HASH_MISMATCH")
            return ""
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            findings.append("CODE_ARTIFACT_NOT_UTF8")
            return ""

    def _static_findings(
        self,
        source: str,
        *,
        allow_open: bool = False,
        require_controlled_open: bool = False,
    ) -> list[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ["PYTHON_SYNTAX_INVALID"]
        findings: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", maxsplit=1)[0]
                    if root not in self._allowed_imports or root in self._forbidden_imports:
                        findings.add("PROHIBITED_IMPORT")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".", maxsplit=1)[0]
                if root not in self._allowed_imports or root in self._forbidden_imports:
                    findings.add("PROHIBITED_IMPORT")
            elif isinstance(node, ast.Name) and node.id in self._forbidden_names:
                if node.id != "open" or not allow_open:
                    findings.add("PROHIBITED_OPERATION")
            elif require_controlled_open and isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "open" and not self._is_controlled_open(node):
                    findings.add("UNCONTROLLED_FILE_ACCESS")
            elif isinstance(node, ast.Attribute) and node.attr in {"system", "popen", "run"}:
                findings.add("PROHIBITED_OPERATION")
        return sorted(findings)

    @staticmethod
    def _is_controlled_open(node: ast.Call) -> bool:
        """Allow Codex candidates to use only the two sandbox argv paths."""
        if not node.args or len(node.args) > 3:
            return False
        path = node.args[0]
        if not (
            isinstance(path, ast.Subscript)
            and isinstance(path.value, ast.Attribute)
            and isinstance(path.value.value, ast.Name)
            and path.value.value.id == "sys"
            and path.value.attr == "argv"
            and isinstance(path.slice, ast.Constant)
            and path.slice.value in {1, 2}
        ):
            return False
        if len(node.args) >= 2 and not (
            isinstance(node.args[1], ast.Constant)
            and node.args[1].value in {"r", "rb", "w", "wb"}
        ):
            return False
        allowed_keywords = {"encoding", "newline", "errors"}
        return all(
            keyword.arg in allowed_keywords
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
            for keyword in node.keywords
        )
