"""Controller-owned compilation of approved analysis plans into code specs."""

from __future__ import annotations

from pathlib import Path

from stem_sci.coding.models import CodeSpecification
from stem_sci.research_data.canonical import read_csv_rows
from stem_sci.research_data.models import AnalysisDatasetRef, FrozenDatasetRef
from stem_sci.statistics.models import AnalysisModelSpecification, ExecutableAnalysisPlan
from stem_sci.utils.hash_utils import sha256_text


class CodeSpecificationCompiler:
    """Compile a schema-bound plan without making substantive decisions.

    This compiler has no LLM dependency.  It validates that the already
    approved executable plan, model specification and frozen dataset refer to
    the same project and exact data hash, then expresses those approved facts
    as a narrow code-generation contract.
    """

    compiler_version = "research-code-spec-v1"
    supported_model_families = frozenset({"group_mean_difference"})
    supported_v1_model_families = frozenset(
        {
            "linear_mixed_effects_primary",
            "linear_mixed_effects_prompt_dependency",
            "ols_ancova_transfer",
        }
    )

    def compile_python(
        self,
        *,
        specification_id: str,
        executable_plan: ExecutableAnalysisPlan,
        frozen_dataset: FrozenDatasetRef,
        model_specification: AnalysisModelSpecification,
    ) -> CodeSpecification:
        if executable_plan.project_id != frozen_dataset.project_id:
            raise ValueError("executable plan project does not match frozen dataset")
        if model_specification.project_id != frozen_dataset.project_id:
            raise ValueError("model specification project does not match frozen dataset")
        if executable_plan.frozen_dataset_ref != frozen_dataset.ref:
            raise ValueError("executable plan references a different frozen dataset")
        if executable_plan.frozen_dataset_sha256 != frozen_dataset.sha256:
            raise ValueError("executable plan frozen-dataset hash does not match")
        if model_specification.model_family not in self.supported_model_families:
            raise ValueError("no deterministic Python template supports the requested model family")

        outcome_variable = model_specification.outcome_variables[0]
        group_variable = next(
            iter(model_specification.grouping_variables or model_specification.predictor_variables),
            None,
        )
        if group_variable is None:
            raise ValueError("group_mean_difference requires a grouping or predictor variable")

        approved_variables = sorted(
            {
                *model_specification.outcome_variables,
                *model_specification.predictor_variables,
                *model_specification.grouping_variables,
                *executable_plan.variable_mapping.values(),
            }
        )
        if not approved_variables:
            raise ValueError("model specification must identify at least one approved variable")
        return CodeSpecification(
            specification_id=specification_id,
            language="python",
            entrypoint="analysis.py",
            purpose="research_analysis",
            project_id=frozen_dataset.project_id,
            executable_plan_ref=f"executable-plan://{executable_plan.executable_plan_id}",
            frozen_dataset_ref=frozen_dataset.ref,
            frozen_dataset_sha256=frozen_dataset.sha256,
            model_specification_ref=f"model-spec://{model_specification.model_spec_id}",
            approved_variable_names=approved_variables,
            analysis_parameters={
                "model_family": model_specification.model_family,
                "outcome_variable": outcome_variable,
                "group_variable": group_variable,
            },
            execution_policy_ref="sandbox-policy://research-code/v1",
            input_refs=[frozen_dataset.ref, f"executable-plan://{executable_plan.executable_plan_id}"],
            output_types=["ExecutionRun", "result.json"],
            dependency_refs=["python-stdlib://csv", "python-stdlib://json"],
            random_seed=0,
        )

    def compile_v1_statsmodels(
        self,
        *,
        specification_id: str,
        executable_plan: ExecutableAnalysisPlan,
        frozen_dataset: FrozenDatasetRef,
        analysis_dataset: AnalysisDatasetRef,
        model_specification: AnalysisModelSpecification,
    ) -> CodeSpecification:
        """Compile the immutable v1.0 execution contract without an LLM.

        The Controller may compile only variable mapping, exact hashes, and
        explicitly preregistered execution settings.  It cannot select a
        different model or alter the model-specific AnalysisDataset.
        """

        if executable_plan.project_id != frozen_dataset.project_id:
            raise ValueError("executable plan project does not match frozen dataset")
        if analysis_dataset.project_id != frozen_dataset.project_id:
            raise ValueError("analysis dataset project does not match frozen dataset")
        if model_specification.project_id != frozen_dataset.project_id:
            raise ValueError("model specification project does not match frozen dataset")
        if executable_plan.frozen_dataset_ref != frozen_dataset.ref:
            raise ValueError("executable plan references a different frozen dataset")
        if executable_plan.frozen_dataset_sha256 != frozen_dataset.canonical_content_sha256:
            raise ValueError("executable plan frozen-dataset canonical hash does not match")
        if analysis_dataset.source_frozen_dataset_ref != frozen_dataset.ref:
            raise ValueError("analysis dataset references a different frozen dataset")
        if analysis_dataset.source_dataset_sha256 != frozen_dataset.canonical_content_sha256:
            raise ValueError("analysis dataset frozen-dataset canonical hash does not match")
        if model_specification.model_family not in self.supported_v1_model_families:
            raise ValueError("no deterministic v1 executor supports the requested model family")
        header, _ = read_csv_rows(Path(analysis_dataset.content_uri).read_bytes())
        approved_variables = sorted(
            {
                *model_specification.outcome_variables,
                *model_specification.predictor_variables,
                *model_specification.grouping_variables,
            }
        )
        missing = sorted(set(approved_variables).difference(header))
        if missing:
            raise ValueError("analysis dataset is missing approved variables: " + ", ".join(missing))
        return CodeSpecification(
            specification_id=specification_id,
            language="python",
            entrypoint="statsmodels_template.py",
            purpose="research_analysis",
            project_id=frozen_dataset.project_id,
            executable_plan_ref=f"executable-plan://{executable_plan.executable_plan_id}",
            frozen_dataset_ref=frozen_dataset.ref,
            frozen_dataset_sha256=frozen_dataset.canonical_content_sha256,
            analysis_dataset_ref=analysis_dataset.ref,
            analysis_dataset_sha256=analysis_dataset.canonical_content_sha256,
            deterministic_template_sha256=sha256_text(
                (Path(__file__).parents[1] / "statistics" / "v1_execution.py").read_text(
                    encoding="utf-8"
                )
            ),
            model_specification_ref=f"model-spec://{model_specification.model_spec_id}",
            approved_variable_names=approved_variables,
            analysis_parameters={
                "requires_analysis_dataset": "true",
                "model_family": model_specification.model_family,
                "fixed_formula": model_specification.executable_fixed_formula
                or model_specification.formula_or_design,
                "groups_variable": model_specification.groups_variable or "",
                "re_formula": model_specification.re_formula or "",
                "mixedlm_reml": "true",
                "mixedlm_method": "lbfgs",
                "mixedlm_maxiter": "200",
                "ancova_cov_type": "HC3",
                "ancova_use_t": "true",
            },
            execution_policy_ref="statsmodels-policy://v1.0",
            input_refs=[frozen_dataset.ref, analysis_dataset.ref],
            output_types=["ExecutionRun", "ResultValidationReport", "StatisticalResultCard"],
            dependency_refs=["python://runtime", "statsmodels://0.14.6"],
        )

    @staticmethod
    def fingerprint(specification: CodeSpecification) -> str:
        """Stable fingerprint retained by a code artifact for provenance."""

        return sha256_text(specification.model_dump_json(exclude_none=True))
