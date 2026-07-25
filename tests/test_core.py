"""Тесты ядра. Гоняются без Isaac Sim — на null-бэкенде.

Запуск:  python -m pytest tests -q      (или python tests/test_core.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kcad.build import build                       # noqa: E402
from kcad.checks import load_project_checks, run_all  # noqa: E402
from kcad.io import golden                          # noqa: E402
from kcad.spec import SpecError, from_dict, load    # noqa: E402

MINIMAL = {
    "name": "t",
    "params": {"h": 0.5},
    "derived": {"h2": "h * 2"},
    "frames": {"base": {"parent": None, "translate": [0, 0, "=h"]}},
    "parts": {"b": {"frame": "base", "kind": "box", "size": {"x": 0.2, "y": 0.2, "z": 0.2}}},
}


def test_derive_and_frames():
    spec = from_dict(MINIMAL)
    assert abs(spec.values["h2"] - 1.0) < 1e-12
    br = build(spec)
    assert abs(br.frames.origin("base")[2] - 0.5) < 1e-12


def test_units_suffixes():
    d = dict(MINIMAL)
    d["frames"] = {"base": {"parent": None, "translate": ["0mm", 0, "700mm"]}}
    br = build(from_dict(d))
    assert abs(br.frames.origin("base")[2] - 0.700) < 1e-9


def test_unknown_frame_rejected():
    d = dict(MINIMAL)
    d["parts"] = {"b": {"frame": "nope", "kind": "box", "size": {"x": 1, "y": 1, "z": 1}}}
    try:
        from_dict(d)
    except SpecError:
        return
    raise AssertionError("expected SpecError for unknown frame")


def test_cycle_detected():
    d = dict(MINIMAL)
    d["frames"] = {"a": {"parent": "b"}, "b": {"parent": "a"}}
    try:
        from_dict(d)
    except SpecError:
        return
    raise AssertionError("expected SpecError for frame cycle")


def test_interpenetration_detected():
    d = {
        "name": "t",
        "frames": {"f": {"parent": None}},
        "parts": {
            "a": {"frame": "f", "kind": "box", "size": {"x": 1, "y": 1, "z": 1}},
            "b": {"frame": "f", "kind": "box", "size": {"x": 1, "y": 1, "z": 1},
                  "offset": [0.2, 0, 0]},
        },
        "constraints": [{"kind": "no_interpenetration"}],
    }
    report = run_all(build(from_dict(d)))
    assert not report.ok, "overlapping boxes must fail"


def test_joint_axis_direction_catches_flip():
    d = {
        "name": "t",
        "forward_axis": "+X",
        "frames": {"f": {"parent": None}},
        "parts": {
            "p": {"frame": "f", "kind": "box", "size": {"x": 1, "y": 1, "z": 0.1}},
            "c": {"frame": "f", "kind": "box", "size": {"x": 0.2, "y": 0.2, "z": 0.2}},
        },
        "joints": {"j": {"kind": "prismatic", "parent": "p", "child": "c",
                         "axis": [1, 0, 0]}},
        "constraints": [{"kind": "joint_axis_direction", "joint": "j",
                         "expect": "lateral"}],
    }
    report = run_all(build(from_dict(d)))
    assert not report.ok, "axis along forward must fail a 'lateral' expectation"


def test_golden_diff_localises_change():
    a = build(from_dict(MINIMAL))
    snap_a = golden.snapshot(a)
    d = dict(MINIMAL)
    d["params"] = {"h": 0.6}
    b = build(from_dict(d))
    diff = golden.diff(snap_a, golden.snapshot(b))
    assert any("values.h" in line for line in diff)
    assert any("parts.b" in line for line in diff)


def test_example_project_is_green():
    spec_path = ROOT / "examples" / "crossbelt_sorter" / "spec" / "machine.yaml"
    if not spec_path.exists():
        return
    load_project_checks(str(ROOT / "examples" / "crossbelt_sorter" / "project"))
    br = build(load(spec_path))
    report = run_all(br)
    assert report.ok, "example project must pass all invariants:\n" + report.text()


def test_array_along_closed_path_is_evenly_spaced():
    d = {
        "name": "t",
        "frames": {"f": {"parent": None}},
        "paths": {"loop": {"frame": "f", "closed": True,
                           "points": [[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0]]}},
        "parts": {"c": {"frame": "f", "kind": "box", "size": {"x": 0.1, "y": 0.1, "z": 0.1},
                        "instances": 6, "array_along_path": "loop"}},
    }
    br = build(from_dict(d))
    worlds = br.instance_world["c"]
    gaps = [float(np.linalg.norm(worlds[i + 1][:3, 3] - worlds[i][:3, 3]))
            for i in range(len(worlds) - 1)]
    assert max(gaps) - min(gaps) < 0.35, gaps


def main() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
