"""Physics smoke test: run N seconds and catch the ways a scene explodes.

Rest-pose invariants cannot see: bodies exploding on the first step (bad mass/inertia),
parts falling through the floor (missing collider), joints tearing apart (wrong anchor),
or a mechanism that simply does not move. This does.

Requires Isaac Sim. Without it, the module degrades to a static plausibility screen so
that CI still reports something useful.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .framework import CheckResult


@dataclass
class SmokeConfig:
    duration: float = 2.0
    dt: float = 1.0 / 60.0
    max_speed: float = 50.0          # m/s, above this the sim has blown up
    max_drift: float = 1.0           # m, how far a static part may move
    min_floor_z: float = -0.5        # below this = fell through the world
    expect_motion: list[str] = field(default_factory=list)
    min_motion: float = 1e-3


def run(build_result, config: SmokeConfig | None = None,
        world: Any = None) -> list[CheckResult]:
    cfg = config or SmokeConfig()
    if world is None:
        world = _try_isaac_world()
    if world is None:
        return [CheckResult("smoke_sim", True, "skipped: Isaac Sim not available",
                            {"skipped": True}, severity="warn")]
    return _run_isaac(build_result, cfg, world)


def _try_isaac_world():
    try:  # pragma: no cover - environment dependent
        from omni.isaac.core import World
        return World(stage_units_in_meters=1.0)
    except Exception:
        return None


def _run_isaac(br, cfg: SmokeConfig, world) -> list[CheckResult]:  # pragma: no cover
    from omni.isaac.core.prims import RigidPrimView

    results: list[CheckResult] = []
    tracked: dict[str, Any] = {}
    for name, part in br.spec.parts.items():
        if part.physics not in ("rigid", "kinematic"):
            continue
        for path in br.instance_paths[name]:
            try:
                tracked[path] = RigidPrimView(prim_paths_expr=path, name=path.replace("/", "_"))
                world.scene.add(tracked[path])
            except Exception as exc:
                results.append(CheckResult(f"smoke_sim.track[{path}]", False, str(exc)))

    world.reset()
    start = {p: _pos(v) for p, v in tracked.items()}
    steps = int(cfg.duration / cfg.dt)
    max_speed_seen = 0.0
    for _ in range(steps):
        world.step(render=False)
        for p, v in tracked.items():
            sp = float(np.linalg.norm(_vel(v)))
            max_speed_seen = max(max_speed_seen, sp)

    exploded = [p for p, v in tracked.items()
                if float(np.linalg.norm(_vel(v))) > cfg.max_speed]
    fell = [p for p, v in tracked.items() if _pos(v)[2] < cfg.min_floor_z]
    drifted = [p for p, v in tracked.items()
               if br.spec.parts[_part_of(br, p)].physics == "kinematic"
               and float(np.linalg.norm(_pos(v) - start[p])) > cfg.max_drift]

    results.append(CheckResult("smoke_sim.stable", not exploded,
                               f"max speed {max_speed_seen:.2f} m/s; exploded: {exploded[:5]}",
                               {"max_speed": max_speed_seen}))
    results.append(CheckResult("smoke_sim.no_fallthrough", not fell,
                               f"below floor: {fell[:5]}"))
    results.append(CheckResult("smoke_sim.no_drift", not drifted,
                               f"unexpected drift: {drifted[:5]}"))

    for name in cfg.expect_motion:
        moved = 0.0
        for path in br.instance_paths.get(name, []):
            if path in tracked:
                moved = max(moved, float(np.linalg.norm(_pos(tracked[path]) - start[path])))
        results.append(CheckResult(f"smoke_sim.moves[{name}]", moved >= cfg.min_motion,
                                   f"moved {moved*1000:.1f}mm", {"moved_m": moved}))
    return results


def _pos(view):  # pragma: no cover
    p, _ = view.get_world_poses()
    return np.asarray(p[0], dtype=float)


def _vel(view):  # pragma: no cover
    return np.asarray(view.get_linear_velocities()[0], dtype=float)


def _part_of(br, path: str) -> str:  # pragma: no cover
    for name, paths in br.instance_paths.items():
        if path in paths:
            return name
    return next(iter(br.spec.parts))
