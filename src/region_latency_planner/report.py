"""Text and JSON reports for plans."""

from __future__ import annotations

import json

from .model import Problem
from .score import Plan


def render_plan(problem: Problem, plan: Plan, *, blurb: str = "") -> str:
    lines = [blurb or f"Plan for {problem.name}", "=" * 66]
    lines.append(f"regions        {', '.join(plan.names)}")
    lines.append(f"mean rtt       {plan.mean_rtt:6.1f} ms   (traffic weighted)")
    lines.append(f"p95 rtt        {plan.p95_rtt:6.1f} ms")
    lines.append(f"worst rtt      {plan.worst_rtt:6.1f} ms")
    lines.append(
        f"within {problem.target_ms:g}ms  {plan.within_target * 100:5.1f}% of traffic"
    )
    lines.append(f"cost           {plan.cost:6.1f} units")
    lines.append("")
    lines.append(f"{'client':<16}{'region':<16}{'rtt':>8}{'weight':>9}")
    for item in plan.assignments:
        lines.append(
            f"{item.client[:15]:<16}{item.region[:15]:<16}{item.rtt:>8.1f}{item.weight:>9.2f}"
        )
    return "\n".join(lines)


def render_sweep(problem: Problem, plans: list[Plan]) -> str:
    lines = [f"Latency by number of regions - {problem.name}", "=" * 84]
    lines.append(f"{'k':>2}  {'regions':<52}{'mean':>8}{'p95':>8}{'<target':>9}")
    previous: float | None = None
    for plan in plans:
        gain = 0.0 if previous is None else previous - plan.mean_rtt
        lines.append(
            f"{len(plan.names):>2}  {plan.label[:51]:<52}{plan.mean_rtt:>8.1f}"
            f"{plan.p95_rtt:>8.1f}{plan.within_target * 100:>8.0f}%"
        )
        if previous is not None:
            note = f"-{gain:.1f} ms" if gain > 0.05 else "no measurable gain"
            lines.append(f"{'':>2}  {note:<52}")
        previous = plan.mean_rtt
    return "\n".join(lines)


def render_matrix(problem: Problem) -> str:
    width = 12
    header = f"{'client':<14}{'w':>5}" + "".join(
        f"{region.name[:width - 1]:>{width}}" for region in problem.regions
    )
    lines = [f"RTT matrix - {problem.name} (ms)", "=" * len(header)]
    lines.append(header)
    for client in problem.clients:
        cells = "".join(f"{client.rtt[region.name]:>{width}.0f}" for region in problem.regions)
        lines.append(f"{client.name[:13]:<14}{client.weight:>5.2f}{cells}")
    lines.append("")
    costs = "".join(f"{region.cost:>{width}.0f}" for region in problem.regions)
    lines.append("cost units  " + costs)
    return "\n".join(lines)


def render_compare(problem: Problem, rows: list[tuple[str, Plan]]) -> str:
    lines = [f"Method comparison at k={len(rows[0][1].names)} - {problem.name}", "=" * 78]
    best = min(plan.mean_rtt for _, plan in rows)
    lines.append(f"{'method':<12}{'regions':<38}{'mean':>9}{'vs best':>10}{'cost':>8}")
    for method, plan in rows:
        gap = "" if plan.mean_rtt <= best + 1e-9 else f"+{plan.mean_rtt - best:5.1f} ms"
        lines.append(
            f"{method:<12}{plan.label[:37]:<38}{plan.mean_rtt:>9.1f}{gap:>10}{plan.cost:>8.0f}"
        )
    return "\n".join(lines)


def render_budget(problem: Problem, plan: Plan, budget: float) -> str:
    lines = [f"Budget plan (limit {budget:g} units, spent {plan.cost:g})", "=" * 66]
    lines.append(f"regions        {', '.join(plan.names)}")
    lines.append(f"mean rtt       {plan.mean_rtt:6.1f} ms")
    lines.append(f"within {problem.target_ms:g}ms  {plan.within_target * 100:5.1f}% of traffic")
    return "\n".join(lines)


def plan_as_dict(plan: Plan) -> dict:
    return {
        "regions": list(plan.names),
        "mean_rtt": round(plan.mean_rtt, 3),
        "p95_rtt": round(plan.p95_rtt, 3),
        "worst_rtt": round(plan.worst_rtt, 3),
        "within_target": round(plan.within_target, 4),
        "cost": round(plan.cost, 3),
        "assignments": [
            {
                "client": item.client,
                "region": item.region,
                "rtt": item.rtt,
                "weight": item.weight,
            }
            for item in plan.assignments
        ],
    }


def render_json(plan: Plan) -> str:
    return json.dumps(plan_as_dict(plan), indent=2)
