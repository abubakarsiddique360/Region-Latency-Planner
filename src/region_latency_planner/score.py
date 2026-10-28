"""Scoring for a chosen set of regions."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Assignment, Problem


@dataclass(frozen=True)
class Plan:
    names: tuple[str, ...]
    mean_rtt: float
    p95_rtt: float
    worst_rtt: float
    within_target: float
    cost: float
    assignments: tuple[Assignment, ...]
    @property
    def label(self) -> str:
        return "+".join(self.names)


def assign(problem: Problem, names: tuple[str, ...]) -> tuple[Assignment, ...]:
    """Give every client the closest region in ``names``."""
    if not names:
        raise ValueError("a plan needs at least one region")
    chosen = tuple(names)
    known = set(problem.region_names)
    for name in chosen:
        if name not in known:
            raise ValueError(f"unknown region {name!r}")
    result = []
    for client in problem.clients:
        best = min(chosen, key=lambda name: (client.rtt[name], name))
        result.append(
            Assignment(
                client=client.name,
                region=best,
                rtt=client.rtt[best],
                weight=client.weight,
            )
        )
    return tuple(result)


def score(problem: Problem, names: tuple[str, ...]) -> Plan:
    assignments = assign(problem, names)
    total = problem.total_weight
    mean = sum(item.weight * item.rtt for item in assignments) / total

    ordered = sorted(assignments, key=lambda item: (item.rtt, item.client))
    cumulative = 0.0
    p95 = ordered[-1].rtt
    for item in ordered:
        cumulative += item.weight
        if cumulative / total >= 0.95:
            p95 = item.rtt
            break

    within = sum(item.weight for item in assignments if item.rtt <= problem.target_ms) / total
    return Plan(
        names=tuple(sorted(names)),
        mean_rtt=mean,
        p95_rtt=p95,
        worst_rtt=max(item.rtt for item in assignments),
        within_target=within,
        cost=problem.cost_of(tuple(sorted(names))),
        assignments=assignments,
    )
