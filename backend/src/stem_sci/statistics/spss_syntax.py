"""Deterministic SPSS syntax preparation for the CSV dual-engine MVP.

This produces a reviewable ``CodeArtifact``; it does not run IBM SPSS.  The
separate adapter owns batch execution and only receives an already reviewed
syntax artifact.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from uuid import uuid4

from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.providers import CodeArtifactStore, CodeGenerationRequest
from stem_sci.research_data.models import FrozenDatasetRef
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import AnalysisModelSpecification, ExecutableAnalysisPlan


class SpssSyntaxSpecificationCompiler:
    """Compile a dual-engine plan into a schema-bound SPSS syntax contract."""

    compiler_version = "spss-syntax-spec-v1"

    def compile(
        self,
        *,
        specification_id: str,
        executable_plan: ExecutableAnalysisPlan,
        frozen_dataset: FrozenDatasetRef,
        model_specification: AnalysisModelSpecification,
    ) -> CodeSpecification:
        if executable_plan.analysis_mode is not AnalysisMode.SPSS_PYTHON_DUAL:
            raise ValueError("SPSS syntax compilation requires an SPSS_PYTHON_DUAL plan")
        if executable_plan.project_id != frozen_dataset.project_id:
            raise ValueError("executable plan project does not match frozen dataset")
        if model_specification.project_id != frozen_dataset.project_id:
            raise ValueError("model specification project does not match frozen dataset")
        if executable_plan.frozen_dataset_ref != frozen_dataset.ref:
            raise ValueError("executable plan references a different frozen dataset")
        if executable_plan.frozen_dataset_sha256 != frozen_dataset.sha256:
            raise ValueError("executable plan frozen-dataset hash does not match")
        if model_specification.model_family != "group_mean_difference":
            raise ValueError("the SPSS MVP template supports group_mean_difference only")
        columns = self._read_csv_columns(frozen_dataset)
        outcome = model_specification.outcome_variables[0]
        group = next(
            iter(model_specification.grouping_variables or model_specification.predictor_variables),
            None,
        )
        if group is None or outcome not in columns or group not in columns:
            raise ValueError("SPSS template requires approved group and outcome columns")
        return CodeSpecification(
            specification_id=specification_id,
            language="spss",
            entrypoint="analysis.sps",
            purpose="research_analysis",
            project_id=frozen_dataset.project_id,
            executable_plan_ref=f"executable-plan://{executable_plan.executable_plan_id}",
            frozen_dataset_ref=frozen_dataset.ref,
            frozen_dataset_sha256=frozen_dataset.sha256,
            model_specification_ref=f"model-spec://{model_specification.model_spec_id}",
            approved_variable_names=columns,
            analysis_parameters={
                "model_family": model_specification.model_family,
                "outcome_variable": outcome,
                "group_variable": group,
                "dataset_columns": "|".join(columns),
            },
            execution_policy_ref="sandbox-policy://spss-batch/v1",
            input_refs=[frozen_dataset.ref, f"executable-plan://{executable_plan.executable_plan_id}"],
            output_types=["ExecutionRun", "spss_aggregate.csv"],
            dependency_refs=["spss://statistics/batch"],
            random_seed=0,
        )

    @staticmethod
    def _read_csv_columns(frozen_dataset: FrozenDatasetRef) -> list[str]:
        with Path(frozen_dataset.content_uri).open("r", encoding="utf-8", newline="") as source:
            columns = next(csv.reader(source), [])
        if not columns or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", column) for column in columns):
            raise ValueError("SPSS MVP requires simple CSV column identifiers")
        return columns


class SpssSyntaxTemplateProvider:
    """Generate fixed, reviewable SPSS syntax from an approved specification."""

    provider_id = "deterministic_spss_template"
    provider_version = "v1"

    def __init__(self, artifact_store: CodeArtifactStore) -> None:
        self.artifact_store = artifact_store

    def generate(self, request: CodeGenerationRequest) -> CodeArtifact:
        request.validate_project_scope()
        specification = request.specification
        if specification.language.lower() != "spss":
            raise ValueError("SPSS template provider requires an SPSS specification")
        if specification.analysis_parameters.get("model_family") != "group_mean_difference":
            raise ValueError("SPSS template provider supports group_mean_difference only")
        return self.artifact_store.put(
            project_id=request.project_id,
            specification=specification,
            content=self._render(specification),
            language="spss",
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            artifact_id=f"spss-code-{uuid4().hex}",
        )

    @staticmethod
    def _render(specification: CodeSpecification) -> str:
        columns = specification.analysis_parameters["dataset_columns"].split("|")
        outcome = specification.analysis_parameters["outcome_variable"]
        group = specification.analysis_parameters["group_variable"]
        task_filter = 'SELECT IF RTRIM(task_id) = "C".\n' if "task_id" in columns else ""
        declarations = "\n  ".join(
            f"{column} {'F16.8' if column == outcome else 'A256'}" for column in columns
        )
        return f"""* STEM_SCI_REVIEWED_SPSS_TEMPLATE_V1.
* Controller materializes only these two placeholders inside the run directory.
GET DATA
  /TYPE=TXT
  /FILE='{{{{FROZEN_DATASET_PATH}}}}'
  /ENCODING='UTF8'
  /DELCASE=LINE
  /DELIMITERS=\",\"
  /ARRANGEMENT=DELIMITED
  /FIRSTCASE=2
  /VARIABLES=
  {declarations}.
DATASET NAME ResearchData WINDOW=FRONT.
{task_filter}AGGREGATE
  /OUTFILE=* MODE=ADDVARIABLES
  /BREAK={group}
  /n=N({outcome})
  /mean=MEAN({outcome})
  /sd=SD({outcome}).
SORT CASES BY {group}.
MATCH FILES /FILE=* /BY {group} /FIRST=first_group.
SELECT IF first_group=1.
SAVE TRANSLATE OUTFILE='{{{{RESULT_CSV_PATH}}}}'
  /TYPE=CSV
  /REPLACE
  /FIELDNAMES.
EXECUTE.
"""
