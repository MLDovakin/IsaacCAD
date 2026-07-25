"""Проектные runtime-шаги.

Каждый шаг объявляет requires (что должно быть в контексте) и provides (что он кладёт).
Ветвление и петли выражаются через невыполненные предусловия, а не через if в коде.
"""
from __future__ import annotations

from kcad.runtime.context import Context
from kcad.runtime.graph import step


@step("example_step", requires=["item"], provides=["result"],
      description="Шаблон шага: читает item, кладёт result.")
def example_step(ctx: Context):
    ctx.set("result", {"ok": True, "item": ctx.get("item")})
    ctx.say("example_step выполнен")
