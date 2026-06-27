"""Chart generation — factor NAV, comparison, correlation, yearly breakdown."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import CJK, BG, FG, LG, FACTOR_LABELS, COLORS
from .factor_backtest import compute_factor_correlations


def plot_factor_nav(factor_results: dict, outdir: Path) -> None:
    """Multi-panel factor NAV charts."""
    fig, axes = plt.subplots(3, 2, figsize=(18, 14))
    axes = axes.flatten()

    for i, name in enumerate(FACTOR_LABELS):
        ax = axes[i]
        ls = factor_results[name]["long_short"].dropna()
        cum = (1 + ls).cumprod()

        ax.fill_between(cum.index, cum, 1, where=(cum >= 1), color="#ff6b6b", alpha=0.3)
        ax.fill_between(cum.index, cum, 1, where=(cum < 1), color="#00d4aa", alpha=0.3)
        ax.plot(cum.index, cum, color=COLORS[i], linewidth=1.2)

        ann = ((cum.iloc[-1]) ** (252 / len(cum)) - 1) * 100
        ax.set_title(f"{FACTOR_LABELS[name]}  (年化 {ann:.1f}%)", fontproperties=CJK, fontsize=11)
        ax.axhline(1, color="#555", linewidth=0.5, linestyle="--")
        ax.set_ylabel("净值", fontproperties=CJK)

    axes[5].set_visible(False)
    fig.suptitle("A 股 5 因子 Long-Short 净值曲线", fontproperties=CJK, fontsize=14, y=0.99)
    fig.tight_layout()
    fig.savefig(outdir / "style_factor_nav.png", dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] factor NAV → {outdir / 'style_factor_nav.png'}")


def plot_cumulative_comparison(factor_results: dict, outdir: Path) -> None:
    """Single chart: all factor long-short cumulative returns overlaid."""
    fig, ax = plt.subplots(figsize=(16, 7))

    for i, name in enumerate(FACTOR_LABELS):
        ls = factor_results[name]["long_short"].dropna()
        cum = (1 + ls).cumprod()
        ann = ((cum.iloc[-1]) ** (252 / len(cum)) - 1) * 100
        ax.plot(cum.index, cum, color=COLORS[i], linewidth=1.4,
                label=f"{FACTOR_LABELS[name]} ({ann:.1f}%/y)")

    ax.axhline(1, color="#555", linewidth=0.5, linestyle="--")
    ax.legend(loc="upper left", prop=CJK, framealpha=0.5, facecolor=BG, edgecolor=LG)
    ax.set_ylabel("净值", fontproperties=CJK)
    ax.set_title("A 股 5 因子 Long-Short 收益对比", fontproperties=CJK, fontsize=13)
    fig.tight_layout()
    fig.savefig(outdir / "style_factor_comparison.png", dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] comparison → {outdir / 'style_factor_comparison.png'}")


def plot_correlation_heatmap(factor_results: dict, outdir: Path) -> None:
    """Factor return correlation heatmap."""
    corr = compute_factor_correlations(factor_results)

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)

    labels = [FACTOR_LABELS.get(c, c) for c in corr.columns]
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, fontproperties=CJK, fontsize=9, rotation=45, ha="right")
    ax.set_yticklabels(labels, fontproperties=CJK, fontsize=9)

    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center",
                    fontsize=9, fontweight="bold",
                    color="white" if abs(corr.iloc[i, j]) > 0.5 else "#333")

    ax.set_title("因子收益相关性", fontproperties=CJK, fontsize=12)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(outdir / "style_factor_corr.png", dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] correlation → {outdir / 'style_factor_corr.png'}")


def plot_yearly_barchart(yearly: pd.DataFrame, outdir: Path) -> None:
    """Stacked bar chart of yearly factor returns + annual best-factor chart."""
    ret_pivot = yearly.pivot(index="year", columns="factor", values="annual_ret")
    years = sorted(ret_pivot.index)
    x = np.arange(len(years))
    bar_w = 0.15
    factor_names = list(FACTOR_LABELS.keys())

    fig, axes = plt.subplots(2, 1, figsize=(16, 12))

    ax1 = axes[0]
    for i, name in enumerate(factor_names):
        vals = [ret_pivot.loc[y, name] if name in ret_pivot.columns and y in ret_pivot.index else 0
                for y in years]
        ax1.bar(x + i * bar_w, vals, bar_w, label=FACTOR_LABELS[name], color=COLORS[i], alpha=0.85)
    ax1.set_xticks(x + bar_w * 2)
    ax1.set_xticklabels([str(y) for y in years], fontproperties=CJK, fontsize=8)
    ax1.axhline(0, color="#555", linewidth=0.5)
    ax1.set_ylabel("年化收益 (%)", fontproperties=CJK)
    ax1.set_title("逐年风格因子收益", fontproperties=CJK, fontsize=14)
    ax1.legend(loc="upper left", prop=CJK, framealpha=0.5, facecolor=BG, edgecolor="#333")

    ax2 = axes[1]
    best_ret, best_label = [], []
    for y in years:
        row = yearly[yearly["year"] == y]
        if row.empty:
            best_ret.append(0); best_label.append("")
            continue
        best = row.nlargest(1, "annual_ret").iloc[0]
        best_ret.append(best["annual_ret"])
        best_label.append(FACTOR_LABELS.get(best["factor"], ""))
    colors_best = ["#ff6b6b" if r < 0 else "#00d4aa" for r in best_ret]
    ax2.bar(x, best_ret, color=colors_best, alpha=0.8)
    for i, (y, f, r) in enumerate(zip(years, best_label, best_ret)):
        ax2.text(i, r + (1 if r >= 0 else -3), f"{f}\n{r:+.1f}%",
                 ha="center", va="bottom" if r >= 0 else "top",
                 fontproperties=CJK, fontsize=8, color=FG)
    ax2.set_xticks(x)
    ax2.set_xticklabels([str(y) for y in years], fontproperties=CJK, fontsize=8)
    ax2.axhline(0, color="#555", linewidth=0.5)
    ax2.set_ylabel("收益 (%)", fontproperties=CJK)
    ax2.set_title("每年最强因子", fontproperties=CJK, fontsize=14)

    fig.tight_layout()
    fig.savefig(outdir / "style_factor_yearly.png", dpi=150, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] yearly → {outdir / 'style_factor_yearly.png'}")
