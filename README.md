# kinematic-cad

A Claude skill + Python toolkit for building kinematic machines in USD / NVIDIA Isaac Sim
so that editing one subassembly cannot silently break the rest.

The core idea is borrowed from parametric CAD: **the scene is not edited, it is rebuilt
from a spec**, and design intent is stored as **machine-checkable invariants** rather than
in a chat transcript.

## Quick start

```bash
pip install pyyaml numpy                 # core deps; usd-core optional for the USD backend
export PYTHONPATH=$PWD                   # or pip install -e .

python -m kcad.cli new     --project ../my_machine     # scaffold
python -m kcad.cli inspect --project ../my_machine     # read actual state
python -m kcad.cli build   --project ../my_machine
python -m kcad.cli check   --project ../my_machine
python -m kcad.cli golden  --project ../my_machine --save
```

Inside Isaac Sim (real USD stage, physics, screenshots):

```bash
./python.sh -m kcad.cli build  --project /path/to/my_machine --backend usd
./python.sh -m kcad.cli check  --project /path/to/my_machine --backend usd --smoke
./python.sh -m kcad.cli views  --project /path/to/my_machine --backend usd --capture
```

## What you get

- **Parametric spec** — one YAML with params, derived expressions, frames, parts, joints.
  No magic numbers anywhere else.
- **20 built-in invariants** — heights, clearances, interpenetration, workspace bounds,
  joint axis direction, array pitch, closed paths, slip/tip-over on inclines, ballistic
  landing, cycle time, actuator windows — plus your own via `@check`.
- **Idempotent rebuild** — `build()` wipes and re-authors; no partial state.
- **Golden regression snapshots** — change a wall height, see exactly what else moved.
- **Stage inspector** — compact text dump of the actual scene, for reading before editing.
- **Runtime process graph** — separate from the build graph, with preconditions,
  branching and bounded loops.
- **Two backends** — `null` (pure Python, CI-friendly) and `usd` (Isaac Sim).

## Layout

```
kinematic-cad/
├── SKILL.md                  # the skill: rules and mandatory work cycle
├── CONVENTIONS.md            # axes, units, naming, tolerances
├── references/               # checks.md, spec.md, isaac.md
├── kcad/                     # the library
│   ├── spec/    schema, loader, derive
│   ├── build/   frames, paths, primitives, joints, assembly, backends
│   ├── checks/  framework, invariants, smoke_sim, views
│   ├── io/      inspect_stage, golden
│   ├── runtime/ graph, context, steps
│   └── cli.py
├── templates/project_template/   # `kcad new` scaffolds this
├── examples/crossbelt_sorter/    # worked example: 3-way sorter, 21 invariants
└── tests/test_core.py            # runs without Isaac Sim
```

## Example

`examples/crossbelt_sorter` is a full three-way cross-belt sorter: a closed carousel of
20 carriers, a ramp, two receivers and a fixed infeed, with 21 invariants covering deck
clearance, ramp slip and tip-over, ballistic ejection, actuator timing, throughput and
workspace bounds — and a runtime graph with a bounded recirculation loop for
low-confidence items.

```bash
python -m kcad.cli check --project examples/crossbelt_sorter
# 21 passed, 0 failed, 0 warnings
python tests/test_core.py
# 9 passed, 0 failed
```

## Requirements

- Python 3.10+, `pyyaml`, `numpy` — that is all for the `null` backend and every check.
- `usd-core` for geometry authoring outside Isaac; Isaac Sim for physics and rendering.
