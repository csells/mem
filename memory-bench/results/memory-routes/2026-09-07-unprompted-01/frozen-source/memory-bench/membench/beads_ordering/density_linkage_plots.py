from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_ARMS = ("key", "pagerank", "bm25f")
_COLORS = {"key": "#333333", "pagerank": "#0072B2", "bm25f": "#D55E00"}
_LABELS = {"key": "key", "pagerank": "PageRank", "bm25f": "BM25F"}


def _numeric(value: object, *, name: str) -> float:
    if not isinstance(value, (bool, int, float)):
        raise TypeError(f"{name} must be numeric")
    return float(value)


def _navigation_curves(analysis: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = analysis.get("curves")
    if not isinstance(raw, Sequence):
        raise ValueError("density/linkage analysis has no curves")
    return [
        curve
        for curve in raw
        if isinstance(curve, Mapping)
        and curve.get("mode") == "navigation"
        and curve.get("page_size") == "5"
        and curve.get("arm") in _ARMS
    ]


def _summary_value(curve: Mapping[str, object], field: str, statistic: str) -> float:
    summary = curve.get(field)
    if not isinstance(summary, Mapping):
        raise ValueError(f"curve has no {field} summary")
    return _numeric(summary.get(statistic), name=f"{field}.{statistic}")


def _plot_probability(
    curves: Sequence[Mapping[str, object]],
    out: Path,
    *,
    field: str,
    title: str,
    ylabel: str,
) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["svg.hashsalt"] = "mem-density-linkage"
    import matplotlib.pyplot as plt

    linkages = [
        linkage
        for linkage in ("sparse", "native", "enriched")
        if any(curve["linkage_level"] == linkage for curve in curves)
    ]
    figure, axes = plt.subplots(1, len(linkages), figsize=(10.5, 4.8), sharey=True)
    if len(linkages) == 1:
        axes = [axes]
    for axis, linkage in zip(axes, linkages, strict=True):
        for arm in _ARMS:
            selected = sorted(
                (
                    curve
                    for curve in curves
                    if curve["linkage_level"] == linkage and curve["arm"] == arm
                ),
                key=lambda curve: _numeric(curve["candidate_count"], name="candidate_count"),
            )
            if not selected:
                continue
            xs = [_numeric(curve["candidate_count"], name="candidate_count") for curve in selected]
            ys = [_summary_value(curve, field, "estimate") for curve in selected]
            lows = [_summary_value(curve, field, "low") for curve in selected]
            highs = [_summary_value(curve, field, "high") for curve in selected]
            color = _COLORS[arm]
            axis.plot(xs, ys, color=color, marker="o", linewidth=1.5, markersize=4)
            axis.vlines(xs, lows, highs, color=color, linewidth=0.7, alpha=0.6)
            axis.annotate(
                _LABELS[arm],
                (xs[-1], ys[-1]),
                xytext=(5, {"key": -9, "pagerank": 0, "bm25f": 9}[arm]),
                textcoords="offset points",
                color=color,
                fontsize=9,
                va="center",
            )
        axis.set_title(f"{linkage} links", loc="left", fontsize=11)
        axis.set_xlim(10, 150)
        axis.set_xticks((10, 40, 150))
        axis.set_ylim(0, 1)
        axis.set_yticks((0, 0.5, 1))
        axis.spines[["top", "right"]].set_visible(False)
        axis.spines["bottom"].set_bounds(10, 150)
        axis.spines["left"].set_bounds(0, 1)
        axis.tick_params(labelsize=9, length=3)
        axis.set_xlabel("lexical candidates", fontsize=10)
    axes[0].set_ylabel(ylabel, fontsize=10)
    figure.suptitle(title, x=0.07, ha="left", fontsize=14, fontfamily="serif")
    figure.text(
        0.07,
        0.91,
        "Navigation, five-result pages; points are task means, "
        "whiskers are 90% clustered intervals",
        fontsize=9,
        fontfamily="serif",
    )
    figure.tight_layout(rect=(0.04, 0.03, 0.98, 0.87))
    return _save_pair(figure, out, plt)


def _plot_cost(curves: Sequence[Mapping[str, object]], out: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["svg.hashsalt"] = "mem-density-linkage"
    import matplotlib.pyplot as plt

    linkages = [
        linkage
        for linkage in ("sparse", "native", "enriched")
        if any(curve["linkage_level"] == linkage for curve in curves)
    ]
    maxima = [_summary_value(curve, "compact_tokens_to_first_useful", "p90") for curve in curves]
    ymax = max(maxima, default=1.0)
    figure, axes = plt.subplots(1, len(linkages), figsize=(10.5, 4.8), sharey=True)
    if len(linkages) == 1:
        axes = [axes]
    for axis, linkage in zip(axes, linkages, strict=True):
        for arm in _ARMS:
            selected = sorted(
                (
                    curve
                    for curve in curves
                    if curve["linkage_level"] == linkage and curve["arm"] == arm
                ),
                key=lambda curve: _numeric(curve["candidate_count"], name="candidate_count"),
            )
            if not selected:
                continue
            xs = [_numeric(curve["candidate_count"], name="candidate_count") for curve in selected]
            medians = [
                _summary_value(curve, "compact_tokens_to_first_useful", "p50") for curve in selected
            ]
            p90s = [
                _summary_value(curve, "compact_tokens_to_first_useful", "p90") for curve in selected
            ]
            color = _COLORS[arm]
            axis.plot(xs, medians, color=color, marker="o", linewidth=1.5, markersize=4)
            axis.vlines(xs, medians, p90s, color=color, linewidth=0.7, alpha=0.6)
            axis.annotate(
                _LABELS[arm],
                (xs[-1], medians[-1]),
                xytext=(5, {"key": -9, "pagerank": 0, "bm25f": 9}[arm]),
                textcoords="offset points",
                color=color,
                fontsize=9,
                va="center",
            )
        axis.set_title(f"{linkage} links", loc="left", fontsize=11)
        axis.set_xlim(10, 150)
        axis.set_xticks((10, 40, 150))
        axis.set_ylim(0, ymax)
        axis.spines[["top", "right"]].set_visible(False)
        axis.spines["bottom"].set_bounds(10, 150)
        axis.spines["left"].set_bounds(0, ymax)
        axis.tick_params(labelsize=9, length=3)
        axis.set_xlabel("lexical candidates", fontsize=10)
    axes[0].set_ylabel("compact tokens to first useful Memory", fontsize=10)
    figure.suptitle(
        "Model-facing discovery cost", x=0.07, ha="left", fontsize=14, fontfamily="serif"
    )
    figure.text(
        0.07,
        0.91,
        "Navigation, five-result pages; points are p50, whiskers extend to p90",
        fontsize=9,
        fontfamily="serif",
    )
    figure.tight_layout(rect=(0.04, 0.03, 0.98, 0.87))
    return _save_pair(figure, out, plt)


def _save_pair(figure: Any, base: Path, pyplot: Any) -> list[Path]:
    base.parent.mkdir(parents=True, exist_ok=True)
    svg = base.with_suffix(".svg")
    png = base.with_suffix(".png")
    figure.savefig(svg, format="svg", metadata={"Date": None})
    svg_text = svg.read_text(encoding="utf-8")
    svg.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )
    figure.savefig(
        png,
        format="png",
        dpi=180,
        metadata={"Software": "mem memory-bench"},
    )
    pyplot.close(figure)
    return [svg, png]


def render_density_linkage_plots(analysis: Mapping[str, object], out_dir: Path) -> list[Path]:
    curves = _navigation_curves(analysis)
    if not curves:
        raise ValueError("density/linkage analysis has no navigation page-five curves")
    outputs: list[Path] = []
    outputs.extend(
        _plot_probability(
            curves,
            out_dir / "page-one-useful",
            field="page_one_useful_probability",
            title="Useful Memory visible on the first page",
            ylabel="probability",
        )
    )
    outputs.extend(
        _plot_probability(
            curves,
            out_dir / "task-success",
            field="task_success_rate",
            title="Task success after retrieval",
            ylabel="success probability",
        )
    )
    outputs.extend(_plot_cost(curves, out_dir / "compact-token-cost"))
    return outputs
