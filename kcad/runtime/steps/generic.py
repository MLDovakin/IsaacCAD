"""Reusable runtime steps that are not domain-specific.

Project-specific steps live in <project>/steps/*.py and register the same way.
"""
from __future__ import annotations

from ..context import Context
from ..graph import step


@step("wait", requires=[], provides=[],
      description="Advance simulated time by ctx.data['wait_s'] (default 0.1s).")
def wait(ctx: Context):
    dt = float(ctx.get("wait_s", 0.1))
    ctx.t += dt
    if ctx.world is not None:  # pragma: no cover
        for _ in range(max(1, int(dt * 60))):
            ctx.world.step(render=False)
    return dt


@step("spawn_item", provides=["item"],
      description="Place a test item at the entry frame; ctx.data['item_spec'] optional.")
def spawn_item(ctx: Context):
    item = dict(ctx.get("item_spec") or {"name": "item_0", "size": [0.3, 0.2, 0.15]})
    entry = ctx.value("entry_frame", "entry")
    if ctx.build is not None and entry in ctx.build.spec.frames:
        item["pose"] = [float(v) for v in ctx.build.frames.origin(entry)]
    ctx.set("item", item)
    ctx.say(f"spawned {item['name']}")
    return item


@step("assign_id", requires=["item"], provides=["item_id"],
      description="Bind the item to a carrier/slot id so downstream steps can address it.")
def assign_id(ctx: Context):
    n = int(ctx.get("_id_counter", 0))
    ctx.set("_id_counter", n + 1)
    ctx.set("item_id", n)
    return n


@step("record", description="Append the current context snapshot to ctx.data['trace'].")
def record(ctx: Context):
    trace = ctx.get("trace", [])
    trace.append({"t": ctx.t, **{k: v for k, v in ctx.data.items()
                                 if not k.startswith("_") and k != "trace"}})
    ctx.set("trace", trace)
    return len(trace)
