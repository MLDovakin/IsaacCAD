"""Blackboard shared by runtime steps. Explicit keys, no hidden globals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Context:
    spec: Any = None
    build: Any = None
    world: Any = None                       # Isaac World, if running in sim
    t: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def has(self, *keys: str) -> bool:
        return all(k in self.data for k in keys)

    def require(self, *keys: str) -> None:
        missing = [k for k in keys if k not in self.data]
        if missing:
            raise KeyError(f"missing context keys: {missing}")

    def say(self, msg: str) -> None:
        self.log.append(f"[t={self.t:7.3f}] {msg}")

    def value(self, key: str, default: Any = None) -> Any:
        return self.spec.values.get(key, default) if self.spec else default
