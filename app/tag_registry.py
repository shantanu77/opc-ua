from __future__ import annotations

import fnmatch
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class TagValue:
    path: str
    value: Any
    quality: str
    timestamp: str
    writable: bool = True
    data_type: str = "Double"


class TagRegistry:
    """Thread-safe tag catalog and current-value cache shared by UA and Pyro."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tags: dict[str, TagValue] = {}
        self._aliases: dict[str, str] = {}

    def clear(self) -> None:
        with self._lock:
            self._tags.clear()
            self._aliases.clear()

    def register(
        self,
        path: str,
        value: Any,
        *,
        writable: bool = True,
        data_type: str = "Double",
        aliases: Iterable[str] = (),
        quality: str = "Good",
        timestamp: str | None = None,
    ) -> TagValue:
        normalized = self._normalize_path(path)
        record = TagValue(
            path=normalized,
            value=value,
            quality=quality,
            timestamp=timestamp or utc_timestamp(),
            writable=writable,
            data_type=data_type,
        )
        with self._lock:
            self._tags[normalized] = record
            self._aliases[normalized] = normalized
            for alias in aliases:
                if alias:
                    self._aliases[str(alias)] = normalized
        return record

    def resolve(self, path: str) -> str | None:
        with self._lock:
            return self._aliases.get(str(path))

    def read(self, path: str) -> TagValue | None:
        with self._lock:
            canonical = self._aliases.get(str(path))
            return self._tags.get(canonical) if canonical else None

    def update(
        self,
        path: str,
        value: Any,
        *,
        quality: str = "Good",
        timestamp: str | None = None,
        require_writable: bool = False,
    ) -> TagValue | None:
        with self._lock:
            canonical = self._aliases.get(str(path))
            if canonical is None:
                return None
            current = self._tags[canonical]
            if require_writable and not current.writable:
                return replace(
                    current,
                    quality="Bad: Not writable",
                    timestamp=timestamp or utc_timestamp(),
                )
            updated = replace(
                current,
                value=value,
                quality=quality,
                timestamp=timestamp or utc_timestamp(),
            )
            self._tags[canonical] = updated
            return updated

    def list_paths(self, pattern: str = "*", *, recursive: bool = True) -> list[str]:
        normalized_pattern = str(pattern or "*")
        if not any(token in normalized_pattern for token in "*?["):
            normalized_pattern = (
                f"{normalized_pattern}*" if recursive else f"{normalized_pattern}.*"
            )
        with self._lock:
            return sorted(
                path for path in self._tags if fnmatch.fnmatchcase(path, normalized_pattern)
            )

    def snapshot(self) -> list[TagValue]:
        with self._lock:
            return [self._tags[path] for path in sorted(self._tags)]

    def __len__(self) -> int:
        with self._lock:
            return len(self._tags)

    @staticmethod
    def _normalize_path(path: str) -> str:
        normalized = str(path).strip().strip(".")
        if not normalized:
            raise ValueError("tag path must not be empty")
        return normalized
