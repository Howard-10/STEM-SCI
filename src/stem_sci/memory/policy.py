"""Deterministic privacy policy applied before any memory write."""

from __future__ import annotations

import re

from .models import Sensitivity

_PROHIBITED_PATTERNS = (
    r"\b(?:sk|api)[-_][A-Za-z0-9]{12,}\b",
    r"(?i)(api[_ -]?key|password|\u5bc6\u7801|\u5bc6\u94a5)\s*[:=\uff1a]",
    r"\b\d{15,18}[0-9Xx]\b",
    r"\b1[3-9]\d{9}\b",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    r"(?i)(chain[- ]?of[- ]?thought|hidden reasoning|\u601d\u7ef4\u94fe|\u5185\u90e8\u63a8\u7406)",
)

_SENSITIVE_TERMS = (
    "\u672a\u6210\u5e74\u4eba",
    "\u5b66\u751f\u539f\u59cb\u6570\u636e",
    "\u5b66\u751f\u4e2a\u4eba\u4fe1\u606f",
    "\u75c5\u53f2",
    "\u8bca\u65ad",
    "\u5065\u5eb7\u4fe1\u606f",
    "\u5bb6\u5ead\u4f4f\u5740",
    "\u8eab\u4efd\u8bc1",
    "\u62a4\u7167",
    "\u94f6\u884c\u5361",
    "\u4eba\u8138",
    "\u6307\u7eb9",
)


def classify_sensitivity(text: str) -> Sensitivity:
    """Classify text conservatively; prohibited content can never be persisted."""

    if any(re.search(pattern, text) for pattern in _PROHIBITED_PATTERNS):
        return Sensitivity.PROHIBITED
    if any(term in text for term in _SENSITIVE_TERMS):
        return Sensitivity.PROHIBITED
    return Sensitivity.NORMAL
