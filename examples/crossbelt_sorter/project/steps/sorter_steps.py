"""Runtime-шаги кроссбелт-сортера.

Каждый шаг объявляет requires/provides. Именно поэтому петля второго круга не требует
отдельной ветки в коде: если dispatch не получил уверенной категории, его предусловие
не выполнено, каретка едет дальше и попадает в recirculate.
"""
from __future__ import annotations

import random

from kcad.runtime.context import Context
from kcad.runtime.graph import step


@step("induct", provides=["carrier_id", "item"],
      description="Передать товар с накопителя на свободную каретку, привязав ID.")
def induct(ctx: Context):
    n = int(ctx.get("_next_carrier", 0))
    count = int(ctx.value("carrier_count", 16))
    ctx.set("_next_carrier", (n + 1) % count)
    ctx.set("carrier_id", n)
    ctx.set("item", ctx.get("item_spec") or {"name": f"item_{n}", "size": [0.3, 0.2, 0.15]})
    ctx.say(f"инъекция товара на каретку #{n}")


@step("perceive", requires=["item"], provides=["observation"],
      description="Снять стереопару / глубину над накопителем.")
def perceive(ctx: Context):
    item = ctx.get("item")
    lap = int(ctx.get("lap", 0))
    noise = 0.004 if lap == 0 else 0.002      # второй круг снимается точнее
    obs = {"dims": [d + random.gauss(0, noise) for d in item["size"]],
           "k_round": item.get("k_round", 0.35) + random.gauss(0, 0.01)}
    ctx.set("observation", obs)


@step("classify", requires=["observation"], provides=["category", "confidence"],
      description="Габариты + круг в сечении -> одна из трёх категорий.")
def classify(ctx: Context):
    obs = ctx.get("observation")
    dims = sorted(obs["dims"])
    lo, hi = [0.010] * 3, sorted([0.450, 0.320, 0.320])
    oversize = any(d < lo[i] for i, d in enumerate(dims)) or \
        any(d > hi[i] for i, d in enumerate(dims))
    if oversize:
        cat, margin = "C", min(abs(d - h) for d, h in zip(dims, hi))
    elif obs["k_round"] > 0.8:
        cat, margin = "D", abs(obs["k_round"] - 0.8)
    else:
        cat, margin = "B", min(min(abs(d - h) for d, h in zip(dims, hi)),
                               abs(obs["k_round"] - 0.8))
    conf = min(1.0, margin / 0.010)
    ctx.set("category", cat)
    ctx.set("confidence", conf)
    ctx.say(f"категория {cat}, уверенность {conf:.2f}")


def _confident(ctx: Context) -> bool:
    """Сбрасываем, если уверены — либо если исчерпали круги и уходим в ручной разбор."""
    if ctx.get("force_manual"):
        return True
    return float(ctx.get("confidence", 0.0)) >= float(ctx.get("min_confidence", 0.5))


@step("dispatch", requires=["carrier_id", "category", "confidence"],
      guard=_confident, provides=["dispatched"],
      description="Дать команду сброса в зоне нужного кейджа по позиции энкодера.")
def dispatch(ctx: Context):
    cat = "MANUAL" if ctx.get("force_manual") else ctx.get("category")
    ctx.set("dispatched", {"carrier": ctx.get("carrier_id"), "zone": cat,
                           "speed": ctx.value("eject_speed")})
    ctx.say(f"сброс каретки #{ctx.get('carrier_id')} в зону {cat}")


@step("recirculate", provides=["lap"],
      description="Неуверенный случай: каретка не сбрасывает и идёт на второй круг.")
def recirculate(ctx: Context):
    """Ограниченная рециркуляция: после max_laps товар уходит в ручной разбор.

    Без этого ограничения неуверенный товар крутится вечно — что и показал первый
    прогон графа. Промышленные системы всегда ставят такой предохранитель.
    """
    lap = int(ctx.get("lap", 0)) + 1
    ctx.set("lap", lap)
    ctx.data.pop("dispatched", None)
    ctx.t += float(ctx.value("loop_perimeter", 20.0)) / float(ctx.value("belt_speed", 1.0))
    if lap >= int(ctx.get("max_laps", 2)):
        ctx.set("force_manual", True)
        ctx.set("category", "MANUAL")
        ctx.say(f"круги исчерпаны (lap={lap}) -> ручной разбор")
    else:
        ctx.say(f"повторный круг (lap={lap})")
