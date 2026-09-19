"""Declarative scenario configuration.

A config file describes one study: a network, a mission, a hazard ensemble and
a dispatch grid.  It can also just name a fixture and override a few fields,
which is how most experiments start.

The loader is deliberately strict.  Unknown keys are errors, not warnings: a
silently ignored ``pickup_duration`` (instead of ``pickup``) would produce a
plausible-looking feasibility set for the wrong mission, and nothing downstream
would ever notice.

Example
-------
.. code-block:: yaml

    name: ridge-study
    network:
      nodes:
        - {id: base, kind: base}
        - {id: home, kind: residence}
        - {id: shelter, kind: destination}
      roads:
        - {u: base, v: home, travel_time: 10}
        - {u: home, v: shelter, travel_time: 10, corridor: egress}
    mission:
      base: base
      resident: home
      destinations:
        - {node: shelter, min_safe_dwell: 0}
      pickup: {duration: 5}
      policy: {admission: full_interval, horizon: 120}
    hazards:
      scenarios:
        - name: coherent
          weight: 1.0
          edges:
            egress: {closes_at: 40}
    sweep: {start: 0, stop: 30, step: 1, threshold: 1.0}
    dispatch_time: 0
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..feasibility.dispatch import dispatch_grid
from ..hazards.scenario import HazardScenario, ScenarioEnsemble
from ..hazards.semantics import TraversalAdmission
from ..hazards.timeline import Timeline
from ..missions.policy import MissionPolicy, WaitingPolicy
from ..missions.spec import Destination, MissionSpec
from ..network.graph import NodeKind, RoadNetwork
from ..service.pickup import PickupModel
from ..units import INFINITY

try:  # pragma: no cover - environment dependent
    import yaml
    HAVE_YAML = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_YAML = False


class ConfigError(ValueError):
    """The configuration does not describe a well-formed study."""


@dataclass(frozen=True)
class StudyConfig:
    """A loaded study: everything the CLI needs to run."""

    name: str
    spec: MissionSpec
    ensemble: ScenarioEnsemble
    grid: tuple[float, ...]
    threshold: float = 1.0
    dispatch_time: float | None = None
    source: str = "<inline>"
    fixture_key: str | None = None

    def describe(self) -> str:
        lines = [f"study {self.name!r} from {self.source}"]
        if self.fixture_key:
            lines.append(f"  built on fixture {self.fixture_key}")
        lines.append(self.spec.describe())
        lines.append(f"  scenarios: {', '.join(s.name for s in self.ensemble)}")
        lines.append(f"  grid     : {self.grid[0]:g}..{self.grid[-1]:g} min "
                     f"({len(self.grid)} samples)")
        lines.append(f"  threshold: q = {self.threshold:g}")
        return "\n".join(lines)


# -- parsing helpers --------------------------------------------------------

def _require_keys(mapping: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        raise ConfigError(
            f"{where}: unknown key(s) {sorted(unknown)}; "
            f"allowed keys are {sorted(allowed)}"
        )


def parse_timeline(spec: Any, where: str) -> Timeline:
    """Build a :class:`Timeline` from one of the declarative forms."""
    if spec is None or spec is True:
        return Timeline.always_open()
    if spec is False:
        return Timeline.always_closed()
    if not isinstance(spec, Mapping):
        raise ConfigError(f"{where}: expected a mapping, got {type(spec).__name__}")
    _require_keys(spec, {"always_open", "always_closed", "closes_at", "opens_at",
                         "closed_between", "open_between", "windows"}, where)
    if len(spec) != 1:
        raise ConfigError(
            f"{where}: give exactly one timeline form, got {sorted(spec)}"
        )
    (form, value), = spec.items()
    if form == "always_open":
        return Timeline.always_open()
    if form == "always_closed":
        return Timeline.always_closed()
    if form == "closes_at":
        return Timeline.closes_at(float(value))
    if form == "opens_at":
        return Timeline.opens_at(float(value))
    if form in {"closed_between", "open_between"}:
        if not isinstance(value, Sequence) or len(value) != 2:
            raise ConfigError(f"{where}: {form} takes [start, end]")
        a, b = float(value[0]), float(value[1])
        return (Timeline.closed_between(a, b) if form == "closed_between"
                else Timeline.open_between(a, b))
    if form == "windows":
        if not isinstance(value, Sequence):
            raise ConfigError(f"{where}: windows takes a list of [start, end] pairs")
        return Timeline.from_windows(
            [(float(w[0]), INFINITY if w[1] is None else float(w[1])) for w in value]
        )
    raise ConfigError(f"{where}: unknown timeline form {form!r}")  # pragma: no cover


def parse_network(payload: Mapping[str, Any], name: str) -> RoadNetwork:
    _require_keys(payload, {"name", "nodes", "roads"}, "network")
    net = RoadNetwork(payload.get("name", name))
    for entry in payload.get("nodes", []):
        if isinstance(entry, str):
            net.add_node(entry)
            continue
        _require_keys(entry, {"id", "kind", "label"}, "network.nodes")
        net.add_node(entry["id"], NodeKind(entry.get("kind", "junction")),
                     entry.get("label", ""))
    for entry in payload.get("roads", []):
        _require_keys(entry, {"u", "v", "travel_time", "oneway", "corridor", "label"},
                      "network.roads")
        net.add_road(
            entry["u"], entry["v"], float(entry["travel_time"]),
            oneway=bool(entry.get("oneway", False)),
            corridor=entry.get("corridor"), label=entry.get("label", ""),
        )
    return net


def parse_pickup(payload: Any) -> PickupModel:
    if payload is None:
        raise ConfigError("mission.pickup is required")
    if isinstance(payload, (int, float)):
        return PickupModel(float(payload))
    _require_keys(payload, {"duration", "profile", "note"}, "mission.pickup")
    if "profile" in payload and "duration" not in payload:
        return PickupModel.of(payload["profile"])
    if "duration" not in payload:
        raise ConfigError("mission.pickup needs a duration or a profile")
    return PickupModel(float(payload["duration"]),
                       payload.get("profile", "custom"),
                       payload.get("note", ""))


def parse_policy(payload: Mapping[str, Any] | None) -> MissionPolicy:
    payload = payload or {}
    _require_keys(payload, {"admission", "waiting", "horizon", "max_states",
                            "max_resident_arrivals", "allow_node_revisits"},
                  "mission.policy")
    return MissionPolicy(
        admission=TraversalAdmission(payload.get("admission", "full_interval")),
        waiting=WaitingPolicy(payload.get("waiting", "prohibited")),
        horizon=float(payload.get("horizon", 480.0)),
        max_states=int(payload.get("max_states", 200_000)),
        max_resident_arrivals=int(payload.get("max_resident_arrivals", 64)),
        allow_node_revisits=bool(payload.get("allow_node_revisits", False)),
    )


def parse_destinations(payload: Sequence[Any]) -> tuple[Destination, ...]:
    out: list[Destination] = []
    for entry in payload:
        if isinstance(entry, str):
            out.append(Destination(entry))
            continue
        _require_keys(entry, {"node", "kind", "min_safe_dwell", "available_from",
                              "available_until", "label", "priority"},
                      "mission.destinations")
        out.append(Destination(
            node=entry["node"],
            kind=NodeKind(entry.get("kind", "destination")),
            min_safe_dwell=float(entry.get("min_safe_dwell", 0.0)),
            available_from=float(entry.get("available_from", 0.0)),
            available_until=float(entry.get("available_until", INFINITY)),
            label=entry.get("label", ""),
            priority=int(entry.get("priority", 0)),
        ))
    if not out:
        raise ConfigError("mission.destinations must list at least one destination")
    return tuple(out)


def parse_scenarios(payload: Mapping[str, Any]) -> ScenarioEnsemble:
    _require_keys(payload, {"scenarios"}, "hazards")
    entries = payload.get("scenarios") or []
    if not entries:
        raise ConfigError("hazards.scenarios must list at least one scenario")
    scenarios: list[HazardScenario] = []
    for entry in entries:
        _require_keys(entry, {"name", "weight", "edges", "nodes", "description"},
                      "hazards.scenarios")
        name = entry["name"]
        scenarios.append(HazardScenario(
            name=name,
            edges={k: parse_timeline(v, f"hazards.{name}.edges.{k}")
                   for k, v in (entry.get("edges") or {}).items()},
            nodes={k: parse_timeline(v, f"hazards.{name}.nodes.{k}")
                   for k, v in (entry.get("nodes") or {}).items()},
            weight=float(entry.get("weight", 1.0)),
            description=entry.get("description", ""),
        ))
    return ScenarioEnsemble.of(scenarios)


def parse_sweep(payload: Mapping[str, Any] | None) -> tuple[tuple[float, ...], float]:
    payload = payload or {}
    _require_keys(payload, {"start", "stop", "step", "threshold"}, "sweep")
    grid = dispatch_grid(float(payload.get("start", 0.0)),
                         float(payload.get("stop", 60.0)),
                         float(payload.get("step", 1.0)))
    return grid, float(payload.get("threshold", 1.0))


# -- loading ----------------------------------------------------------------

TOP_LEVEL_KEYS = {"name", "fixture", "network", "mission", "hazards", "sweep",
                  "dispatch_time", "pickup", "policy"}


def build_config(payload: Mapping[str, Any], source: str = "<inline>") -> StudyConfig:
    """Build a :class:`StudyConfig` from an already-parsed mapping."""
    if not isinstance(payload, Mapping):
        raise ConfigError("the top level of a config must be a mapping")
    _require_keys(payload, TOP_LEVEL_KEYS, "config")

    if "fixture" in payload:
        return _config_from_fixture(payload, source)

    for required in ("network", "mission", "hazards"):
        if required not in payload:
            raise ConfigError(
                f"config needs a {required!r} section (or a 'fixture' shortcut)"
            )

    name = payload.get("name", "study")
    mission = payload["mission"]
    _require_keys(mission, {"base", "resident", "destinations", "pickup", "policy",
                            "name"}, "mission")
    net = parse_network(payload["network"], name)
    spec = MissionSpec(
        network=net,
        base=mission["base"],
        resident=mission["resident"],
        destinations=parse_destinations(mission.get("destinations", [])),
        pickup=parse_pickup(mission.get("pickup")),
        policy=parse_policy(mission.get("policy")),
        name=mission.get("name", name),
    )
    ensemble = parse_scenarios(payload["hazards"])
    ensemble.validate(net)
    grid, threshold = parse_sweep(payload.get("sweep"))
    dispatch_time = payload.get("dispatch_time")
    return StudyConfig(
        name=name, spec=spec, ensemble=ensemble, grid=grid, threshold=threshold,
        dispatch_time=None if dispatch_time is None else float(dispatch_time),
        source=source,
    )


def _config_from_fixture(payload: Mapping[str, Any], source: str) -> StudyConfig:
    from ..fixtures import load as load_fixture  # local import: avoids a cycle

    key = str(payload["fixture"])
    fixture = load_fixture(key)
    spec = fixture.spec
    if "pickup" in payload:
        spec = spec.with_pickup(parse_pickup(payload["pickup"]))
    if "policy" in payload:
        spec = spec.with_policy(parse_policy(payload["policy"]))

    grid, threshold = (fixture.grid, fixture.threshold)
    if "sweep" in payload:
        grid, threshold = parse_sweep(payload["sweep"])
    dispatch_time = payload.get("dispatch_time")
    return StudyConfig(
        name=payload.get("name", f"fixture-{key}"),
        spec=spec, ensemble=fixture.ensemble, grid=grid, threshold=threshold,
        dispatch_time=None if dispatch_time is None else float(dispatch_time),
        source=source, fixture_key=key,
    )


def load_config(path: str | Path) -> StudyConfig:
    """Load a YAML or JSON study configuration."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no such config file: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        if not HAVE_YAML:
            raise ConfigError(
                f"{path} is YAML but PyYAML is not installed; "
                "install it, or use a JSON config"
            )
        payload = yaml.safe_load(text)
    elif path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        raise ConfigError(f"{path}: expected a .yaml, .yml or .json config")
    return build_config(payload or {}, source=str(path))


__all__ = [
    "ConfigError",
    "StudyConfig",
    "load_config",
    "build_config",
    "parse_timeline",
    "parse_network",
    "parse_pickup",
    "parse_policy",
    "parse_destinations",
    "parse_scenarios",
    "parse_sweep",
]
