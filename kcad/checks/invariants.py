"""Generic geometric and kinematic invariants.

These encode design intent as machine-checkable statements. Domain-specific intent
("the carrier deck must clear the cage rim") is expressed by composing these generic
kinds in the spec, or by adding project checks in <project>/checks/.

RULE: when a check fails, fix the spec. Never relax the check to make it pass — that is
the single fastest way to quietly destroy a working assembly.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..build.frames import instance_transforms
from ..build.joints import joint_axis_world
from ..build.primitives import half_extents
from ..util.vecmath import aabb_from_box, aabb_penetration, angle_between, normalize
from .framework import CheckResult, check

# ---------------------------------------------------------------- structural


@check("frames_resolve")
def frames_resolve(br, **_) -> CheckResult:
    bad = []
    for name in br.spec.frames:
        m = br.frames.world(name)
        if not np.all(np.isfinite(m)):
            bad.append(name)
    return CheckResult("frames_resolve", not bad,
                       "" if not bad else f"non-finite frame transforms: {bad}",
                       {"frames": len(br.spec.frames)})


@check("unique_prim_paths")
def unique_prim_paths(br, **_) -> CheckResult:
    paths = list(br.prims.keys())
    dupes = {p for p in paths if paths.count(p) > 1}
    return CheckResult("unique_prim_paths", not dupes,
                       "" if not dupes else f"duplicate prim paths: {sorted(dupes)}",
                       {"prims": len(paths)})


@check("finite_transforms")
def finite_transforms(br, **_) -> CheckResult:
    bad = [name for name, worlds in br.instance_world.items()
           if not all(np.all(np.isfinite(w)) for w in worlds)]
    return CheckResult("finite_transforms", not bad,
                       "" if not bad else f"non-finite part transforms: {bad}")


@check("joint_axes_sane")
def joint_axes_sane(br, **_) -> CheckResult:
    bad = []
    for j in br.spec.joints.values():
        if j.kind not in ("revolute", "prismatic"):
            continue
        a = np.asarray(j.axis, dtype=float)
        n = float(np.linalg.norm(a))
        if n < 1e-9 or not math.isfinite(n):
            bad.append(f"{j.name}: degenerate axis")
            continue
        w = joint_axis_world(br.spec, br.frames, j)
        if abs(float(np.linalg.norm(w)) - 1.0) > 1e-6:
            bad.append(f"{j.name}: world axis not unit ({np.linalg.norm(w):.6f})")
    return CheckResult("joint_axes_sane", not bad, "; ".join(bad),
                       {"joints": len(br.spec.joints)})


# ------------------------------------------------------------------- heights


@check("height")
def height_check(br, frame: str | None = None, part: str | None = None,
                 min: float | None = None, max: float | None = None, **_) -> CheckResult:
    """Signed height along the up axis of a frame or part origin."""
    h = _height_of(br, frame=frame, part=part)
    ok = True
    msgs = []
    if min is not None and h < float(min) - 1e-9:
        ok = False
        msgs.append(f"{h*1000:.1f}mm < min {float(min)*1000:.1f}mm")
    if max is not None and h > float(max) + 1e-9:
        ok = False
        msgs.append(f"{h*1000:.1f}mm > max {float(max)*1000:.1f}mm")
    label = frame or part
    return CheckResult(f"height[{label}]", ok,
                       ", ".join(msgs) or f"h={h*1000:.1f}mm", {"height_m": h})


@check("clearance")
def clearance_check(br, a: str, b: str, axis: str = "up",
                    min: float | None = None, max: float | None = None, **_) -> CheckResult:
    """Gap between two parts measured along an axis: 'up', 'forward', 'lateral' or a vector."""
    d = _axis_vector(br, axis)
    gap = _gap_along(br, a, b, d)
    ok = True
    msgs = []
    if min is not None and gap < float(min) - 1e-9:
        ok = False
        msgs.append(f"gap {gap*1000:.1f}mm < min {float(min)*1000:.1f}mm")
    if max is not None and gap > float(max) + 1e-9:
        ok = False
        msgs.append(f"gap {gap*1000:.1f}mm > max {float(max)*1000:.1f}mm")
    return CheckResult(f"clearance[{a}|{b}]", ok,
                       ", ".join(msgs) or f"gap={gap*1000:.1f}mm", {"gap_m": gap})


# ------------------------------------------------------------------ geometry


@check("no_interpenetration")
def no_interpenetration(br, ignore_pairs: list[list[str]] | None = None,
                        ignore_tags: list[str] | None = None,
                        tolerance: float = 0.0, **_) -> CheckResult:
    """AABB overlap test over all part instances in the rest pose."""
    ignore = {tuple(sorted(p)) for p in (ignore_pairs or [])}
    skip_tags = set(ignore_tags or [])
    boxes: list[tuple[str, np.ndarray, np.ndarray, set[str]]] = []
    for name, part in br.spec.parts.items():
        if part.kind in ("camera", "light", "xform") or not part.collision:
            continue
        if skip_tags & set(part.tags):
            continue
        h = half_extents(part)
        for i, w in enumerate(br.instance_world[name]):
            lo, hi = aabb_from_box(h, w)
            label = name if len(br.instance_world[name]) == 1 else f"{name}[{i}]"
            boxes.append((label, lo, hi, set(part.tags)))

    hits = []
    for i in range(len(boxes)):
        for k in range(i + 1, len(boxes)):
            n1, lo1, hi1, _ = boxes[i]
            n2, lo2, hi2, _ = boxes[k]
            base1, base2 = n1.split("[")[0], n2.split("[")[0]
            if base1 == base2 or tuple(sorted((base1, base2))) in ignore:
                continue
            pen = aabb_penetration(lo1, hi1, lo2, hi2)
            if np.all(pen > tolerance):
                hits.append(f"{n1}~{n2} ({float(pen.min())*1000:.1f}mm)")
    return CheckResult("no_interpenetration", not hits,
                       "" if not hits else "overlaps: " + ", ".join(hits[:8]),
                       {"pairs_tested": len(boxes) * (len(boxes) - 1) // 2,
                        "overlaps": len(hits)})


@check("inside_workspace")
def inside_workspace(br, bounds: dict[str, list[float]], parts: list[str] | None = None,
                     tags: list[str] | None = None, **_) -> CheckResult:
    """Every selected part instance must sit inside an axis-aligned world box."""
    lo = np.asarray(bounds["min"], dtype=float)
    hi = np.asarray(bounds["max"], dtype=float)
    names = _select_parts(br, parts, tags)
    out = []
    for name in names:
        part = br.spec.parts[name]
        h = half_extents(part)
        for i, w in enumerate(br.instance_world[name]):
            blo, bhi = aabb_from_box(h, w)
            if np.any(blo < lo - 1e-9) or np.any(bhi > hi + 1e-9):
                out.append(f"{name}[{i}]")
    return CheckResult("inside_workspace", not out,
                       "" if not out else f"outside bounds: {out[:8]}",
                       {"checked": len(names)})


@check("axis_angle_between")
def axis_angle_between(br, a: str, b: str, expect_deg: float = 90.0,
                       tol_deg: float = 0.5, **_) -> CheckResult:
    """Angle between two direction sources: 'joint:<name>', 'frame:<name>:<x|y|z>',
    'axis:up|forward|lateral', or a literal [x,y,z]. Catches inverted / rotated axes."""
    va, vb = _direction(br, a), _direction(br, b)
    ang = angle_between(va, vb)
    ok = abs(ang - float(expect_deg)) <= float(tol_deg)
    return CheckResult(f"axis_angle[{a}|{b}]", ok,
                       f"{ang:.3f}deg (expected {float(expect_deg)}±{tol_deg})",
                       {"angle_deg": ang})


@check("joint_axis_direction")
def joint_axis_direction(br, joint: str, expect: Any = "lateral",
                         tol_deg: float = 0.5, allow_flip: bool = False, **_) -> CheckResult:
    """The classic bug guard: a joint whose axis silently points the wrong way."""
    j = br.spec.joints[joint]
    got = joint_axis_world(br.spec, br.frames, j)
    want = normalize(_direction(br, expect if isinstance(expect, str) else expect))
    ang = angle_between(got, want)
    if allow_flip:
        ang = min(ang, 180.0 - ang)
    ok = ang <= float(tol_deg)
    return CheckResult(f"joint_axis[{joint}]", ok,
                       f"off by {ang:.3f}deg from {expect}", {"angle_deg": ang})


@check("relative_pose")
def relative_pose(br, a: str, b: str, expect_translate: list[float] | None = None,
                  tol: float = 1e-3, **_) -> CheckResult:
    """Vector from a to b (frames or parts), compared with an expected offset."""
    pa, pb = _origin_of(br, a), _origin_of(br, b)
    d = pb - pa
    if expect_translate is None:
        return CheckResult(f"relative_pose[{a}->{b}]", True,
                           f"delta={d*1000}mm", {"delta_m": d.tolist()})
    e = np.asarray(expect_translate, dtype=float)
    err = float(np.linalg.norm(d - e))
    return CheckResult(f"relative_pose[{a}->{b}]", err <= float(tol),
                       f"error {err*1000:.2f}mm", {"error_m": err, "delta_m": d.tolist()})


@check("array_pitch")
def array_pitch(br, part: str, min_pitch: float | None = None,
                expect_pitch: float | None = None, tol: float = 1e-3, **_) -> CheckResult:
    """Spacing between consecutive instances of an arrayed part (carriers, rollers, cells)."""
    worlds = br.instance_world[part]
    if len(worlds) < 2:
        return CheckResult(f"array_pitch[{part}]", False, "fewer than 2 instances")
    d = [float(np.linalg.norm(worlds[i + 1][:3, 3] - worlds[i][:3, 3]))
         for i in range(len(worlds) - 1)]
    lo, hi = min(d), max(d)
    msgs, ok = [], True
    if min_pitch is not None and lo < float(min_pitch) - 1e-9:
        ok = False
        msgs.append(f"min pitch {lo*1000:.1f}mm < {float(min_pitch)*1000:.1f}mm")
    if expect_pitch is not None and abs(lo - float(expect_pitch)) > float(tol):
        ok = False
        msgs.append(f"pitch {lo*1000:.1f}mm != expected {float(expect_pitch)*1000:.1f}mm")
    return CheckResult(f"array_pitch[{part}]", ok,
                       ", ".join(msgs) or f"pitch {lo*1000:.1f}..{hi*1000:.1f}mm",
                       {"min_m": lo, "max_m": hi})


@check("path_closed")
def path_closed(br, path: str, tol: float = 1e-6, **_) -> CheckResult:
    """A carousel/loop must actually close, or instances drift over a full revolution."""
    from ..build.paths import path_points_world, total_length
    p = br.spec.paths[path]
    if not p.closed:
        return CheckResult(f"path_closed[{path}]", False, "path is not declared closed")
    pts = path_points_world(br.frames, p)
    closing = float(np.linalg.norm(pts[0] - pts[-1]))
    length = total_length(br.frames, p)
    degenerate = length <= 0 or len(pts) < 3
    return CheckResult(f"path_closed[{path}]", not degenerate,
                       f"loop length {length*1000:.1f}mm, "
                       f"closing segment {closing*1000:.1f}mm, {len(pts)} vertices",
                       {"length_m": length, "closing_m": closing, "vertices": len(pts)})


@check("capacity_fits")
def capacity_fits(br, path: str, count: int, item_size: float,
                  extra: float = 0.0, **_) -> CheckResult:
    """N items of given footprint (+margin) must fit on a path without touching."""
    from ..build.paths import total_length
    length = total_length(br.frames, br.spec.paths[path])
    need = int(count) * (float(item_size) + float(extra))
    return CheckResult(f"capacity_fits[{path}]", need <= length + 1e-9,
                       f"needs {need*1000:.0f}mm of {length*1000:.0f}mm",
                       {"need_m": need, "have_m": length})


# ------------------------------------------------------------------- physics


@check("no_slip_on_incline")
def no_slip_on_incline(br, angle_deg: float, friction: float, margin: float = 1.2,
                       **_) -> CheckResult:
    """tan(theta) < mu / margin — an object must not slide down a tilted surface."""
    t = math.tan(math.radians(float(angle_deg)))
    limit = float(friction) / float(margin)
    return CheckResult("no_slip_on_incline", t < limit,
                       f"tan={t:.3f} vs mu/margin={limit:.3f}",
                       {"tan": t, "limit": limit})


@check("no_tipover_on_incline")
def no_tipover_on_incline(br, angle_deg: float, base: float, height: float,
                          margin: float = 1.5, **_) -> CheckResult:
    """tan(theta) < (base/height)/margin — a tall item must not topple on a ramp."""
    t = math.tan(math.radians(float(angle_deg)))
    limit = (float(base) / float(height)) / float(margin)
    return CheckResult("no_tipover_on_incline", t < limit,
                       f"tan={t:.3f} vs (base/height)/margin={limit:.3f}",
                       {"tan": t, "limit": limit})


@check("projectile_lands_in")
def projectile_lands_in(br, speed: float, drop: float, target_min: float,
                        target_max: float, carrier_speed: float = 0.0,
                        along_min: float | None = None,
                        along_max: float | None = None, g: float = 9.80665,
                        **_) -> CheckResult:
    """Ballistic release: does the item land inside the receiver footprint?

    Generic: 'thrown/ejected item with horizontal speed falls by `drop`'. Applies to
    cross-belt ejection, chute drops, pusher discharge, part rejection bins.
    """
    t = math.sqrt(2.0 * float(drop) / float(g))
    x = float(speed) * t
    ok = float(target_min) <= x <= float(target_max)
    msgs = [f"lateral {x*1000:.0f}mm in [{float(target_min)*1000:.0f}, "
            f"{float(target_max)*1000:.0f}] (t={t:.3f}s)"]
    vals = {"flight_s": t, "lateral_m": x}
    if carrier_speed:
        y = float(carrier_speed) * t
        vals["along_m"] = y
        msgs.append(f"along-track drift {y*1000:.0f}mm")
        if along_min is not None and along_max is not None:
            ok = ok and (float(along_min) <= y <= float(along_max))
    return CheckResult("projectile_lands_in", ok, "; ".join(msgs), vals)


@check("cycle_time")
def cycle_time(br, distance: float, speed: float, max_time: float | None = None,
               min_time: float | None = None, **_) -> CheckResult:
    t = float(distance) / float(speed)
    ok = True
    msgs = [f"t={t:.3f}s"]
    if max_time is not None and t > float(max_time):
        ok = False
        msgs.append(f"> max {max_time}s")
    if min_time is not None and t < float(min_time):
        ok = False
        msgs.append(f"< min {min_time}s")
    return CheckResult("cycle_time", ok, " ".join(msgs), {"time_s": t})


@check("actuator_window")
def actuator_window(br, available_time: float, actuator_time: float,
                    margin: float = 1.5, **_) -> CheckResult:
    """The command must complete before the part leaves the station."""
    need = float(actuator_time) * float(margin)
    return CheckResult("actuator_window", need <= float(available_time),
                       f"needs {need*1000:.0f}ms of {float(available_time)*1000:.0f}ms",
                       {"need_s": need, "have_s": float(available_time)})


@check("expr")
def expr_check(br, expression: str, **_) -> CheckResult:
    """Escape hatch: any boolean expression over spec values. Prefer a typed check."""
    from ..spec.derive import _eval, _SAFE_FUNCS
    scope = {**_SAFE_FUNCS, **{k: v for k, v in br.spec.values.items()
                               if not k.startswith("_")}}
    val = _eval(expression, scope)
    return CheckResult(f"expr[{expression}]", bool(val), f"= {val}", {"value": val})


# ------------------------------------------------------------------- helpers


def _select_parts(br, parts, tags) -> list[str]:
    if parts:
        return list(parts)
    if tags:
        return [p.name for p in br.spec.parts.values() if set(tags) & set(p.tags)]
    return list(br.spec.parts.keys())


def _origin_of(br, ref: str) -> np.ndarray:
    if ref.startswith("frame:"):
        return br.frames.origin(ref.split(":", 1)[1])
    if ref.startswith("part:"):
        return br.instance_world[ref.split(":", 1)[1]][0][:3, 3]
    if ref in br.spec.frames:
        return br.frames.origin(ref)
    if ref in br.spec.parts:
        return br.instance_world[ref][0][:3, 3]
    raise KeyError(f"unknown frame/part reference {ref!r}")


def _height_of(br, frame=None, part=None) -> float:
    up = br.frames.up()
    if frame:
        return float(np.dot(br.frames.origin(frame), up))
    if part:
        return float(np.dot(br.instance_world[part][0][:3, 3], up))
    raise ValueError("height check needs 'frame' or 'part'")


def _axis_vector(br, axis) -> np.ndarray:
    if isinstance(axis, (list, tuple, np.ndarray)):
        return normalize(axis)
    return {"up": br.frames.up(), "forward": br.frames.forward(),
            "lateral": br.frames.lateral()}[axis]


def _direction(br, ref) -> np.ndarray:
    if isinstance(ref, (list, tuple, np.ndarray)):
        return normalize(ref)
    if ref.startswith("joint:"):
        j = br.spec.joints[ref.split(":", 1)[1]]
        return joint_axis_world(br.spec, br.frames, j)
    if ref.startswith("frame:"):
        _, name, comp = ref.split(":")
        col = {"x": 0, "y": 1, "z": 2}[comp.lower()]
        return normalize(br.frames.world(name)[:3, col])
    if ref.startswith("axis:"):
        return _axis_vector(br, ref.split(":", 1)[1])
    return _axis_vector(br, ref)


def _gap_along(br, a: str, b: str, axis: np.ndarray) -> float:
    """Signed clearance between the AABBs of two parts projected on `axis`."""
    def extent(name):
        part = br.spec.parts[name]
        h = half_extents(part)
        projections = []
        for w in br.instance_world[name]:
            lo, hi = aabb_from_box(h, w)
            corners = np.array([[lo[0], lo[1], lo[2]], [hi[0], hi[1], hi[2]],
                                [lo[0], hi[1], lo[2]], [hi[0], lo[1], hi[2]],
                                [lo[0], lo[1], hi[2]], [hi[0], hi[1], lo[2]],
                                [lo[0], hi[1], hi[2]], [hi[0], lo[1], lo[2]]])
            projections.extend((corners @ axis).tolist())
        return min(projections), max(projections)

    a_lo, a_hi = extent(a)
    b_lo, b_hi = extent(b)
    if a_hi <= b_lo:
        return b_lo - a_hi
    if b_hi <= a_lo:
        return a_lo - b_hi
    return -(min(a_hi, b_hi) - max(a_lo, b_lo))
