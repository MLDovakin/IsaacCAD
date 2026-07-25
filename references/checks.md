# Built-in checks

Every check is declared in `spec/machine.yaml` under `constraints:` as:

```yaml
- kind: <check kind>
  name: "human readable name"     # optional, defaults to kind
  severity: error | warn          # optional, default error
  <arguments...>
```

Values may use `"=expression"` to reference params/derived, and unit suffixes (`"450mm"`).

## Contents
- [Always-on structural](#always-on-structural)
- [Heights and clearances](#heights-and-clearances)
- [Geometry](#geometry)
- [Kinematics](#kinematics)
- [Physics and timing](#physics-and-timing)
- [Escape hatch](#escape-hatch)
- [Writing your own](#writing-your-own)

## Always-on structural

Run automatically on every `check`, no declaration needed.

| kind | catches |
|---|---|
| `frames_resolve` | non-finite frame transforms |
| `unique_prim_paths` | duplicate prim paths |
| `finite_transforms` | NaN/inf in part transforms |
| `joint_axes_sane` | degenerate or non-unit joint axes |

## Heights and clearances

**`height`** — signed height of a frame or part origin along the up axis.
```yaml
- kind: height
  frame: deck          # or: part: carrier_deck
  min: "=cage_rim_height + 0.050"
  max: 0.960
```

**`clearance`** — gap between two parts' AABBs along an axis.
```yaml
- kind: clearance
  a: carrier_deck
  b: cage_c_body
  axis: up             # up | forward | lateral | [x,y,z]
  min: 0.100
```

## Geometry

**`no_interpenetration`** — AABB overlap over all part instances in the rest pose.
```yaml
- kind: no_interpenetration
  ignore_pairs: [[floor, table_top], [deck, wall]]
  ignore_tags: [sensor]
  tolerance: 0.0
```

**`inside_workspace`** — selected parts must sit inside a world-aligned box.
```yaml
- kind: inside_workspace
  bounds: {min: [-2, -2, -0.1], max: [2, 2, 2]}
  tags: [structure, moving]      # or: parts: [a, b]
```

**`relative_pose`** — vector between two frames/parts vs an expected offset.
```yaml
- kind: relative_pose
  a: frame:infeed
  b: frame:deck
  expect_translate: [2.4, 0, 0.2]
  tol: 0.001
```

**`array_pitch`** — spacing between consecutive instances of an arrayed part.
```yaml
- kind: array_pitch
  part: carrier_deck
  min_pitch: "=max_item + 0.100"
  expect_pitch: "=carrier_pitch"     # optional
```

**`path_closed`** — a carousel/loop is non-degenerate and actually closed.
```yaml
- kind: path_closed
  path: carousel
```

**`capacity_fits`** — N items of a given footprint fit on a path.
```yaml
- kind: capacity_fits
  path: carousel
  count: "=carrier_count"
  item_size: "=carrier_len"
  extra: 0.040
```

## Kinematics

**`joint_axis_direction`** — the single most valuable check in the toolkit. Guards against
an axis that silently points the wrong way after a frame edit.
```yaml
- kind: joint_axis_direction
  joint: cross_belt_drive
  expect: lateral        # forward | up | lateral | joint:<name> | frame:<name>:<x|y|z> | [x,y,z]
  tol_deg: 0.5
  allow_flip: true       # accept 180° reversal (same line of action)
```

**`axis_angle_between`** — angle between any two direction sources.
```yaml
- kind: axis_angle_between
  a: joint:cross_belt_drive
  b: axis:forward
  expect_deg: 90
  tol_deg: 0.5
```

## Physics and timing

**`no_slip_on_incline`** — `tan(θ) < μ / margin`.
```yaml
- kind: no_slip_on_incline
  angle_deg: "=ramp_angle"
  friction: 0.40
  margin: 1.2
```

**`no_tipover_on_incline`** — `tan(θ) < (base/height) / margin`.
```yaml
- kind: no_tipover_on_incline
  angle_deg: "=ramp_angle"
  base: 0.100            # footprint of the worst-case item
  height: 0.500
  margin: 1.5
```

**`projectile_lands_in`** — ballistic release: ejection, chute drop, pusher discharge.
```yaml
- kind: projectile_lands_in
  speed: "=eject_speed"          # horizontal release speed
  drop: "=drop_to_floor"
  target_min: 0.250              # acceptable lateral landing window
  target_max: 0.850
  carrier_speed: "=belt_speed"   # optional: along-track drift during flight
  along_min: 0.0
  along_max: 1.0
```

**`cycle_time`** — `distance / speed` against a budget.
```yaml
- kind: cycle_time
  distance: "=cycle_distance"
  speed: "=cycle_speed"
  max_time: 2.5
```

**`actuator_window`** — the command must complete before the part leaves the station.
```yaml
- kind: actuator_window
  available_time: "=eject_window"
  actuator_time: 0.150
  margin: 1.5
```

## Escape hatch

**`expr`** — any boolean expression over spec values. Prefer a typed check; use this for
one-off sanity rules.
```yaml
- kind: expr
  expression: "eject_speed < 2.5"
  severity: warn
```

## Writing your own

Put it in `project/checks/*.py`. It registers automatically and is then declarable in the
spec exactly like a built-in.

```python
from kcad.checks.framework import CheckResult, check

@check("my_rule")
def my_rule(br, threshold: float, **_) -> CheckResult:
    """One line describing the design intent this encodes."""
    value = float(br.spec.value("some_param"))
    return CheckResult("my_rule", value >= threshold,
                       f"{value*1000:.0f}mm vs {threshold*1000:.0f}mm",
                       {"value_m": value})
```

`br` is the `BuildResult`: `br.spec`, `br.frames` (frame graph), `br.instance_world[part]`
(list of 4×4 world transforms), `br.instance_paths[part]`, `br.spec.value(name)`.

Report numbers, not verdicts — a message reading `gap=112mm` is worth ten `FAIL`s with no
figure. And never write a check whose failure mode is "loosen the tolerance".
