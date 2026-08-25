"""Stable signatures for protocol, data, code, environment, and output refs."""

from __future__ import annotations

import hashlib


def build_workflow_signature(*references: str) -> str:
    """Build an order-sensitive SHA256 signature over immutable references."""
    payload = "\n".join(reference.strip() for reference in references if reference.strip())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
