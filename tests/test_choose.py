import pytest

from region_latency_planner.choose import (
    SolverError,
    budget_plan,
    exact,
    greedy,
    improve,
    marginal,
    sweep,
)
from region_latency_planner.model import problem_from_dict

# A compromise hub is cheap for everyone and best for nobody. Greedy takes it first
# because it wins on the one-region score, then cannot undo the choice.
HUB_PROBLEM = {
    "name": "hub-trap",
    "regions": [
        {"name": "hub", "cost": 10},
        {"name": "left", "cost": 5},
        {"name": "right", "cost": 5},
    ],
    "clients": [
        {"name": "c-left", "weight": 5, "rtt": {"hub": 6, "left": 1, "right": 20}},
        {"name": "c-right", "weight": 5, "rtt": {"hub": 6, "left": 20, "right": 1}},
    ],
}


def problem():
    return problem_from_dict(HUB_PROBLEM)


def test_exact_finds_the_split_pair():
    plan = exact(problem(), 2)
    assert plan.names == ("left", "right")
    assert plan.mean_rtt == pytest.approx(1.0)


def test_greedy_falls_for_the_hub():
    plan = greedy(problem(), 2)
    assert plan.names == ("hub", "left")
    assert plan.mean_rtt == pytest.approx(3.5)


def test_improve_recovers_the_optimum():
    improved = improve(problem(), greedy(problem(), 2))
    assert improved.mean_rtt == pytest.approx(1.0)
    assert improved.names == ("left", "right")


def test_improve_never_makes_a_plan_worse():
    best = exact(problem(), 2)
    assert improve(problem(), best).mean_rtt <= best.mean_rtt + 1e-9


def test_sweep_is_monotone_in_k():
    plans = sweep(problem())
    assert [len(plan.names) for plan in plans] == [1, 2, 3]
    for earlier, later in zip(plans, plans[1:], strict=False):
        assert later.mean_rtt <= earlier.mean_rtt + 1e-9


def test_marginal_gain_shrinks():
    first = marginal(problem(), 2)
    assert first > 0


def test_budget_respects_the_limit():
    plan = budget_plan(problem(), 10)
    assert plan.cost <= 10 + 1e-9
    assert plan.names == ("left", "right")


def test_budget_too_small():
    with pytest.raises(SolverError, match="no single region costs"):
        budget_plan(problem(), 1)


def test_k_below_one_rejected():
    with pytest.raises(SolverError, match="at least 1"):
        exact(problem(), 0)


def test_k_above_region_count_rejected():
    with pytest.raises(SolverError, match="needs at least"):
        greedy(problem(), 4)


def test_single_region_exact_matches_greedy():
    assert exact(problem(), 1).names == greedy(problem(), 1).names == ("hub",)


def test_ties_break_on_cost_then_name():
    tie = problem_from_dict(
        {
            "regions": [
                {"name": "b", "cost": 5},
                {"name": "a", "cost": 5},
            ],
            "clients": [{"name": "c", "weight": 1, "rtt": {"a": 10, "b": 10}}],
        }
    )
    assert exact(tie, 1).names == ("a",)


def test_marginal_rejects_out_of_range_k():
    with pytest.raises(SolverError, match="k is larger"):
        marginal(problem(), 9)
