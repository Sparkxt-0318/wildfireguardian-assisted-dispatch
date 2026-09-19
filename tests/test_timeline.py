"""Timeline algebra and the closed-interval boundary convention."""

import pytest

from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline, Window
from wildfireguardian_assisted_dispatch.units import INFINITY


def test_closes_at_includes_the_closure_instant():
    # The documented convention: `end` is the LAST SAFE instant.
    tl = Timeline.closes_at(30)
    assert tl.is_open_at(29.9)
    assert tl.is_open_at(30.0)
    assert not tl.is_open_at(30.1)


def test_is_open_throughout_is_a_whole_interval_question():
    tl = Timeline.closes_at(30)
    assert tl.is_open_throughout(20, 30)
    assert not tl.is_open_throughout(20, 30.5)
    assert not tl.is_open_throughout(31, 32)


def test_closed_between_marks_the_open_interval_unsafe():
    tl = Timeline.closed_between(12, 18)
    assert tl.is_open_at(12) and tl.is_open_at(18)
    assert not tl.is_open_at(15)
    assert tl.windows == (Window(0.0, 12.0), Window(18.0, INFINITY))


def test_windows_are_normalised_and_merged():
    a = Timeline.from_windows([[10, 20], [0, 10], [19, 25]])
    assert a.windows == (Window(0.0, 25.0),)
    assert a == Timeline.from_windows([[0, 25]])
    assert hash(a) == hash(Timeline.from_windows([[0, 25]]))


def test_safety_horizon_distinguishes_unsafe_from_never_closing():
    reopening = Timeline.from_windows([[0, 12], [18, 25]])
    assert reopening.safety_horizon(5) == 12
    assert reopening.safety_horizon(15) is None       # currently unsafe
    assert reopening.safety_horizon(20) == 25
    assert Timeline.always_open().safety_horizon(99) == INFINITY


def test_next_opening_reports_the_reopening():
    reopening = Timeline.from_windows([[0, 12], [18, 25]])
    assert reopening.next_opening(15) == 18
    assert reopening.next_opening(5) == 5
    assert reopening.next_opening(30) is None


def test_intersect():
    a = Timeline.from_windows([[0, 20]])
    b = Timeline.from_windows([[10, 30]])
    assert a.intersect(b).windows == (Window(10.0, 20.0),)


def test_reversed_interval_is_rejected():
    with pytest.raises(ValueError):
        Timeline.always_open().is_open_throughout(10, 5)
    with pytest.raises(ValueError):
        Window(10.0, 5.0)


def test_always_closed_is_falsey_and_never_open():
    tl = Timeline.always_closed()
    assert not tl
    assert not tl.is_open_at(0)
    assert tl.describe() == "never safe"
