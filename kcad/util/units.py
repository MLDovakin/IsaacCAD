"""Units. Internal representation is always SI-ish: metres, degrees, seconds.

Rule of the skill: the spec may use suffixed values ('900mm', '5.7deg'), but by the
time a value reaches build/ or checks/ it is already a float in metres/degrees.
No place in the codebase where the unit is implied.
"""
from __future__ import annotations

import re

_LENGTH = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}
_ANGLE = {"deg": 1.0, "rad": 57.29577951308232}
_TIME = {"s": 1.0, "ms": 0.001, "min": 60.0}
_SPEED = {"m/s": 1.0, "mm/s": 0.001, "km/h": 1 / 3.6}
_MASS = {"kg": 1.0, "g": 0.001, "t": 1000.0}

_NUM = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*([a-zA-Z/]+)?\s*$")


def _parse(value, table: dict[str, float], name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name}: bool is not a quantity")
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM.match(str(value))
    if not m:
        raise ValueError(f"cannot parse {name} value: {value!r}")
    num, unit = m.group(1), m.group(2)
    if unit is None:
        return float(num)
    if unit not in table:
        raise ValueError(f"unknown {name} unit {unit!r} in {value!r}; known: {sorted(table)}")
    return float(num) * table[unit]


def length(value) -> float:
    """-> metres. Accepts 0.9, '900mm', '90cm', '3in'."""
    return _parse(value, _LENGTH, "length")


def angle(value) -> float:
    """-> degrees. Accepts 5.7, '5.7deg', '0.1rad'."""
    return _parse(value, _ANGLE, "angle")


def time(value) -> float:
    return _parse(value, _TIME, "time")


def speed(value) -> float:
    return _parse(value, _SPEED, "speed")


def mass(value) -> float:
    return _parse(value, _MASS, "mass")


def quantity(value, kind: str) -> float:
    return {"length": length, "angle": angle, "time": time,
            "speed": speed, "mass": mass}[kind](value)


def mm(metres: float) -> str:
    return f"{metres * 1000:.1f}mm"
