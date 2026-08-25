"""Read-only tools exposed to the conversational GraphRAG router."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

from .models import ContextMode, RetrievalSearchRequest
from .qa_models import QARoute
from .service import HybridKnowledgeService


TOOL_NAMES = (
    "graph_search",
    "vector_search",
    "hybrid_search",
    "paper_lookup",
    "workflow_agent",
    "start_research_workflow",
    "get_workflow_status",
    "run_next_workflow_agent",
    "get_workflow_artifacts",
    "prepare_workflow_approval",
    "external_paper_search",
)
WORKFLOW_TOOL_NAMES = frozenset(
    {
        "start_research_workflow",
        "get_workflow_status",
        "run_next_workflow_agent",
        "get_workflow_artifacts",
        "prepare_workflow_approval",
    }
)


def tool_definitions() -> list[dict[str, Any]]:
    """Return OpenAI-compatible function definitions with strict arguments."""

    query_tool = {
        "type": "function",
        "function": {
            "name": "hybrid_search",
            "description": (
                "Search the STEM-SCI paper corpus using graph navigation plus "
                "dense and BM25 text retrieval. Use this for evidence-based questions."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["query"],
            },
        },
    }
    graph_tool = _clone_tool(
        query_tool,
        name="graph_search",
        description=(
            "Navigate the paper graph to find related candidate papers. Graph "
            "relations are navigation hints and are never formal evidence."
        ),
    )
    vector_tool = _clone_tool(
        query_tool,
        name="vector_search",
        description=(
            "Search original paper chunks with dense and sparse retrieval. "
            "Use this when the user needs textual evidence."
        ),
    )
    paper_tool = {
        "type": "function",
        "function": {
            "name": "paper_lookup",
            "description": "Locate a specific paper by title, DOI, filename, or paper identifier.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["query"],
            },
        },
    }
    workflow_tool = {
        "type": "function",
        "function": {
            "name": "workflow_agent",
            "description": (
                "Recommend one of the six research workflow Agents for a task. "
                "This tool is proposal-only and never changes workflow state."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": [
                            "MentorPlanningAgent",
                            "EvidenceReviewAgent",
                            "ResearchDesignAgent",
                            "DataAnalysisAgent",
                            "PaperWritingAgent",
                            "IndependentReviewAgent",
                        ],
                    },
                    "task": {"type": "string", "minLength": 1},
                },
                "required": ["agent", "task"],
            },
        },
    }
    external_tool = {
        "type": "function",
        "function": {
            "name": "external_paper_search",
            "description": (
                "Request a search outside the local corpus. This deployment "
                "does not perform external network search unless explicitly configured."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    }
    workflow_start_tool = {
        "type": "function",
        "function": {
            "name": "start_research_workflow",
            "description": (
                "Create a research project and run the first MentorPlanningAgent. "
                "Use only when the user explicitly asks to start or create a research project."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "research_intent": {"type": "string", "minLength": 1},
                },
                "required": ["research_intent"],
            },
        },
    }
    workflow_status_tool = _workflow_tool(
        name="get_workflow_status",
        description="Read the current research workflow stage, Agent, approvals, and risks.",
    )
    workflow_next_tool = _workflow_tool(
        name="run_next_workflow_agent",
        description=(
            "Run the next Controller-selected research Agent. Never bypass a pending "
            "human approval."
        ),
    )
    workflow_artifacts_tool = _workflow_tool(
        name="get_workflow_artifacts",
        description="Read the candidate artifacts generated for the research project.",
    )
    workflow_approval_tool = _workflow_tool(
        name="prepare_workflow_approval",
        description=(
            "Read the pending approval and prepare a confirmation message. This tool "
            "never approves or rejects a workflow step."
        ),
    )
    return [
        graph_tool,
        vector_tool,
        query_tool,
        paper_tool,
        workflow_tool,
        workflow_start_tool,
        workflow_status_tool,
        workflow_next_tool,
        workflow_artifacts_tool,
        workflow_approval_tool,
        external_tool,
    ]


class QAToolExecutor:
    """Execute retrieval tools and bounded Controller workflow actions."""

    def __init__(
        self,
        knowledge_service: HybridKnowledgeService,
        workflow_controller: Any | None = None,
        artifact_store: Any | None = None,
    ) -> None:
        self._knowledge_service = knowledge_service
        self._workflow_controller = workflow_controller
        self._artifact_store = artifact_store

    def execute(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        project_id: str,
        default_query: str,
        mode: ContextMode = ContextMode.DISCOVERY,
    ) -> dict[str, Any]:
        if name in {"graph_search", "vector_search", "hybrid_search", "paper_lookup"}:
            query = str(arguments.get("query") or default_query).strip()
            if not query:
                return {"ok": False, "error": "query is required"}
            limit = _bounded_int(arguments.get("limit"), default=8, maximum=12)
            response = self._knowledge_service.search(
                RetrievalSearchRequest(
                    project_id=project_id,
                    corpus_ids=["physics_stem_v1"],
                    query=query,
                    mode=mode,
                    limit=limit,
                )
            )
            payload = response.model_dump(mode="json")
            payload["retrieval_response"] = response.model_dump(mode="json")
            if name == "graph_search":
                payload = {
                    "project_id": project_id,
                    "corpus_id": response.corpus_id,
                    "retrieval_status": response.retrieval_status,
                    "candidate_papers": [
                        item.model_dump(mode="json") for item in response.candidate_papers
                    ],
                    "risk_flags": [
                        *response.risk_flags,
                        "graph_relations_are_navigation_only",
                    ],
                    "retrieval_trace": response.retrieval_trace.model_dump(mode="json"),
                    "retrieval_response": response.model_dump(mode="json"),
                }
            elif name == "vector_search":
                payload = {
                    "project_id": project_id,
                    "corpus_id": response.corpus_id,
                    "retrieval_status": response.retrieval_status,
                    "chunk_hits": [
                        item.model_dump(mode="json") for item in response.chunk_hits
                    ],
                    "risk_flags": response.risk_flags,
                    "retrieval_response": response.model_dump(mode="json"),
                }
            elif name == "paper_lookup":
                payload = {
                    "project_id": project_id,
                    "corpus_id": response.corpus_id,
                    "retrieval_status": response.retrieval_status,
                    "papers": [
                        item.model_dump(mode="json") for item in response.candidate_papers
                    ],
                    "matching_chunks": [
                        item.model_dump(mode="json") for item in response.chunk_hits
                    ],
                    "risk_flags": response.risk_flags,
                    "retrieval_response": response.model_dump(mode="json"),
                }
            return payload

        if name in WORKFLOW_TOOL_NAMES:
            return self._execute_workflow(
                name=name,
                arguments=arguments,
                project_id=project_id,
                default_query=default_query,
            )

        if name == "workflow_agent":
            agent = str(arguments.get("agent") or "MentorPlanningAgent")
            task = str(arguments.get("task") or default_query).strip()
            return {
                "ok": True,
                "mode": "proposal_only",
                "agent": agent,
                "task": task,
                "message": (
                    "The conversational endpoint can recommend an Agent, but it "
                    "does not create, approve, or reject a workflow project. "
                    "Use the workflow tools for bounded project actions."
                ),
            }

        if name == "external_paper_search":
            return {
                "ok": False,
                "status": "NOT_CONFIGURED",
                "query": str(arguments.get("query") or default_query),
                "message": (
                    "External paper search is not configured for this deployment. "
                    "Only the declared local corpus was searched."
                ),
                "risk_flags": ["external_search_not_configured"],
            }

        return {"ok": False, "error": f"unknown tool: {name}"}

    def _execute_workflow(
        self,
        *,
        name: str,
        arguments: Mapping[str, Any],
        project_id: str,
        default_query: str,
    ) -> dict[str, Any]:
        if self._workflow_controller is None:
            return {
                "ok": False,
                "status": "NOT_CONFIGURED",
                "message": "Workflow Controller is not configured for this deployment.",
                "risk_flags": ["workflow_controller_not_configured"],
                "workflow_action": {
                    "action": "UNAVAILABLE",
                    "project_id": project_id,
                    "message": "Workflow Controller is not configured.",
                },
            }

        if name == "start_research_workflow":
            research_intent = str(arguments.get("research_intent") or default_query).strip()
            if not research_intent:
                return {"ok": False, "error": "research_intent is required"}
            try:
                # Import lazily to avoid the Controller -> context -> knowledge
                # import cycle during application and test-module startup.
                from stem_sci.controller.router import PlanningRequest

                result = self._workflow_controller.start_planning(
                    PlanningRequest(
                        project_id=project_id,
                        research_intent=research_intent,
                        run_id=f"chat-planning-{uuid4().hex}",
                    )
                )
            except ValueError as error:
                return {
                    "ok": False,
                    "status": "WORKFLOW_START_FAILED",
                    "message": str(error),
                    "risk_flags": ["workflow_action_failed"],
                }
            state = result.workflow_state
            return {
                "ok": True,
                "status": "STARTED",
                "workflow_action": _workflow_action(
                    action="STARTED",
                    project_id=project_id,
                    message=(
                        "研究项目已创建，MentorPlanningAgent 已生成候选研究范围，"
                        "当前等待人工审批。"
                    ),
                    state=state,
                    selected_agent=result.agent_result.agent_id,
                    approval=result.approval_request,
                    next_available_actions=["prepare_workflow_approval"],
                ),
            }

        try:
            state = self._workflow_controller.get_state(project_id)
        except ValueError as error:
            return {
                "ok": False,
                "status": "UNKNOWN_PROJECT",
                "message": str(error),
                "risk_flags": ["workflow_project_not_found"],
            }

        if name == "get_workflow_status":
            approval = _pending_approval(self._workflow_controller, project_id, state)
            return {
                "ok": True,
                "status": "READY",
                "workflow_action": _workflow_action(
                    action="STATUS",
                    project_id=project_id,
                    message="已读取当前研究工作流状态。",
                    state=state,
                    selected_agent=(
                        state.last_route_decision.selected_route
                        if state.last_route_decision is not None
                        else None
                    ),
                    approval=approval,
                    next_available_actions=_next_actions(state, approval),
                ),
            }

        if name == "prepare_workflow_approval":
            approval = _pending_approval(self._workflow_controller, project_id, state)
            if approval is None:
                return {
                    "ok": False,
                    "status": "NO_PENDING_APPROVAL",
                    "message": "当前项目没有待处理审批。",
                    "workflow_action": _workflow_action(
                        action="APPROVAL_READY",
                        project_id=project_id,
                        message="当前项目没有待处理审批。",
                        state=state,
                        next_available_actions=_next_actions(state, None),
                    ),
                }
            return {
                "ok": True,
                "status": "APPROVAL_REQUIRED",
                "workflow_action": _workflow_action(
                    action="APPROVAL_READY",
                    project_id=project_id,
                    message=(
                        "当前存在待审批候选。请在工作流页面确认批准或退回，"
                        "对话工具不会直接执行审批。"
                    ),
                    state=state,
                    approval=approval,
                    confirmation_required=True,
                    next_available_actions=["approve", "reject"],
                ),
            }

        if name == "run_next_workflow_agent":
            approval = _pending_approval(self._workflow_controller, project_id, state)
            if approval is not None:
                return {
                    "ok": False,
                    "status": "APPROVAL_REQUIRED",
                    "message": "项目正在等待人工审批，不能直接运行下一个 Agent。",
                    "workflow_action": _workflow_action(
                        action="APPROVAL_READY",
                        project_id=project_id,
                        message="请先处理当前待审批候选。",
                        state=state,
                        approval=approval,
                        confirmation_required=True,
                        next_available_actions=["approve", "reject"],
                    ),
                }
            try:
                result = self._workflow_controller.run_next(project_id)
            except ValueError as error:
                return {
                    "ok": False,
                    "status": "WORKFLOW_NEXT_FAILED",
                    "message": str(error),
                    "risk_flags": ["workflow_action_failed"],
                }
            return {
                "ok": True,
                "status": "NEXT_AGENT",
                "workflow_action": _workflow_action(
                    action="NEXT_AGENT",
                    project_id=project_id,
                    message=f"{result.agent_result.agent_id} 已生成新的候选输出，当前等待人工审批。",
                    state=result.workflow_state,
                    selected_agent=result.agent_result.agent_id,
                    approval=result.approval_request,
                    next_available_actions=["prepare_workflow_approval"],
                ),
            }

        if name == "get_workflow_artifacts":
            if self._artifact_store is None:
                return {
                    "ok": False,
                    "status": "NOT_CONFIGURED",
                    "message": "Artifact store is not configured.",
                    "risk_flags": ["artifact_store_not_configured"],
                }
            artifacts = self._artifact_store.list_project(project_id)
            return {
                "ok": True,
                "status": "READY",
                "workflow_action": _workflow_action(
                    action="STATUS",
                    project_id=project_id,
                    message="已读取项目候选工件。",
                    state=state,
                    artifacts=[item.model_dump(mode="json") for item in artifacts],
                    next_available_actions=_next_actions(
                        state,
                        _pending_approval(self._workflow_controller, project_id, state),
                    ),
                ),
            }

        return {"ok": False, "error": f"unsupported workflow tool: {name}"}

def _clone_tool(
    source: Mapping[str, Any],
    *,
    name: str,
    description: str,
) -> dict[str, Any]:
    function = dict(source["function"])
    function["name"] = name
    function["description"] = description
    return {"type": "function", "function": function}


def _bounded_int(value: Any, *, default: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, parsed))


def _workflow_tool(*, name: str, description: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
    }


def _pending_approval(controller: Any, project_id: str, state: Any) -> Any | None:
    if state.pending_approval_ref is None:
        return None
    try:
        return controller.get_pending_approval(project_id)
    except ValueError:
        return None


def _next_actions(state: Any, approval: Any | None) -> list[str]:
    if approval is not None:
        return ["prepare_workflow_approval", "approve", "reject"]
    if str(state.current_stage) in {"VERIFIED", "RELEASED", "BLOCKED"}:
        return ["get_workflow_status", "get_workflow_artifacts"]
    return ["run_next_workflow_agent", "get_workflow_status", "get_workflow_artifacts"]


def _workflow_action(
    *,
    action: str,
    project_id: str,
    message: str,
    state: Any,
    selected_agent: str | None = None,
    approval: Any | None = None,
    confirmation_required: bool = False,
    artifacts: list[dict[str, Any]] | None = None,
    next_available_actions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "project_id": project_id,
        "message": message,
        "current_stage": str(state.current_stage),
        "selected_agent": selected_agent,
        "approval_required": approval is not None,
        "confirmation_required": confirmation_required,
        "approval_request_id": approval.request_id if approval is not None else None,
        "approval_request": (
            approval.model_dump(mode="json") if approval is not None else None
        ),
        "workflow_state": state.model_dump(mode="json"),
        "artifacts": artifacts or [],
        "next_available_actions": next_available_actions or [],
    }


def route_for_tool(name: str) -> QARoute:
    """Map a tool call to the public QA route vocabulary."""

    if name in TOOL_NAMES:
        if name in WORKFLOW_TOOL_NAMES:
            return "workflow_agent"
        return cast(QARoute, name)
    return "direct_answer"


def tool_reason(name: str) -> str:
    reasons = {
        "graph_search": "LLM selected graph navigation for candidate-paper discovery.",
        "vector_search": "LLM selected original-text retrieval for evidence.",
        "hybrid_search": "LLM selected graph-guided dense plus sparse retrieval.",
        "paper_lookup": "LLM selected a targeted paper lookup.",
        "workflow_agent": "LLM selected a proposal-only research workflow Agent.",
        "start_research_workflow": "LLM selected project creation and the first workflow Agent.",
        "get_workflow_status": "LLM selected a read-only workflow status lookup.",
        "run_next_workflow_agent": "LLM selected the next Controller-routed workflow Agent.",
        "get_workflow_artifacts": "LLM selected a read-only workflow artifact lookup.",
        "prepare_workflow_approval": "LLM selected a read-only pending-approval lookup.",
        "external_paper_search": "LLM requested external search, which is currently unavailable.",
    }
    return reasons.get(name, "LLM answered directly without a retrieval tool.")
