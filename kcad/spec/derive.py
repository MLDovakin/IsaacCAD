"""Derived-value engine.

Every number used by build/ and checks/ is either an explicit parameter or a derived
expression. Magic numbers in assembly code are forbidden by the skill: a tilt angle is
never written as 5.7, it is derived from rise and run so that editing one parameter
propagates everywhere instead of leaving three places out of sync.

Expressions are plain Python restricted to a safe namespace (math + previously defined
names). Evaluation order is resolved topologically, cycles are reported explicitly.
"""
from __future__ import annotations

import ast
import math
from typing import Any, Iterable

_SAFE_FUNCS = {
    "abs": abs, "min": min, "max": max, "round": round, "sum": sum,
    "pi": math.pi, "e": math.e, "sqrt": math.sqrt, "hypot": math.hypot,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "deg": math.degrees, "rad": math.radians,
    "floor": math.floor, "ceil": math.ceil,
    "g": 9.80665,
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
    ast.Call, ast.Tuple, ast.List, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Compare,
    ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq, ast.IfExp,
    ast.BoolOp, ast.And, ast.Or, ast.Not,
)


class DeriveError(RuntimeError):
    pass


def _names_in(expr: str) -> set[str]:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise DeriveError(f"bad expression {expr!r}: {exc}") from exc
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise DeriveError(f"disallowed syntax {type(node).__name__} in {expr!r}")
        if isinstance(node, ast.Name):
            out.add(node.id)
    return out


def _eval(expr: str, scope: dict[str, Any]) -> Any:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise DeriveError(f"disallowed syntax {type(node).__name__} in {expr!r}")
    try:
        return eval(compile(tree, "<derive>", "eval"), {"__builtins__": {}}, scope)
    except Exception as exc:  # noqa: BLE001 - surface the offending expression
        raise DeriveError(f"failed to evaluate {expr!r}: {exc}") from exc


def resolve(params: dict[str, Any], derived: dict[str, str]) -> dict[str, Any]:
    """Return params + derived, evaluated in dependency order."""
    scope: dict[str, Any] = dict(_SAFE_FUNCS)
    scope.update(params)

    pending = dict(derived)
    resolved_order: list[str] = []
    guard = 0
    while pending:
        guard += 1
        if guard > len(derived) + 2:
            raise DeriveError(
                "cyclic or unresolvable derived values: " + ", ".join(sorted(pending))
            )
        progressed = False
        for name in list(pending):
            expr = pending[name]
            deps = _names_in(expr)
            missing = {d for d in deps if d not in scope}
            if missing:
                continue
            scope[name] = _eval(expr, scope)
            resolved_order.append(name)
            del pending[name]
            progressed = True
        if not progressed:
            details = []
            for name, expr in pending.items():
                missing = sorted({d for d in _names_in(expr) if d not in scope})
                details.append(f"  {name} = {expr}   (missing: {', '.join(missing) or 'cycle'})")
            raise DeriveError("cannot resolve derived values:\n" + "\n".join(details))

    out = {k: v for k, v in scope.items() if k not in _SAFE_FUNCS}
    out["_derived_order"] = resolved_order
    return out


def evaluate_in(value: Any, scope: dict[str, Any]) -> Any:
    """Evaluate '=expr' strings anywhere in the spec tree; pass other values through."""
    if isinstance(value, str) and value.startswith("="):
        return _eval(value[1:], {**_SAFE_FUNCS, **scope})
    if isinstance(value, dict):
        return {k: evaluate_in(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [evaluate_in(v, scope) for v in value]
    return value


def referenced_names(exprs: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for e in exprs:
        out |= _names_in(e)
    return out - set(_SAFE_FUNCS)
