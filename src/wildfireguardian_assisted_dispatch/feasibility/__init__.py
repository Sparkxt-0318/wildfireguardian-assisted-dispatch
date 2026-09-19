"""Dispatch-time feasibility: the set T, its shape, and its sensitivities."""

from .dispatch import (
    DispatchOutcome,
    DispatchSweep,
    FeasibleDispatchSet,
    NonMonotonicFeasibilityError,
    dispatch_grid,
    p_success,
    sweep_dispatch_times,
)
from .refine import Transition, refine_transitions
from .sensitivity import PickupCase, PickupSensitivity, sweep_pickup_durations

__all__ = [
    "dispatch_grid",
    "sweep_dispatch_times",
    "p_success",
    "DispatchSweep",
    "DispatchOutcome",
    "FeasibleDispatchSet",
    "NonMonotonicFeasibilityError",
    "refine_transitions",
    "Transition",
    "sweep_pickup_durations",
    "PickupSensitivity",
    "PickupCase",
]
