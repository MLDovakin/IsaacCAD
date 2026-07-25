"""Load + validate a spec YAML into the typed model."""
from __future__ import annotations

from pathlib import Path as FsPath
from typing import Any

import yaml

from .derive import DeriveError, evaluate_in, resolve
from .schema import Constraint, Frame, Joint, Part, Path, Spec


class SpecError(ValueError):
    pass


def load(path: str | FsPath) -> Spec:
    p = FsPath(path)
    if not p.exists():
        raise SpecError(f"spec not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    spec = from_dict(raw)
    spec.source_path = str(p.resolve())
    return spec


def from_dict(raw: dict[str, Any]) -> Spec:
    params = dict(raw.get("params") or {})
    derived = dict(raw.get("derived") or {})
    try:
        values = resolve(params, derived)
    except DeriveError as exc:
        raise SpecError(str(exc)) from exc

    scope = {k: v for k, v in values.items() if not k.startswith("_")}
    body = {k: evaluate_in(v, scope) for k, v in raw.items()
            if k not in {"params", "derived"}}

    spec = Spec(
        name=body.get("name", "machine"),
        units_length=body.get("units_length", "m"),
        up_axis=str(body.get("up_axis", "Z")).upper(),
        meters_per_unit=float(body.get("meters_per_unit", 1.0)),
        forward_axis=str(body.get("forward_axis", "+X")),
        params=params,
        derived=derived,
        values=values,
    )

    for name, d in (body.get("frames") or {}).items():
        spec.frames[name] = Frame.from_dict(name, d or {})
    for name, d in (body.get("paths") or {}).items():
        spec.paths[name] = Path.from_dict(name, d or {})
    for name, d in (body.get("parts") or {}).items():
        spec.parts[name] = Part.from_dict(name, d or {})
    for name, d in (body.get("joints") or {}).items():
        spec.joints[name] = Joint.from_dict(name, d or {})
    for d in (body.get("constraints") or []):
        spec.constraints.append(Constraint.from_dict(d))
    spec.runtime = body.get("runtime") or {}
    spec.views = body.get("views") or {}

    validate(spec)
    return spec


def validate(spec: Spec) -> None:
    """Structural validation. Geometry/kinematics live in checks/invariants.py."""
    errors: list[str] = []

    if spec.up_axis not in {"Y", "Z"}:
        errors.append(f"up_axis must be Y or Z, got {spec.up_axis!r}")
    if spec.forward_axis not in {"+X", "-X", "+Y", "-Y"}:
        errors.append(f"forward_axis must be one of +X/-X/+Y/-Y, got {spec.forward_axis!r}")

    # frame graph: parents exist, no cycles
    for f in spec.frames.values():
        if f.parent and f.parent != "world" and f.parent not in spec.frames:
            errors.append(f"frame {f.name!r}: unknown parent {f.parent!r}")
    for f in spec.frames.values():
        seen, cur, depth = {f.name}, f, 0
        while cur.parent and cur.parent != "world":
            if cur.parent in seen:
                errors.append(f"frame cycle through {f.name!r}")
                break
            if cur.parent not in spec.frames:
                break
            seen.add(cur.parent)
            cur = spec.frames[cur.parent]
            depth += 1
            if depth > 64:
                errors.append(f"frame chain too deep at {f.name!r}")
                break

    for p in spec.parts.values():
        if p.frame != "world" and p.frame not in spec.frames:
            errors.append(f"part {p.name!r}: unknown frame {p.frame!r}")
        if p.kind == "mesh" and not p.mesh:
            errors.append(f"part {p.name!r}: kind=mesh requires 'mesh' path")
        if p.instances > 1 and p.array_along_path is None and \
                all(abs(c) < 1e-12 for c in p.array_step):
            errors.append(f"part {p.name!r}: instances>1 needs array_step or array_along_path")
        if p.array_along_path and p.array_along_path not in spec.paths:
            errors.append(f"part {p.name!r}: unknown path {p.array_along_path!r}")
        _validate_size(p, errors)

    for j in spec.joints.values():
        for role in ("parent", "child"):
            ref = getattr(j, role)
            if ref != "world" and ref not in spec.parts:
                errors.append(f"joint {j.name!r}: unknown {role} part {ref!r}")
        if j.anchor_frame and j.anchor_frame not in spec.frames:
            errors.append(f"joint {j.name!r}: unknown anchor_frame {j.anchor_frame!r}")
        if j.kind in {"revolute", "prismatic"}:
            if sum(abs(c) for c in j.axis) < 1e-9:
                errors.append(f"joint {j.name!r}: degenerate axis {j.axis}")
            if j.limits and j.limits[0] > j.limits[1]:
                errors.append(f"joint {j.name!r}: limits reversed {j.limits}")

    for c in spec.constraints:
        if c.severity not in {"error", "warn"}:
            errors.append(f"constraint {c.name!r}: bad severity {c.severity!r}")

    if errors:
        raise SpecError("spec validation failed:\n  - " + "\n  - ".join(errors))


_REQUIRED_SIZE = {
    "box": ("x", "y", "z"),
    "cylinder": ("radius", "height"),
    "capsule": ("radius", "height"),
    "sphere": ("radius",),
    "plane": ("x", "y"),
}


def _validate_size(p: Part, errors: list[str]) -> None:
    req = _REQUIRED_SIZE.get(p.kind)
    if not req:
        return
    missing = [k for k in req if k not in p.size]
    if missing:
        errors.append(f"part {p.name!r} (kind={p.kind}): missing size keys {missing}")
    for k, v in p.size.items():
        if v <= 0:
            errors.append(f"part {p.name!r}: size.{k} must be > 0, got {v}")
