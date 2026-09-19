"""The command line surface, end to end."""

import json

import pytest

from wildfireguardian_assisted_dispatch.cli.main import main
from wildfireguardian_assisted_dispatch.cli.plotting import ascii_strip, has_matplotlib
from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.scenarios.io import HAVE_PARQUET, read_rows


def test_evaluate_prints_a_mission_log(capsys):
    assert main(["evaluate", "a", "--dispatch-time", "0"]) == 0
    out = capsys.readouterr().out
    assert "SUCCESS" in out
    assert "pickup, 5 min" in out
    assert "arrival at shelter t=25" in out


def test_evaluate_reports_a_failure_with_its_hazard_conflict(capsys):
    assert main(["evaluate", "a", "--dispatch-time", "20"]) == 0
    out = capsys.readouterr().out
    assert "FAILED (no_safe_route_egress)" in out
    assert "hazard conflict" in out


def test_evaluate_can_write_json(tmp_path, capsys):
    path = tmp_path / "records.json"
    assert main(["evaluate", "c", "--dispatch-time", "10", "--json", str(path)]) == 0
    payload = json.loads(path.read_text())
    assert payload["dispatch_time"] == 10
    record = payload["results"][0]
    assert record["mission_success"] is True
    # The full record the research plan asks for.
    assert set(record) >= {
        "dispatch_time", "ingress_route", "resident_arrival_time",
        "pickup_start", "pickup_end", "egress_route", "destination_arrival",
        "mission_success", "failure_reason", "hazard_conflict",
    }


def test_sweep_prints_the_strip_and_the_monotonicity_warning(capsys):
    assert main(["sweep", "f"]) == 0
    out = capsys.readouterr().out
    assert "#..........###" in out
    assert "NOT monotone" in out
    assert "NOT a valid latest-dispatch summary" in out


def test_sweep_writes_a_table(tmp_path, capsys):
    suffix = ".parquet" if HAVE_PARQUET else ".csv"
    path = tmp_path / f"results{suffix}"
    assert main(["sweep", "b_ensemble", "--out", str(path)]) == 0
    rows = read_rows(path)
    assert len(rows) == 41
    assert float(rows[0]["p_success"]) == pytest.approx(1.0)


def test_sweep_detail_rows_cover_every_scenario(tmp_path):
    path = tmp_path / "detail.csv"
    assert main(["sweep", "b_ensemble", "--out", str(path), "--detail"]) == 0
    rows = read_rows(path)
    assert len({r["scenario"] for r in rows}) == 3


def test_sweep_refinement_locates_the_boundary(capsys):
    assert main(["sweep", "a", "--refine", "--tolerance", "0.01"]) == 0
    out = capsys.readouterr().out
    assert "refined boundaries" in out
    assert "feasibility is lost between t=15" in out


def test_pickup_sweep_reports_all_four_durations(capsys):
    assert main(["pickup-sweep", "d"]) == 0
    out = capsys.readouterr().out
    for duration in ("2", "5", "10", "15"):
        assert f"pickup {duration:>5} min" in out
    assert "not validated medical or triage categories" in out


def test_plot_feasibility_reads_a_sweep_table(tmp_path, capsys):
    table = tmp_path / "f.csv"
    main(["sweep", "f", "--out", str(table)])
    capsys.readouterr()
    assert main(["plot-feasibility", str(table)]) == 0
    out = capsys.readouterr().out
    assert "feasible dispatch set" in out
    assert "#..........###" in out


@pytest.mark.skipif(not has_matplotlib(), reason="matplotlib not installed")
def test_plot_feasibility_writes_a_png(tmp_path):
    table = tmp_path / "f.csv"
    main(["sweep", "f", "--out", str(table)])
    png = tmp_path / "f.png"
    assert main(["plot-feasibility", str(table), "--out", str(png)]) == 0
    assert png.exists() and png.stat().st_size > 1000


def test_fixtures_check_passes(capsys):
    assert main(["fixtures", "--check"]) == 0
    assert "fixtures match their hand calculations" in capsys.readouterr().out


def test_fixtures_show_prints_the_hand_calculation(capsys):
    assert main(["fixtures", "--show", "c"]) == 0
    out = capsys.readouterr().out
    assert "t_dagger = 45 - (10 + 8 + 5 + 8) = 14" in out


def test_a_bad_config_path_is_a_clean_error(capsys):
    assert main(["sweep", "does-not-exist.yaml"]) == 2
    assert "wg-dispatch:" in capsys.readouterr().err


def test_ascii_strip_downsamples_wide_grids():
    strip = ascii_strip(load("e").feasible_set(), width=20)
    assert len(strip.strip.strip()) == 20
    assert "feasible" in strip.legend
