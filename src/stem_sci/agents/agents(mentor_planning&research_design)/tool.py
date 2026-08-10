from __future__ import annotations

import re

from workflow.protocol import AgentInput, AgentOutput
from workflow.utils import normalize_response, safe_eval_expression


def tool_agent(agent_input: AgentInput) -> AgentOutput:
    query = agent_input["query"]
    tool_name = str(agent_input["context"].get("extra_params", {}).get("tool_name", "python_calculator(mock)"))
    expression = extract_math_expression(query)
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", query)]
    confidence = 0.92

    if expression:
        result = safe_eval_expression(expression)
        pretty = int(result) if result.is_integer() else round(result, 4)
        answer = f"[Mock Tool Agent] Computation finished. `{expression}` = {pretty}."
        raw = {"expression": expression, "result": pretty}
    elif len(numbers) >= 2 and any(k in query.lower() or k in query for k in ["average", "mean", "\u5e73\u5747"]):
        result = sum(numbers) / len(numbers)
        pretty = int(result) if result.is_integer() else round(result, 4)
        answer = f"[Mock Tool Agent] Average calculation finished. Input values={numbers}, average={pretty}."
        raw = {"values": numbers, "average": pretty}
    elif numbers and any(k in query.lower() or k in query for k in ["sum", "total", "\u6c42\u548c", "\u603b\u5206"]):
        result = sum(numbers)
        pretty = int(result) if result.is_integer() else round(result, 4)
        answer = f"[Mock Tool Agent] Sum calculation finished. Input values={numbers}, sum={pretty}."
        raw = {"values": numbers, "sum": pretty}
    else:
        answer = "[Mock Tool Agent] The demo calculator supports arithmetic expressions, average, and sum requests."
        raw = {"expression": expression, "numbers": numbers}
        confidence = 0.58

    return normalize_response({
        "answer": answer,
        "sources": [{"title": "Mock Calculator Runtime", "url": "https://example.local/mock-calculator-runtime", "type": "tool_computation"}],
        "confidence": confidence,
        "status": "success",
        "extra": {"tool_name": tool_name, "tool_params": {"query": query}, "raw_output": raw},
    })


def extract_math_expression(query: str) -> str:
    match = re.search(r"(-?\d+(?:\.\d+)?(?:\s*[-+*/()]\s*-?\d+(?:\.\d+)?)+)", query)
    return re.sub(r"\s+", "", match.group(1)) if match else ""
