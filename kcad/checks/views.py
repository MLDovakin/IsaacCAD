"""Canonical orthographic screenshots.

Screenshots are the SECOND verification step, never the first. And they are orthographic
from fixed poses: in a perspective view you cannot judge alignment, parallelism or a
15 mm offset by eye, in an ortho front/side/top you can.

Order enforced by the skill: invariants -> smoke sim -> views (for the human and video).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..util.vecmath import Mat4, identity, normalize

CANONICAL = ("front", "side", "top", "iso")


@dataclass
class ViewSpec:
    name: str
    direction: tuple[float, float, float]
    up: tuple[float, float, float]
    ortho: bool = True


def canonical_views(up_axis: str = "Z") -> list[ViewSpec]:
    if up_axis == "Z":
        return [
            ViewSpec("front", (0, 1, 0), (0, 0, 1)),
            ViewSpec("side", (-1, 0, 0), (0, 0, 1)),
            ViewSpec("top", (0, 0, -1), (0, 1, 0)),
            ViewSpec("iso", (-1, 1, -1), (0, 0, 1), ortho=False),
        ]
    return [
        ViewSpec("front", (0, 0, -1), (0, 1, 0)),
        ViewSpec("side", (-1, 0, 0), (0, 1, 0)),
        ViewSpec("top", (0, -1, 0), (0, 0, 1)),
        ViewSpec("iso", (-1, -1, -1), (0, 1, 0), ortho=False),
    ]


def scene_bounds(build_result) -> tuple[np.ndarray, np.ndarray]:
    from ..build.primitives import half_extents
    from ..util.vecmath import aabb_from_box
    los, his = [], []
    for name, part in build_result.spec.parts.items():
        if part.kind in ("camera", "light"):
            continue
        h = half_extents(part)
        for w in build_result.instance_world[name]:
            lo, hi = aabb_from_box(h, w)
            los.append(lo)
            his.append(hi)
    if not los:
        return np.zeros(3), np.ones(3)
    return np.min(np.array(los), axis=0), np.max(np.array(his), axis=0)


def camera_transform(build_result, view: ViewSpec, pad: float = 1.25) -> tuple[Mat4, float]:
    lo, hi = scene_bounds(build_result)
    center = (lo + hi) / 2.0
    radius = float(np.linalg.norm(hi - lo)) / 2.0 * pad
    d = normalize(view.direction)
    eye = center - d * max(radius * 3.0, 1.0)
    fwd = normalize(center - eye)
    up = np.asarray(view.up, dtype=float)
    right = normalize(np.cross(fwd, up))
    true_up = normalize(np.cross(right, fwd))
    m = identity()
    m[:3, 0] = right
    m[:3, 1] = true_up
    m[:3, 2] = -fwd            # USD cameras look down -Z
    m[:3, 3] = eye
    return m, radius * 2.0


def author_cameras(build_result, backend=None, pad: float = 1.25) -> dict[str, str]:
    """Create the canonical cameras in the stage; returns name -> prim path."""
    be = backend or build_result.backend
    out: dict[str, str] = {}
    root = f"{build_result.root}/views"
    be.create_xform(root, identity(), note="canonical review cameras")
    for v in canonical_views(build_result.spec.up_axis):
        m, aperture = camera_transform(build_result, v, pad)
        path = f"{root}/cam_{v.name}"
        be.create_camera(path, m, {"orthographic": v.ortho,
                                   "aperture_mm": aperture * 1000.0,
                                   "focal_mm": 24.0})
        out[v.name] = path
    return out


def capture(build_result, out_dir: str, resolution: tuple[int, int] = (1280, 720),
            views: tuple[str, ...] = CANONICAL) -> list[str]:
    """Render the canonical views. Requires Isaac Sim; returns written file paths."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    try:  # pragma: no cover - environment dependent
        import omni.replicator.core as rep
    except Exception:
        return []
    paths = author_cameras(build_result)
    written: list[str] = []
    for name in views:  # pragma: no cover
        cam = rep.create.camera(position=(0, 0, 0))
        rp = rep.create.render_product(paths[name], resolution)
        writer = rep.WriterRegistry.get("BasicWriter")
        writer.initialize(output_dir=str(Path(out_dir) / name), rgb=True)
        writer.attach([rp])
        rep.orchestrator.step()
        written.append(str(Path(out_dir) / name))
    return written
