"""Command line entry point for region-plan."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .choose import SolverError, budget_plan, exact, greedy, improve, sweep
from .model import ProblemError, load_problem
from .report import (
    render_budget,
    render_compare,
    render_json,
    render_matrix,
    render_plan,
    render_sweep,
)

METHODS = ("exact", "greedy", "improved")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="region-plan",
        description="Choose deployment regions from an RTT matrix to minimise latency.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="best set of k regions")
    plan.add_argument("--problem", required=True)
    plan.add_argument("--regions", type=int, required=True, help="how many regions to deploy")
    plan.add_argument("--method", choices=METHODS, default="exact")
    plan.add_argument("--format", choices=("text", "json"), default="text")

    sweep_cmd = sub.add_parser("sweep", help="best plan for every k, with the marginal gain")
    sweep_cmd.add_argument("--problem", required=True)
    sweep_cmd.add_argument("--max-regions", type=int, default=None)

    compare = sub.add_parser("compare", help="exact vs greedy vs local search at one k")
    compare.add_argument("--problem", required=True)
    compare.add_argument("--regions", type=int, required=True)

    matrix = sub.add_parser("matrix", help="print the RTT matrix and region costs")
    matrix.add_argument("--problem", required=True)

    budget = sub.add_parser("budget", help="best plan that fits a cost budget")
    budget.add_argument("--problem", required=True)
    budget.add_argument("--budget", type=float, required=True)
    budget.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def _plan_for(args: argparse.Namespace, problem):
    if args.method == "exact":
        return exact(problem, args.regions)
    if args.method == "greedy":
        return greedy(problem, args.regions)
    return improve(problem, greedy(problem, args.regions))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        problem = load_problem(args.problem)
    except ProblemError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "plan":
            plan = _plan_for(args, problem)
            if args.format == "json":
                print(render_json(plan))
            else:
                blurb = f"Plan for {problem.name} using {args.method}"
                print(render_plan(problem, plan, blurb=blurb))
            return 0
        if args.command == "sweep":
            print(render_sweep(problem, sweep(problem, args.max_regions)))
            return 0
        if args.command == "compare":
            rows = [
                ("exact", exact(problem, args.regions)),
                ("greedy", greedy(problem, args.regions)),
                ("improved", improve(problem, greedy(problem, args.regions))),
            ]
            print(render_compare(problem, rows))
            return 0
        if args.command == "matrix":
            print(render_matrix(problem))
            return 0
        if args.command == "budget":
            plan = budget_plan(problem, args.budget)
            if args.format == "json":
                print(render_json(plan))
            else:
                print(render_budget(problem, plan, args.budget))
            return 0
    except SolverError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unknown command")
    return 2
