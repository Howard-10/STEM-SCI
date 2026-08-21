"""Environment validation and deployment-safe runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigurationReport:
    """Non-secret configuration status used by health checks."""

    valid: bool
    warnings: tuple[str, ...] = ()


def validate_environment() -> ConfigurationReport:
    """Validate values that can otherwise cause a late runtime failure.

    Secrets are never returned in the report. Optional services remain optional
    unless their configuration is partially supplied or strict mode is enabled.
    """

    errors: list[str] = []
    warnings: list[str] = []
    strict = _as_bool(os.getenv("STEM_SCI_CONFIG_STRICT", "false"))

    origins = _csv("STEM_SCI_CORS_ORIGINS") or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    if not origins:
        errors.append("STEM_SCI_CORS_ORIGINS must contain at least one origin")
    if "*" in origins:
        errors.append("STEM_SCI_CORS_ORIGINS must not contain '*'")

    context_provider = os.getenv("STEM_SCI_CONTEXT_PROVIDER", "local").strip().lower()
    if context_provider not in {"local", "hybrid"}:
        errors.append("STEM_SCI_CONTEXT_PROVIDER must be local or hybrid")

    _validate_positive_int("STEM_SCI_MAX_UPLOAD_BYTES", errors)
    _validate_positive_int("STEM_SCI_MAX_LLM_CALLS", errors)

    llm_key = os.getenv("STEM_SCI_LLM_API_KEY", "").strip()
    llm_fields = {
        "STEM_SCI_LLM_BASE_URL": os.getenv("STEM_SCI_LLM_BASE_URL", "").strip(),
        "STEM_SCI_LLM_MODEL": os.getenv("STEM_SCI_LLM_MODEL", "").strip(),
    }
    if llm_key:
        missing = [name for name, value in llm_fields.items() if not value]
        if missing:
            errors.append(f"LLM configuration is incomplete: {', '.join(missing)}")
    elif strict and any(llm_fields.values()):
        warnings.append("LLM API key is not configured; QA will use fallback synthesis")

    graph_backend = os.getenv("STEM_SCI_GRAPH_BACKEND", "auto").strip().lower()
    if graph_backend not in {"auto", "neo4j", "json"}:
        errors.append("STEM_SCI_GRAPH_BACKEND must be auto, neo4j, or json")
    if graph_backend == "neo4j" and not os.getenv("NEO4J_PASSWORD", "").strip():
        errors.append("NEO4J_PASSWORD is required when STEM_SCI_GRAPH_BACKEND=neo4j")

    if os.getenv("STEM_SCI_CONTEXT_PROVIDER", "local").strip().lower() == "hybrid":
        if not os.getenv("STEM_SCI_VECTOR_KB_ROOT", "").strip():
            warnings.append(
                "STEM_SCI_VECTOR_KB_ROOT is not set; repository-local assets will be used"
            )
        if not os.getenv("DASHSCOPE_API_KEY", "").strip():
            warnings.append("DASHSCOPE_API_KEY is not configured; dense retrieval will degrade")

    if errors:
        raise ValueError("; ".join(errors))
    return ConfigurationReport(valid=True, warnings=tuple(sorted(set(warnings))))


def _csv(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _validate_positive_int(name: str, errors: list[str]) -> None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return
    try:
        if int(value) <= 0:
            raise ValueError
    except ValueError:
        errors.append(f"{name} must be a positive integer")


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
