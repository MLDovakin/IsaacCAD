"""Check registry and report.

A check is a pure function of (BuildResult, args) -> CheckResult. Checks are cheap,
deterministic and printable — which is precisely why they, and not screenshots, are the
primary verification mechanism. A screenshot proves 'looks plausible'; a check proves
'the axis is orthogonal to 1e-9 and the clearance is 112 mm'.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

CheckFn = Callable[..., "CheckResult"]
_REGISTRY: dict[str, CheckFn] = {}


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    values: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.severity == "error" else "WARN"

    def line(self) -> str:
        head = f"[{self.status}] {self.name}"
        return f"{head}: {self.message}" if self.message else head


def check(kind: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        if kind in _REGISTRY:
            raise ValueError(f"check kind {kind!r} already registered")
        _REGISTRY[kind] = fn
        return fn
    return deco


def registry() -> dict[str, CheckFn]:
    return dict(_REGISTRY)


def load_project_checks(project_dir: str) -> None:
    """Import <project>/checks/*.py so @check decorators in the project register."""
    import importlib.util
    from pathlib import Path

    d = Path(project_dir) / "checks"
    if not d.is_dir():
        return
    for f in sorted(d.glob("*.py")):
        if f.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"kcad_project_checks.{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "error"]

    @property
    def warned(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "warn"]

    @property
    def ok(self) -> bool:
        return not self.failed

    def text(self, verbose: bool = True) -> str:
        lines = [r.line() for r in self.results if verbose or not r.passed]
        lines.append("")
        lines.append(
            f"{len(self.results) - len(self.failed) - len(self.warned)} passed, "
            f"{len(self.failed)} failed, {len(self.warned)} warnings"
        )
        return "\n".join(lines)


def run_all(build_result, spec=None, extra: list[Any] | None = None) -> Report:
    """Run every constraint declared in the spec, plus always-on structural checks."""
    spec = spec or build_result.spec
    report = Report()
    reg = registry()

    for kind in ("frames_resolve", "unique_prim_paths", "finite_transforms",
                 "joint_axes_sane"):
        fn = reg.get(kind)
        if fn:
            report.results.append(_safe(fn, kind, build_result, {}, "error"))

    for c in list(spec.constraints) + list(extra or []):
        fn = reg.get(c.kind)
        if fn is None:
            report.results.append(CheckResult(
                name=c.name, passed=False, severity="error",
                message=f"unknown check kind {c.kind!r}; known: {', '.join(sorted(reg))}"))
            continue
        report.results.append(_safe(fn, c.name, build_result, c.args, c.severity))
    return report


def _safe(fn: CheckFn, name: str, build_result, args: dict[str, Any],
          severity: str) -> CheckResult:
    try:
        res = fn(build_result, **args)
        res.name = name
        res.severity = severity if not res.passed else res.severity
        return res
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name=name, passed=False, severity="error",
                           message=f"check raised {type(exc).__name__}: {exc}",
                           values={"traceback": traceback.format_exc(limit=3)})
