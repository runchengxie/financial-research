"""Generate hotspot analysis charts and HTML dashboard for financial research.

Usage:
    uv run --with matplotlib --with pandas python scripts/chart_hotspot.py
    or from market-data-platform venv:
    ../market-data-platform/.venv/bin/python scripts/chart_hotspot.py

Output: charts/hotspot-dashboard.html (self-contained, open in browser)
"""

import pandas as pd
from pathlib import Path
import json
import io
import base64

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "company-hotspot-data.csv"
CHARTS_DIR = ROOT / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "figure.dpi": 120,
})

# Chinese font fallback
for font in ["WenQuanYi Micro Hei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"]:
    try:
        plt.rcParams["font.sans-serif"] = [font]
        break
    except Exception:
        continue

COLORS = {
    "双重确认": "#e74c3c",
    "外资+杠杆共振": "#e67e22",
    "内资杠杆驱动": "#f39c12",
    "纯内资杠杆": "#f1c40f",
    "内资杠杆为主": "#f39c12",
    "外资驱动+杠杆": "#e67e22",
    "内资杠杆": "#f39c12",
    "杠杆温和": "#2ecc71",
    "机构主导": "#3498db",
}


def load_data():
    df = pd.read_csv(CSV_PATH)
    df["hot_days"] = pd.to_numeric(df["hot_days_2026_ytd"], errors="coerce").fillna(0).astype(int)
    df["limit_events"] = pd.to_numeric(df["limit_events_2026"], errors="coerce").fillna(0).astype(int)
    df["total_net"] = pd.to_numeric(df["mf_total_net_wan"], errors="coerce").fillna(0)
    df["margin_delta"] = pd.to_numeric(df["margin_delta_rz_wan"], errors="coerce").fillna(0)
    df["hsgt_days"] = pd.to_numeric(df["hsgt_top10_days"], errors="coerce").fillna(0).astype(int)
    return df


def scatter_hot_vs_margin(df):
    """Scatter: hot days vs margin change, bubble = northbound days, color = signal."""
    active = df[df["hot_days"] > 0].copy()
    if active.empty:
        return None

    signal_map = {
        (1, 1, 1): "双重确认",
        (1, 0, 1): "外资+杠杆共振",
        (1, 0, 0): "内资杠杆驱动",
        (0, 1, 0): "纯内资杠杆",
        (1, 1, 0): "内资杠杆为主",
        (0, 0, 1): "机构主导",
    }
    active["has_hot"] = active["hot_days"] >= 20
    active["has_hsgt"] = active["hsgt_days"] >= 10
    active["high_margin"] = active["margin_delta"] > 30e8
    active["signal"] = active.apply(
        lambda r: signal_map.get(
            (int(r["has_hot"]), int(r["high_margin"]), int(r["has_hsgt"])),
            "内资杠杆"
        ), axis=1
    )

    fig, ax = plt.subplots(figsize=(10, 6.5))
    for sig in active["signal"].unique():
        sub = active[active["signal"] == sig]
        sizes = sub["hsgt_days"].clip(lower=1) * 8 + 40
        ax.scatter(
            sub["hot_days"], sub["margin_delta"] / 1e8,
            s=sizes, c=COLORS.get(sig, "#95a5a6"),
            alpha=0.75, edgecolors="white", linewidth=0.5,
            label=sig, zorder=3,
        )

    # Label top companies
    for _, r in active.nlargest(10, "hot_days").iterrows():
        offset = 2 if r["hot_days"] < 30 else -4
        ax.annotate(
            r["company"], (r["hot_days"], r["margin_delta"] / 1e8),
            fontsize=7, ha="center", va="bottom" if offset > 0 else "top",
            xytext=(0, offset), textcoords="offset points",
            alpha=0.85,
        )

    ax.axhline(0, color="#bdc3c7", linewidth=0.5, zorder=1)
    ax.set_xlabel("热榜天数（2026 上半年）")
    ax.set_ylabel("融资余额变化（亿元）")
    ax.set_title("热榜关注度 vs 融资杠杆 · 气泡大小 = 北向 Top10 天数")
    ax.legend(loc="upper left", fontsize=7, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def bar_composite_rank(df):
    """Horizontal bar: composite rank top 15."""
    active = df[df["hot_days"] > 0].copy()
    active["composite"] = active["hot_days"] + active["limit_events"] * 3
    top = active.nlargest(15, "composite").sort_values("composite")

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.barh(top["company"], top["composite"], color="#3498db", height=0.6)

    # Overlay limit events
    for i, (_, r) in enumerate(top.iterrows()):
        if r["limit_events"] > 0:
            ax.text(
                r["composite"] + 1, i,
                f'  +{r["limit_events"]}次涨停',
                fontsize=7, va="center", color="#c0392b",
            )

    ax.set_xlabel("综合得分（热榜天 + 涨停×3）")
    ax.set_title("热榜 + 涨停综合排名 Top 15")
    ax.invert_yaxis()
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    return fig


def timeline_top3(df):
    """Timeline of hot appearances for top 3 companies."""
    top3 = df.nlargest(3, "hot_days")
    fig, ax = plt.subplots(figsize=(10, 3))

    colors_list = ["#e74c3c", "#3498db", "#2ecc71"]
    for idx, (_, row) in enumerate(top3.iterrows()):
        dates_str = str(row["hot_dates_2026_ytd"])
        dates = [d.strip() for d in dates_str.split("|") if d.strip()]
        if dates:
            y_vals = [idx] * len(dates)
            ax.scatter(
                pd.to_datetime(dates), y_vals,
                color=colors_list[idx], s=20, alpha=0.6,
                label=row["company"], zorder=3,
            )

    ax.set_yticks(range(len(top3)))
    ax.set_yticklabels(top3["company"].tolist())
    ax.set_xlabel("日期")
    ax.set_title("热榜命中时间线（Top 3）")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    return fig


def fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def build_html(df, charts):
    top_stats = df[df["hot_days"] > 0].agg({
        "hot_days": ["count", "max", "mean"],
        "limit_events": "sum",
        "hsgt_days": "sum",
    })
    n_hot = int(top_stats.loc["count", "hot_days"])
    n_total = len(df)
    total_limit = int(top_stats.loc["sum", "limit_events"])
    total_hsgt = int(top_stats.loc["sum", "hsgt_days"])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A 股电子行业热点仪表盘</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8f9fa; color: #2c3e50; padding: 20px; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .subtitle {{ color: #7f8c8d; font-size: 0.85rem; margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat {{ background: white; border-radius: 8px; padding: 12px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .stat .value {{ font-size: 1.4rem; font-weight: 600; color: #2c3e50; }}
  .stat .label {{ font-size: 0.75rem; color: #95a5a6; }}
  .chart {{ background: white; border-radius: 8px; padding: 16px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .chart img {{ width: 100%; height: auto; }}
  .footer {{ font-size: 0.7rem; color: #bdc3c7; margin-top: 20px; text-align: center; }}
</style>
</head>
<body>
<h1>电子行业 80 家公司热点仪表盘</h1>
<p class="subtitle">覆盖 2026-01-01 至 2026-06-23 · 数据源：TuShare 同花顺系列接口</p>

<div class="stats">
  <div class="stat"><div class="value">{n_hot}<span style="font-size:0.8rem;color:#95a5a6">/{n_total}</span></div><div class="label">曾上热榜</div></div>
  <div class="stat"><div class="value">{total_limit}</div><div class="label">涨停事件</div></div>
  <div class="stat"><div class="value">{total_hsgt}</div><div class="label">北向活跃天数</div></div>
  <div class="stat"><div class="value">{int(top_stats.loc["max", "hot_days"])}</div><div class="label">最高热榜天数</div></div>
  <div class="stat"><div class="value">{top_stats.loc["mean", "hot_days"]:.0f}</div><div class="label">均值热榜天数</div></div>
</div>

<div class="chart">
  <h3 style="margin-bottom:8px">热榜关注度 vs 融资杠杆</h3>
  <p style="font-size:0.8rem;color:#7f8c8d;margin-bottom:8px">
    横轴 = 2026 上半年热榜天数，纵轴 = 融资余额变化（亿元）。气泡大小 = 北向 Top10 上榜天数。
    右上角区域为最拥挤交易，需重点关注杠杆平仓风险。
  </p>
  <img src="data:image/svg+xml;base64,{charts.get('scatter', '')}" alt="热榜 vs 融资杠杆">
</div>

<div class="chart">
  <h3 style="margin-bottom:8px">综合排名 Top 15</h3>
  <p style="font-size:0.8rem;color:#7f8c8d;margin-bottom:8px">
    得分 = 热榜天数 + 涨停次数 × 3。红色标注为涨停事件次数。
  </p>
  <img src="data:image/svg+xml;base64,{charts.get('bar', '')}" alt="综合排名">
</div>

<div class="chart">
  <h3 style="margin-bottom:8px">热榜命中时间线（Top 3）</h3>
  <p style="font-size:0.8rem;color:#7f8c8d;margin-bottom:8px">
    兆易创新 59 天、通富微电 54 天、沪电股份 44 天在 2026 上半年的热榜出现节奏。
  </p>
  <img src="data:image/svg+xml;base64,{charts.get('timeline', '')}" alt="时间线">
</div>

<p class="footer">
  数据来源：TuShare ths_hot / ths_index / limit_list_ths / moneyflow_ths / margin_detail / hsgt_top10
  · 生成时间：{pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
  · 本仪表盘不构成投资建议
</p>
</body>
</html>"""


def main():
    df = load_data()

    charts = {}
    for name, fn in [
        ("scatter", scatter_hot_vs_margin),
        ("bar", bar_composite_rank),
        ("timeline", timeline_top3),
    ]:
        fig = fn(df)
        if fig:
            charts[name] = fig_to_b64(fig)

    html = build_html(df, charts)
    out = CHARTS_DIR / "hotspot-dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard written: {out}")
    print(f"  Charts: {len(charts)} generated")
    print(f"  Open: file://{out.resolve()}")


if __name__ == "__main__":
    main()
