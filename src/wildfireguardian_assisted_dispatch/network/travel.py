"""Travel-time models.

Phase 1 ships exactly one model: constant free-flow travel time per edge.

This is a modelling decision, not an oversight.  A time-dependent speed model
interacts with the no-waiting rule in ways that need their own audit (in
particular, non-FIFO travel times make "leave later, arrive earlier" possible
*without* any hazard, which would confound the non-monotonicity result this
project is trying to isolate).  See docs/DECISIONS.md D-007.
"""

from __future__ import annotations

from typing import Protocol

from .graph import Edge


class TravelModel(Protocol):
    """Maps (edge, entry time) to a traversal duration in minutes."""

    def duration(self, edge: Edge, entry_time: float) -> float: ...

    @property
    def is_fifo(self) -> bool: ...


class ConstantTravelModel:
    """Duration depends only on the edge.  Trivially FIFO."""

    def duration(self, edge: Edge, entry_time: float) -> float:  # noqa: ARG002
        return edge.travel_time

    @property
    def is_fifo(self) -> bool:
        return True

    def __repr__(self) -> str:  # pragma: no cover
        return "ConstantTravelModel()"


DEFAULT_TRAVEL_MODEL = ConstantTravelModel()

__all__ = ["TravelModel", "ConstantTravelModel", "DEFAULT_TRAVEL_MODEL"]
