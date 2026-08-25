"""Export the FastAPI contract without starting a network service."""
from __future__ import annotations

import json
from pathlib import Path

from stem_sci.api import app

Path(__file__).parents[2].joinpath("contracts", "openapi", "context-mvp.openapi.json").write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8"
)
