"""Pure-python backend: records what WOULD be authored.

This is what makes the whole skill testable without Isaac Sim running — invariants,
golden diffs and CI all work against this. The USD backend must produce the same
prim paths and transforms, so a green run here means the geometry intent is sound.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ...util.vecmath import Mat4


class NullBackend:
    name = "null"

    def __init__(self) -> None:
        self.prims: dict[str, dict[str, Any]] = {}
        self.joints: dict[str, dict[str, Any]] = {}
        self.stage_meta: dict[str, Any] = {}

    def open_stage(self, spec, layer: str | None = None) -> None:
        self.stage_meta = {
            "name": spec.name,
            "up_axis": spec.up_axis,
            "meters_per_unit": spec.meters_per_unit,
            "layer": layer,
        }

    def clear(self, root: str) -> None:
        for p in [k for k in self.prims if k == root or k.startswith(root + "/")]:
            del self.prims[p]
        for j in [k for k in self.joints if k == root or k.startswith(root + "/")]:
            del self.joints[j]

    def _put(self, prim_path: str, rec: dict[str, Any]) -> None:
        if prim_path in self.prims:
            raise ValueError(f"duplicate prim path: {prim_path}")
        self.prims[prim_path] = rec

    def create_xform(self, prim_path: str, world: Mat4, note: str = "") -> None:
        self._put(prim_path, {"type": "Xform", "world": np.asarray(world).tolist(), "note": note})

    def create_prim(self, prim_path: str, kind: str, size: dict[str, float],
                    world: Mat4, opts: dict[str, Any]) -> None:
        self._put(prim_path, {"type": kind, "size": dict(size),
                              "world": np.asarray(world).tolist(), **opts})

    def create_joint(self, prim_path: str, kind: str, parent_path: str, child_path: str,
                     axis, anchor, limits, drive: dict[str, Any]) -> None:
        if prim_path in self.joints:
            raise ValueError(f"duplicate joint path: {prim_path}")
        self.joints[prim_path] = {
            "kind": kind, "parent": parent_path, "child": child_path,
            "axis": list(np.asarray(axis, dtype=float)),
            "anchor": None if anchor is None else list(np.asarray(anchor, dtype=float)),
            "limits": None if limits is None else list(limits),
            "drive": dict(drive or {}),
        }

    def create_camera(self, prim_path: str, world: Mat4, opts: dict[str, Any]) -> None:
        self._put(prim_path, {"type": "Camera", "world": np.asarray(world).tolist(), **opts})

    def save(self, path: str | None = None) -> str | None:
        return None

    def dump(self) -> dict[str, Any]:
        return {"stage": self.stage_meta, "prims": self.prims, "joints": self.joints}
