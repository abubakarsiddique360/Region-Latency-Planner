import json

import pytest

from region_latency_planner.model import ProblemError, load_problem, problem_from_dict

REGIONS = [
    {"name": "a", "cost": 10},
    {"name": "b", "cost": 20},
]
CLIENTS = [
    {"name": "near-a", "weight": 3, "rtt": {"a": 5, "b": 50}},
    {"name": "near-b", "weight": 1, "rtt": {"a": 60, "b": 4}},
]


def payload(clients=CLIENTS, regions=REGIONS, **extra):
    body = {"name": "tiny", "regions": regions, "clients": clients}
    body.update(extra)
    return body


def test_parses_regions_clients_and_weights():
    problem = problem_from_dict(payload())
    assert problem.name == "tiny"
    assert problem.region_names == ("a", "b")
    assert problem.total_weight == 4
    assert problem.target_ms == 100
    assert problem.cost_of(("a",)) == 10


def test_region_string_shorthand_is_allowed():
    problem = problem_from_dict(payload(regions=["a", "b"]))
    assert [region.cost for region in problem.regions] == [0.0, 0.0]


def test_rejects_empty_regions():
    with pytest.raises(ProblemError, match="regions"):
        problem_from_dict({"regions": [], "clients": CLIENTS})


def test_rejects_duplicate_region():
    with pytest.raises(ProblemError, match="duplicate region"):
        problem_from_dict(payload(regions=REGIONS + [{"name": "a"}]))


def test_rejects_missing_rtt_entry():
    clients = [{"name": "x", "weight": 1, "rtt": {"a": 1}}]
    with pytest.raises(ProblemError, match="missing rtt"):
        problem_from_dict(payload(clients=clients))


def test_rejects_unknown_region_in_rtt():
    clients = [{"name": "x", "weight": 1, "rtt": {"a": 1, "b": 2, "z": 3}}]
    with pytest.raises(ProblemError, match="unknown regions"):
        problem_from_dict(payload(clients=clients))


def test_rejects_non_positive_weight():
    clients = [{"name": "x", "weight": 0, "rtt": {"a": 1, "b": 2}}]
    with pytest.raises(ProblemError, match="positive weight"):
        problem_from_dict(payload(clients=clients))


def test_rejects_negative_rtt():
    clients = [{"name": "x", "weight": 1, "rtt": {"a": -1, "b": 2}}]
    with pytest.raises(ProblemError, match="negative rtt"):
        problem_from_dict(payload(clients=clients))


def test_rejects_zero_target():
    with pytest.raises(ProblemError, match="target_ms"):
        problem_from_dict(payload(target_ms=0))


def test_rejects_bad_type():
    with pytest.raises(ProblemError, match="JSON object"):
        problem_from_dict(["not", "an", "object"])


def test_load_problem_roundtrip(tmp_path):
    path = tmp_path / "net.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")
    problem = load_problem(path)
    assert problem.region_names == ("a", "b")


def test_load_problem_missing_file(tmp_path):
    with pytest.raises(ProblemError, match="file not found"):
        load_problem(tmp_path / "absent.json")


def test_load_problem_invalid_json(tmp_path):
    path = tmp_path / "net.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ProblemError, match="not valid JSON at line 1"):
        load_problem(path)
