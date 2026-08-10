from __future__ import annotations

import ast
import copy
from typing import Any

from .protocol import AgentContext, AgentInput, AgentOutput

_ALLOWED_BINOPS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def normalize_request(payload: dict[str, Any] | None) -> AgentInput:
    payload = payload or {}
    history = payload.get("history")
    context = payload.get("context")

    if not isinstance(history, list):
        history = []
    if not isinstance(context, dict):
        context = {}

    normalized_context: AgentContext = {
        "scene": str(context.get("scene", "general")),
        "user_profile": context.get("user_profile") if isinstance(context.get("user_profile"), dict) else {},
        "extra_params": context.get("extra_params") if isinstance(context.get("extra_params"), dict) else {},
    }

    return {
        "query": str(payload.get("query", "")).strip(),
        "history": [
            {
                "role": str(item.get("role", "user")),
                "content": str(item.get("content", "")),
            }
            for item in history
            if isinstance(item, dict)
        ],
        "context": normalized_context,
    }


def normalize_response(response: dict[str, Any] | None) -> AgentOutput:
    response = copy.deepcopy(response or {})

    answer = str(response.get("answer", ""))
    sources = response.get("sources") if isinstance(response.get("sources"), list) else []
    raw_confidence = response.get("confidence", 0.0)

    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    status = response.get("status", "success")
    if status not in {"success", "error"}:
        status = "success"

    extra = response.get("extra") if isinstance(response.get("extra"), dict) else {}

    normalized_sources = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        normalized_sources.append(
            {
                "title": str(source.get("title", "")),
                "url": str(source.get("url", "")),
                "type": str(source.get("type", "")),
            }
        )

    return {
        "answer": answer,
        "sources": normalized_sources,
        "confidence": confidence,
        "status": status,
        "extra": extra,
    }


def error_response(message: str) -> AgentOutput:
    return {
        "answer": "",
        "sources": [],
        "confidence": 0.0,
        "status": "error",
        "extra": {"error_msg": message},
    }


def deduplicate_sources(*source_lists: list[dict[str, Any]]) -> list[dict[str, str]]:
    deduplicated: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for source_list in source_lists:
        for source in source_list:
            key = (
                str(source.get("title", "")),
                str(source.get("url", "")),
                str(source.get("type", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(
                {
                    "title": key[0],
                    "url": key[1],
                    "type": key[2],
                }
            )

    return deduplicated


def safe_eval_expression(expression: str) -> float:
    parsed = ast.parse(expression, mode="eval")
    return float(_eval_ast(parsed.body))


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Num):
        return float(node.n)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        return float(_ALLOWED_BINOPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return float(_ALLOWED_UNARYOPS[type(node.op)](_eval_ast(node.operand)))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")
