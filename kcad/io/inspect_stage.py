"""Compact, machine-readable dump of the ACTUAL scene state.

This is the most under-rated file in the toolkit. Without it, an agent editing the scene
is guessing what is in the stage and reconstructing it from memory of the conversation.
With it, 'read the current state' is one command and a few hundred lines of text.

Rule of the skill: read this BEFORE proposing any edit.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np


def dump_build(build_result, max_prims: int = 400) -> dict[str, Any]:
    br = build_result
    prims = []
    for name, part in br.spec.parts.items():
        worlds = br.instance_world[name]
        w0 = np.asarray(worlds[0])
        prims.append({
            "part": name,
            "kind": part.kind,
            "frame": part.frame,
            "instances": len(worlds),
            "world_t": [round(float(v), 6) for v in w0[:3, 3]],
            "world_x": [round(float(v), 4) for v in w0[:3, 0]],
            "world_z": [round(float(v), 4) for v in w0[:3, 2]],
            "size": {k: round(float(v), 6) for k, v in part.size.items()},
            "physics": part.physics,
            "tags": part.tags,
        })
    frames = []
    for name, f in br.spec.frames.items():
        m = np.asarray(br.frames.world(name))
        frames.append({
            "frame": name,
            "parent": f.parent or "world",
            "world_t": [round(float(v), 6) for v in m[:3, 3]],
            "rotate_xyz": [round(float(v), 4) for v in f.rotate_xyz],
            "note": f.note,
        })
    joints = []
    from ..build.joints import joint_axis_world
    for name, j in br.spec.joints.items():
        joints.append({
            "joint": name,
            "kind": j.kind,
            "parent": j.parent,
            "child": j.child,
            "axis_local": [round(float(v), 4) for v in j.axis],
            "axis_world": [round(float(v), 4)
                           for v in joint_axis_world(br.spec, br.frames, j)],
            "limits": list(j.limits) if j.limits else None,
            "drive": j.drive or None,
        })
    return {
        "machine": br.spec.name,
        "root": br.root,
        "up_axis": br.spec.up_axis,
        "forward_axis": br.spec.forward_axis,
        "values": {k: _round(v) for k, v in br.spec.values.items()
                   if not k.startswith("_")},
        "frames": frames,
        "parts": prims[:max_prims],
        "joints": joints,
    }


def text_report(build_result) -> str:
    d = dump_build(build_result)
    out = [f"machine: {d['machine']}  root={d['root']}  up={d['up_axis']}  "
           f"forward={d['forward_axis']}", ""]
    out.append("values:")
    for k, v in sorted(d["values"].items()):
        out.append(f"  {k:<28} {v}")
    out.append("")
    out.append(f"frames ({len(d['frames'])}):")
    for f in d["frames"]:
        note = f"  # {f['note']}" if f["note"] else ""
        out.append(f"  {f['frame']:<24} parent={f['parent']:<20} "
                   f"t={_v(f['world_t'])} rpy={_v(f['rotate_xyz'])}{note}")
    out.append("")
    out.append(f"parts ({len(d['parts'])}):")
    for p in d["parts"]:
        size = ",".join(f"{k}={v}" for k, v in sorted(p["size"].items()))
        inst = f" x{p['instances']}" if p["instances"] > 1 else ""
        out.append(f"  {p['part']:<24} {p['kind']:<9}{inst:<5} frame={p['frame']:<18} "
                   f"t={_v(p['world_t'])} [{size}] {p['physics']}")
    out.append("")
    out.append(f"joints ({len(d['joints'])}):")
    for j in d["joints"]:
        out.append(f"  {j['joint']:<24} {j['kind']:<10} {j['parent']} -> {j['child']}")
        out.append(f"      axis local={_v(j['axis_local'])} world={_v(j['axis_world'])} "
                   f"limits={j['limits']} drive={j['drive']}")
    return "\n".join(out)


def dump_usd_stage(stage, max_prims: int = 500) -> dict[str, Any]:
    """Dump a live USD stage (Isaac Sim) — for when the stage was changed outside kcad."""
    from pxr import UsdGeom, UsdPhysics  # pragma: no cover
    out = []
    for i, prim in enumerate(stage.Traverse()):  # pragma: no cover
        if i >= max_prims:
            break
        rec: dict[str, Any] = {"path": str(prim.GetPath()), "type": prim.GetTypeName()}
        x = UsdGeom.Xformable(prim)
        if x:
            m = x.ComputeLocalToWorldTransform(0)
            rec["world_t"] = [round(float(v), 6) for v in m.ExtractTranslation()]
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            rec["rigid"] = True
        if prim.IsA(UsdPhysics.RevoluteJoint) or prim.IsA(UsdPhysics.PrismaticJoint):
            j = UsdPhysics.RevoluteJoint(prim) if prim.IsA(UsdPhysics.RevoluteJoint) \
                else UsdPhysics.PrismaticJoint(prim)
            rec["axis"] = str(j.GetAxisAttr().Get())
            rec["body0"] = [str(t) for t in j.GetBody0Rel().GetTargets()]
            rec["body1"] = [str(t) for t in j.GetBody1Rel().GetTargets()]
        out.append(rec)
    return {"prims": out}


def _v(x) -> str:
    return "[" + ", ".join(f"{float(v):+.4f}" for v in x) + "]"


def _round(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, list):
        return [_round(x) for x in v]
    return v


def to_json(build_result) -> str:
    return json.dumps(dump_build(build_result), indent=2, ensure_ascii=False)
