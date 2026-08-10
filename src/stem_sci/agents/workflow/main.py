from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .graph import run_workflow_with_state



def build_default_payload() -> dict[str, Any]:
    return {
        "query": "Create a remediation plan for a student whose math score dropped from 92 to 78, and compute the decline percentage.",
        "history": [],
        "context": {
            "scene": "learning_companion",
            "user_profile": {"grade": "8", "subject": "math"},
            "extra_params": {},
        },
    }



def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_file:
        return json.loads(Path(args.input_file).read_text(encoding="utf-8"))

    payload = build_default_payload()
    if args.query:
        payload["query"] = args.query
    if args.scene:
        payload["context"]["scene"] = args.scene
    if args.tool_name:
        payload["context"]["extra_params"]["tool_name"] = args.tool_name
    return payload



def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock LangGraph workflow with protocol-compliant I/O.")
    parser.add_argument("--query", help="Override the default query.")
    parser.add_argument("--scene", help="Override the context.scene field.")
    parser.add_argument("--tool-name", help="Inject context.extra_params.tool_name for routing demos.")
    parser.add_argument("--input-file", help="Path to a JSON file matching the agreed agent input protocol.")
    parser.add_argument("--show-state", action="store_true", help="Print the full LangGraph state instead of only final_response.")
    args = parser.parse_args()

    payload = load_payload(args)
    state = run_workflow_with_state(payload)
    if args.show_state:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(state["final_response"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
