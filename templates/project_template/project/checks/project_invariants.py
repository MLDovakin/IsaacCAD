"""Проектные инварианты. Регистрируются тем же @check, объявляются в spec.constraints.

Пишите сюда только то, что не выражается композицией универсальных проверок из
kcad/checks/invariants.py. Сначала посмотрите список: python -m kcad.cli check --help
"""
from __future__ import annotations

from kcad.checks.framework import CheckResult, check


@check("example_project_rule")
def example_project_rule(br, min_value: float = 0.0, **_) -> CheckResult:
    """Шаблон проектной проверки: возьмите значение из спеки и сравните с порогом."""
    v = float(br.spec.value("base_height", 0.0))
    return CheckResult("example_project_rule", v >= float(min_value),
                       f"base_height={v*1000:.0f}mm (need >= {float(min_value)*1000:.0f}mm)",
                       {"value_m": v})
