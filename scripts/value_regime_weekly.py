"""Value factor weekly regime report.

Usage:
    python scripts/value_regime_weekly.py [--out /tmp/report.md]

Outputs a markdown report suitable for Feishu delivery.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Config ───────────────────────────────────────────────────
FACTOR_CSV = Path(__file__).resolve().parents[1] / "artifacts" / "style_analysis" / "factor_value_daily.csv"
OUT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "value_regime"

# ── Regime parameters ────────────────────────────────────────
CONTRARIAN_52W_THRESHOLD = -0.15   # rolling 52w return < -15%
CONTRARIAN_DD_THRESHOLD = -20      # drawdown < -20%
MOMENTUM_12W_THRESHOLD = 0.05      # rolling 12w return > 5%


def load_weekly_returns() -> pd.DataFrame:
    """Load and resample value factor to weekly frequency."""
    vf = pd.read_csv(FACTOR_CSV, index_col=0, parse_dates=True, names=["ls_return"], header=0)
    vf = vf.sort_index()
    vf_w = vf.resample("W-FRI").apply(lambda x: (1 + x).prod() - 1).dropna()
    vf_w.columns = ["weekly_return"]
    return vf_w


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute weekly regime features."""
    df = df.copy()
    df["ret_4w"] = df["weekly_return"].rolling(4).sum()
    df["ret_12w"] = df["weekly_return"].rolling(12).sum()
    df["ret_52w"] = df["weekly_return"].rolling(52).sum()
    df["vol_12w"] = df["weekly_return"].rolling(12).std() * np.sqrt(52)
    df["cum"] = (1 + df["weekly_return"]).cumprod()
    df["cum_max"] = df["cum"].cummax()
    df["drawdown"] = (df["cum"] / df["cum_max"] - 1) * 100
    df["up_ratio_12w"] = df["weekly_return"].rolling(12).apply(lambda x: (x > 0).mean())
    df = df.dropna()
    return df


def assign_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Assign regime labels."""
    df = df.copy()
    conditions = [
        (df["ret_52w"] < CONTRARIAN_52W_THRESHOLD) & (df["drawdown"] < CONTRARIAN_DD_THRESHOLD),
        df["ret_12w"] > MOMENTUM_12W_THRESHOLD,
    ]
    df["regime"] = np.select(conditions, ["CONTRARIAN", "MOMENTUM"], default="NEUTRAL")
    return df


def historical_patterns(df: pd.DataFrame) -> dict:
    """Analyze historical patterns for each regime."""
    patterns = {}
    for regime in ["CONTRARIAN", "MOMENTUM", "NEUTRAL"]:
        subset = df[df["regime"] == regime]
        if len(subset) == 0:
            patterns[regime] = {"count": 0}
            continue

        # Forward returns at different horizons
        fwd = {}
        for horizon, label in [(4, "4w"), (13, "13w"), (26, "26w"), (52, "52w")]:
            fwd_col = f"fwd_{label}"
            df_tmp = df.copy()
            df_tmp[fwd_col] = df_tmp["weekly_return"].shift(-horizon).rolling(horizon).sum().shift(-horizon + 1)
            fwd_vals = df_tmp.loc[subset.index, fwd_col].dropna()
            if len(fwd_vals) > 0:
                fwd[label] = {
                    "mean": round(fwd_vals.mean() * 100, 1),
                    "median": round(fwd_vals.median() * 100, 1),
                    "win_rate": round((fwd_vals > 0).mean() * 100, 0),
                }

        patterns[regime] = {
            "count": len(subset),
            "pct_of_total": round(len(subset) / len(df) * 100, 1),
            "fwd_returns": fwd,
        }
    return patterns


def generate_report(df: pd.DataFrame, patterns: dict) -> str:
    """Generate markdown report."""
    last = df.iloc[-1]
    today = df.index[-1].date()
    monday = today - timedelta(days=today.weekday())

    lines = []
    lines.append(f"# 价值因子周报")
    lines.append(f"**{monday.strftime('%Y-%m-%d')} 周**")
    lines.append("")

    # ── Current state ────────────────────────────────────────
    regime = last["regime"]
    regime_labels = {"CONTRARIAN": "🔴 深度折价（逆势区间）", "MOMENTUM": "🟢 趋势延续", "NEUTRAL": "⚪ 中性"}
    regime_name = regime_labels.get(regime, regime)
    lines.append(f"## 当前状态：{regime_name}")
    lines.append("")
    lines.append("| 指标 | 数值 | 说明 |")
    lines.append("|------|------|------|")
    lines.append(f"| 12 周滚动收益 | {last['ret_12w']*100:+.1f}% | {'偏弱' if last['ret_12w'] < 0 else '偏强'} |")
    lines.append(f"| 52 周滚动收益 | {last['ret_52w']*100:+.1f}% | 年化口径 |")
    lines.append(f"| 当前回撤 | {last['drawdown']:.1f}% | 从历史高点 |")
    lines.append(f"| 12 周波动率 | {last['vol_12w']*100:.1f}% | 年化 |")
    lines.append(f"| 12 周胜率 | {last['up_ratio_12w']*100:.0f}% | 上涨周占比 |")
    lines.append("")

    # ── Historical context ───────────────────────────────────
    lines.append("## 历史规律")
    lines.append("")
    for regime_name, label in [("CONTRARIAN", "深度折价"), ("MOMENTUM", "趋势延续"), ("NEUTRAL", "中性")]:
        p = patterns.get(regime_name, {})
        count = p.get("count", 0)
        if count == 0:
            continue
        lines.append(f"### {label}（{count} 周，占 {p.get('pct_of_total', 0)}%）")
        fwd = p.get("fwd_returns", {})
        if fwd:
            lines.append("| 前瞻周期 | 均值 | 中位数 | 胜率 |")
            lines.append("|----------|------|--------|------|")
            for horizon, hdata in fwd.items():
                lines.append(f"| {horizon} | {hdata['mean']:+.1f}% | {hdata['median']:+.1f}% | {hdata['win_rate']:.0f}% |")
        lines.append("")

    # ── Position sizing suggestion ───────────────────────────
    lines.append("## 仓位建议")
    lines.append("")
    if regime == "CONTRARIAN":
        lines.append("当前处于**深度折价区间**。历史规律：")
        lines.append("- 短期（4-13 周）可能继续承压，不宜追涨")
        lines.append("- 中期（26-52 周）均值回归概率较高")
        lines.append("- 建议：逐步建仓，不一次性满仓，分 4-8 周分批")
        # Find current CONTRARIAN streak
        current_streak = 0
        for i in range(len(df) - 1, -1, -1):
            if df["regime"].iloc[i] == "CONTRARIAN":
                current_streak += 1
            else:
                break
        lines.append(f"- 本轮已持续 {current_streak} 周")
        # Find all CONTRARIAN episodes for reference
        episodes = []
        in_episode = False
        ep_start = None
        for i in range(len(df)):
            if df["regime"].iloc[i] == "CONTRARIAN" and not in_episode:
                in_episode = True
                ep_start = df.index[i]
            elif df["regime"].iloc[i] != "CONTRARIAN" and in_episode:
                in_episode = False
                episodes.append((ep_start, df.index[i-1]))
        if in_episode:
            episodes.append((ep_start, df.index[-1]))
        if episodes:
            longest = max((e[1] - e[0]).days // 7 for e in episodes)
            lines.append(f"- 历史深度折价共出现 {len(episodes)} 次，最长持续 {longest} 周")
    elif regime == "MOMENTUM":
        lines.append("当前处于**趋势延续区间**。历史规律：")
        lines.append("- 短期跟随趋势，持有为主")
        lines.append("- 建议：标准配置，不追高不减仓")
    else:
        lines.append("当前处于**中性区间**，无明显方向性信号。建议标准配置。")

    lines.append("")
    lines.append("---")
    lines.append(f"_数据截止：{today}，基于 2015 年以来价值因子日收益序列_")
    lines.append(f"_计算方法：月度调仓的等权 long-short 组合（top quintile - bottom quintile）_")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Value factor weekly regime report")
    ap.add_argument("--out", help="Output path (default: stdout)")
    args = ap.parse_args()

    print("[value_regime] Loading data ...", file=sys.stderr)
    df_w = load_weekly_returns()
    df = compute_features(df_w)
    df = assign_regime(df)

    print("[value_regime] Computing patterns ...", file=sys.stderr)
    patterns = historical_patterns(df)

    print("[value_regime] Generating report ...", file=sys.stderr)
    report = generate_report(df, patterns)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"[value_regime] Report written to {out_path}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
