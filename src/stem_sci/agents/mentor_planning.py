from __future__ import annotations

import re
from typing import Any

from workflow.protocol import AgentInput, AgentOutput
from workflow.utils import normalize_response


_MENTOR_KEYWORDS = (
    "research scope", "research question", "question tree", "feasibility", "research roadmap",
    "research plan", "study topic", "research intent", "\u7814\u7a76\u8303\u56f4", "\u7814\u7a76\u95ee\u9898",
    "\u95ee\u9898\u6811", "\u53ef\u884c\u6027", "\u7814\u7a76\u8def\u7ebf", "\u79d1\u7814\u89c4\u5212", "\u8bfe\u9898", "\u9009\u9898",
)


def is_mentor_planning_request(query: str, extra_params: dict[str, Any] | None = None) -> bool:
    extra_params = extra_params or {}
    requested_agent = str(extra_params.get("agent", "")).lower()
    if requested_agent in {"mentor", "mentor_planning", "mentorplanningagent"}:
        return True
    query_lower = query.lower()
    return any(keyword in query_lower or keyword in query for keyword in _MENTOR_KEYWORDS)


def _project_slug(agent_input: AgentInput) -> str:
    extra_params = agent_input["context"].get("extra_params", {})
    explicit = extra_params.get("project_id") or extra_params.get("task_ref")
    if explicit:
        return re.sub(r"[^A-Za-z0-9_-]+", "-", str(explicit)).strip("-") or "research-project"
    words = re.findall(r"[A-Za-z0-9]+", agent_input["query"])
    return "-".join(words[:4]).lower() or "research-project"


def _candidate_ref(project: str, artifact_type: str) -> str:
    return f"candidate://mentor_planning/{project}/{artifact_type}"


def mentor_planning_agent(agent_input: AgentInput) -> AgentOutput:
    """Produce bounded research-planning candidates; Controller approval is required."""
    query = agent_input["query"]
    project = _project_slug(agent_input)
    refs = [
        _candidate_ref(project, "ResearchContractCandidate"),
        _candidate_ref(project, "ResearchQuestionTree"),
        _candidate_ref(project, "FeasibilityAssessment"),
        _candidate_ref(project, "ResearchRoadmap"),
    ]
    question = query or "Define a feasible research question for the stated topic."
    extra_params = agent_input["context"].get("extra_params", {})
    extra: dict[str, Any] = {
        "agent_name": "MentorPlanningAgent",
        "candidate_artifact_refs": refs,
        "policy_version": str(extra_params.get("policy_version", "policy-v1")),
        "prompt_template_version": str(extra_params.get("prompt_template_version", "prompt-v1")),
        "is_formal_approval": False,
        "research_contract_candidate": {
            "title": "Candidate research contract",
            "research_intent": question,
            "scope": ["target population", "intervention or exposure", "outcomes", "time horizon"],
            "status": "candidate",
        },
        "research_question_tree": [
            {"level": 1, "question": question},
            {"level": 2, "question": "What population, exposure, outcome, and comparison are measurable?"},
            {"level": 2, "question": "Which confounders, constraints, and ethical risks must be addressed?"},
        ],
        "feasibility_assessment": {
            "data": "Needs confirmation from the project context or data owner.",
            "methods": "A staged observational or experimental design can be evaluated after scope approval.",
            "risks": ["scope creep", "unclear outcome definition", "insufficient sample or follow-up"],
        },
        "research_roadmap": [
            "Approve the research scope and question tree.",
            "Define estimands and a candidate study protocol.",
            "Review evidence and data availability before preregistration.",
        ],
        "approval_request": {
            "approval_type": "research_scope",
            "title": "Approve candidate research scope and roadmap",
            "candidate_artifact_refs": refs,
            "required_controller_action": "approve_or_revise",
        },
        "unresolved_questions": [
            "Who is the target population?",
            "What data source and observation window are available?",
            "Which outcome is primary?",
        ],
    }
    return normalize_response({
        "answer": "Mentor planning produced candidate research scope, question-tree, feasibility, and roadmap artifacts. Controller approval is required before formal scoping.",
        "sources": [],
        "confidence": 0.86 if query else 0.55,
        "status": "success",
        "extra": extra,
    })


class MentorPlanningAgent:
    run = staticmethod(mentor_planning_agent)


MENTOR_PLANNING_AGENT = MentorPlanningAgent()
