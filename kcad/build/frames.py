"""Frame graph. THE ONLY place in the codebase where axes and poses are decided.

If you are about to write a translate/rotate anywhere else, you are creating the exact
bug this skill exists to prevent: a subassembly that carries its own idea of 'up' and
'forward' and silently desyncs from the rest of the machine when edited.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..spec.schema import Spec
from ..util.vecmath import Mat4, compose, identity, normalize, xform_dir, xform_point


@dataclass
class FrameGraph:
    spec: Spec
    world_of: dict[str, Mat4]

    def world(self, frame: str) -> Mat4:
        if frame in ("world", None):
            return identity()
        if frame not in self.world_of:
            raise KeyError(f"unknown frame {frame!r}")
        return self.world_of[frame]

    def point_in_world(self, frame: str, local=(0, 0, 0)):
        return xform_point(self.world(frame), local)

    def dir_in_world(self, frame: str, local_dir):
        return xform_dir(self.world(frame), local_dir)

    def origin(self, frame: str):
        return self.world(frame)[:3, 3]

    def up(self):
        return np.array([0.0, 1.0, 0.0]) if self.spec.up_axis == "Y" else np.array([0.0, 0.0, 1.0])

    def forward(self):
        sign = -1.0 if self.spec.forward_axis.startswith("-") else 1.0
        axis = self.spec.forward_axis[-1].upper()
        base = {"X": [1.0, 0, 0], "Y": [0, 1.0, 0], "Z": [0, 0, 1.0]}[axis]
        return sign * np.array(base)

    def lateral(self):
        """Right-hand cross product of up and forward: the 'sideways' axis."""
        return normalize(np.cross(self.up(), self.forward()))

    def height_of(self, frame: str) -> float:
        """Signed distance along the up axis. Used by most height invariants."""
        return float(np.dot(self.origin(frame), self.up()))


def build_frame_graph(spec: Spec) -> FrameGraph:
    world_of: dict[str, Mat4] = {}

    def resolve(name: str, stack: tuple[str, ...] = ()) -> Mat4:
        if name in world_of:
            return world_of[name]
        if name in stack:
            raise ValueError(f"frame cycle: {' -> '.join(stack + (name,))}")
        f = spec.frames[name]
        local = compose(translate=f.translate, rotate_xyz=f.rotate_xyz)
        parent = identity() if f.parent in (None, "world") else resolve(f.parent, stack + (name,))
        world_of[name] = parent @ local
        return world_of[name]

    for name in spec.frames:
        resolve(name)
    return FrameGraph(spec=spec, world_of=world_of)


def part_world_transform(fg: FrameGraph, part) -> Mat4:
    """World transform of a part instance 0 (frame * local offset/rotation)."""
    return fg.world(part.frame) @ compose(translate=part.offset, rotate_xyz=part.rotate_xyz)


def instance_transforms(fg: FrameGraph, part) -> list[Mat4]:
    """World transforms of every instance of a part (arrays included)."""
    base = part_world_transform(fg, part)
    if part.instances <= 1:
        return [base]
    if part.array_along_path:
        return _along_path(fg, part, base)
    out = []
    step = np.asarray(part.array_step, dtype=float)
    for i in range(part.instances):
        m = base.copy()
        m[:3, 3] = m[:3, 3] + xform_dir(fg.world(part.frame), step * i)
        out.append(m)
    return out


def _along_path(fg: FrameGraph, part, base: Mat4) -> list[Mat4]:
    from .paths import sample_path  # local import: paths depends on frames
    poses = sample_path(fg, fg.spec.paths[part.array_along_path], part.instances)
    return [p @ compose(translate=part.offset, rotate_xyz=part.rotate_xyz) for p in poses]
