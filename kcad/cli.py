"""Command line entry point.

    python -m kcad.cli <command> --project <dir> [options]

Commands mirror the mandatory work cycle in SKILL.md:
    build     rebuild the machine from spec (never edit the stage by hand)
    check     run every declared invariant (this is the real verification)
    inspect   dump the ACTUAL state — run this before proposing any edit
    golden    save / diff the geometry regression snapshot
    views     author or capture the canonical orthographic cameras
    run       execute the runtime graph
    graph     print the runtime graph as mermaid
    new       scaffold a new project from the template
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import build as build_machine
from .checks import load_project_checks, run_all
from .io import golden as golden_io
from .io import text_report
from .spec import SpecError, load


def _project_paths(project: str) -> tuple[Path, Path]:
    p = Path(project)
    spec = p / "spec" / "machine.yaml"
    if not spec.exists():
        cands = sorted((p / "spec").glob("*.yaml")) if (p / "spec").is_dir() else []
        if not cands:
            raise SystemExit(f"no spec found under {p / 'spec'}")
        spec = cands[0]
    return p, spec


def _prepare(args):
    project, spec_path = _project_paths(args.project)
    spec = load(args.spec or spec_path)
    load_project_checks(str(project / "project"))
    load_project_checks(str(project))
    kwargs = {}
    if args.backend == "usd":
        kwargs["stage_path"] = args.stage or str(project / "out" / f"{spec.name}.usda")
        kwargs["geometry_layer"] = args.layer or str(project / "out" / f"{spec.name}_geom.usda")
        Path(kwargs["stage_path"]).parent.mkdir(parents=True, exist_ok=True)
    br = build_machine(spec, backend=args.backend, **kwargs)
    return project, spec, br


def cmd_build(args) -> int:
    project, spec, br = _prepare(args)
    saved = br.backend.save() if args.backend == "usd" else None
    print(f"built {spec.name}: {len(spec.frames)} frames, {len(spec.parts)} parts "
          f"({sum(len(v) for v in br.instance_world.values())} instances), "
          f"{len(spec.joints)} joints")
    if saved:
        print(f"stage saved: {saved}")
    return 0


def cmd_check(args) -> int:
    project, spec, br = _prepare(args)
    report = run_all(br, spec)
    if args.smoke:
        from .checks.smoke_sim import SmokeConfig, run as run_smoke
        report.results.extend(run_smoke(br, SmokeConfig(duration=args.duration)))
    print(report.text(verbose=not args.quiet))
    return 0 if report.ok else 1


def cmd_inspect(args) -> int:
    project, spec, br = _prepare(args)
    if args.json:
        from .io import to_json
        print(to_json(br))
    else:
        print(text_report(br))
    return 0


def cmd_golden(args) -> int:
    project, spec, br = _prepare(args)
    path = args.file or str(project / "golden" / f"{spec.name}.json")
    if args.save:
        print(f"golden saved: {golden_io.save(br, path)}")
        return 0
    if not Path(path).exists():
        print(f"no golden at {path}; run with --save first")
        return 1
    old = golden_io.load(path)
    new = golden_io.snapshot(br)
    text = golden_io.diff_text(old, new, tol=args.tol)
    print(text)
    return 0 if text.endswith("no changes") else (1 if args.strict else 0)


def cmd_views(args) -> int:
    project, spec, br = _prepare(args)
    from .checks.views import author_cameras, capture
    cams = author_cameras(br)
    print("cameras: " + ", ".join(f"{k} -> {v}" for k, v in cams.items()))
    if args.capture:
        out = args.out or str(project / "out" / "views")
        written = capture(br, out)
        print(f"captured: {written or 'skipped (Isaac Sim not available)'}")
    if args.backend == "usd":
        br.backend.save()
    return 0


def cmd_run(args) -> int:
    project, spec, br = _prepare(args)
    from .runtime import Context, Graph, load_project_steps
    from .runtime.steps import generic  # noqa: F401  (registers generic steps)
    load_project_steps(str(project / "project"))
    load_project_steps(str(project))
    graph = Graph.from_spec(spec.runtime or {})
    errs = graph.validate()
    if errs:
        print("runtime graph invalid:\n  - " + "\n  - ".join(errs))
        return 1
    ctx = Context(spec=spec, build=br)
    graph.run(ctx, max_steps=args.max_steps, verbose=True)
    print("\n".join(ctx.log))
    return 0


def cmd_graph(args) -> int:
    project, spec, br = _prepare(args)
    from .runtime import Graph, load_project_steps
    from .runtime.steps import generic  # noqa: F401
    load_project_steps(str(project / "project"))
    load_project_steps(str(project))
    print(Graph.from_spec(spec.runtime or {}).to_mermaid())
    return 0


def cmd_new(args) -> int:
    import shutil
    src = Path(__file__).resolve().parent.parent / "templates" / "project_template"
    dst = Path(args.project)
    if dst.exists() and any(dst.iterdir()):
        print(f"refusing to scaffold into non-empty {dst}")
        return 1
    shutil.copytree(src, dst, dirs_exist_ok=True)
    print(f"scaffolded project at {dst}\nnext: edit {dst}/spec/machine.yaml, then "
          f"`python -m kcad.cli check --project {dst}`")
    return 0


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=".", help="project directory")
    common.add_argument("--spec", default=None, help="explicit spec path")
    common.add_argument("--backend", default="null", choices=["null", "usd"])
    common.add_argument("--stage", default=None, help="usd stage path")
    common.add_argument("--layer", default=None, help="usd geometry sublayer path")

    ap = argparse.ArgumentParser(prog="kcad", description=__doc__,
                                 parents=[common],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name):
        return sub.add_parser(name, parents=[common])

    add("build").set_defaults(func=cmd_build)

    c = add("check")
    c.add_argument("--smoke", action="store_true", help="also run the physics smoke test")
    c.add_argument("--duration", type=float, default=2.0)
    c.add_argument("--quiet", action="store_true", help="only show failures")
    c.set_defaults(func=cmd_check)

    i = add("inspect")
    i.add_argument("--json", action="store_true")
    i.set_defaults(func=cmd_inspect)

    g = add("golden")
    g.add_argument("--save", action="store_true")
    g.add_argument("--file", default=None)
    g.add_argument("--tol", type=float, default=1e-6)
    g.add_argument("--strict", action="store_true", help="exit 1 when anything changed")
    g.set_defaults(func=cmd_golden)

    v = add("views")
    v.add_argument("--capture", action="store_true")
    v.add_argument("--out", default=None)
    v.set_defaults(func=cmd_views)

    r = add("run")
    r.add_argument("--max-steps", type=int, default=200)
    r.set_defaults(func=cmd_run)

    add("graph").set_defaults(func=cmd_graph)

    n = add("new")
    n.set_defaults(func=cmd_new)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except SpecError as exc:
        print(f"SPEC ERROR\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
