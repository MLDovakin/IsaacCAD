"""Golden snapshots: regression detection for geometry.

After a good build, freeze the key numbers. Before accepting an edit, diff. If you meant
to change one wall height and the carrier pitch moved too, you see it in the same minute
instead of three iterations later.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def snapshot(build_result, decimals: int = 6) -> dict[str, Any]:
    br = build_result
    parts: dict[str, Any] = {}
    for name in sorted(br.spec.parts):
        worlds = br.instance_world[name]
        parts[name] = {
            "n": len(worlds),
            "t0": [round(float(v), decimals) for v in np.asarray(worlds[0])[:3, 3]],
            "tN": [round(float(v), decimals) for v in np.asarray(worlds[-1])[:3, 3]],
            "R0": [[round(float(v), decimals) for v in row]
                   for row in np.asarray(worlds[0])[:3, :3]],
        }
    from ..build.joints import joint_axis_world
    joints = {
        name: {
            "kind": j.kind,
            "axis_world": [round(float(v), decimals)
                           for v in joint_axis_world(br.spec, br.frames, j)],
            "limits": list(j.limits) if j.limits else None,
        }
        for name, j in sorted(br.spec.joints.items())
    }
    frames = {
        name: [round(float(v), decimals) for v in np.asarray(br.frames.world(name))[:3, 3]]
        for name in sorted(br.spec.frames)
    }
    values = {k: (round(v, decimals) if isinstance(v, float) else v)
              for k, v in sorted(br.spec.values.items()) if not k.startswith("_")}
    return {"machine": br.spec.name, "values": values, "frames": frames,
            "parts": parts, "joints": joints}


def save(build_result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot(build_result), indent=2, ensure_ascii=False),
                 encoding="utf-8")
    return str(p)


def load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def diff(old: dict[str, Any], new: dict[str, Any], tol: float = 1e-6) -> list[str]:
    out: list[str] = []
    _diff_node(old, new, "", out, tol)
    return out


def diff_text(old: dict[str, Any], new: dict[str, Any], tol: float = 1e-6) -> str:
    d = diff(old, new, tol)
    if not d:
        return "golden: no changes"
    return "golden diff ({} change{}):\n".format(len(d), "" if len(d) == 1 else "s") + \
        "\n".join("  " + line for line in d)


def _diff_node(a: Any, b: Any, path: str, out: list[str], tol: float) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            sub = f"{path}.{k}" if path else k
            if k not in a:
                out.append(f"+ {sub} = {_short(b[k])}")
            elif k not in b:
                out.append(f"- {sub} (was {_short(a[k])})")
            else:
                _diff_node(a[k], b[k], sub, out, tol)
        return
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _diff_node(x, y, f"{path}[{i}]", out, tol)
        return
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        if abs(float(a) - float(b)) > tol:
            delta = float(b) - float(a)
            out.append(f"~ {path}: {a} -> {b}  (delta {delta:+.6g})")
        return
    if a != b:
        out.append(f"~ {path}: {_short(a)} -> {_short(b)}")


def _short(v: Any) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 80 else s[:77] + "..."
