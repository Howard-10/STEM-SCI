from __future__ import annotations

import re
from typing import Any

from workflow.protocol import AgentInput, AgentOutput
from workflow.utils import normalize_response


_DESIGN_KEYWORDS = (
    "research design", "study design", "estimand", "hypothesis", "protocol", "preregister",
    "pre-register", "analysis plan", "measurement", "\u7814\u7a76\u8bbe\u8ba1", "\u7814\u7a76\u65b9\u6848",
    "\u4f30\u8ba1\u76ee\u6807", "\u5047\u8bbe", "\u7814\u7a76\u534f\u8bae", "\u9884\u6ce8\u518c", "\u5206\u6790\u8ba1\u5212", "\u6d4b\u91cf\u89c4\u8303",
)


def is_research_design_request(query: str, extra_params: dict[str, Any] | None = None) -> bool:
    extra_params = extra_params or {}
    requested_agent = str(extra_params.get("agent", "")).lower()
    if requested_agent in {"design", "research_design", "researchdesignagent"}:
        return True
    query_lower = query.lower()
    return any(keyword in query_lower or keyword in query for keyword in _DESIGN_KEYWORDS)


def is_research_collaboration_request(query: str, extra_params: dict[str, Any] | None = None) -> bool:
    extra_params = extra_params or {}
    requested_agent = str(extra_params.get("agent", "")).lower()
    if requested_agent in {"research", "research_collaboration", "mentor_and_design"}:
        return True
    from .mentor_planning import is_mentor_planning_request

    return is_mentor_planning_request(query, extra_params) and is_research_design_request(query, extra_params)


def _project_slug(agent_input: AgentInput) -> str:
    extra_params = agent_input["context"].get("extra_params", {})
    explicit = extra_params.get("project_id") or extra_params.get("task_ref")
    if explicit:
        return re.sub(r"[^A-Za-z0-9_-]+", "-", str(explicit)).strip("-") or "research-project"
    words = re.findall(r"[A-Za-z0-9]+", agent_input["query"])
    return "-".join(words[:4]).lower() or "research-project"


def _candidate_ref(project: str, artifact_type: str) -> str:
    return f"candidate://research_design/{project}/{artifact_type}"


def research_design_agent(agent_input: AgentInput) -> AgentOutput:
    """Produce a candidate protocol and analysis plan without freezing or approving it."""
    query = agent_input["query"]
    project = _project_slug(agent_input)
    refs = [
        _candidate_ref(project, "EstimandCandidate"),
        _candidate_ref(project, "StudyProtocolCandidate"),
        _candidate_ref(project, "TaskAndMeasurementSpec"),
        _candidate_ref(project, "PreregisteredAnalysisPlanCandidate"),
    ]
    extra_params = agent_input["context"].get("extra_params", {})
    extra: dict[str, Any] = {
        "agent_name": "ResearchDesignAgent",
        "candidate_artifact_refs": refs,
        "policy_version": str(extra_params.get("policy_version", "policy-v1")),
        "prompt_template_version": str(extra_params.get("prompt_template_version", "prompt-v1")),
        "is_formal_approval": False,
        "estimand": {
            "population": "Target population to be confirmed",
            "treatment_or_exposure": "Primary intervention or exposure from the approved scope",
            "outcome": "Primary measurable outcome to be specified",
            "time_horizon": "Follow-up window to be specified",
            "contrast": "Difference between prespecified comparison conditions",
            "status": "candidate",
        },
        "study_protocol": {
            "design": "Candidate design pending scope and evidence review",
            "eligibility": ["Define inclusion criteria", "Define exclusion criteria"],
            "groups": ["exposure or intervention group", "comparison group"],
            "outcomes": {"primary": "To be specified", "secondary": []},
            "bias_controls": ["prespecify confounders", "document missing-data handling", "record deviations"],
            "status": "candidate",
        },
        "tasks": [
            "Confirm estimand and primary outcome.",
            "Audit data fields, provenance, and missingness.",
            "Specify analysis population and exclusion rules.",
            "Run a dry-run review before any formal analysis.",
        ],
        "measurement_spec": {
            "primary_outcome": {"definition": "To be specified", "unit": "To be specified", "measurement_time": "To be specified"},
            "covariates": [],
            "quality_checks": ["range checks", "duplicate checks", "time-order checks"],
        },
        "preregistered_analysis_plan": {
            "status": "candidate",
            "hypotheses": ["State directional or nondirectional hypotheses before analysis."],
            "model": "Specify the primary model after data and estimand review.",
            "missing_data": "Specify a prespecified handling rule.",
            "sensitivity_analyses": ["alternative model specification", "alternative missing-data assumption"],
            "approval_ref": "",
            "frozen_at": "",
        },
        "unresolved_questions": [
            "What is the primary estimand?",
            "Which variables operationalize the outcome and exposure?",
            "Which approval is required before freezing the analysis plan?",
        ],
        "approval_request": {
            "approval_type": "research_design",
            "title": "Review candidate estimand, protocol, and analysis plan",
            "candidate_artifact_refs": refs,
            "required_controller_action": "approve_or_revise",
        },
    }
    return normalize_response({
        "answer": "Research design produced candidate estimand, study protocol, task and measurement specification, and preregistered analysis plan. The plan remains candidate and cannot be frozen without Controller approval.",
        "sources": [],
        "confidence": 0.84 if query else 0.5,
        "status": "success",
        "extra": extra,
    })


class ResearchDesignAgent:
    run = staticmethod(research_design_agent)


RESEARCH_DESIGN_AGENT = ResearchDesignAgent()
