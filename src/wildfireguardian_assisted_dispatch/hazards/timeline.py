"""Hazard timelines: when a network element is safe to occupy.

A :class:`Timeline` is a set of disjoint, ascending *open windows* — the closed
time intervals during which an element (edge corridor or node) may be occupied.
Outside those windows the element is unsafe.

Boundary convention (see docs/TIME_SEMANTICS.md, D-002)
-------------------------------------------------------
Windows are **closed** intervals ``[start, end]``.  ``end`` is the *last safe
instant*: an element that "closes at 25" is safe at exactly t = 25 and unsafe
for every t > 25.  Conversely ``closed_between(a, b)`` marks the element unsafe
on the *open* interval ``(a, b)``.

This convention is chosen so that fixture deadlines read as ``arrival <= T``
rather than ``arrival < T``, which keeps hand-calculation honest.  Because these
hazards are synthetic step functions, the difference between the two
conventions is a measure-zero set of instants and carries no physical content —
but it must be stated once and obeyed everywhere, which is what this module is
for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..units import INFINITY, geq, gt, leq, lt


@dataclass(frozen=True, order=True)
class Window:
    """A closed interval ``[start, end]`` of safety."""

    start: float = 0.0
    end: float = INFINITY

    def __post_init__(self) -> None:
        if gt(self.start, self.end):
            raise ValueError(f"window start {self.start} is after end {self.end}")

    def contains(self, t: float) -> bool:
        return geq(t, self.start) and leq(t, self.end)

    def contains_interval(self, a: float, b: float) -> bool:
        return geq(a, self.start) and leq(b, self.end)

    def as_tuple(self) -> tuple[float, float]:
        return (self.start, self.end)

    def __str__(self) -> str:  # pragma: no cover - display
        end = "inf" if self.end == INFINITY else f"{self.end:g}"
        return f"[{self.start:g}, {end}]"


class Timeline:
    """Availability of one element across time.

    Immutable.  Windows are normalised on construction: sorted, overlapping or
    touching windows merged, so ``windows`` is always a canonical form and two
    equivalent timelines compare equal.
    """

    __slots__ = ("_windows",)

    def __init__(self, windows: Iterable[Window | Sequence[float]] = ()) -> None:
        normalised: list[Window] = []
        raw = []
        for w in windows:
            raw.append(w if isinstance(w, Window) else Window(
                float(w[0]),
                INFINITY if w[1] is None else float(w[1]),
            ))
        for w in sorted(raw):
            if normalised and leq(w.start, normalised[-1].end):
                prev = normalised[-1]
                normalised[-1] = Window(prev.start, max(prev.end, w.end))
            else:
                normalised.append(w)
        self._windows: tuple[Window, ...] = tuple(normalised)

    # -- constructors -------------------------------------------------------
    @classmethod
    def always_open(cls) -> "Timeline":
        return cls([Window(0.0, INFINITY)])

    @classmethod
    def always_closed(cls) -> "Timeline":
        return cls(())

    @classmethod
    def closes_at(cls, t: float) -> "Timeline":
        """Open from the epoch through ``t`` inclusive, unsafe afterwards."""
        return cls([Window(0.0, float(t))])

    @classmethod
    def opens_at(cls, t: float) -> "Timeline":
        """Unsafe before ``t``, open from ``t`` onwards."""
        return cls([Window(float(t), INFINITY)])

    @classmethod
    def open_between(cls, a: float, b: float) -> "Timeline":
        return cls([Window(float(a), float(b))])

    @classmethod
    def closed_between(cls, a: float, b: float) -> "Timeline":
        """Unsafe on the open interval ``(a, b)``; safe elsewhere."""
        a, b = float(a), float(b)
        if not lt(a, b):
            return cls.always_open()
        return cls([Window(0.0, a), Window(b, INFINITY)])

    @classmethod
    def from_windows(cls, windows: Iterable[Sequence[float]]) -> "Timeline":
        return cls(windows)

    # -- queries ------------------------------------------------------------
    @property
    def windows(self) -> tuple[Window, ...]:
        return self._windows

    def is_open_at(self, t: float) -> bool:
        return any(w.contains(t) for w in self._windows)

    def is_open_throughout(self, a: float, b: float) -> bool:
        """True iff every instant of the closed interval ``[a, b]`` is safe."""
        if gt(a, b):
            raise ValueError(f"interval [{a}, {b}] is reversed")
        return any(w.contains_interval(a, b) for w in self._windows)

    def safety_horizon(self, t: float) -> float | None:
        """Last safe instant of the unbroken safe stretch that starts at ``t``.

        Returns ``None`` when the element is *already* unsafe at ``t``, and
        ``inf`` when the containing window never closes.  This single query is
        what the full-traversal-interval assessment is built on: an element can
        be occupied over ``[t_in, t_out]`` exactly when
        ``safety_horizon(t_in) >= t_out``.
        """
        for w in self._windows:
            if w.contains(t):
                return w.end
        return None

    def next_opening(self, t: float) -> float | None:
        """Earliest instant >= ``t`` at which the element is safe."""
        if self.is_open_at(t):
            return t
        for w in self._windows:
            if gt(w.start, t):
                return w.start
        return None

    def closure_after(self, t: float) -> float | None:
        """Finite closure time of the window containing ``t``.

        ``None`` means either "not currently safe" or "never closes"; use
        :meth:`safety_horizon` when that distinction matters.
        """
        horizon = self.safety_horizon(t)
        if horizon is None or horizon == INFINITY:
            return None
        return horizon

    # -- algebra ------------------------------------------------------------
    def intersect(self, other: "Timeline") -> "Timeline":
        out: list[Window] = []
        for a in self._windows:
            for b in other._windows:
                start, end = max(a.start, b.start), min(a.end, b.end)
                if leq(start, end):
                    out.append(Window(start, end))
        return Timeline(out)

    # -- dunder -------------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Timeline) and self._windows == other._windows

    def __hash__(self) -> int:
        return hash(self._windows)

    def __bool__(self) -> bool:
        return bool(self._windows)

    def __repr__(self) -> str:  # pragma: no cover - display
        return f"Timeline({', '.join(str(w) for w in self._windows) or 'closed'})"

    def describe(self) -> str:
        if not self._windows:
            return "never safe"
        return "safe on " + " U ".join(str(w) for w in self._windows)


ALWAYS_OPEN = Timeline.always_open()

__all__ = ["Window", "Timeline", "ALWAYS_OPEN"]
