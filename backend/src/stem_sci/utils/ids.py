"""Stable identifier helpers."""

from uuid import uuid4


def new_id(prefix: str) -> str:
    if not prefix:
        raise ValueError("prefix must not be empty")
    return f"{prefix}-{uuid4().hex}"
