"""Runtime process graph — SEPARATE from the build graph on purpose.

'Build a carrier' and 'move an item onto the carrier' fail for different reasons, live at
different times and are debugged differently. Mixing them into one numbered chain of
step_0/step_1 files is what makes both hard to reason about.

Nodes declare preconditions and postconditions. Branching and loops fall out of that:
if a precondition is not met, the node does not fire and the item keeps going — which is
exactly how a 'send it round again' recirculation loop is expressed, with no special case
in the code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .context import Context

StepFn = Callable[[Context], Any]
CondFn = Callable[[Context], bool]

_STEPS: dict[str, "Step"] = {}


@dataclass
class Step:
    name: str
    fn: StepFn
    requires: list[str] = field(default_factory=list)     # context keys
    provides: list[str] = field(default_factory=list)     # context keys
    guard: CondFn | None = None
    description: str = ""

    def ready(self, ctx: Context) -> tuple[bool, str]:
        missing = [k for k in self.requires if k not in ctx.data]
        if missing:
            return False, f"missing {missing}"
        if self.guard and not self.guard(ctx):
            return False, "guard false"
        return True, ""

    def run(self, ctx: Context) -> Any:
        out = self.fn(ctx)
        missing = [k for k in self.provides if k not in ctx.data]
        if missing:
            raise RuntimeError(
                f"step {self.name!r} finished but did not provide {missing}")
        return out


def step(name: str, requires: list[str] | None = None, provides: list[str] | None = None,
         guard: CondFn | None = None, description: str = ""):
    def deco(fn: StepFn) -> StepFn:
        if name in _STEPS:
            raise ValueError(f"step {name!r} already registered")
        _STEPS[name] = Step(name=name, fn=fn, requires=requires or [],
                            provides=provides or [], guard=guard,
                            description=description or (fn.__doc__ or "").strip())
        return fn
    return deco


def registry() -> dict[str, Step]:
    return dict(_STEPS)


def load_project_steps(project_dir: str) -> None:
    import importlib.util
    from pathlib import Path

    d = Path(project_dir) / "steps"
    if not d.is_dir():
        return
    for f in sorted(d.glob("*.py")):
        if f.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"kcad_project_steps.{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)


@dataclass
class Transition:
    src: str
    dst: str
    when: CondFn | None = None
    label: str = ""


@dataclass
class Graph:
    nodes: list[str] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    entry: str | None = None

    @staticmethod
    def from_spec(runtime_spec: dict[str, Any]) -> "Graph":
        """Graph declared as data in the spec, not as file ordering.

        A transition may declare, in the spec:
            when_has:     [keys]   fire only if all keys are present in the context
            when_missing: [keys]   fire only if none of the keys are present
        Ordering matters: the first transition whose condition holds is taken, so put
        the specific branch before the fallback. This is how a recirculation loop is
        expressed: 'dispatched missing -> go round again'.
        """
        g = Graph(nodes=list(runtime_spec.get("nodes") or []),
                  entry=runtime_spec.get("entry"))
        for t in runtime_spec.get("transitions") or []:
            g.transitions.append(Transition(
                src=t["from"], dst=t["to"], label=t.get("label", ""),
                when=_condition(t.get("when_has"), t.get("when_missing"))))
        if g.entry is None and g.nodes:
            g.entry = g.nodes[0]
        return g

    def successors(self, node: str) -> list[Transition]:
        return [t for t in self.transitions if t.src == node]

    def validate(self) -> list[str]:
        errs = []
        reg = registry()
        for n in self.nodes:
            if n not in reg:
                errs.append(f"node {n!r} has no registered step")
        for t in self.transitions:
            if t.src not in self.nodes:
                errs.append(f"transition from unknown node {t.src!r}")
            if t.dst not in self.nodes:
                errs.append(f"transition to unknown node {t.dst!r}")
        if self.entry and self.entry not in self.nodes:
            errs.append(f"entry {self.entry!r} is not a node")
        return errs

    def run(self, ctx: Context, max_steps: int = 200, verbose: bool = False) -> Context:
        reg = registry()
        current = self.entry
        count = 0
        while current and count < max_steps:
            count += 1
            st = reg[current]
            ready, why = st.ready(ctx)
            if ready:
                st.run(ctx)
                if verbose:
                    ctx.say(f"{current}: ok")
            else:
                ctx.say(f"{current}: skipped ({why})")
            nxt = self.successors(current)
            current = None
            for t in nxt:
                if t.when is None or t.when(ctx):
                    current = t.dst
                    break
        if count >= max_steps:
            ctx.say(f"graph stopped at max_steps={max_steps}")
        return ctx

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        for n in self.nodes:
            lines.append(f"    {_id(n)}[{n}]")
        for t in self.transitions:
            arrow = f"-->|{t.label}|" if t.label else "-->"
            lines.append(f"    {_id(t.src)} {arrow} {_id(t.dst)}")
        return "\n".join(lines)


def _condition(when_has, when_missing) -> CondFn | None:
    has = list(when_has or [])
    missing = list(when_missing or [])
    if not has and not missing:
        return None

    def cond(ctx: Context) -> bool:
        return all(k in ctx.data for k in has) and all(k not in ctx.data for k in missing)

    return cond


def _id(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)
