"""Joints, drives, articulation.

Joint axes are always expressed in the PARENT part's frame and converted to world here.
Nothing else in the codebase converts a joint axis — that single-conversion rule is what
makes the 'inverted axis' class of bug detectable by an invariant instead of by eye.
"""
from __future__ import annotations

import numpy as np

from ..spec.schema import Joint, Spec
from ..util.vecmath import normalize, xform_dir
from .frames import FrameGraph, part_world_transform


def joint_axis_world(spec: Spec, fg: FrameGraph, joint: Joint) -> np.ndarray:
    """Unit axis in world coordinates."""
    if joint.parent == "world":
        return normalize(joint.axis)
    parent = spec.parts[joint.parent]
    return normalize(xform_dir(part_world_transform(fg, parent), joint.axis))


def joint_anchor_world(spec: Spec, fg: FrameGraph, joint: Joint):
    if joint.anchor_frame:
        return fg.origin(joint.anchor_frame)
    child = spec.parts.get(joint.child)
    if child is None:
        return None
    return part_world_transform(fg, child)[:3, 3]


def author_joints(backend, spec: Spec, fg: FrameGraph, root: str,
                  path_of_part: dict[str, str]) -> None:
    for joint in spec.joints.values():
        parent_path = "world" if joint.parent == "world" else path_of_part[joint.parent]
        child_path = path_of_part[joint.child]
        backend.create_joint(
            prim_path=f"{root}/joints/{joint.name}",
            kind=joint.kind,
            parent_path=parent_path,
            child_path=child_path,
            axis=joint_axis_world(spec, fg, joint),
            anchor=joint_anchor_world(spec, fg, joint),
            limits=joint.limits,
            drive=joint.drive,
        )


def actuated_joints(spec: Spec) -> list[Joint]:
    return [j for j in spec.joints.values() if j.drive]
