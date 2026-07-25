"""Typed primitive wrappers.

Every part in a spec goes through exactly one of these functions, so 'what does size.x
mean for a cylinder' has one answer, everywhere. Add a new machine element by adding a
function here — never by hand-authoring prims in assembly code.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..spec.schema import Part
from ..util.vecmath import Mat4, as_vec3


def half_extents(part: Part) -> np.ndarray:
    """Local half-extents used for AABB-based invariants."""
    s = part.size
    if part.kind == "box":
        return np.array([s["x"], s["y"], s["z"]], dtype=float) / 2.0
    if part.kind in ("cylinder", "capsule"):
        r, h = float(s["radius"]), float(s["height"])
        extra = r if part.kind == "capsule" else 0.0
        return np.array([r, r, h / 2.0 + extra], dtype=float)
    if part.kind == "sphere":
        r = float(s["radius"])
        return np.array([r, r, r], dtype=float)
    if part.kind == "plane":
        return np.array([s["x"] / 2.0, s["y"] / 2.0, 1e-3], dtype=float)
    if part.kind == "mesh":
        bb = s.get("bbox")
        if bb:
            return as_vec3(bb) / 2.0
        return np.array([s.get("x", 0.1), s.get("y", 0.1), s.get("z", 0.1)], dtype=float) / 2.0
    return np.zeros(3, dtype=float)


def prim_options(part: Part) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "physics": part.physics,
        "collision": part.collision,
        "tags": list(part.tags),
    }
    if part.mass is not None:
        opts["mass"] = part.mass
    if part.material:
        opts["material"] = part.material
    if part.mesh:
        opts["mesh"] = part.mesh
    if part.note:
        opts["note"] = part.note
    return opts


def author(backend, prim_path: str, part: Part, world: Mat4) -> None:
    """Author one instance of `part` at `world` through the backend."""
    if part.kind == "camera":
        backend.create_camera(prim_path, world, prim_options(part))
    elif part.kind == "xform":
        backend.create_xform(prim_path, world, part.note)
    else:
        backend.create_prim(prim_path, part.kind, part.size, world, prim_options(part))


def describe(part: Part) -> str:
    s = ", ".join(f"{k}={v:.4g}" for k, v in sorted(part.size.items()))
    return f"{part.name}<{part.kind}>({s}) @frame={part.frame} physics={part.physics}"
