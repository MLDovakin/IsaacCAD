# Running inside Isaac Sim

## Backends

| backend | needs | use for |
|---|---|---|
| `null` | pyyaml + numpy | every geometric check, golden diffs, CI, fast iteration |
| `usd` | `usd-core`, or Isaac Sim's python | real stage, physics, rendering |

A green `null` run means the geometric intent is sound. Escalate to `usd` when you need
physics or pictures — not before, because it is far slower to iterate on.

## Invocation

```bash
# geometry only, any python
pip install usd-core
python -m kcad.cli build --project <dir> --backend usd

# full Isaac (physics, replicator, screenshots)
cd ~/.local/share/ov/pkg/isaac-sim-*/
./python.sh -m kcad.cli check --project /abs/path/to/project --backend usd --smoke
./python.sh -m kcad.cli views --project /abs/path/to/project --backend usd --capture
```

Stage and geometry sublayer default to `<project>/out/<name>.usda` and
`<project>/out/<name>_geom.usda`; override with `--stage` / `--layer`.

## Layering

Geometry is authored into its own sublayer. Lights, cameras, render settings and any
manual scene dressing live in the root layer or another sublayer, so a full rebuild never
destroys the environment and is always reversible. Do not author geometry into the root
layer by hand — the next rebuild will not know about it.

## Physics smoke test

`--smoke` runs the scene for a couple of seconds and reports:

- `smoke_sim.stable` — nothing exceeded `max_speed` (a body exploding usually means bad
  mass/inertia or a joint anchored in the wrong frame)
- `smoke_sim.no_fallthrough` — nothing dropped below the floor (missing collider)
- `smoke_sim.no_drift` — kinematic parts stayed put
- `smoke_sim.moves[part]` — a mechanism that is supposed to move actually moved

Without Isaac available it degrades to a `WARN` skip so CI still reports cleanly.

## Screenshots

`views --capture` authors four cameras (`front`, `side`, `top` orthographic; `iso`
perspective) framed on the scene bounds, then renders them via Replicator into
`out/views/`. Orthographic matters: alignment, parallelism and a 15 mm offset are simply
not judgeable in perspective.

Screenshots are for the human and for the demo video. They are never the verification
step — that is `check`.

## Meshes

`kind: mesh` references an external asset by path (`mesh: "./assets/box.usd"`). Isaac does
not import STL directly in a useful way for physics; convert to USD/OBJ first (Asset
Converter, or `trimesh` one-liner). Give mesh parts an explicit
`size: {bbox: [x, y, z]}` so AABB-based checks have something to work with.

## Articulations

For a serial chain that Isaac should treat as an articulation, keep the joints in the spec
as usual and apply `ArticulationRootAPI` to the base part in your own post-build hook.
The toolkit deliberately does not guess where the articulation root belongs — that is a
design decision, and design decisions belong in the spec.
