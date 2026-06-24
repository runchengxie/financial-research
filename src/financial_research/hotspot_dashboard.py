"""Generate hotspot analysis SVG charts and an HTML dashboard.

Usage: python scripts/chart_hotspot.py
"""

from html import escape
from math import ceil, floor
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "data/company-hotspot-data.csv"


def load_data():
    df = pd.read_csv(CSV_PATH)
    df["hot_days"] = pd.to_numeric(df["hot_days_2026_ytd"], errors="coerce").fillna(0).astype(int)
    df["limit_events"] = pd.to_numeric(df["limit_events_2026"], errors="coerce").fillna(0).astype(int)
    df["total_net"] = pd.to_numeric(df["mf_total_net_wan"], errors="coerce").fillna(0)
    df["margin_delta"] = pd.to_numeric(df["margin_delta_rz_wan"], errors="coerce").fillna(0)
    df["hsgt_days"] = pd.to_numeric(df["hsgt_top10_days"], errors="coerce").fillna(0).astype(int)
    return df


def svg_scatter(df):
    """Scatter: hot days vs margin change, bubble = Top10 trading activity."""
    active = df[df["hot_days"] > 0].copy()
    if active.empty:
        return ""

    margin = active["margin_delta"] / 1e8
    hot = active["hot_days"]
    hsgt = active["hsgt_days"].clip(lower=1) * 6 + 12

    colors = []
    for _, r in active.iterrows():
        if r["hsgt_days"] >= 10 and r["hot_days"] >= 20:
            colors.append("#e74c3c")
        elif r["hsgt_days"] >= 10:
            colors.append("#e67e22")
        elif r["hot_days"] >= 20:
            colors.append("#f39c12")
        else:
            colors.append("#3498db")

    W, H = 700, 440
    ml, mr, mt, mb = 60, 30, 30, 50
    x_max = max(int(hot.max()), 1)
    y_min = min(float(margin.min()), 0.0)
    y_max = max(float(margin.max()), 0.0)
    px = lambda x: ml + x / x_max * (W - ml - mr)
    py = lambda y: H - mb - (y - y_min) / max(y_max - y_min, 1) * (H - mt - mb)

    circles = []
    labels = []
    for i, (_, r) in enumerate(active.iterrows()):
        cx, cy, r_size = px(r["hot_days"]), py(r["margin_delta"] / 1e8), hsgt.iloc[i]
        circles.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_size:.1f}" '
            f'fill="{colors[i]}" fill-opacity="0.7" stroke="white" stroke-width="0.5"/>'
        )
        if r["hot_days"] >= 20:
            labels.append(
                f'<text x="{cx:.1f}" y="{cy - r_size - 3:.1f}" '
                f'text-anchor="middle" font-size="8" fill="#2c3e50">{escape(str(r["company"]))}</text>'
            )

    # Axes
    zero_y = py(0)
    grid_lines = ""
    for pct in [0.25, 0.5, 0.75]:
        x = ml + (W - ml - mr) * pct
        grid_lines += f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{H - mb}" stroke="#ecf0f1" stroke-width="0.5"/>'

    y_step = max(10, ceil((y_max - y_min) / 4 / 10) * 10)
    for step in range(int(floor(y_min / y_step) * y_step), int(ceil(y_max / y_step) * y_step) + y_step, y_step):
        y = py(step)
        if mt < y < H - mb:
            grid_lines += f'<line x1="{ml}" y1="{y:.1f}" x2="{W - mr}" y2="{y:.1f}" stroke="#ecf0f1" stroke-width="0.5"/>'
            grid_lines += f'<text x="{ml - 5}" y="{y + 3:.1f}" text-anchor="end" font-size="8" fill="#95a5a6">{step}</text>'

    # X labels
    x_step = 10 if x_max <= 60 else 20
    for v in range(0, x_max + x_step, x_step):
        x = px(v)
        grid_lines += f'<text x="{x:.1f}" y="{H - mb + 15}" text-anchor="middle" font-size="8" fill="#95a5a6">{v}</text>'

    legend_items = [
        ("#e74c3c", "两项均活跃"),
        ("#e67e22", "Top10 更活跃"),
        ("#f39c12", "热榜驱动"),
        ("#3498db", "其他"),
    ]
    legend_svg = ""
    for i, (c, t) in enumerate(legend_items):
        lx, ly = W - mr - 160 + i * 90, mt + 5
        legend_svg += (
            f'<circle cx="{lx + 4}" cy="{ly + 4}" r="5" fill="{c}" fill-opacity="0.7"/>'
            f'<text x="{lx + 14}" y="{ly + 8}" font-size="8" fill="#7f8c8d">{t}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%">
  <rect width="{W}" height="{H}" fill="white"/>
  <text x="{W/2:.0f}" y="18" text-anchor="middle" font-size="12" font-weight="bold" fill="#2c3e50">热榜关注度 vs 融资杠杆</text>
  <text x="{W/2:.0f}" y="30" text-anchor="middle" font-size="8" fill="#95a5a6">横轴=热榜天数，纵轴=融资余额变化（亿元），气泡=沪深港通 Top10 上榜天数</text>
  {grid_lines}
  <line x1="{ml}" y1="{zero_y:.1f}" x2="{W - mr}" y2="{zero_y:.1f}" stroke="#bdc3c7" stroke-width="1"/>
  {"".join(circles)}
  {"".join(labels)}
  {legend_svg}
</svg>'''


def svg_bar(df):
    """Horizontal bar: composite rank top 15."""
    active = df[df["hot_days"] > 0].copy()
    active["composite"] = active["hot_days"] + active["limit_events"] * 3
    top = active.nlargest(15, "composite").sort_values("composite")
    if top.empty:
        return ""

    W, H = 400, 460
    ml, mr, mt, mb = 90, 30, 20, 20
    bar_h = 24
    max_v = top["composite"].max()

    bars_svg = ""
    for i, (_, r) in enumerate(top.iterrows()):
        y = mt + i * (bar_h + 4)
        bw = (r["composite"] / max_v) * (W - ml - mr)
        color = "#e74c3c" if r["hot_days"] >= 30 else "#3498db"
        bars_svg += (
            f'<rect x="{ml}" y="{y:.0f}" width="{bw:.0f}" height="{bar_h}" '
            f'fill="{color}" fill-opacity="0.8" rx="2"/>'
            f'<text x="{ml - 5}" y="{y + bar_h/2 + 3:.0f}" text-anchor="end" '
            f'font-size="9" fill="#2c3e50">{escape(str(r["company"]))}</text>'
            f'<text x="{ml + bw + 5:.0f}" y="{y + bar_h/2 + 3:.0f}" '
            f'font-size="8" fill="#2c3e50">{r["composite"]:.0f}</text>'
        )
        if r["limit_events"] > 0:
            bars_svg += (
                f'<text x="{ml + bw + 40:.0f}" y="{y + bar_h/2 + 3:.0f}" '
                f'font-size="7" fill="#c0392b">+{r["limit_events"]}次涨停</text>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%">
  <rect width="{W}" height="{H}" fill="white"/>
  <text x="{W/2:.0f}" y="15" text-anchor="middle" font-size="12" font-weight="bold" fill="#2c3e50">综合排名 Top 15</text>
  {bars_svg}
  <text x="{W - mr}" y="{H - 2}" text-anchor="end" font-size="7" fill="#bdc3c7">得分 = 热榜天 + 涨停x3</text>
</svg>'''


def svg_timeline(df):
    """Timeline of hot appearances for top 3."""
    top3 = df.nlargest(3, "hot_days")
    W, H = 700, 160
    ml, mr, mt, mb = 60, 20, 15, 30

    all_dates = []
    company_pts = []
    colors = ["#e74c3c", "#3498db", "#2ecc71"]
    for idx, (_, row) in enumerate(top3.iterrows()):
        dates_str = str(row["hot_dates_2026_ytd"])
        pts = []
        for d in dates_str.replace(" ", "").split("|"):
            d = d.strip()
            if len(d) == 10:
                pts.append(d)
                all_dates.append(pd.Timestamp(d))
        company_pts.append((row["company"], pts, colors[idx], row["hot_days"]))

    if not all_dates:
        return ""

    t_min, t_max = min(all_dates), max(all_dates)
    span = max((t_max - t_min).days, 1)

    px = lambda d: ml + (d - t_min).days / span * (W - ml - mr)
    py = lambda i: mt + 10 + i * 40

    circles = ""
    for i, (name, pts, color, _) in enumerate(company_pts):
        circles += f'<text x="{ml - 5}" y="{py(i) + 4:.0f}" text-anchor="end" font-size="9" fill="#2c3e50">{escape(str(name))}</text>'
        for pt in pts:
            cx = px(pd.Timestamp(pt))
            circles += f'<circle cx="{cx:.1f}" cy="{py(i):.0f}" r="4" fill="{color}" fill-opacity="0.6"/>'

    months = []
    cur = pd.Timestamp("2026-01-01")
    while cur <= t_max:
        months.append(cur)
        cur = cur + pd.DateOffset(months=1)
    month_labels = ""
    for m in months:
        x = px(m)
        month_labels += (
            f'<line x1="{x:.0f}" y1="{mt}" x2="{x:.0f}" y2="{H - mb}" stroke="#ecf0f1" stroke-width="0.5"/>'
            f'<text x="{x:.0f}" y="{H - mb + 15}" text-anchor="middle" font-size="8" fill="#95a5a6">{m.strftime("%m月")}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%">
  <rect width="{W}" height="{H}" fill="white"/>
  <text x="{W/2:.0f}" y="12" text-anchor="middle" font-size="11" font-weight="bold" fill="#2c3e50">热榜命中时间线（Top 3）</text>
  {month_labels}
  {circles}
</svg>'''


def signal_table(df: pd.DataFrame) -> str:
    """Render a compact table of unusual trading-activity combinations."""
    candidates = df[
        (df["hot_days"] >= 20)
        | (df["limit_events"] >= 5)
        | (df["hsgt_days"] >= 20)
    ].copy()
    if candidates.empty:
        return "<p>无满足当前筛选条件的公司。</p>"

    candidates["signal_score"] = (
        (candidates["hot_days"] >= 20).astype(int)
        + (candidates["limit_events"] >= 5).astype(int)
        + (candidates["hsgt_days"] >= 20).astype(int)
        + (candidates["margin_delta"].abs() >= 1e9).astype(int)
    )
    top = candidates.sort_values(
        ["signal_score", "hot_days", "limit_events"], ascending=False
    ).head(12)
    rows = []
    for _, row in top.iterrows():
        rows.append(
            "<tr>"
            f"<td>{escape(str(row['company']))}</td>"
            f"<td>{row['hot_days']}</td>"
            f"<td>{row['limit_events']}</td>"
            f"<td>{row['total_net'] / 1e4:+.1f}</td>"
            f"<td>{row['hsgt_days']}</td>"
            f"<td>{row['margin_delta'] / 1e8:+.1f}</td>"
            "</tr>"
        )
    return """<table class=\"signal-table\">
  <thead><tr><th>公司</th><th>热榜天</th><th>涨停</th><th>净流入（亿）</th><th>Top10 天</th><th>融资变化（亿）</th></tr></thead>
  <tbody>""" + "".join(rows) + "</tbody></table>"


def build_html(df, charts):
    n_hot = int((df["hot_days"] > 0).sum())
    n_total = len(df)
    total_limit = int(df["limit_events"].sum())
    max_hot = int(df["hot_days"].max())
    avg_hot = df.loc[df["hot_days"] > 0, "hot_days"].mean()
    total_hsgt = int(df["hsgt_days"].sum())

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A 股电子行业热点仪表盘</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8f9fa; color: #2c3e50; padding: 24px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 2px; }}
  .subtitle {{ color: #7f8c8d; font-size: 0.8rem; margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat {{ background: white; border-radius: 8px; padding: 10px 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }}
  .stat .value {{ font-size: 1.3rem; font-weight: 600; }}
  .stat .label {{ font-size: 0.7rem; color: #95a5a6; }}
  .chart {{ background: white; border-radius: 8px; padding: 12px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }}
  .chart h3 {{ font-size: 0.95rem; margin-bottom: 4px; }}
  .chart .desc {{ font-size: 0.75rem; color: #7f8c8d; margin-bottom: 8px; }}
  .signal-table {{ width: 100%; border-collapse: collapse; font-size: 0.78rem; }}
  .signal-table th, .signal-table td {{ padding: 7px 8px; text-align: right; border-bottom: 1px solid #ecf0f1; }}
  .signal-table th:first-child, .signal-table td:first-child {{ text-align: left; }}
  .signal-table th {{ color: #7f8c8d; font-weight: 600; }}
  .footer {{ font-size: 0.65rem; color: #bdc3c7; margin-top: 16px; text-align: center; }}
</style>
</head>
<body>
<h1>电子行业 80 家公司热点仪表盘</h1>
<p class="subtitle">数据窗口：2026-01-01 至 2026-06-23 · 数据源：TuShare 同花顺系列接口</p>

<div class="stats">
  <div class="stat"><div class="value">{n_hot}<span style="font-size:0.8rem;color:#95a5a6">/{n_total}</span></div><div class="label">曾上热榜</div></div>
  <div class="stat"><div class="value">{total_limit}</div><div class="label">涨停事件</div></div>
  <div class="stat"><div class="value">{total_hsgt}</div><div class="label">沪深港通 Top10 上榜天数</div></div>
  <div class="stat"><div class="value">{max_hot}</div><div class="label">最高热榜天数</div></div>
  <div class="stat"><div class="value">{avg_hot:.0f}</div><div class="label">均值热榜天数</div></div>
</div>

<div class="chart">
  <h3>热榜关注度 vs 融资杠杆</h3>
  <p class="desc">横轴 = 2026 上半年热榜天数，纵轴 = 融资余额变化（亿元）。气泡大小 = 沪深港通 Top10 上榜天数；该指标仅代表交易活跃度，不代表净买入或持仓方向。</p>
  {charts.get('scatter', '<p>无数据</p>')}
</div>

<div class="chart">
  <h3>需复核的交易信号</h3>
  <p class="desc">列出热榜、涨停、沪深港通 Top10 与融资变化中至少一项明显的公司。它用于安排核验，不构成交易方向结论。</p>
  {signal_table(df)}
</div>

<div class="chart">
  <h3>综合排名 Top 15</h3>
  <p class="desc">得分 = 热榜天数 + 涨停次数 x 3。红色柱为热榜天数 >= 30。</p>
  {charts.get('bar', '<p>无数据</p>')}
</div>

<div class="chart">
  <h3>热榜时间线（Top 3）</h3>
  <p class="desc">兆易创新、通富微电、沪电股份在 2026 上半年的热榜出现节奏。</p>
  {charts.get('timeline', '<p>无数据</p>')}
</div>

<p class="footer">
  来源：TuShare（ths_hot / limit_list_ths / moneyflow_ths / margin_detail / hsgt_top10）
  · 生成时间：{pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
  · 不构成投资建议
</p>
</body>
</html>"""


def main():
    df = load_data()

    charts = {}
    for name, fn in [
        ("scatter", svg_scatter),
        ("bar", svg_bar),
        ("timeline", svg_timeline),
    ]:
        try:
            svg = fn(df)
            if svg:
                charts[name] = svg
        except Exception as e:
            print(f"  [WARN] {name}: {e}")

    html = build_html(df, charts)

    artifacts_dir = REPO_ROOT / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    out = artifacts_dir / "hotspot-dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard: {out}")
    print(f"  Charts: {len(charts)} generated")
    print(f"  Open: file://{out.resolve()}")


if __name__ == "__main__":
    main()
