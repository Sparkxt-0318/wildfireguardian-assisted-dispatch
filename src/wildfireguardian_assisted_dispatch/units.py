"""Canonical units and numeric conventions.

Canonical time unit: **minutes** (float), measured from the scenario epoch
``t = 0``.  See docs/TIME_SEMANTICS.md for the full rationale; the short version
is that hand-checkable fixtures are the primary validation instrument in this
phase, and minutes keep every fixture arithmetic mentally verifiable.

All time comparisons in this package go through the helpers below so that the
boundary convention is defined in exactly one place.
"""

from __future__ import annotations

# Absolute tolerance for time comparisons, in minutes.  Times in this project
# come from summing a handful of exactly-representable fixture constants, so
# this is a guard against float dust, not a modelling parameter.
EPS: float = 1e-9

MINUTE: float = 1.0
HOUR: float = 60.0

INFINITY: float = float("inf")


def leq(a: float, b: float) -> bool:
    """``a <= b`` within :data:`EPS`."""
    return a <= b + EPS


def geq(a: float, b: float) -> bool:
    """``a >= b`` within :data:`EPS`."""
    return a >= b - EPS


def lt(a: float, b: float) -> bool:
    """``a < b`` within :data:`EPS`."""
    return a < b - EPS


def gt(a: float, b: float) -> bool:
    """``a > b`` within :data:`EPS`."""
    return a > b + EPS


def approx(a: float, b: float) -> bool:
    """``a == b`` within :data:`EPS`."""
    return abs(a - b) <= EPS


def quantize(t: float, places: int = 6) -> float:
    """Round a time for use as a dictionary key in state de-duplication."""
    return round(t, places)


__all__ = [
    "EPS",
    "MINUTE",
    "HOUR",
    "INFINITY",
    "leq",
    "geq",
    "lt",
    "gt",
    "approx",
    "quantize",
]
