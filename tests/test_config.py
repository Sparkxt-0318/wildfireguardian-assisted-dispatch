"""The declarative config loader, and its deliberate strictness."""

import json

import pytest

from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.scenarios.config import (
    ConfigError,
    build_config,
    load_config,
    parse_timeline,
)

FULL_CONFIG = {
    "name": "ridge-study",
    "network": {
        "nodes": [
            {"id": "base", "kind": "base"},
            {"id": "home", "kind": "residence"},
            {"id": "shelter", "kind": "destination"},
        ],
        "roads": [
            {"u": "base", "v": "home", "travel_time": 10},
            {"u": "home", "v": "shelter", "travel_time": 10,
             "corridor": "egress"},
        ],
    },
    "mission": {
        "base": "base",
        "resident": "home",
        "destinations": [{"node": "shelter"}],
        "pickup": {"duration": 5},
        "policy": {"horizon": 120},
    },
    "hazards": {
        "scenarios": [
            {"name": "coherent", "weight": 1.0,
             "edges": {"egress": {"closes_at": 40}}},
        ],
    },
    "sweep": {"start": 0, "stop": 30, "step": 1, "threshold": 1.0},
}


def test_a_full_config_builds_a_runnable_study():
    study = build_config(FULL_CONFIG)
    assert study.spec.pickup.duration == 5
    assert study.grid[-1] == 30
    from wildfireguardian_assisted_dispatch.feasibility.dispatch import (
        sweep_dispatch_times,
    )
    result = sweep_dispatch_times(study.spec, study.ensemble, study.grid)
    # Same arithmetic as fixture A: 40 - 10 - 5 - 10.
    assert result.feasible_set().latest_dispatch() == 15.0


def test_unknown_keys_are_errors_not_warnings():
    payload = json.loads(json.dumps(FULL_CONFIG))
    payload["mission"]["pickup_duration"] = 5
    with pytest.raises(ConfigError, match="unknown key"):
        build_config(payload)


def test_a_fixture_shortcut_with_overrides():
    study = build_config({"fixture": "d", "pickup": {"duration": 15}})
    assert study.fixture_key == "d"
    assert study.spec.pickup.duration == 15


def test_unknown_fixture_names_are_rejected():
    with pytest.raises(KeyError, match="unknown fixture"):
        build_config({"fixture": "zzz"})


@pytest.mark.parametrize("payload,expected", [
    ({"closes_at": 30}, Timeline.closes_at(30)),
    ({"opens_at": 30}, Timeline.opens_at(30)),
    ({"closed_between": [10, 20]}, Timeline.closed_between(10, 20)),
    ({"open_between": [10, 20]}, Timeline.open_between(10, 20)),
    ({"windows": [[0, 12], [18, None]]},
     Timeline.from_windows([[0, 12], [18, None]])),
    ({"always_open": True}, Timeline.always_open()),
])
def test_timeline_forms(payload, expected):
    assert parse_timeline(payload, "test") == expected


def test_timeline_needs_exactly_one_form():
    with pytest.raises(ConfigError, match="exactly one timeline form"):
        parse_timeline({"closes_at": 3, "opens_at": 1}, "test")


def test_hazard_keys_must_match_the_network():
    payload = json.loads(json.dumps(FULL_CONFIG))
    payload["hazards"]["scenarios"][0]["edges"] = {"nonexistent": {"closes_at": 4}}
    with pytest.raises(KeyError, match="matches no edge or corridor"):
        build_config(payload)


def test_yaml_round_trip(tmp_path):
    yaml = pytest.importorskip("yaml")
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(FULL_CONFIG))
    study = load_config(path)
    assert study.name == "ridge-study"
    assert "ridge-study" in study.describe()


def test_json_configs_work_without_yaml(tmp_path):
    path = tmp_path / "study.json"
    path.write_text(json.dumps(FULL_CONFIG))
    assert load_config(path).spec.base == "base"


def test_unsupported_suffixes_are_rejected(tmp_path):
    path = tmp_path / "study.toml"
    path.write_text("nope")
    with pytest.raises(ConfigError, match="expected a .yaml"):
        load_config(path)


def test_missing_sections_are_reported_by_name():
    with pytest.raises(ConfigError, match="needs a 'network' section"):
        build_config({"mission": {}, "hazards": {}})
