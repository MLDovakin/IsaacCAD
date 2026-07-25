# Spec format

`spec/machine.yaml` is the single source of truth. Anything not in it is an artifact.

## Header

```yaml
name: my_machine
up_axis: Z             # Z (default, USD/Isaac) or Y
forward_axis: "+X"     # +X | -X | +Y | -Y — the machine's principal direction
meters_per_unit: 1.0
```

## params / derived

`params` are the numbers a human will want to change. `derived` are expressions over
params (and over previously derived names — order does not matter, dependencies are
resolved topologically; cycles are reported).

```yaml
params:
  infeed_height: 0.700
  cage_rim_height: 0.800
  deck_clearance: 0.100
  ramp_run: 2.000

derived:
  deck_height: "cage_rim_height + deck_clearance"
  rise: "deck_height - infeed_height"
  ramp_angle: "atan2(rise, ramp_run)"
```

Available in expressions: `+ - * / // % **`, comparisons, `and/or/not`, ternary,
`abs min max round sum sqrt hypot floor ceil`, trig in **degrees**
(`sin cos tan asin acos atan atan2`), `deg rad`, `pi e`, and `g` = 9.80665.

Anywhere else in the spec, a string starting with `=` is evaluated in that scope:
`translate: [0, 0, "=deck_height"]`.

Units may be written with suffixes: `"900mm"`, `"90cm"`, `"3in"`, `"5.7deg"`, `"0.1rad"`.

## frames

The only place poses are expressed.

```yaml
frames:
  station:
    parent: null                 # null => world
    translate: [0, 0, 0]
    note: "machine origin; +X forward, +Z up"
  deck:
    parent: station
    translate: ["=ramp_run", 0, "=deck_height"]
    rotate_xyz: [0, "=-ramp_angle", 0]     # intrinsic X -> Y -> Z, degrees
    note: "carrier working plane"
```

## paths

Polylines used to array parts evenly — rails, carousels, tracks.

```yaml
paths:
  carousel:
    frame: loop
    closed: true
    points:
      - [0, "=-loop_width_y / 2", 0]
      - ["=loop_length_x", "=-loop_width_y / 2", 0]
      - ["=loop_length_x", "=loop_width_y / 2", 0]
      - [0, "=loop_width_y / 2", 0]
```

## parts

```yaml
parts:
  carrier_deck:
    frame: loop                  # required
    kind: box                    # box | cylinder | capsule | sphere | plane | mesh | camera | xform
    size: {x: 0.640, y: 0.560, z: 0.030}   # cylinder/capsule: radius, height; sphere: radius
    offset: [0, 0, 0]            # small local offset inside the frame
    rotate_xyz: [0, 0, 0]
    physics: kinematic           # static | rigid | kinematic | visual
    mass: 6.0
    collision: true
    mesh: "./assets/part.usd"    # kind: mesh
    material: "cardboard"
    instances: 20                # array
    array_along_path: carousel   # or array_step: [dx, dy, dz]
    tags: [carrier]              # used by tag-based checks
    note: "cross-belt carrier"
```

## joints

```yaml
joints:
  cross_belt_drive:
    kind: prismatic              # fixed | revolute | prismatic | spherical | free
    parent: carrier_deck         # part name, or 'world'
    child: carrier_wall_front
    axis: [0, 1, 0]              # IN THE PARENT PART'S FRAME, always
    anchor_frame: deck           # optional; defaults to the child origin
    limits: [-0.4, 0.4]          # deg for revolute, m for prismatic
    drive: {target_velocity: 0.0, stiffness: 0.0, damping: 1000.0, max_force: 500.0}
```

## constraints

See `references/checks.md`. Every non-trivial joint should carry a
`joint_axis_direction` entry.

## runtime

The process graph, declared as data — not as file ordering or step numbering.

```yaml
runtime:
  entry: induct
  nodes: [induct, perceive, classify, dispatch, recirculate, record]
  transitions:
    - {from: induct, to: perceive}
    - {from: perceive, to: classify}
    - {from: classify, to: dispatch}
    - {from: dispatch, to: record,      label: "ejected",        when_has: [dispatched]}
    - {from: dispatch, to: recirculate, label: "low confidence", when_missing: [dispatched]}
    - {from: recirculate, to: perceive, label: "second lap"}
```

Transition conditions: `when_has: [keys]` / `when_missing: [keys]` against the runtime
context. The first transition whose condition holds is taken, so put specific branches
before fallbacks. Bound every loop.

## views

```yaml
views:
  pad: 1.2        # framing margin for the canonical ortho cameras
```
