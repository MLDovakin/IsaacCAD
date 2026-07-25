"""Проектные инварианты кроссбелт-сортера.

Сюда попадает то, что не выражается композицией универсальных проверок.
Регистрируются тем же декоратором @check и объявляются в spec.constraints.
"""
from __future__ import annotations

import math

import numpy as np

from kcad.checks.framework import CheckResult, check


@check("carrier_wall_covers_item")
def carrier_wall_covers_item(br, item_height: float, min_ratio: float = 0.2,
                             **_) -> CheckResult:
    """Борт каретки должен удерживать товар при динамике приёма.

    Статически при малом угле хватает пары сантиметров, но реальный триггер — подскок
    при передаче с накопителя, поэтому меряем долю от высоты худшего товара.
    """
    wall = float(br.spec.value("wall_height"))
    ratio = wall / float(item_height)
    return CheckResult("carrier_wall_covers_item", ratio >= float(min_ratio),
                       f"wall {wall*1000:.0f}mm = {ratio*100:.0f}% of item "
                       f"{float(item_height)*1000:.0f}mm (need >= {min_ratio*100:.0f}%)",
                       {"ratio": ratio})


@check("throughput")
def throughput(br, pitch: float, speed: float, min_items_per_hour: float,
               **_) -> CheckResult:
    """Теоретический темп: одна каретка на шаг pitch при скорости speed."""
    rate = float(speed) / float(pitch) * 3600.0
    return CheckResult("throughput", rate >= float(min_items_per_hour),
                       f"{rate:.0f} items/h (need {float(min_items_per_hour):.0f})",
                       {"items_per_hour": rate})


@check("cage_reachable_from_deck")
def cage_reachable_from_deck(br, cage_part: str, path: str = "carousel",
                             tolerance: float = 0.150, **_) -> CheckResult:
    """Дальность баллистического сброса должна дотягивать от трассы до кейджа.

    Меряем от БЛИЖАЙШЕЙ точки трассы, а не от центра петли: сброс происходит с ветви
    карусели, и разница между этими двумя опорами — половина ширины петли.
    """
    from kcad.build.paths import path_points_world

    pts = path_points_world(br.frames, br.spec.paths[path])
    cage = br.instance_world[cage_part][0][:3, 3]
    lateral = br.frames.lateral()
    cage_y = float(np.dot(cage, lateral))
    dist = min(abs(cage_y - float(np.dot(p, lateral))) for p in pts)
    reach = float(br.spec.value("lateral_at_landing", 0.0))
    ok = abs(reach - dist) <= float(tolerance)
    return CheckResult(f"cage_reachable[{cage_part}]", ok,
                       f"track-to-cage {dist*1000:.0f}mm vs ballistic reach "
                       f"{reach*1000:.0f}mm (tol {float(tolerance)*1000:.0f}mm)",
                       {"distance_m": dist, "reach_m": reach})
