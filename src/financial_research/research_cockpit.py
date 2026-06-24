"""Render a static research cockpit from the enhanced-screening snapshot."""

from __future__ import annotations

from html import escape
from math import ceil
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "artifacts/research-snapshot.csv"


def load_snapshot(path: Path = SNAPSHOT_PATH) -> pd.DataFrame:
    """Load the machine-readable output of the enhanced-screening run."""
    if not path.exists():
        raise FileNotFoundError(
            f"缺少研究快照：{path}。请先运行 scripts/enhanced_screen.py。"
        )
    return pd.read_csv(path)


def _fmt_ratio(value: object) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.2f}"


def _fmt_pct(value: object) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value) * 100:.1f}%"


def _trim(value: object, limit: int = 38) -> str:
    text = "" if pd.isna(value) else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def svg_risk_counts(df: pd.DataFrame) -> str:
    """Show coverage counts for the dashboard's main risk checks."""
    metrics = [
        ("PE 3Y > p90", int((df["pe_3y_level"] == ">p90").sum())),
        ("PB 3Y > p90", int((df["pb_3y_level"] == ">p90").sum())),
        ("Q1 经营现金流为负", int((df["q1_cf_to_ni"] < 0).sum())),
        ("融资/流通市值 > 3%", int((df["rz_to_float"] > 0.03).sum())),
        ("存在交易背离", int((df["diverge_score"] > 0).sum())),
    ]
    width, height = 700, 260
    left, right, top = 190, 50, 24
    bar_h, gap = 25, 16
    maximum = max(value for _, value in metrics) or 1
    bars = []
    for index, (label, value) in enumerate(metrics):
        y = top + index * (bar_h + gap)
        bar_width = value / maximum * (width - left - right)
        bars.append(
            f'<text x="{left - 8}" y="{y + 17}" text-anchor="end" font-size="11" fill="#334155">{escape(label)}</text>'
            f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" height="{bar_h}" fill="#2563eb" fill-opacity="0.78" rx="3"/>'
            f'<text x="{left + bar_width + 7:.1f}" y="{y + 17}" font-size="11" fill="#334155">{value}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%">
  <rect width="{width}" height="{height}" fill="white"/>
  {''.join(bars)}
</svg>'''


def svg_research_priority(df: pd.DataFrame) -> str:
    """Rank the companies that require the most verification work."""
    top = df.nlargest(12, "research_priority_score").sort_values("research_priority_score")
    if top.empty:
        return ""
    width, height = 760, 420
    left, right, top_margin, bottom = 150, 70, 20, 20
    bar_h = 22
    maximum = max(float(top["research_priority_score"].max()), 1)
    parts = []
    for index, (_, row) in enumerate(top.iterrows()):
        y = top_margin + index * 31
        value = float(row["research_priority_score"])
        bar_width = value / maximum * (width - left - right)
        color = "#1d4ed8" if row["priority"] == "P0" else "#64748b"
        parts.append(
            f'<text x="{left - 8}" y="{y + 15}" text-anchor="end" font-size="10" fill="#334155">{escape(str(row["company"]))}</text>'
            f'<rect x="{left}" y="{y}" width="{bar_width:.1f}" height="{bar_h}" fill="{color}" rx="3"/>'
            f'<text x="{left + bar_width + 7:.1f}" y="{y + 15}" font-size="10" fill="#334155">{value:.0f}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%">
  <rect width="{width}" height="{height}" fill="white"/>
  {''.join(parts)}
  <text x="{left}" y="{height - 5}" font-size="9" fill="#64748b">蓝色 P0；灰色 P1。分数用于安排核验，不代表投资评级。</text>
</svg>'''


def risk_table(df: pd.DataFrame) -> str:
    """Render a detailed lookup table after the summary charts."""
    subset = df.nlargest(20, "research_priority_score")
    rows = []
    for _, row in subset.iterrows():
        rows.append(
            "<tr>"
            f"<td>{escape(str(row['company']))}</td>"
            f"<td>{escape(str(row['priority']))}</td>"
            f"<td>{int(row['research_priority_score'])}</td>"
            f"<td>{escape(str(row.get('pe_3y_level') or '—'))} / {escape(str(row.get('pb_3y_level') or '—'))}</td>"
            f"<td>{_fmt_ratio(row.get('q1_cf_to_ni'))}</td>"
            f"<td>{_fmt_pct(row.get('rz_to_float'))}</td>"
            f"<td>{escape(_trim(row.get('bs_warning')) or '—')}</td>"
            f"<td>{escape(_trim(row.get('diverge_tags')) or '—')}</td>"
            "</tr>"
        )
    return """<table>
  <thead><tr><th>公司</th><th>优先级</th><th>核验分</th><th>PE / PB 分位</th><th>Q1 CF/NI</th><th>融资/流通市值</th><th>营运资本预警</th><th>交易背离</th></tr></thead>
  <tbody>""" + "".join(rows) + "</tbody></table>"


def build_html(df: pd.DataFrame) -> str:
    """Build a self-contained, desktop and mobile readable research cockpit."""
    reference_date = df["source_reference_date"].iloc[0]
    margin_date = df["source_margin_date"].iloc[0]
    fin_date = df["source_fin_date"].iloc[0]
    generated_at = df["snapshot_generated_at"].iloc[0]
    n_total = len(df)
    n_pe = int((df["pe_3y_level"] == ">p90").sum())
    n_pb = int((df["pb_3y_level"] == ">p90").sum())
    n_cf = int((df["q1_cf_to_ni"] < 0).sum())
    n_margin = int((df["rz_to_float"] > 0.03).sum())

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>电子行业研究驾驶舱</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px; color: #1e293b; background: #f8fafc; font-family: system-ui, -apple-system, "Microsoft YaHei", sans-serif; }}
  main {{ max-width: 1180px; margin: 0 auto; }}
  h1 {{ margin: 0; font-size: 1.55rem; }}
  h2 {{ margin: 0 0 6px; font-size: 1rem; }}
  .subtitle, .desc, .footer {{ color: #64748b; font-size: .82rem; line-height: 1.55; }}
  .subtitle {{ margin: 6px 0 20px; }}
  .cards {{ display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: 12px; margin-bottom: 18px; }}
  .card, section {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; }}
  .card {{ padding: 13px; }}
  .card .value {{ font-size: 1.45rem; font-weight: 700; color: #0f172a; }}
  .card .label {{ margin-top: 4px; color: #64748b; font-size: .73rem; }}
  section {{ padding: 16px; margin-bottom: 14px; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .78rem; }}
  th, td {{ padding: 8px; text-align: right; vertical-align: top; border-bottom: 1px solid #e2e8f0; white-space: nowrap; }}
  th:first-child, td:first-child, th:nth-child(7), td:nth-child(7), th:nth-child(8), td:nth-child(8) {{ text-align: left; white-space: normal; }}
  th {{ color: #64748b; font-weight: 600; }}
  .source {{ margin-top: 8px; padding: 10px 12px; border-left: 3px solid #2563eb; background: #eff6ff; color: #475569; font-size: .78rem; line-height: 1.55; }}
  @media (max-width: 760px) {{ body {{ padding: 14px; }} .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
</style>
</head>
<body><main>
<h1>电子行业 80 家样本研究驾驶舱</h1>
<p class="subtitle">覆盖 {n_total} 家 A 股代表。估值截止 {reference_date}，融资截止 {margin_date}，财务截止 {fin_date}；快照生成于 {escape(str(generated_at))}。</p>
<div class="cards">
  <div class="card"><div class="value">{n_total}</div><div class="label">A 股覆盖</div></div>
  <div class="card"><div class="value">{n_pe}</div><div class="label">PE 3Y &gt; p90</div></div>
  <div class="card"><div class="value">{n_pb}</div><div class="label">PB 3Y &gt; p90</div></div>
  <div class="card"><div class="value">{n_cf}</div><div class="label">Q1 经营现金流为负</div></div>
  <div class="card"><div class="value">{n_margin}</div><div class="label">融资/流通市值 &gt; 3%</div></div>
</div>
<section><h2>估值、现金流与杠杆风险覆盖</h2><p class="desc">各指标计数可交叉重叠。它们是核验风险，而非买卖信号。</p>{svg_risk_counts(df)}</section>
<section><h2>研究核验优先名单</h2><p class="desc">分数沿用增强初筛：交易背离优先，其后叠加估值高位、现金流预警与融资拥挤度；P0/P1 仅来自原研报措辞。</p>{svg_research_priority(df)}</section>
<section><h2>公司级风险与待核验项</h2><p class="desc">用于定位需要回到公告、产品、价格、产能和客户信息复核的公司。PE/PB 高位和交易背离并不构成投资结论。</p><div class="table-wrap">{risk_table(df)}</div></section>
<section><h2>口径与数据来源</h2><div class="source">快照由 `scripts/enhanced_screen.py` 生成，合并 `daily_basic`、`normalized_fundamentals`、`margin_detail` 与 `data/company-hotspot-data.csv`。`hsgt_top10_days` 只表示进入沪深港通每日十大成交的次数，不代表净买入、持仓变化或投资者身份。原研报预测与同花顺概念标签均属于待验证信息。</div></section>
<p class="footer">不构成投资建议。使用前请以公司公告、交易所披露和专题研究的新增证据复核。</p>
</main></body></html>"""


def main() -> None:
    df = load_snapshot()
    html = build_html(df)
    output = REPO_ROOT / "artifacts/research-cockpit.html"
    output.write_text(html, encoding="utf-8")
    print(f"Research cockpit: {output}")
    print(f"  Companies: {len(df)}")
    print(f"  Source snapshot: {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
