---
name: kinematic-cad
description: Parametric, invariant-checked assembly of kinematic machines in USD / NVIDIA Isaac Sim. Use this skill whenever the user is building, editing, or debugging a simulated mechanism, rig, conveyor, carousel, gantry, robot cell, test bench, or any multi-part assembly with joints — especially when they mention Isaac Sim, Omniverse, USD stages, prim paths, articulations, kinematics, frames, origins, or axes.
---

# Kinematic CAD

Parametric assembly toolkit for USD / Isaac Sim. It exists to solve one specific failure:
an agent edits one subassembly and silently breaks the rest of the machine, because the
design intent lives in a chat transcript instead of in the project.

## The two rules everything else follows from

**1. The scene is never edited in place — it is rebuilt from a spec.**
Edits go into `spec/machine.yaml`. `build` wipes the machine root and re-authors
everything. There is no partially-updated stage for the rest of the machine to disagree
with. Hand-authoring prims, nudging transforms in the viewport, or patching a single
Xform is how the assembly gets destroyed.

**2. Design intent is stored as machine-checkable invariants, not as prose.**
"The deck must clear the cage rim" is a `constraints:` entry that prints
`clearance 112mm`, not a sentence someone has to remember. When a check fails, **fix the
spec — never relax the check.** Weakening an assertion to make a build pass is the single
fastest way to quietly destroy a working machine.

## Mandatory work cycle

Follow this every time, in this order. Do not skip step 1 and do not reorder 4–6.

```bash
python -m kcad.cli inspect --project <dir>            # 1. READ ACTUAL STATE FIRST
#                                                       2. edit spec/machine.yaml only
python -m kcad.cli build   --project <dir>            # 3. full rebuild
python -m kcad.cli check   --project <dir>            # 4. invariants (the real check)
python -m kcad.cli check   --project <dir> --smoke    # 4b. physics smoke test
python -m kcad.cli golden  --project <dir> --strict   # 5. what moved vs the baseline
python -m kcad.cli views   --project <dir> --capture  # 6. ortho screenshots (for humans)
```

Step 1 is not optional. Without it you are reconstructing the scene from memory of the
conversation, which is exactly how origins and axes drift.

Step 5 requires explaining **every** changed number. If you edited a wall height and the
carrier pitch also moved, that is a bug, not a coincidence.

Screenshots are step 6, never step 4. A render proves "looks plausible"; a check proves
"the axis is orthogonal to 1e-9 and the clearance is 112 mm". Views are orthographic from
fixed poses (front / side / top / iso) because alignment and a 15 mm offset are invisible
in perspective.

## Adding to a machine

| Want to | Do this | Never do this |
|---|---|---|
| move a subassembly | move its **frame** in `frames:` | edit each part's offset |
| change a dimension | edit `params:` / `derived:` | type the number into a part |
| add a part | add to `parts:`, attach to a frame | author a prim in the stage |
| add a mechanism | add to `joints:` + a `joint_axis_direction` constraint | set the axis and hope |
| encode a requirement | add to `constraints:` | write it in a comment |
| add a process step | `@step` in `project/steps/` + a node in `runtime:` | inline it into build code |

**Magic numbers are forbidden in build code.** A tilt angle is never `5.7`; it is
`derived: ramp_angle: "atan2(rise, run)"`. That is what makes editing one parameter
propagate correctly instead of leaving three places out of sync.

## Build graph vs runtime graph

Keep them separate. "Build a carrier" and "move an item onto the carrier" fail for
different reasons, at different times, and are debugged differently.

- `build/` — geometry, physics, joints. Rebuilt wholesale from the spec.
- `runtime/` — process steps with explicit `requires` / `provides`. Branching and loops
  fall out of preconditions: if a step's precondition is unmet it does not fire and the
  item continues — which is exactly how a "send it round again" recirculation loop is
  expressed, with no special case in the code. Bound such loops (max laps → manual
  handling), or they run forever.

Do not number steps `step_0`, `step_1`. Numbering implies a straight line; real processes
branch and loop. The graph is declared as data in `runtime:` in the spec.

## Coordinate conventions

Read `CONVENTIONS.md` before touching frames. Short version: Z-up, metres, `+X` is the
machine's forward direction, every frame is defined relative to its parent, no part
carries absolute world coordinates, and joint axes are expressed in the parent part's
frame — converted to world in exactly one function (`build/joints.py`). That single
conversion point is what makes an inverted axis detectable by a check instead of by eye.

## Files

| Path | Role |
|---|---|
| `spec/machine.yaml` | single source of truth: params, derived, frames, parts, joints, constraints, runtime |
| `kcad/spec/` | schema, loader, derived-value engine |
| `kcad/build/` | frames, primitives, joints, paths, idempotent assembly, backends |
| `kcad/checks/` | check registry, 20 built-in invariants, smoke sim, ortho views |
| `kcad/io/` | `inspect_stage` (read actual state), `golden` (regression snapshots) |
| `kcad/runtime/` | process graph, context blackboard, generic steps |
| `project/checks/`, `project/steps/` | project-specific `@check` / `@step` |
| `golden/`, `out/` | baselines and artifacts — never sources of truth |

Backends: `null` (pure Python, no Isaac needed — use it for CI and for every check that
does not need physics) and `usd` (real stage; run from Isaac Sim's `./python.sh`).
A green `null` run means the geometric intent is sound.

For the full list of built-in checks and their arguments, read
`references/checks.md`. For the spec format field by field, read `references/spec.md`.
For a worked example with real numbers, read `examples/crossbelt_sorter/`.

## Invocation

The skill triggers on its description, and a project may also install explicit slash
commands (`/kcad`, `/kcad-check`, `/kcad-diff`, `/kcad-new`) plus a post-edit hook that
runs `build` + `check` automatically after any edit to `machine.yaml`. See
`claude-integration/README.md`. When a hook has already produced check output, read it —
do not re-run the same command.

## When the user reports a broken assembly

1. `inspect` — get the actual state, do not theorise.
2. `check` — the failing invariant usually names the broken assumption directly.
3. `golden --strict` against the last good baseline — locates what moved.
4. If nothing fails but the machine is visibly wrong, the intent was never encoded:
   add the missing constraint **first**, watch it fail, then fix the spec.

That last step matters. A bug that no invariant catches will come back.
