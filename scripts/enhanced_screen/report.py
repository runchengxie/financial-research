"""Markdown report generation for enhanced screening.

Consumes the merged report DataFrame and produces the markdown string
written to enhanced-screening-report.md.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .data import get_fin_date, get_margin_date, get_reference_date


def generate_report(report: pd.DataFrame) -> str:
    """Generate the full enhanced screening report as a markdown string.

    Parameters
    ----------
    report : pd.DataFrame
        Merged DataFrame with all computed columns from data.py functions.

    Returns
    -------
    str
        Markdown content for enhanced-screening-report.md.
    """
    ref_date = get_reference_date()
    margin_date = get_margin_date()
    fin_date = get_fin_date()

    lines: list[str] = []
    _header(lines, ref_date, margin_date, fin_date)
    _summary(lines, report)
    _section_valuation(lines, report)
    _section_pe_pb_divergence(lines, report)
    _section_cashflow(lines, report)
    _section_ar_inventory(lines, report)
    _section_margin(lines, report)
    _section_divergence(lines, report)
    _section_ranking(lines, report)

    return "\n".join(lines) + "\n"


def _header(lines: list[str], ref_date: str, margin_date: str, fin_date: str) -> None:
    lines.append("# 增强初筛报告")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"数据截止：每日估值 {ref_date}，融资融券 {margin_date}，财务 {fin_date}")
    lines.append("")
    lines.append("## 读法")
    lines.append("")
    lines.append("- PE/PB 分位基于最近 3 年历史，`>p90` 表示当前估值处于近 3 年最高的 10% 区间。")
    lines.append("- 现金流质量 = 经营活动现金流净额 / 归母净利润。Q1 为单季，FY 为全年。比率持续 < 0.5 需警惕利润质量。")
    lines.append("- 融资拥挤度 = 融资余额 / 流通市值。> 3% 为较高杠杆，> 5% 为拥挤。")
    lines.append("- 背离标签表示市场行为存在矛盾（如热度高但资金流出），共识标签表示多维度信号一致。")
    lines.append("")


def _summary(lines: list[str], report: pd.DataFrame) -> None:
    n_total = len(report)
    n_pe = _count(report, "pe_3y_level", ">p90")
    n_pb = _count(report, "pb_3y_level", ">p90")
    n_cf = _count_cond(report, lambda r: pd.notna(r.get("q1_cf_to_ni")) and r["q1_cf_to_ni"] < 0)
    n_mg = _count_cond(report, lambda r: pd.notna(r.get("rz_to_float")) and r["rz_to_float"] > 0.03)
    n_dv = _count_cond(report, lambda r: r.get("diverge_score", 0) > 0)

    lines.append("## 摘要统计")
    lines.append("")
    lines.append("| 指标 | 数量 | 占比 |")
    lines.append("| --- | ---: | ---: |")
    lines.append(f"| 覆盖 A 股 | {n_total} | 100% |")
    lines.append(f"| PE 3Y > p90 | {n_pe} | {_pct(n_pe, n_total)} |")
    lines.append(f"| PB 3Y > p90 | {n_pb} | {_pct(n_pb, n_total)} |")
    lines.append(f"| Q1 经营现金流为负 | {n_cf} | {_pct(n_cf, n_total)} |")
    lines.append(f"| 融资占流通市值 > 3% | {n_mg} | {_pct(n_mg, n_total)} |")
    lines.append(f"| 存在背离信号 | {n_dv} | {_pct(n_dv, n_total)} |")
    lines.append("")


def _section_valuation(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("## 1. 估值预警（PE/PB 分位）")
    lines.append("")

    # PE alerts: top 25%
    pe_alert = report[report["pe_3y_level"].isin([">p90", "p75-p90"])].sort_values("pe_ttm", ascending=False)
    if not pe_alert.empty:
        lines.append("### PE TTM 处于 3 年高位（top 25%）")
        lines.append("")
        lines.append("| 公司 | 优先级 | PE TTM | PE 3Y p50 | PE 3Y p75 | PE 3Y p90 | 分位 | PB 3Y 分位 |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
        for _, r in pe_alert.iterrows():
            lines.append(
                f"| {r['company']} | {r['priority']} | {_fmt(r, 'pe_ttm')} | "
                f"{_fmt(r, 'pe_3y_p50')} | {_fmt(r, 'pe_3y_p75')} | {_fmt(r, 'pe_3y_p90')} | "
                f"{r.get('pe_3y_level', '')} | {r.get('pb_3y_level', '')} |"
            )
        lines.append("")

    # PB alerts: >p90
    pb_alert = report[report["pb_3y_level"] == ">p90"]
    if not pb_alert.empty:
        lines.append("### PB 处于 3 年极高位（> p90）")
        lines.append("")
        lines.append("| 公司 | 优先级 | PB | PB 3Y p50 | PB 3Y p90 | PE 3Y 分位 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- |")
        for _, r in pb_alert.sort_values("pb", ascending=False).iterrows():
            lines.append(
                f"| {r['company']} | {r['priority']} | {_fmt(r, 'pb')} | "
                f"{_fmt(r, 'pb_3y_p50')} | {_fmt(r, 'pb_3y_p90')} | "
                f"{r.get('pe_3y_level', '')} |"
            )
        lines.append("")


def _section_pe_pb_divergence(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("### PE/PB 背离分析")
    lines.append("")
    lines.append("PE 与 PB 分位不一致时，估值信号的含义不同：")
    lines.append("")
    lines.append("- **多重扩张**（PE 和 PB 均 > p90）：市场定价繁荣，估值容错空间极小。")
    lines.append("- **利润压缩型**（PE > p90 但 PB 正常）：高 PE 来自利润处于周期底部，利润恢复后 PE 自然回落，可能是低估信号。")
    lines.append("- **资产重估型**（PB > p90 但 PE 正常）：资产已被重估但利润尚未跟上，需验证利润能否兑现。")
    lines.append("")

    patterns = report[report["pe_pb_pattern"].notna()]
    for name, desc in [
        ("多重扩张", "PE 和 PB 均处于 3 年极高位"),
        ("利润压缩型", "PE 极高位但 PB 未到极端"),
        ("资产重估型", "PB 极高位但 PE 未到极端"),
    ]:
        subset = patterns[patterns["pe_pb_pattern"] == name].sort_values("pe_ttm", ascending=False)
        if not subset.empty:
            lines.append(f"#### {name}（{desc}）")
            lines.append("")
            lines.append("| 公司 | 优先级 | PE TTM | PE 3Y 分位 | PB | PB 3Y 分位 |")
            lines.append("| --- | --- | ---: | --- | ---: | --- |")
            for _, r in subset.iterrows():
                lines.append(
                    f"| {r['company']} | {r['priority']} | {_fmt(r, 'pe_ttm')} | "
                    f"{r.get('pe_3y_level', '')} | {_fmt(r, 'pb')} | "
                    f"{r.get('pb_3y_level', '')} |"
                )
            lines.append("")


def _section_cashflow(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("## 2. 现金流质量")
    lines.append("")

    cf_q1 = report[report["q1_cf_to_ni"].notna()].sort_values("q1_cf_to_ni")
    if not cf_q1.empty:
        fin_date = get_fin_date()
        lines.append(f"### Q1 {fin_date[:4]} 经营现金流 / 净利润")
        lines.append("")
        lines.append("注：Q1 单季现金流季节性波动大，负值不一定是结构性恶化，但值得核对。")
        lines.append("")
        lines.append("| 公司 | 优先级 | Q1 净利润(亿) | Q1 经营CF(亿) | CF/NI | 评估 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- |")
        for _, r in cf_q1.iterrows():
            ni = _fmt_yi(r, "q1_net_income")
            cf = _fmt_yi(r, "q1_oper_cf")
            ratio = r["q1_cf_to_ni"]
            rs = f"{ratio:.2f}" if pd.notna(ratio) else "N/A"
            lines.append(f"| {r['company']} | {r['priority']} | {ni} | {cf} | {rs} | {_cf_assess(ratio)} |")
        lines.append("")

    cf_fy = report[report["fy_cf_to_ni"].notna()].sort_values("fy_cf_to_ni")
    if not cf_fy.empty:
        lines.append("### FY 全年经营现金流 / 净利润")
        lines.append("")
        lines.append("| 公司 | 优先级 | FY 净利润(亿) | FY 经营CF(亿) | CF/NI | 评估 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- |")
        for _, r in cf_fy.iterrows():
            ni = _fmt_yi(r, "fy_net_income")
            cf = _fmt_yi(r, "fy_oper_cf")
            ratio = r["fy_cf_to_ni"]
            rs = f"{ratio:.2f}" if pd.notna(ratio) else "N/A"
            lines.append(f"| {r['company']} | {r['priority']} | {ni} | {cf} | {rs} | {_cf_assess(ratio)} |")
        lines.append("")


def _section_ar_inventory(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("## 2b. 应收与存货趋势（Q1 同比）")
    lines.append("")
    lines.append("注：应收/存货同比超过 50% 标为「暴增」，超过 30% 标为「偏快」。应收/单季收入 > 1.0 标为「应收超单季收入」。")
    lines.append("")

    ar_data = report[report["ar_yoy"].notna()].sort_values("ar_yoy", ascending=False)
    if not ar_data.empty:
        lines.append("| 公司 | 优先级 | 应收同比 | 存货同比 | 应收/单季收入 | 存货/单季收入 | 预警 |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")
        for _, r in ar_data.iterrows():
            ar_y = f"{r['ar_yoy'] * 100:.0f}%" if pd.notna(r.get("ar_yoy")) else "N/A"
            inv_y = f"{r['inv_yoy'] * 100:.0f}%" if pd.notna(r.get("inv_yoy")) else "N/A"
            ar_r = f"{r.get('ar_to_rev', 0):.2f}" if pd.notna(r.get("ar_to_rev")) else "N/A"
            inv_r = f"{r.get('inv_to_rev', 0):.2f}" if pd.notna(r.get("inv_to_rev")) else "N/A"
            lines.append(f"| {r['company']} | {r['priority']} | {ar_y} | {inv_y} | {ar_r} | {inv_r} | {r.get('bs_warning', '')} |")
        lines.append("")


def _section_margin(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("## 3. 融资拥挤度")
    lines.append("")

    mg = report[report["rz_to_float"].notna()].sort_values("rz_to_float", ascending=False)
    if not mg.empty:
        lines.append("| 公司 | 优先级 | 融资余额(亿) | 流通市值(亿) | 融资/流通市值 | 拥挤度 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- |")
        for _, r in mg.iterrows():
            rz = f"{r['rzye'] / 1e8:.1f}" if pd.notna(r.get("rzye")) else "N/A"
            mv = f"{r.get('circ_mv_yuan', 0) / 1e8:.0f}" if pd.notna(r.get("circ_mv_yuan")) else "N/A"
            ratio = r["rz_to_float"]
            rs = f"{ratio * 100:.1f}%"
            if ratio > 0.05:
                crowd = "[ALERT] 高度拥挤"
            elif ratio > 0.03:
                crowd = "[WARN] 较高杠杆"
            else:
                crowd = "正常"
            lines.append(f"| {r['company']} | {r['priority']} | {rz} | {mv} | {rs} | {crowd} |")
        lines.append("")


def _section_divergence(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("## 4. 背离与共识信号")
    lines.append("")

    diverge = report[report["diverge_score"] > 0].sort_values("diverge_score", ascending=False)
    if not diverge.empty:
        lines.append("### 存在背离信号的公司（研究价值较高）")
        lines.append("")
        lines.append("背离信号提示市场行为存在矛盾，往往是预期差的来源。")
        lines.append("")
        lines.append("| 公司 | 优先级 | 背离标签 | 热榜天 | 净流入(亿) | 北向天 | 融资变化(亿) |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: |")
        for _, r in diverge.iterrows():
            nf = f"{r.get('net_flow_yi', 0):.1f}"
            md = f"{r.get('margin_delta_yi', 0):.1f}"
            lines.append(f"| {r['company']} | {r['priority']} | {r['diverge_tags']} | {r['hot_days']} | {nf} | {r['hsgt_days']} | {md} |")
        lines.append("")

    consensus = report[report["consensus_tags"].notna() & (report["consensus_tags"] != "")]
    if not consensus.empty:
        lines.append("### 极度拥挤共识（多维度信号一致看多）")
        lines.append("")
        lines.append("共识拥挤不等于看空，但意味着预期差空间被压缩，需做估值反推。")
        lines.append("")
        lines.append("| 公司 | 优先级 | 共识标签 | 热榜天 | 北向天 | 融资变化(亿) | PE 3Y 分位 |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | --- |")
        for _, r in consensus.iterrows():
            md = f"{r.get('margin_delta_yi', 0):.1f}"
            lines.append(f"| {r['company']} | {r['priority']} | {r['consensus_tags']} | {r['hot_days']} | {r['hsgt_days']} | {md} | {r.get('pe_3y_level', '')} |")
        lines.append("")


def _section_ranking(lines: list[str], report: pd.DataFrame) -> None:
    lines.append("## 5. 研究价值排序（背离信号加权）")
    lines.append("")
    lines.append("排序逻辑：背离信号 > 共识信号。得分 = 背离分 × 3 + 共识分 + (PE/PB 高位分) + (现金流预警分)")
    lines.append("")

    scores = []
    for _, r in report.iterrows():
        score = (r.get("diverge_score", 0) or 0) * 3
        ctag = r.get("consensus_tags", "")
        if pd.notna(ctag) and ctag != "":
            score += 1
        if r.get("pe_3y_level") == ">p90":
            score += 1
        if r.get("pb_3y_level") == ">p90":
            score += 1
        if pd.notna(r.get("q1_cf_to_ni")) and r["q1_cf_to_ni"] < 0:
            score += 1
        if pd.notna(r.get("rz_to_float")) and r["rz_to_float"] > 0.05:
            score += 1
        scores.append((r["company"], r["priority"], score, r.get("diverge_tags", ""), r.get("consensus_tags", "")))

    scores.sort(key=lambda x: x[2], reverse=True)
    top = scores[:25]

    lines.append("| 排名 | 公司 | 优先级 | 研究价值分 | 信号 |")
    lines.append("| ---: | --- | --- | ---: | --- |")
    for i, (name, pri, sc, dtags, ctags) in enumerate(top):
        tags = dtags
        if ctags:
            tags += (" | " if tags else "") + ctags
        lines.append(f"| {i + 1} | {name} | {pri} | {sc} | {tags} |")
    lines.append("")


# ── helpers ────────────────────────────────────────────────────

def _count(df: pd.DataFrame, col: str, val: str) -> int:
    return int((df[col] == val).sum())


def _count_cond(df: pd.DataFrame, fn) -> int:
    return sum(1 for _, r in df.iterrows() if fn(r))


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{n / total * 100:.0f}%"


def _fmt(row: pd.Series, col: str) -> str:
    val = row.get(col)
    return f"{val:.1f}" if pd.notna(val) else "N/A"


def _fmt_yi(row: pd.Series, col: str) -> str:
    """Format as 亿 (divide by 1e8)."""
    val = row.get(col)
    return f"{val / 1e8:.2f}" if pd.notna(val) else "N/A"


def _cf_assess(ratio: float) -> str:
    if pd.isna(ratio):
        return "N/A"
    if ratio < 0:
        return "[ALERT] 现金流方向与利润相反"
    if ratio < 0.5:
        return "[WARN] 利润质量偏低"
    if ratio < 1.0:
        return "偏低"
    return "健康"
