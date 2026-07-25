# Coordinate and naming conventions

These are checked by the toolkit, not just documented. If you deviate, change the spec
header (`up_axis`, `forward_axis`) — never quietly deviate in one subassembly.

## Units

- Length: **metres** internally. The spec may write `"900mm"`, `"90cm"`, `"3in"`;
  by the time a value reaches `build/` or `checks/` it is a float in metres.
- Angles: **degrees**. `"0.1rad"` is accepted in the spec and converted.
- Time: seconds. Speed: m/s.
- There is no place in the codebase where a unit is implied. If you find one, it is a bug.

## Axes

- `up_axis: Z` and `meters_per_unit: 1.0` — the USD/Isaac default. Y-up is supported but
  must be declared in the spec header.
- `forward_axis: "+X"` — the machine's principal direction of travel/operation.
- `lateral = cross(up, forward)` — computed, never hand-typed. Sideways motions
  (cross-belt ejection, pushers, transverse drives) reference `lateral`, so that rotating
  the machine's forward axis rotates them with it.

## Frames

- Every pose lives in `frames:`. Parts attach to a frame and may carry only a small local
  `offset` / `rotate_xyz` inside it.
- **No part carries absolute world coordinates.** Moving a subassembly = moving its frame.
- Frame chains are relative to the parent. The root frame (parent `null`) is the machine
  origin; place the machine in the world by moving that one frame.
- Rotations are intrinsic X → Y → Z, degrees.
- Give frames notes. `note: "точка A: приём с подающего конвейера"` costs nothing and is
  what the next reader (human or model) uses to understand intent.

## Joints

- `axis` is expressed **in the parent part's frame**, always.
- Conversion to world happens in exactly one function: `kcad/build/joints.py :: joint_axis_world`.
- Every non-trivial joint should carry a `joint_axis_direction` constraint stating what
  the axis is supposed to be (`forward`, `lateral`, `up`, another joint, or a literal
  vector). This is the guard against the most common and most invisible bug class.
- `limits` are degrees for revolute, metres for prismatic.

## Naming

- Prim paths: `/World/<machine>/{frames,parts,joints,views}/<name>`, generated — do not
  hand-author paths.
- Part and frame names: `snake_case`, no spaces, no leading digits.
- Arrayed parts get `<part>/inst_000`, `inst_001`, … — index order follows the path or
  the array step, and is stable across rebuilds (golden diffs depend on this).

## Layers

- Geometry is authored into its own USD sublayer. Lights, cameras and render settings live
  elsewhere, so "nuke and rebuild" never takes the environment with it and every rebuild
  is reversible.

## Tolerances

- Geometry comparisons: 1e-6 m unless a check says otherwise.
- Angle comparisons: 0.5° default for axis direction checks.
- Golden diffs: 1e-6 by default; raise it only if you have a reason and say so.
