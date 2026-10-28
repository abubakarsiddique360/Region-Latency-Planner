"""Choosing which regions to deploy in.

Three methods, on purpose:

``exact``   brute force over every combination - the ground truth for small problems.
``greedy``  add the region that helps most right now - what a dashboard "recommend k regions"
            button does, and it can commit to a compromise hub it cannot undo.
``improve`` greedy followed by single-region swaps until nothing helps - cheap repair.
"""

from __future__ import annotations

from itertools import combinations

from .model import Problem
from .score import Plan, score

MAX_COMBINATIONS = 400_000


class SolverError(ValueError):
    """Raised when a solver cannot answer for the requested size."""


def _better(candidate: Plan, incumbent: Plan | None) -> bool:
    if incumbent is None:
        return True
    if abs(candidate.mean_rtt - incumbent.mean_rtt) > 1e-9:
        return candidate.mean_rtt < incumbent.mean_rtt
    if abs(candidate.cost - incumbent.cost) > 1e-9:
        return candidate.cost < incumbent.cost
    return candidate.names < incumbent.names


def exact(problem: Problem, k: int) -> Plan:
    names = problem.region_names
    _check_k(len(names), k)
    total = _combinations(len(names), k)
    if total > MAX_COMBINATIONS:
        raise SolverError(
            f"{total} combinations would be searched; use --method greedy or lower the region count"
        )
    best: Plan | None = None
    for combination in combinations(names, k):
        plan = score(problem, combination)
        if _better(plan, best):
            best = plan
    assert best is not None
    return best


def greedy(problem: Problem, k: int) -> Plan:
    names = problem.region_names
    _check_k(len(names), k)
    chosen: list[str] = []
    while len(chosen) < k:
        best_name: str | None = None
        best_plan: Plan | None = None
        for name in names:
            if name in chosen:
                continue
            plan = score(problem, tuple([*chosen, name]))
            if _better(plan, best_plan):
                best_name, best_plan = name, plan
        assert best_name is not None and best_plan is not None
        chosen.append(best_name)
        if best_plan.mean_rtt == 0:
            # Everything already answers instantly; extra regions cannot help.
            remaining = [name for name in names if name not in chosen]
            chosen.extend(remaining[: k - len(chosen)])
            break
    return score(problem, tuple(chosen))


def improve(problem: Problem, plan: Plan) -> Plan:
    """Single-swap local search. Never returns a worse plan than it was given."""
    current = plan
    k = len(current.names)
    improved = True
    while improved:
        improved = False
        outside = [name for name in problem.region_names if name not in current.names]
        for dropped in current.names:
            for added in outside:
                names = [name for name in current.names if name != dropped] + [added]
                candidate = score(problem, tuple(sorted(names)))
                if candidate.mean_rtt < current.mean_rtt - 1e-9:
                    current = candidate
                    improved = True
                    break
            if improved:
                break
    assert len(current.names) == k
    return current


def sweep(problem: Problem, max_k: int | None = None) -> list[Plan]:
    """Best plan for every k, using exact search when it is affordable."""
    limit = len(problem.region_names) if max_k is None else min(max_k, len(problem.region_names))
    plans = []
    for k in range(1, limit + 1):
        if _combinations(len(problem.region_names), k) <= MAX_COMBINATIONS:
            plans.append(exact(problem, k))
        else:
            plans.append(improve(problem, greedy(problem, k)))
    return plans


def budget_plan(problem: Problem, budget: float) -> Plan:
    """Best plan that fits the budget.

    A budget turns region selection into a knapsack, and greedy-by-value-per-cost can miss
    a cheap pair that beats an expensive hub. So the subset space is searched exactly when
    it is small, with the greedy ratio rule kept only as a fallback for large region lists.
    """
    affordable = [region.name for region in problem.regions if region.cost <= budget]
    if not affordable:
        raise SolverError(f"no single region costs {budget:g} or less")
    if (1 << len(affordable)) - 1 <= MAX_COMBINATIONS:
        return _budget_exhaustive(problem, budget, affordable)
    return _budget_greedy(problem, budget, affordable)


def _budget_exhaustive(problem: Problem, budget: float, affordable: list[str]) -> Plan:
    best: Plan | None = None
    for size in range(1, len(affordable) + 1):
        for combination in combinations(affordable, size):
            if problem.cost_of(combination) > budget + 1e-9:
                continue
            plan = score(problem, combination)
            if _better(plan, best):
                best = plan
    if best is None:
        raise SolverError("no affordable combination of regions exists")
    return best


def _budget_greedy(problem: Problem, budget: float, affordable: list[str]) -> Plan:
    subset = Problem(
        name=problem.name,
        regions=tuple(region for region in problem.regions if region.name in set(affordable)),
        clients=problem.clients,
        target_ms=problem.target_ms,
    )
    # Baseline for the first purchase: the worst single region, so every gain is positive.
    current = max(score(problem, (region.name,)).mean_rtt for region in subset.regions)
    chosen: list[str] = []
    spent = 0.0
    while True:
        best_choice: tuple[tuple[float, float], str, Plan] | None = None
        for region in subset.regions:
            if region.name in chosen or spent + region.cost > budget + 1e-9:
                continue
            plan = score(problem, tuple([*chosen, region.name]))
            gain = current - plan.mean_rtt
            if gain <= 1e-9:
                continue
            ratio = gain / region.cost if region.cost > 0 else float("inf")
            key = (ratio, gain)
            if best_choice is None or key > best_choice[0]:
                best_choice = (key, region.name, plan)
        if best_choice is None:
            break
        _, name, plan = best_choice
        chosen.append(name)
        spent += next(region.cost for region in subset.regions if region.name == name)
        current = plan.mean_rtt
    if not chosen:
        raise SolverError("budget cannot buy a first region")
    return _affordable_swaps(problem, score(problem, tuple(chosen)), budget)


def _affordable_swaps(problem: Problem, plan: Plan, budget: float) -> Plan:
    current = plan
    improved = True
    while improved:
        improved = False
        outside = [name for name in problem.region_names if name not in current.names]
        for dropped in current.names:
            for added in outside:
                names = tuple(sorted([n for n in current.names if n != dropped] + [added]))
                if problem.cost_of(names) > budget + 1e-9:
                    continue
                candidate = score(problem, names)
                if candidate.mean_rtt < current.mean_rtt - 1e-9:
                    current = candidate
                    improved = True
                    break
            if improved:
                break
    return current


def marginal(problem: Problem, k: int) -> float:
    """Latency improvement bought by the k-th region of the greedy path."""
    if k <= 0:
        raise SolverError("k must be positive")
    if k > len(problem.region_names):
        raise SolverError("k is larger than the number of regions")
    if k == 1:
        return score(problem, (problem.region_names[0],)).mean_rtt
    return greedy(problem, k - 1).mean_rtt - greedy(problem, k).mean_rtt


def _combinations(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    result = 1
    for index in range(k):
        result = result * (n - index) // (index + 1)
    return result


def _check_k(n: int, k: int) -> None:
    if k < 1:
        raise SolverError("k must be at least 1")
    if k > n:
        raise SolverError(f"k={k} needs at least {k} regions, the problem has {n}")
