# mypy: disable-error-code="unused-ignore,override"
"""Import LangGraph Store primitives, with an isolated in-memory fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any

try:  # pragma: no cover - exercised in deployment environments
    from langgraph.store.base import BaseStore  # type: ignore[import-not-found]
    from langgraph.store.memory import InMemoryStore  # type: ignore[import-not-found]

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback is covered through consuming modules
    LANGGRAPH_AVAILABLE = False

    @dataclass(frozen=True)
    class StoreItem:
        namespace: tuple[str, ...]
        key: str
        value: dict[str, Any]
        created_at: datetime
        updated_at: datetime

    class BaseStore:  # type: ignore[no-redef]
        pass

    class InMemoryStore(BaseStore):  # type: ignore[misc,no-redef]
        def __init__(self) -> None:
            self._items: dict[tuple[tuple[str, ...], str], StoreItem] = {}
            self._lock = RLock()

        def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
            now = datetime.now(UTC)
            item_key = (namespace, key)
            with self._lock:
                existing = self._items.get(item_key)
                self._items[item_key] = StoreItem(
                    namespace=namespace,
                    key=key,
                    value=value,
                    created_at=existing.created_at if existing else now,
                    updated_at=now,
                )

        def get(self, namespace: tuple[str, ...], key: str) -> StoreItem | None:
            with self._lock:
                return self._items.get((namespace, key))

        def search(self, namespace: tuple[str, ...]) -> list[StoreItem]:
            with self._lock:
                return [
                    item
                    for (item_namespace, _), item in self._items.items()
                    if item_namespace == namespace
                ]

        def delete(self, namespace: tuple[str, ...], key: str) -> None:
            with self._lock:
                self._items.pop((namespace, key), None)


__all__ = ["LANGGRAPH_AVAILABLE", "BaseStore", "InMemoryStore"]
