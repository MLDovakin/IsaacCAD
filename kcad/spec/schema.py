"""Typed model of a machine spec. This is the single source of truth for a project.

Nothing here is domain-specific: a spec describes frames, parts, joints, actuators and
declared constraints. A conveyor, a gantry, a pick-and-drop cell and a test rig all fit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..util import units
from ..util.vecmath import as_vec3

PrimKind = Literal["box", "cylinder", "capsule", "sphere", "plane", "mesh", "xform", "camera", "light"]
JointKind = Literal["fixed", "revolute", "prismatic", "spherical", "free"]


@dataclass
class Frame:
    """A named coordinate frame. The ONLY place poses are expressed.

    Parts never carry absolute world coordinates; they attach to a frame. This is what
    makes 'edit one subassembly' safe: moving a frame moves everything under it.
    """
    name: str
    parent: str | None = None          # None => world
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)   # metres, in parent frame
    rotate_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)  # degrees, intrinsic X->Y->Z
    note: str = ""

    @staticmethod
    def from_dict(name: str, d: dict[str, Any]) -> "Frame":
        t = [units.length(v) for v in (d.get("translate") or (0, 0, 0))]
        r = [units.angle(v) for v in (d.get("rotate_xyz") or (0, 0, 0))]
        return Frame(
            name=name,
            parent=d.get("parent"),
            translate=tuple(as_vec3(t)),
            rotate_xyz=tuple(as_vec3(r)),
            note=d.get("note", ""),
        )


@dataclass
class Part:
    """A rigid body or a piece of visual geometry attached to a frame."""
    name: str
    frame: str
    kind: PrimKind = "box"
    size: dict[str, float] = field(default_factory=dict)   # metres; keys depend on kind
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)   # metres, inside the frame
    rotate_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    physics: str = "static"            # static | rigid | kinematic | visual
    mass: float | None = None
    collision: bool = True
    mesh: str | None = None            # for kind == mesh
    material: str | None = None
    instances: int = 1                 # >1 => array (see array_* fields)
    array_step: tuple[float, float, float] = (0.0, 0.0, 0.0)
    array_along_path: str | None = None   # name of a path in spec.paths
    tags: list[str] = field(default_factory=list)
    note: str = ""

    @staticmethod
    def from_dict(name: str, d: dict[str, Any]) -> "Part":
        size = {k: units.length(v) for k, v in (d.get("size") or {}).items()}
        return Part(
            name=name,
            frame=d["frame"],
            kind=d.get("kind", "box"),
            size=size,
            offset=tuple(as_vec3([units.length(v) for v in (d.get("offset") or (0, 0, 0))])),
            rotate_xyz=tuple(as_vec3([units.angle(v) for v in (d.get("rotate_xyz") or (0, 0, 0))])),
            physics=d.get("physics", "static"),
            mass=units.mass(d["mass"]) if d.get("mass") is not None else None,
            collision=bool(d.get("collision", True)),
            mesh=d.get("mesh"),
            material=d.get("material"),
            instances=int(d.get("instances", 1)),
            array_step=tuple(as_vec3([units.length(v) for v in (d.get("array_step") or (0, 0, 0))])),
            array_along_path=d.get("array_along_path"),
            tags=list(d.get("tags") or []),
            note=d.get("note", ""),
        )


@dataclass
class Joint:
    """A kinematic connection. Axis is expressed in the PARENT part's frame, always."""
    name: str
    kind: JointKind
    parent: str                      # part name ('world' allowed)
    child: str                       # part name
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    anchor_frame: str | None = None  # frame whose origin is the joint anchor
    limits: tuple[float, float] | None = None   # deg for revolute, m for prismatic
    drive: dict[str, Any] = field(default_factory=dict)  # type/target/stiffness/damping/max_force
    note: str = ""

    @staticmethod
    def from_dict(name: str, d: dict[str, Any]) -> "Joint":
        lim = d.get("limits")
        if lim is not None:
            kind = d.get("kind", "revolute")
            conv = units.angle if kind == "revolute" else units.length
            lim = (conv(lim[0]), conv(lim[1]))
        return Joint(
            name=name,
            kind=d.get("kind", "fixed"),
            parent=d["parent"],
            child=d["child"],
            axis=tuple(as_vec3(d.get("axis") or (0, 0, 1))),
            anchor_frame=d.get("anchor_frame"),
            limits=lim,
            drive=dict(d.get("drive") or {}),
            note=d.get("note", ""),
        )


@dataclass
class Path:
    """A polyline / closed loop used to array parts (rails, carousels, tracks)."""
    name: str
    frame: str = "world"
    points: list[tuple[float, float, float]] = field(default_factory=list)
    closed: bool = False

    @staticmethod
    def from_dict(name: str, d: dict[str, Any]) -> "Path":
        pts = [tuple(as_vec3([units.length(c) for c in p])) for p in (d.get("points") or [])]
        return Path(name=name, frame=d.get("frame", "world"), points=pts,
                    closed=bool(d.get("closed", False)))


@dataclass
class Constraint:
    """A declared design intent, checked by checks/invariants.py.

    This is the mechanism that stops an edit to one subassembly from silently breaking
    the rest: the intent lives in the spec, not in someone's head or a chat transcript.
    """
    name: str
    kind: str                        # see checks/invariants.py for the registry
    args: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"          # error | warn
    note: str = ""

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Constraint":
        args = {k: v for k, v in d.items() if k not in {"name", "kind", "severity", "note"}}
        return Constraint(name=d.get("name") or d["kind"], kind=d["kind"], args=args,
                          severity=d.get("severity", "error"), note=d.get("note", ""))


@dataclass
class Spec:
    name: str = "machine"
    units_length: str = "m"
    up_axis: str = "Z"
    meters_per_unit: float = 1.0
    forward_axis: str = "+X"
    params: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, str] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)    # params + derived, resolved
    frames: dict[str, Frame] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    joints: dict[str, Joint] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    views: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None

    def value(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def parts_with_tag(self, tag: str) -> list[Part]:
        return [p for p in self.parts.values() if tag in p.tags]
