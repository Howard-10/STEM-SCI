from __future__ import annotations

import re

from workflow.protocol import AgentInput, AgentOutput
from workflow.utils import normalize_response


def knowledge_agent(agent_input: AgentInput) -> AgentOutput:
    query = agent_input["query"]
    scene = agent_input["context"].get("scene", "general")
    entities = extract_entities(query)
    return normalize_response({
        "answer": f"[Mock Knowledge Agent] Scene={scene}. Clarify the task objective, surface relevant concepts, and turn them into an actionable response. Query focus: {query}",
        "sources": [
            {"title": "Mock Curriculum Guide", "url": "https://example.local/mock-curriculum-guide", "type": "teaching_material"},
            {"title": "Mock Domain Notes", "url": "https://example.local/mock-domain-notes", "type": "knowledge_graph"},
        ],
        "confidence": 0.88 if query else 0.2,
        "status": "success",
        "extra": {
            "retrieval_method": "BM25+BGE(mock)",
            "graph_entities": entities,
            "chunk_ids": [f"chunk-{i}" for i, _ in enumerate(entities[:3], 1)],
            "history_depth": len(agent_input["history"]),
        },
    })


def extract_entities(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", query)
    return list(dict.fromkeys(tokens))[:5]
