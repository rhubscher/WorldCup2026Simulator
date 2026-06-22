from __future__ import annotations

import argparse
import json
import sys

import matplotlib.pyplot as plt
import seaborn as sns

ROUNDS = ["r32", "r16", "qf", "sf", "final", "win"]
ROUND_LABELS = ["R32", "R16", "QF", "SF", "Final", "Win"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Heatmap of round-reach probabilities from simulator JSON output"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="JSON file produced by main.py --output json (default: stdin)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=48,
        metavar="N",
        help="Show only the top N teams by win probability (default: 48)",
    )
    parser.add_argument(
        "--save",
        metavar="FILE",
        help="Save chart to file instead of opening a window (e.g. chart.png)",
    )
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    round_reach: dict[str, dict[str, float]] = data["round_reach"]
    n_sims: int = data["simulations"]

    # Sort teams by win probability, take top N
    teams = sorted(
        round_reach,
        key=lambda t: tuple(round_reach[t].get(r, 0) for r in ("win", "final", "sf", "qf", "r16", "r32")),
        reverse=True,
    )
    teams = teams[: args.top]

    matrix = [[round_reach[t][r] for r in ROUNDS] for t in teams]

    fig_height = max(6, len(teams) * 0.38)
    fig, ax = plt.subplots(figsize=(9, fig_height))

    sns.heatmap(
        matrix,
        annot=True,
        fmt=".1f",
        xticklabels=ROUND_LABELS,
        yticklabels=teams,
        cmap="YlGn",
        vmin=0,
        vmax=100,
        linewidths=0.4,
        linecolor="white",
        ax=ax,
        annot_kws={"size": 7.5},
        cbar_kws={"label": "Probability (%)"},
    )

    ax.set_title(
        f"FIFA World Cup 2026 — probability of reaching each round\n"
        f"({n_sims:,} simulations)",
        pad=12,
    )
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")

    plt.tight_layout()

    if args.save:
        plt.savefig(args.save, dpi=150, bbox_inches="tight")
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        plt.show()


if __name__ == "__main__":
    main()
