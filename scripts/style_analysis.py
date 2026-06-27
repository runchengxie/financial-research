#!/usr/bin/env python3
"""
全市场风格因子分析 — 5 因子 Long-short 回测 + 报告。

用法:
  cd ~/code/financial-research
  source ~/code/research-workspace/market-data-platform/.venv/bin/activate
  source ~/code/research-workspace/market-data-platform/.env.local
  DATA_PLATFORM_ROOT=/home/richard/data/market-data-platform python3 scripts/style_analysis.py

带策略归因:
  DATA_PLATFORM_ROOT=... python3 scripts/style_analysis.py --strategy-csv returns.csv --strategy-name "cstree"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from financial_research.style.data import load_data
from financial_research.style.factor_calc import compute_factors
from financial_research.style.factor_backtest import (
    get_rebalance_dates,
    build_factor_returns,
    compute_summary,
    compute_factor_correlations,
    compute_yearly_breakdown,
)
from financial_research.style.charts import (
    plot_factor_nav,
    plot_cumulative_comparison,
    plot_correlation_heatmap,
    plot_yearly_barchart,
)
from financial_research.style.attribution import run_strategy_attribution
from financial_research.style.report import generate_report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=os.environ.get("DATA_PLATFORM_ROOT",
                    "/home/richard/data/market-data-platform"))
    ap.add_argument("--outdir", default="artifacts/style_analysis")
    ap.add_argument("--quick", action="store_true", help="Sample mode: only 2020-2026")
    ap.add_argument("--strategy-csv", help="Path to strategy daily return CSV for attribution")
    ap.add_argument("--strategy-name", default="strategy", help="Strategy name for report")
    args = ap.parse_args()

    data_root = Path(args.data_root)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("全市场风格因子分析")
    print(f"数据根: {data_root}")
    print(f"输出:   {outdir}")
    print("=" * 60)

    # 1. Load
    daily, basics = load_data(data_root)
    if args.quick:
        daily = daily[daily["trade_date"] >= "2020-01-01"]
        basics = basics[basics["trade_date"] >= "2020-01-01"]

    # 2. Compute factors
    factors = compute_factors(daily, basics)

    # 3. Rebalance dates
    all_dates_sorted = pd.DatetimeIndex(sorted(factors["trade_date"].unique()))
    rd = get_rebalance_dates(all_dates_sorted)
    print(f"[rebalance] {len(rd)} monthly rebalance dates, {rd[0].date()} ~ {rd[-1].date()}")

    # 4. Factor backtest
    results = build_factor_returns(factors, daily, rd)

    # 5. Summary
    summary = compute_summary(results)
    print("\n=== 因子表现 ===")
    print(summary.to_string(index=False))

    # 6. Correlations
    corr = compute_factor_correlations(results)
    print("\n=== 因子相关性 ===")
    print(corr.to_string())

    # 7. Charts
    plot_factor_nav(results, outdir)
    plot_cumulative_comparison(results, outdir)
    plot_correlation_heatmap(results, outdir)

    # 7.5 Yearly
    yearly = compute_yearly_breakdown(results)
    plot_yearly_barchart(yearly, outdir)
    yearly.to_csv(outdir / "factor_yearly.csv", index=False)
    print("\n=== 逐年收益 ===")
    ret_pivot = yearly.pivot(index="year", columns="factor", values="annual_ret")
    print(ret_pivot.to_string(float_format=lambda x: f"{x:+.1f}"))

    # 8. Attribution
    attribution_result = None
    if args.strategy_csv:
        print(f"\n[strategy attribution] loading {args.strategy_csv} ...")
        strat_df = pd.read_csv(args.strategy_csv, parse_dates=[0], index_col=0)
        if len(strat_df.columns) >= 1:
            attr = run_strategy_attribution(results, strat_df.iloc[:, 0], args.strategy_name)
            print(f"  R²={attr.get('r_squared','N/A')}, alpha={attr.get('annual_alpha','N/A')}%")
            attribution_result = attr

    # 9. Report
    generate_report(summary, corr, results, outdir, attribution_result, yearly)

    # 10. Save
    summary.to_json(outdir / "factor_summary.json", orient="records", indent=2)
    corr.to_json(outdir / "factor_correlation.json", orient="index", indent=2)
    for name, res in results.items():
        res["long_short"].to_csv(outdir / f"factor_{name}_daily.csv", index=True, header=True)

    print(f"\n[OK] 全部产出写入 {outdir}/")
    for f in sorted(outdir.iterdir()):
        print(f"     {f.name}")


if __name__ == "__main__":
    main()
