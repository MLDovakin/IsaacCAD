"""Polyline paths: rails, carousels, tracks. Used to array parts evenly."""
from __future__ import annotations

import numpy as np

from ..util.vecmath import Mat4, identity, normalize
from .frames import FrameGraph


def path_points_world(fg: FrameGraph, path) -> np.ndarray:
    m = fg.world(path.frame)
    pts = [(m @ np.array([p[0], p[1], p[2], 1.0]))[:3] for p in path.points]
    return np.array(pts)


def segment_lengths(pts: np.ndarray, closed: bool) -> np.ndarray:
    idx = list(range(len(pts))) + ([0] if closed else [])
    seq = pts[idx]
    return np.linalg.norm(np.diff(seq, axis=0), axis=1)


def total_length(fg: FrameGraph, path) -> float:
    pts = path_points_world(fg, path)
    if len(pts) < 2:
        return 0.0
    return float(segment_lengths(pts, path.closed).sum())


def point_at(fg: FrameGraph, path, s: float):
    """Point and unit tangent at arc-length s (wraps if the path is closed)."""
    pts = path_points_world(fg, path)
    if len(pts) < 2:
        return pts[0] if len(pts) else np.zeros(3), np.array([1.0, 0, 0])
    segs = segment_lengths(pts, path.closed)
    total = float(segs.sum())
    if path.closed:
        s = s % total
    s = float(np.clip(s, 0.0, total))
    acc = 0.0
    order = list(range(len(pts))) + ([0] if path.closed else [])
    for i in range(len(segs)):
        if acc + segs[i] >= s or i == len(segs) - 1:
            a, b = pts[order[i]], pts[order[i + 1]]
            t = 0.0 if segs[i] < 1e-12 else (s - acc) / segs[i]
            return a + (b - a) * t, normalize(b - a)
        acc += segs[i]
    return pts[-1], normalize(pts[-1] - pts[-2])


def sample_path(fg: FrameGraph, path, count: int) -> list[Mat4]:
    """`count` evenly spaced poses along the path, oriented tangent-forward, up = frame up."""
    total = total_length(fg, path)
    if count <= 0 or total <= 0:
        return [identity()]
    step = total / count if path.closed else (total / max(count - 1, 1))
    up = fg.up()
    out: list[Mat4] = []
    for i in range(count):
        p, tang = point_at(fg, path, i * step)
        side = np.cross(up, tang)
        if np.linalg.norm(side) < 1e-9:
            side = np.array([0.0, 1.0, 0.0])
        side = normalize(side)
        true_up = normalize(np.cross(tang, side))
        m = identity()
        m[:3, 0] = tang
        m[:3, 1] = side
        m[:3, 2] = true_up
        m[:3, 3] = p
        out.append(m)
    return out
