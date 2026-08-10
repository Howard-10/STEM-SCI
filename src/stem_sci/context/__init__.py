"""Budgeted model-context assembly."""

from .builder import ContextBudgetError, ContextBuilder, build_context
from .config import ContextModelConfig
from .models import (
    ApprovedDecision,
    ContextPackage,
    ContextRequest,
    ContextTrace,
    EvidenceContext,
    RuntimeContext,
    TokenBudget,
    evidence_from_rag,
)

__all__ = [
    "ApprovedDecision",
    "ContextBudgetError",
    "ContextBuilder",
    "ContextModelConfig",
    "ContextPackage",
    "ContextRequest",
    "ContextTrace",
    "EvidenceContext",
    "RuntimeContext",
    "TokenBudget",
    "build_context",
    "evidence_from_rag",
]
