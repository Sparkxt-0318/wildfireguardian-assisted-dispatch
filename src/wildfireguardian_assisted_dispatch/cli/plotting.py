"""Feasibility rendering: an ASCII strip always, a PNG when matplotlib is there.

The ASCII strip is the primary output, not a fallback.  This is a terminal
research tool, the feasible set is one-dimensional, and a row of characters
shows a hole in the set just as clearly as a figure does — while working over
ssh, in CI logs and in a commit message.

The PNG follows one rule that matters more than any styling choice: it is two
stacked panels on a **single shared x axis**, never two y scales on one panel.
The top panel carries P_success, the bottom carries the feasible set itself.
Colours are a validated blue/orange pair (they survive deuteranopia and
protanopia, unlike the obvious red/green), and the infeasible bands additionally
carry a 45-degree hatch and a written label, so nothing depends on colour alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..feasibility.dispatch import FeasibleDispatchSet

# Validated palette (see the project's data-visualisation notes).
FEASIBLE_COLOR = "#2a78d6"     # blue
INFEASIBLE_COLOR = "#eb6834"   # orange
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

FEASIBLE_CHAR = "#"
INFEASIBLE_CHAR = "."


@dataclass(frozen=True)
class FeasibilityStrip:
    """An ASCII rendering of a feasible dispatch set."""

    header: str
    axis: str
    strip: str
    ticks: str
    legend: str
    summary: tuple[str, ...]

    def render(self) -> str:
        lines = [self.header, "", self.axis, self.strip, self.ticks, "",
                 self.legend]
        lines += list(self.summary)
        return "\n".join(lines)


def ascii_strip(feasible: FeasibleDispatchSet, *, width: int = 72,
                title: str = "feasible dispatch set") -> FeasibilityStrip:
    """Render the feasible set as a character strip over the dispatch grid."""
    grid = feasible.grid
    if not grid:
        raise ValueError("cannot render an empty grid")

    columns = min(width, len(grid))
    # Sample the grid down to the available columns, keeping the endpoints.
    if len(grid) <= columns:
        indices = list(range(len(grid)))
    else:
        step = (len(grid) - 1) / (columns - 1)
        indices = [round(i * step) for i in range(columns)]

    strip = "".join(FEASIBLE_CHAR if feasible.flags[i] else INFEASIBLE_CHAR
                    for i in indices)
    axis_label = f"t = {grid[0]:g}"
    right_label = f"t = {grid[-1]:g}"
    pad = max(1, len(strip) - len(axis_label) - len(right_label))
    ticks = axis_label + " " * pad + right_label

    summary = [f"  windows : {feasible.format_intervals() or 'empty'}",
               f"  monotone: {feasible.is_monotone}"]
    if feasible.is_monotone and not feasible.is_empty:
        summary.append(f"  t_dagger: {feasible.supremum:g}")
    elif not feasible.is_empty:
        summary.append(f"  sup T   : {feasible.supremum:g} "
                       "(NOT a valid latest-dispatch summary)")
    summary += [f"  warning : {w}" for w in feasible.warnings]

    return FeasibilityStrip(
        header=f"{title}  (threshold q = {feasible.threshold:g}, "
               f"grid step {feasible.resolution:g} min)",
        axis="  " + "-" * len(strip),
        strip="  " + strip,
        ticks="  " + ticks,
        legend=f"  legend: '{FEASIBLE_CHAR}' feasible   "
               f"'{INFEASIBLE_CHAR}' infeasible",
        summary=tuple(summary),
    )


def has_matplotlib() -> bool:
    try:  # pragma: no cover - environment dependent
        import matplotlib  # noqa: F401
        return True
    except ImportError:  # pragma: no cover - environment dependent
        return False


def plot_feasibility(grid: Sequence[float], p_success: Sequence[float],
                     feasible: FeasibleDispatchSet, path: str | Path,
                     *, title: str = "Dispatch feasibility") -> Path:
    """Write a two-panel PNG: P_success on top, the feasible set below."""
    import matplotlib

    matplotlib.use("Agg")  # a research CLI never has a display
    import matplotlib.pyplot as plt  # noqa: E402  (must follow use())
    from matplotlib.patches import Patch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(9, 5), sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.18},
    )
    fig.patch.set_facecolor(SURFACE)
    for ax in (top, bottom):
        ax.set_facecolor(SURFACE)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(BASELINE)
        ax.tick_params(colors=INK_MUTED, labelcolor=INK_SECONDARY, length=3)

    # -- top panel: P_success as a step function (a single y axis, always) ---
    top.step(grid, p_success, where="post", color=FEASIBLE_COLOR, linewidth=2.0,
             solid_capstyle="round")
    top.axhline(feasible.threshold, color=INK_MUTED, linewidth=1.0,
                linestyle=(0, (4, 3)))
    top.annotate(f"q = {feasible.threshold:g}",
                 xy=(grid[-1], feasible.threshold), xytext=(-4, 4),
                 textcoords="offset points", ha="right", va="bottom",
                 color=INK_SECONDARY, fontsize=9)
    top.set_ylim(-0.05, 1.08)
    top.set_ylabel("P_success", color=INK_SECONDARY, fontsize=10)
    top.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    top.set_axisbelow(True)
    top.set_title(title, color=INK_PRIMARY, fontsize=12, loc="left", pad=52)
    top.annotate(
        f"feasible dispatch set T = {feasible.format_intervals() or 'empty'}"
        f"   (q = {feasible.threshold:g}, grid step "
        f"{feasible.resolution:g} min)",
        xy=(0.0, 1.02), xycoords="axes fraction", ha="left", va="bottom",
        color=INK_SECONDARY, fontsize=9,
    )
    if not feasible.is_monotone:
        top.annotate(
            "feasibility is regained after being lost - no single latest "
            "dispatch time describes this set",
            xy=(0.0, 1.12), xycoords="axes fraction", ha="left", va="bottom",
            color=INFEASIBLE_COLOR, fontsize=9,
        )

    # -- bottom panel: the feasible set, with texture and written labels ----
    bottom.set_ylim(0, 1)
    bottom.set_yticks([])
    bottom.axvspan(grid[0], grid[-1], facecolor=INFEASIBLE_COLOR, alpha=0.18,
                   hatch="///", edgecolor=INFEASIBLE_COLOR, linewidth=0.0)
    span = (grid[-1] - grid[0]) or 1.0
    for lo, hi in feasible.intervals:
        span_hi = min(hi + (feasible.resolution or 0.0), grid[-1])
        bottom.axvspan(lo, span_hi, facecolor=FEASIBLE_COLOR, alpha=0.85,
                       linewidth=0.0)
        # Only label a band wide enough to hold the text; narrow bands are
        # already named in the subtitle, and a clipped label is worse than none.
        if (span_hi - lo) / span >= 0.12:
            bottom.annotate(f"[{lo:g}, {hi:g}]",
                            xy=((lo + span_hi) / 2, 0.5), ha="center",
                            va="center", color=SURFACE, fontsize=9)
    bottom.set_xlabel("dispatch time t (min from scenario epoch)",
                      color=INK_SECONDARY, fontsize=10)
    bottom.set_ylabel("T", color=INK_SECONDARY, fontsize=10, rotation=0,
                      labelpad=14, va="center")
    bottom.legend(
        handles=[
            Patch(facecolor=FEASIBLE_COLOR, label="feasible"),
            Patch(facecolor=INFEASIBLE_COLOR, alpha=0.18, hatch="///",
                  edgecolor=INFEASIBLE_COLOR, label="infeasible"),
        ],
        loc="upper center", bbox_to_anchor=(0.5, -0.55), ncol=2,
        frameon=False, fontsize=9, labelcolor=INK_SECONDARY,
    )

    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


__all__ = ["ascii_strip", "plot_feasibility", "has_matplotlib",
           "FeasibilityStrip"]
