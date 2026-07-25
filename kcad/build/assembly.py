"""Idempotent full rebuild.

The central rule of this skill: THE SCENE IS NEVER EDITED IN PLACE, IT IS REBUILT.
Edits go into the spec; `build()` wipes the machine root and re-authors everything from
the spec. That is what makes 'change one subassembly' safe — there is no partially
updated state for the rest of the machine to disagree with.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..spec.schema import Spec
from ..util.vecmath import Mat4
from . import primitives
from .backends import get_backend
from .frames import FrameGraph, build_frame_graph, instance_transforms
from .joints import author_joints


@dataclass
class BuildResult:
    spec: Spec
    frames: FrameGraph
    backend: Any
    root: str
    path_of_part: dict[str, str] = field(default_factory=dict)
    instance_paths: dict[str, list[str]] = field(default_factory=dict)
    instance_world: dict[str, list[Mat4]] = field(default_factory=dict)

    @property
    def prims(self) -> dict[str, Any]:
        return self.backend.dump().get("prims", {})

    def world_of_instance(self, part_name: str, index: int = 0) -> Mat4:
        return self.instance_world[part_name][index]


def build(spec: Spec, backend: str | Any = "null", root: str | None = None,
          layer: str | None = None, **backend_kwargs) -> BuildResult:
    be = get_backend(backend, **backend_kwargs) if isinstance(backend, str) else backend
    root = root or f"/World/{_sanitize(spec.name)}"

    be.open_stage(spec, layer=layer)
    be.clear(root)

    fg = build_frame_graph(spec)
    res = BuildResult(spec=spec, frames=fg, backend=be, root=root)

    be.create_xform(root, fg.world("world") if "world" in spec.frames else _identity(),
                    note=f"kcad root; up={spec.up_axis}; forward={spec.forward_axis}")

    # frames first: they are the skeleton every part hangs from
    be.create_xform(f"{root}/frames", _identity(), note="frame graph")
    for name, frame in spec.frames.items():
        be.create_xform(f"{root}/frames/{_sanitize(name)}", fg.world(name), note=frame.note)

    be.create_xform(f"{root}/parts", _identity(), note="geometry")
    for name, part in spec.parts.items():
        worlds = instance_transforms(fg, part)
        base = f"{root}/parts/{_sanitize(name)}"
        res.path_of_part[name] = base
        res.instance_world[name] = worlds
        if len(worlds) == 1:
            primitives.author(be, base, part, worlds[0])
            res.instance_paths[name] = [base]
        else:
            be.create_xform(base, _identity(), note=f"array of {len(worlds)}")
            paths = []
            for i, w in enumerate(worlds):
                p = f"{base}/inst_{i:03d}"
                primitives.author(be, p, part, w)
                paths.append(p)
            res.instance_paths[name] = paths
            res.path_of_part[name] = paths[0]

    if spec.joints:
        be.create_xform(f"{root}/joints", _identity(), note="kinematics")
        author_joints(be, spec, fg, root, res.path_of_part)

    return res


def rebuild(spec_path: str, **kwargs) -> BuildResult:
    """Convenience: load spec from disk and rebuild. Use this, not partial edits."""
    from ..spec.loader import load
    return build(load(spec_path), **kwargs)


def _identity() -> Mat4:
    from ..util.vecmath import identity
    return identity()


def _sanitize(name: str) -> str:
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    return out if out and not out[0].isdigit() else f"_{out}"
