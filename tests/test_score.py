import pytest

from region_latency_planner.model import problem_from_dict
from region_latency_planner.score import assign, score


def problem(clients, regions=None, target_ms=100):
    return problem_from_dict(
        {
            "name": "tiny",
            "target_ms": target_ms,
            "regions": regions or [{"name": "a", "cost": 10}, {"name": "b", "cost": 20}],
            "clients": clients,
        }
    )


CLIENTS = [
    {"name": "near-a", "weight": 3, "rtt": {"a": 5, "b": 50}},
    {"name": "near-b", "weight": 1, "rtt": {"a": 60, "b": 4}},
]


def test_assign_picks_closest_region():
    assignments = assign(problem(CLIENTS), ("a", "b"))
    assert [item.region for item in assignments] == ["a", "b"]


def test_weighted_mean_uses_population():
    plan = score(problem(CLIENTS), ("a", "b"))
    assert plan.mean_rtt == pytest.approx((3 * 5 + 1 * 4) / 4)


def test_single_region_serves_everyone():
    plan = score(problem(CLIENTS), ("b",))
    assert plan.mean_rtt == pytest.approx((3 * 50 + 1 * 4) / 4)
    assert plan.worst_rtt == 50


def test_within_target_share():
    plan = score(problem(CLIENTS, target_ms=30), ("a",))
    assert plan.within_target == pytest.approx(0.75)


def test_p95_is_weighted_quantile():
    clients = [
        {"name": "c1", "weight": 1, "rtt": {"a": 10, "b": 10}},
        {"name": "c2", "weight": 1, "rtt": {"a": 20, "b": 20}},
        {"name": "c3", "weight": 1, "rtt": {"a": 30, "b": 30}},
        {"name": "c4", "weight": 1, "rtt": {"a": 40, "b": 40}},
    ]
    plan = score(problem(clients), ("a",))
    assert plan.p95_rtt == 40


def test_cost_sums_region_costs():
    plan = score(problem(CLIENTS), ("a", "b"))
    assert plan.cost == 30
    assert plan.label == "a+b"


def test_names_are_sorted_for_stable_labels():
    plan = score(problem(CLIENTS), ("b", "a"))
    assert plan.names == ("a", "b")


def test_rejects_unknown_region():
    with pytest.raises(ValueError, match="unknown region"):
        assign(problem(CLIENTS), ("zzz",))


def test_rejects_empty_choice():
    with pytest.raises(ValueError, match="at least one region"):
        assign(problem(CLIENTS), ())
