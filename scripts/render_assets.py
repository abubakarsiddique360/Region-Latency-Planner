"""Regenerate README assets from real runs.

Usage:  python scripts/render_assets.py
Writes: docs/results.json, docs/images/compare.png,
        docs/images/latency-curve.svg, docs/images/rtt-heatmap.png
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from region_latency_planner.choose import (  # noqa: E402
    budget_plan,
    exact,
    greedy,
    improve,
    sweep,
)
from region_latency_planner.model import load_problem  # noqa: E402
from region_latency_planner.report import (  # noqa: E402
    render_compare,
    render_matrix,
    render_plan,
)

BG = "#0d1117"
CHROME = "#161b22"
FG = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#79c0ff"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def render_terminal(text: str, out_path: Path, title: str) -> None:
    font = load_font(15)
    lines = text.expandtabs(4).splitlines() or [""]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    char_width = probe.textlength("M", font=font)
    line_height = 22
    pad = 24
    width = int(max(len(line) for line in lines) * char_width) + pad * 2
    height = pad * 2 + len(lines) * line_height + 44
    image = Image.new("RGB", (max(width, 700), height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, image.width, 34], fill=CHROME)
    for index, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        draw.ellipse([16 + index * 22, 10, 28 + index * 22, 22], fill=color)
    draw.text((92, 9), title, font=load_font(13), fill=MUTED)

    for row, line in enumerate(lines):
        color = FG
        if line.startswith("$"):
            color = ACCENT
        elif "vs best" in line or "Method comparison" in line:
            color = MUTED
        elif line.startswith(("exact", "greedy", "improved")):
            color = "#3fb950" if line.startswith(("exact", "improved")) else "#d29922"
        draw.text((pad, 50 + row * line_height), line, font=font, fill=color)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def render_curve(problem, out_path: Path) -> dict:
    plans = sweep(problem)
    exact_means = [plan.mean_rtt for plan in plans]
    exact_p95 = [plan.p95_rtt for plan in plans]
    greedy_means = [greedy(problem, k).mean_rtt for k in range(1, len(plans) + 1)]
    ks = list(range(1, len(plans) + 1))

    fig, ax = plt.subplots(figsize=(9.4, 4.2))
    fig.patch.set_facecolor("#ffffff")
    ax.plot(ks, greedy_means, marker="o", color="#d29922", label="greedy (add best now)")
    ax.plot(ks, exact_means, marker="s", color="#1a7f37", label="best possible (exhaustive)")
    ax.plot(ks, exact_p95, marker="^", linestyle="--", color="#8250df", label="p95 of best plan")
    gap = greedy_means[1] - exact_means[1]
    if gap > 0.5:
        ax.annotate(
            f"greedy pays +{gap:.1f} ms at k=2",
            xy=(2, greedy_means[1]),
            xytext=(2.25, greedy_means[1] + 18),
            fontsize=8,
            color="#d29922",
            arrowprops={"arrowstyle": "->", "color": "#d29922", "lw": 1},
        )
    ax.set_xticks(ks)
    ax.set_xlabel("number of deployed regions (k)")
    ax.set_ylabel("traffic-weighted RTT (ms)")
    ax.set_title(
        "Two regions usually buy most of the win - if you pick the right two",
        fontsize=11,
        loc="left",
    )
    ax.grid(linestyle=":", alpha=0.45)
    ax.legend(fontsize=8, frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format=out_path.suffix.lstrip("."))
    plt.close(fig)
    return {
        "k": ks,
        "exact_mean": exact_means,
        "exact_p95": exact_p95,
        "greedy_mean": greedy_means,
    }


def render_heatmap(problem, chosen: tuple[str, ...], out_path: Path) -> None:
    clients = [client.name for client in problem.clients]
    regions = list(problem.region_names)
    grid = [[client.rtt[region] for region in regions] for client in problem.clients]

    fig, ax = plt.subplots(figsize=(9.0, 3.9))
    fig.patch.set_facecolor("#ffffff")
    image = ax.imshow(grid, cmap="RdYlGn_r", aspect="auto")
    ax.set_xticks(range(len(regions)))
    ax.set_xticklabels(regions, fontsize=8)
    ax.set_yticks(range(len(clients)))
    ax.set_yticklabels(
        [f"{client.name} ({client.weight:.2f})" for client in problem.clients], fontsize=8
    )
    for row, client in enumerate(problem.clients):
        best = min(chosen, key=lambda name: (client.rtt[name], name))
        for column, region in enumerate(regions):
            value = client.rtt[region]
            red, green, blue, _ = image.cmap(image.norm(value))
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            ax.text(column, row, f"{value:.0f}", ha="center", va="center", fontsize=7,
                    color="#ffffff" if luminance < 0.55 else "#24292f")
            if region == best:
                ax.add_patch(Rectangle((column - 0.5, row - 0.5), 1, 1, fill=False,
                                       edgecolor="#0969da", linewidth=2.2))
    for column, region in enumerate(regions):
        if region in chosen:
            ax.add_patch(Rectangle((column - 0.5, -0.5), 1, len(clients), fill=False,
                                   edgecolor="#1a7f37", linewidth=3.0))
    ax.set_title(
        "RTT matrix (ms) - green outline = chosen region, blue box = region each client uses",
        fontsize=10,
        loc="left",
    )
    fig.colorbar(image, ax=ax, pad=0.02, fraction=0.03).set_label("ms", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", dpi=150)
    plt.close(fig)


def main() -> int:
    images = ROOT / "docs" / "images"
    images.mkdir(parents=True, exist_ok=True)
    problem = load_problem(ROOT / "examples" / "network.json")

    best_two = exact(problem, 2)
    greedy_two = greedy(problem, 2)
    repaired = improve(problem, greedy_two)
    budget = budget_plan(problem, 130)

    payload = {
        "problem": problem.name,
        "k1": exact(problem, 1).names,
        "k2_best": {"regions": list(best_two.names), "mean_rtt": round(best_two.mean_rtt, 2)},
        "k2_greedy": {
            "regions": list(greedy_two.names),
            "mean_rtt": round(greedy_two.mean_rtt, 2),
        },
        "k2_repaired": {"regions": list(repaired.names), "mean_rtt": round(repaired.mean_rtt, 2)},
        "budget_130": {"regions": list(budget.names), "cost": budget.cost,
                       "mean_rtt": round(budget.mean_rtt, 2)},
        "sweep": [
            {
                "k": len(plan.names),
                "regions": list(plan.names),
                "mean_rtt": round(plan.mean_rtt, 2),
                "p95_rtt": round(plan.p95_rtt, 2),
                "within_target": round(plan.within_target, 3),
                "cost": plan.cost,
            }
            for plan in sweep(problem)
        ],
    }
    (ROOT / "docs" / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rows = [
        ("exact", best_two),
        ("greedy", greedy_two),
        ("improved", repaired),
    ]
    terminal = (
        "$ region-plan compare --problem examples/network.json --regions 2\n\n"
        + render_compare(problem, rows)
        + "\n\n$ region-plan matrix --problem examples/network.json | head -4\n\n"
        + "\n".join(render_matrix(problem).splitlines()[:5])
        + "\n\n$ region-plan plan --problem examples/network.json --regions 2 | head -7\n\n"
        + "\n".join(render_plan(problem, best_two).splitlines()[:6])
    )
    title = "region-plan  -  the greedy shortcut costs 9.9 ms"
    render_terminal(terminal, images / "compare.png", title)
    render_curve(problem, images / "latency-curve.svg")
    render_heatmap(problem, best_two.names, images / "rtt-heatmap.png")

    print(
        f"k=2 exact {best_two.label} {best_two.mean_rtt:.1f} ms | "
        f"greedy {greedy_two.label} {greedy_two.mean_rtt:.1f} ms | "
        f"repaired {repaired.label} {repaired.mean_rtt:.1f} ms | "
        f"budget130 {budget.label} {budget.mean_rtt:.1f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
