"""Markdown report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from . import FACTOR_LABELS


def generate_report(
    summary: pd.DataFrame,
    corr: pd.DataFrame,
    factor_results: dict,
    outdir: Path,
    attribution: Optional[dict] = None,
    yearly: Optional[pd.DataFrame] = None,
) -> str:
    lines = [
        "# A 股全市场风格因子分析报告",
        "",
        "## 因子定义",
        "",
        "| 因子 | 方向 | 构造方法 |",
        "|------|------|----------|",
        "| Size 大市值 | 多-空 | ln(总市值)，月度分层，top quantile - bottom quantile |",
        "| Value 低估值 | 多-空 | 1/PB (账面市值比)，月度分层 |",
        "| Momentum 动量 | 多-空 | 21日收益（跳过T日），月度分层 |",
        "| Quality 盈利 | 多-空 | 1/PE_TTM (盈利收益率)，月度分层 |",
        "| LowVol 低波动 | 多-空 | -20日波动率，月度分层 |",
        "",
        "每期按因子 z-score 排名，等分为 5 组，等权持有至下一个月末调仓。",
        "展示的是 top quintile long - bottom quintile short 的日收益序列。",
        "",
        "## 因子表现总览",
        "",
        summary.to_markdown(index=False),
        "",
        "## 因子相关性",
        "",
        corr.to_markdown(floatfmt=".2f"),
        "",
    ]

    # Yearly section
    if yearly is not None and len(yearly) > 0:
        ret_pivot = yearly.pivot(index="year", columns="factor", values="annual_ret")
        lines.extend([
            "## 逐年收益",
            "",
            ret_pivot.to_markdown(floatfmt="+.1f"),
            "",
            "![逐年因子收益](style_factor_yearly.png)",
            "",
        ])

    # Attribution section
    if attribution and "error" not in attribution:
        att = attribution
        lines.extend([
            "## 策略归因",
            "",
            f"策略: **{att['strategy']}**",
            "",
            f"- 覆盖: {att['days']} 天 ({att['years']} 年)",
            f"- 策略年化收益: {att['annual_return']:.2f}%",
            f"- 因子解释度 (R²): {att['r_squared']:.4f}",
            f"- 纯 alpha (年化): {att['annual_alpha']:.2f}%",
            f"- 截距 (年化): {att['intercept']:.4f}%",
            "",
            "| 因子 | Beta | 贡献 |",
            "|------|------|------|",
        ])
        for fname in ["size", "value", "momentum", "quality", "lowvol"]:
            beta = att["betas"].get(fname, 0)
            factor_ann = summary.loc[summary["factor"] == fname, "annual_ret"].values
            factor_ann = float(factor_ann[0]) if len(factor_ann) > 0 else 0.0
            contrib = beta * factor_ann
            lines.append(f"| {FACTOR_LABELS.get(fname, fname)} | {beta:.4f} | {contrib:+.2f}% |")
        lines.append("")

    lines.extend([
        "## 图表",
        "",
        "![因子净值](style_factor_nav.png)",
        "![收益对比](style_factor_comparison.png)",
        "![相关性](style_factor_corr.png)",
        "",
        "## 数据覆盖",
        "",
    ])

    for name in FACTOR_LABELS:
        ls = factor_results[name]["long_short"].dropna()
        lines.append(f"- {FACTOR_LABELS[name]}: {ls.index.min().date()} ~ {ls.index.max().date()}, {len(ls)} 天")

    lines.extend([
        "",
        "*由 Hermes Agent 自动生成 | 数据来源: market-data-platform (daily + daily_basic)*",
    ])

    report = "\n".join(lines)
    (outdir / "style_analysis_report.md").write_text(report)
    print(f"[report] → {outdir / 'style_analysis_report.md'}")
    return report
