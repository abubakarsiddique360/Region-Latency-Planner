import json

import pytest

from region_latency_planner.choose import exact, greedy, sweep
from region_latency_planner.cli import main
from region_latency_planner.model import problem_from_dict
from region_latency_planner.report import (
    render_compare,
    render_json,
    render_matrix,
    render_plan,
    render_sweep,
)
from region_latency_planner.score import score

PROBLEM = {
    "name": "global",
    "regions": [{"name": "us", "cost": 10}, {"name": "eu", "cost": 12}],
    "clients": [
        {"name": "virginia", "weight": 0.6, "rtt": {"us": 8, "eu": 90}},
        {"name": "frankfurt", "weight": 0.4, "rtt": {"us": 85, "eu": 9}},
    ],
}


@pytest.fixture
def problem_file(tmp_path):
    problem = problem_from_dict(PROBLEM)
    path = tmp_path / "net.json"
    path.write_text(json.dumps(PROBLEM), encoding="utf-8")
    return problem, path


def test_plan_report_lists_every_client(problem_file):
    problem, _ = problem_file
    text = render_plan(problem, score(problem, ("us", "eu")))
    assert "virginia" in text
    assert "frankfurt" in text
    assert "mean rtt" in text


def test_sweep_report_shows_marginal_gain(problem_file):
    problem, _ = problem_file
    text = render_sweep(problem, sweep(problem))
    assert "no measurable gain" in text or "-" in text
    assert "<target" in text


def test_matrix_report_has_costs(problem_file):
    problem, _ = problem_file
    text = render_matrix(problem)
    assert "RTT matrix" in text
    assert "cost units" in text


def test_compare_report_marks_the_gap(problem_file):
    problem, _ = problem_file
    rows = [("exact", exact(problem, 1)), ("greedy", greedy(problem, 1))]
    text = render_compare(problem, rows)
    assert "Method comparison at k=1" in text


def test_json_report_is_machine_readable(problem_file):
    problem, _ = problem_file
    payload = json.loads(render_json(score(problem, ("us",))))
    assert payload["regions"] == ["us"]
    assert payload["assignments"][0]["region"] == "us"
    assert round(payload["mean_rtt"], 3) == pytest.approx(38.8, abs=0.1)


def test_cli_plan_text(problem_file, capsys):
    _, path = problem_file
    assert main(["plan", "--problem", str(path), "--regions", "2"]) == 0
    output = capsys.readouterr().out
    assert "using exact" in output


def test_cli_plan_greedy_and_improved(problem_file, capsys):
    _, path = problem_file
    assert main(["plan", "--problem", str(path), "--regions", "1", "--method", "greedy"]) == 0
    assert main(["plan", "--problem", str(path), "--regions", "1", "--method", "improved"]) == 0
    assert "Plan for global" in capsys.readouterr().out


def test_cli_plan_json(problem_file, capsys):
    _, path = problem_file
    assert main(["plan", "--problem", str(path), "--regions", "1", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["regions"] == ["us"]


def test_cli_sweep(problem_file, capsys):
    _, path = problem_file
    assert main(["sweep", "--problem", str(path)]) == 0
    assert "Latency by number of regions" in capsys.readouterr().out


def test_cli_compare(problem_file, capsys):
    _, path = problem_file
    assert main(["compare", "--problem", str(path), "--regions", "2"]) == 0
    output = capsys.readouterr().out
    assert "exact" in output and "greedy" in output and "improved" in output


def test_cli_matrix(problem_file, capsys):
    _, path = problem_file
    assert main(["matrix", "--problem", str(path)]) == 0
    assert "RTT matrix" in capsys.readouterr().out


def test_cli_budget(problem_file, capsys):
    _, path = problem_file
    assert main(["budget", "--problem", str(path), "--budget", "15"]) == 0
    assert "Budget plan" in capsys.readouterr().out


def test_cli_budget_json(problem_file, capsys):
    _, path = problem_file
    assert main(["budget", "--problem", str(path), "--budget", "15", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["cost"] <= 15


def test_cli_missing_file(tmp_path, capsys):
    assert main(["plan", "--problem", str(tmp_path / "nope.json"), "--regions", "1"]) == 2
    assert "file not found" in capsys.readouterr().err


def test_cli_bad_k(problem_file, capsys):
    _, path = problem_file
    assert main(["plan", "--problem", str(path), "--regions", "9"]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_budget_too_small(problem_file, capsys):
    _, path = problem_file
    assert main(["budget", "--problem", str(path), "--budget", "1"]) == 2
    assert "error:" in capsys.readouterr().err
