"""Minimal transform math. Column-vector convention: p_parent = T @ p_local."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

Vec3 = np.ndarray
Mat4 = np.ndarray


def vec3(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Vec3:
    return np.array([float(x), float(y), float(z)], dtype=float)


def as_vec3(v: Sequence[float] | None, default: Sequence[float] = (0.0, 0.0, 0.0)) -> Vec3:
    if v is None:
        v = default
    arr = np.asarray(v, dtype=float).reshape(-1)
    if arr.size != 3:
        raise ValueError(f"expected 3 components, got {arr.size}: {v!r}")
    return arr


def identity() -> Mat4:
    return np.eye(4, dtype=float)


def translation(t: Sequence[float]) -> Mat4:
    m = identity()
    m[:3, 3] = as_vec3(t)
    return m


def rot_axis_angle(axis: Sequence[float], degrees: float) -> Mat4:
    a = as_vec3(axis)
    n = np.linalg.norm(a)
    if n < 1e-12:
        raise ValueError(f"degenerate rotation axis: {axis!r}")
    a = a / n
    th = math.radians(float(degrees))
    c, s = math.cos(th), math.sin(th)
    x, y, z = a
    r = np.array(
        [
            [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
            [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
            [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
        ],
        dtype=float,
    )
    m = identity()
    m[:3, :3] = r
    return m


def rot_xyz(degrees: Sequence[float]) -> Mat4:
    """Intrinsic X, then Y, then Z. Degrees."""
    rx, ry, rz = as_vec3(degrees)
    return rot_axis_angle((0, 0, 1), rz) @ rot_axis_angle((0, 1, 0), ry) @ rot_axis_angle((1, 0, 0), rx)


def compose(translate: Sequence[float] | None = None,
            rotate_xyz: Sequence[float] | None = None,
            axis_angle: tuple[Sequence[float], float] | None = None) -> Mat4:
    t = translation(translate or (0, 0, 0))
    if axis_angle is not None:
        r = rot_axis_angle(axis_angle[0], axis_angle[1])
    else:
        r = rot_xyz(rotate_xyz or (0, 0, 0))
    return t @ r


def xform_point(m: Mat4, p: Sequence[float]) -> Vec3:
    v = np.ones(4, dtype=float)
    v[:3] = as_vec3(p)
    return (m @ v)[:3]


def xform_dir(m: Mat4, d: Sequence[float]) -> Vec3:
    return m[:3, :3] @ as_vec3(d)


def normalize(v: Sequence[float]) -> Vec3:
    a = as_vec3(v)
    n = float(np.linalg.norm(a))
    if n < 1e-12:
        raise ValueError(f"cannot normalize zero-length vector {v!r}")
    return a / n


def angle_between(a: Sequence[float], b: Sequence[float]) -> float:
    """Degrees."""
    ua, ub = normalize(a), normalize(b)
    return math.degrees(math.acos(float(np.clip(np.dot(ua, ub), -1.0, 1.0))))


def aabb_from_box(half: Sequence[float], m: Mat4, center: Sequence[float] = (0, 0, 0)):
    """World AABB of a local box (half-extents) placed by transform m."""
    c = as_vec3(center)
    h = as_vec3(half)
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                corners.append(xform_point(m, c + h * np.array([sx, sy, sz], dtype=float)))
    arr = np.array(corners)
    return arr.min(axis=0), arr.max(axis=0)


def aabb_penetration(a_min, a_max, b_min, b_max) -> Vec3:
    """Per-axis overlap. All components > 0 means the boxes intersect."""
    return np.minimum(a_max, b_max) - np.maximum(a_min, b_min)


def fmt_vec(v: Iterable[float], nd: int = 4) -> str:
    return "[" + ", ".join(f"{x:.{nd}f}" for x in v) + "]"
