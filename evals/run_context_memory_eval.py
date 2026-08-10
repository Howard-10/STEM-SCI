"""Run the 30 golden context cases against the configured live DeepSeek model."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from stem_sci.context import (
    ApprovedDecision,
    ContextModelConfig,
    ContextRequest,
    EvidenceContext,
    RuntimeContext,
    build_context,
)
from stem_sci.memory.models import MemoryKind, MemoryRecord, MemoryScope


def load_cases() -> list[dict[str, Any]]:
    path = Path(__file__).with_name("context_memory_goldens.json")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError("Golden evaluation file must contain a JSON array of objects")
    return [dict(item) for item in raw]


def run() -> dict[str, Any]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    model = ContextModelConfig.from_env().create_chat_model()
    results = []
    total_tokens = 0
    for case in load_cases():
        identity = RuntimeContext(
            user_id="eval-user",
            project_id="eval-project",
            thread_id=case["id"],
            run_id=f"run-{case['id']}",
        )
        memories = [
            MemoryRecord(
                memory_id=f"{case['id']}-m{index}",
                user_id=identity.user_id,
                project_id=identity.project_id,
                scope=MemoryScope.PROJECT,
                kind=MemoryKind.PROJECT_CONSTRAINT,
                content=content,
            )
            for index, content in enumerate(case.get("memories", []))
        ]
        evidence = [
            EvidenceContext(
                evidence_id=f"{case['id']}-e{index}",
                source="golden",
                content=content,
                relevance=1.0,
            )
            for index, content in enumerate(case.get("evidence", []))
        ]
        request = ContextRequest(
            identity=identity,
            task=case["task"],
            user_message=case["question"],
            approved_decisions=[
                ApprovedDecision(decision_id=f"{case['id']}-d{index}", content=content)
                for index, content in enumerate(case.get("decisions", []))
            ],
            memories=memories,
            evidence=evidence,
        )
        package = build_context(request)
        response = model.invoke(package.messages)
        answer = str(response.content)
        lowered = answer.casefold()
        passed = all(term.casefold() in lowered for term in case["expected"]) and all(
            term.casefold() not in lowered for term in case["forbidden"]
        )
        total_tokens += package.trace.estimated_input_tokens
        results.append({"id": case["id"], "passed": passed, "answer": answer})
    return {
        "cases": len(results),
        "passed": sum(item["passed"] for item in results),
        "pass_rate": sum(item["passed"] for item in results) / len(results),
        "mean_estimated_input_tokens": total_tokens / len(results),
        "results": results,
    }


if __name__ == "__main__":
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps(run(), ensure_ascii=False, indent=2))
