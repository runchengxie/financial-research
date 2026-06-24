"""Enhanced screening: PE/PB percentiles, cash flow quality, margin crowding, divergence signals.

Reads from market-data-platform data assets and the hotspot CSV.
Output: enhanced-screening-report.md in the repo root.

Usage:
    cd ~/code/research-workspace/market-data-platform
    uv run --extra dev python ~/code/financial-research/scripts/enhanced_screen.py
"""

import pandas as pd
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# ── config ─────────────────────────────────────────────────────
DATA_ROOT = Path("/home/richard/data/market-data-platform/assets/tushare/a_share")
REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "company-hotspot-data.csv"
OUT_PATH = REPO_ROOT / "enhanced-screening-report.md"
REFERENCE_DATE = "2026-06-22"  # latest daily_basic
MARGIN_DATE = "20260623"       # latest margin_detail
FIN_DATE = "20260331"          # latest normalized fundamentals

# ── helpers ─────────────────────────────────────────────────────

def load_company_list():
    """Load 75 A-share companies from the hotspot CSV."""
    df = pd.read_csv(CSV_PATH)
    # Filter to A-share only (exclude pure HK stocks)
    mask = df["a_share_code"].notna() & (df["a_share_code"] != "")
    companies = df[mask].copy()
    companies["ts_code"] = companies["a_share_code"].str.replace(".SH", ".SH").str.replace(".SZ", ".SZ")
    return companies[["company", "ts_code", "priority"]].drop_duplicates("ts_code")


def compute_pe_pb_percentiles(companies):
    """Compute 3Y and 5Y PE_TTM and PB percentiles from daily_basic latest."""
    db_dir = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest/data"
    partitions = sorted(os.listdir(db_dir))

    cutoff_3y = "20230623"
    cutoff_5y = "20210623"

    target_codes = set(companies["ts_code"])

    pe_collect_3y = []
    pe_collect_5y = []
    pb_collect_3y = []
    pb_collect_5y = []

    for p_name in partitions:
        trade_date = p_name.replace("trade_date=", "")
        fp = db_dir / p_name / "part.parquet"
        df = pd.read_parquet(fp)
        df = df[df["ts_code"].isin(target_codes)]
        if df.empty:
            continue
        df = df[["ts_code", "pe_ttm", "pb"]].copy()
        df = df[(df["pe_ttm"] > 0) & (df["pb"] > 0)]  # skip negative/zero

        if trade_date >= cutoff_5y:
            pb_collect_5y.append(df[["ts_code", "pb"]])
            pe_collect_5y.append(df[["ts_code", "pe_ttm"]])
        if trade_date >= cutoff_3y:
            pb_collect_3y.append(df[["ts_code", "pb"]])
            pe_collect_3y.append(df[["ts_code", "pe_ttm"]])

    def calc_pctls(collected, col_name):
        if not collected:
            return pd.DataFrame()
        all_data = pd.concat(collected, ignore_index=True)
        result = all_data.groupby("ts_code")[col_name].agg(["mean", "min", "max"]).reset_index()
        # rank-based percentile across all observations per stock
        def _pctl(grp):
            vals = grp[col_name].dropna().values
            if len(vals) == 0:
                return pd.Series({"p25": None, "p50": None, "p75": None, "p90": None, "current_rank_pct": None,
                                  "n_obs": 0})
            return pd.Series({
                "p25": float(pd.Series(vals).quantile(0.25)),
                "p50": float(pd.Series(vals).quantile(0.50)),
                "p75": float(pd.Series(vals).quantile(0.75)),
                "p90": float(pd.Series(vals).quantile(0.90)),
                "n_obs": len(vals),
            })

        rank_pctls = all_data.groupby("ts_code").apply(_pctl).reset_index()
        # merge with the mean/min/max
        result = result.merge(rank_pctls, on="ts_code", how="left")
        return result

    pe_3y = calc_pctls(pe_collect_3y, "pe_ttm")
    pe_3y = pe_3y.rename(columns=lambda c: f"pe_3y_{c}" if c != "ts_code" else c)

    pe_5y = calc_pctls(pe_collect_5y, "pe_ttm")
    pe_5y = pe_5y.rename(columns=lambda c: f"pe_5y_{c}" if c != "ts_code" else c)

    pb_3y = calc_pctls(pb_collect_3y, "pb")
    pb_3y = pb_3y.rename(columns=lambda c: f"pb_3y_{c}" if c != "ts_code" else c)

    pb_5y = calc_pctls(pb_collect_5y, "pb")
    pb_5y = pb_5y.rename(columns=lambda c: f"pb_5y_{c}" if c != "ts_code" else c)

    return pe_3y, pe_5y, pb_3y, pb_5y


def compute_current_valuation(companies):
    """Get current (latest) PE_TTM, PB, circ_mv from daily_basic."""
    db_dir = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest/data"
    fp = db_dir / f"trade_date={REFERENCE_DATE.replace('-','')}" / "part.parquet"
    if not fp.exists():
        # find closest
        partitions = sorted(os.listdir(db_dir))
        closest = max(p for p in partitions if p <= f"trade_date={REFERENCE_DATE.replace('-','')}")
        fp = db_dir / closest / "part.parquet"

    target_codes = set(companies["ts_code"])
    df = pd.read_parquet(fp)
    df = df[df["ts_code"].isin(target_codes)]
    return df[["ts_code", "pe_ttm", "pb", "total_mv", "circ_mv"]].copy()


def compute_cashflow_quality(companies):
    """Compute operating cash flow / net income for latest quarter and TTM."""
    target_codes = set(companies["ts_code"])

    # income
    inc_path = DATA_ROOT / "normalized_fundamentals/a_share_top800_union_20150227_20260529_income/data/part.parquet"
    inc = pd.read_parquet(inc_path)
    inc = inc[inc["ts_code"].isin(target_codes)].copy()
    inc = inc[["ts_code", "end_date", "n_income_attr_p", "total_revenue", "report_type"]].copy()
    inc["end_date"] = inc["end_date"].astype(str)

    # cashflow
    cf_path = DATA_ROOT / "normalized_fundamentals/a_share_top800_union_20150227_20260529_cashflow/data/part.parquet"
    cf = pd.read_parquet(cf_path)
    cf = cf[cf["ts_code"].isin(target_codes)].copy()
    cf = cf[["ts_code", "end_date", "n_cashflow_act", "report_type"]].copy()
    cf["end_date"] = cf["end_date"].astype(str)

    # Merge on ts_code + end_date
    merged = inc.merge(cf, on=["ts_code", "end_date", "report_type"], how="inner")

    # Latest quarter
    latest = merged[merged["end_date"] == FIN_DATE].copy()
    latest = latest.dropna(subset=["n_income_attr_p", "n_cashflow_act"])
    latest = latest[latest["n_income_attr_p"] != 0]
    latest["cf_to_ni"] = latest["n_cashflow_act"] / latest["n_income_attr_p"]

    # Also get TTM (sum of last 4 quarters if Q1)
    # For Q1, TTM = Q1 + (Q4_prev - Q3_prev) + (Q2_prev - Q1_prev) + Q4_prevprev... 
    # Simplified: get annual reports
    annual = merged[merged["end_date"] == "20251231"].copy()
    annual = annual.dropna(subset=["n_income_attr_p", "n_cashflow_act"])
    annual = annual[annual["n_income_attr_p"] != 0]
    annual["cf_to_ni"] = annual["n_cashflow_act"] / annual["n_income_attr_p"]

    return latest[["ts_code", "n_income_attr_p", "n_cashflow_act", "cf_to_ni"]], \
           annual[["ts_code", "n_income_attr_p", "n_cashflow_act", "cf_to_ni", "end_date"]]


def compute_margin_crowding(companies):
    """Compute financing balance / float market cap ratio.

    rzye (margin_detail) is in 元.
    circ_mv (daily_basic) is in 万元.  Convert to 元 before computing ratio.
    """
    target_codes = set(companies["ts_code"])

    # margin - latest date
    md_dir = DATA_ROOT / "margin_detail/a_share_all_margin_detail_latest/data"
    dates = sorted(os.listdir(md_dir))
    target_date = f"trade_date={MARGIN_DATE}"
    if target_date not in dates:
        closest = max(d for d in dates if d <= target_date)
    else:
        closest = target_date
    fp = md_dir / closest / "part.parquet"
    margin = pd.read_parquet(fp)
    margin = margin[margin["ts_code"].isin(target_codes)]
    margin = margin[["ts_code", "rzye"]].copy()

    # daily_basic latest for circ_mv (in 万元)
    db_dir = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest/data"
    partitions = sorted(os.listdir(db_dir))
    ref_part = f"trade_date={REFERENCE_DATE.replace('-','')}"
    if ref_part not in partitions:
        ref_part = max(p for p in partitions if p <= ref_part)
    fp = db_dir / ref_part / "part.parquet"
    db = pd.read_parquet(fp)
    db = db[db["ts_code"].isin(target_codes)]
    db = db[["ts_code", "circ_mv"]].copy()

    merged = margin.merge(db, on="ts_code", how="inner")
    # circ_mv in daily_basic is 万元, rzye is 元 → convert circ_mv to 元
    merged["circ_mv_yuan"] = merged["circ_mv"] * 1e4
    merged["rz_to_float"] = merged["rzye"] / merged["circ_mv_yuan"]
    return merged[["ts_code", "rzye", "circ_mv_yuan", "rz_to_float"]]


def compute_pe_pb_divergence(report_df):
    """Classify PE/PB divergence patterns.

    Returns a Series of labels:
    - '多重扩张': both PE and PB > p90 → market pricing in prosperity
    - '利润压缩型': PE > p90 but PB normal → high PE from earnings trough
    - '资产重估型': PB > p90 but PE normal → assets re-rated before earnings
    - '估值健康': neither extreme
    - 'N/A': insufficient data
    """
    labels = []
    for _, r in report_df.iterrows():
        pe = r.get("pe_3y_level", "N/A")
        pb = r.get("pb_3y_level", "N/A")

        if pe == "N/A" or pb == "N/A":
            labels.append("N/A")
        elif pe == ">p90" and pb == ">p90":
            labels.append("多重扩张")
        elif pe == ">p90" and pb not in (">p90", "N/A"):
            labels.append("利润压缩型")
        elif pb == ">p90" and pe not in (">p90", "N/A"):
            labels.append("资产重估型")
        elif pe in ("p75-p90", ">p90") and pb in ("p75-p90", ">p90"):
            labels.append("偏高共识")
        else:
            labels.append("估值健康")

    return pd.Series(labels, index=report_df.index, name="pe_pb_pattern")


def compute_ar_inventory_trend(companies):
    """Compare Q1 2026 vs Q1 2025 accounts receivable and inventory.

    Returns DataFrame with ts_code, ar_yoy, inv_yoy, ar_to_rev, inv_to_rev
    and warning flags.
    """
    target_codes = set(companies["ts_code"])

    # balance sheet
    bs_path = DATA_ROOT / "normalized_fundamentals/a_share_top800_union_20150227_20260529_balancesheet/data/part.parquet"
    bs = pd.read_parquet(bs_path)
    bs = bs[bs["ts_code"].isin(target_codes)].copy()
    bs["end_date_str"] = bs["end_date"].astype(str)

    q1_25 = bs[bs["end_date_str"] == "20250331"][["ts_code", "accounts_receiv", "inventories"]].copy()
    q1_26 = bs[bs["end_date_str"] == "20260331"][["ts_code", "accounts_receiv", "inventories"]].copy()

    q1_25 = q1_25.rename(columns={"accounts_receiv": "ar_25", "inventories": "inv_25"})
    q1_26 = q1_26.rename(columns={"accounts_receiv": "ar_26", "inventories": "inv_26"})

    merged = q1_25.merge(q1_26, on="ts_code", how="inner")
    merged["ar_yoy"] = (merged["ar_26"] - merged["ar_25"]) / merged["ar_25"].abs().replace(0, float("nan"))
    merged["inv_yoy"] = (merged["inv_26"] - merged["inv_25"]) / merged["inv_25"].abs().replace(0, float("nan"))

    # Get Q1 revenue for ratios
    inc_path = DATA_ROOT / "normalized_fundamentals/a_share_top800_union_20150227_20260529_income/data/part.parquet"
    inc = pd.read_parquet(inc_path)
    inc = inc[inc["ts_code"].isin(target_codes)].copy()
    inc["end_date_str"] = inc["end_date"].astype(str)
    rev_q1 = inc[inc["end_date_str"] == "20260331"][["ts_code", "total_revenue"]].copy()
    rev_q1 = rev_q1.rename(columns={"total_revenue": "q1_revenue"})

    merged = merged.merge(rev_q1, on="ts_code", how="left")
    merged["ar_to_rev"] = merged["ar_26"] / merged["q1_revenue"]
    merged["inv_to_rev"] = merged["inv_26"] / merged["q1_revenue"]

    # Flag warnings
    warnings = []
    for _, r in merged.iterrows():
        tags = []
        ar_y = r["ar_yoy"]
        inv_y = r["inv_yoy"]
        if pd.notna(ar_y) and ar_y > 0.5:
            tags.append("应收暴增")
        elif pd.notna(ar_y) and ar_y > 0.3:
            tags.append("应收增长偏快")
        if pd.notna(inv_y) and inv_y > 0.5:
            tags.append("存货暴增")
        elif pd.notna(inv_y) and inv_y > 0.3:
            tags.append("存货增长偏快")
        if pd.notna(r.get("ar_to_rev")) and r["ar_to_rev"] > 1.0:
            tags.append("应收超单季收入")
        warnings.append(" | ".join(tags) if tags else "")

    merged["bs_warning"] = warnings
    return merged[["ts_code", "ar_yoy", "inv_yoy", "ar_to_rev", "inv_to_rev", "bs_warning"]]


def compute_divergence_signals(companies):
    """Generate divergence scores from existing hotspot data."""
    df = pd.read_csv(CSV_PATH)
    df = df[df["a_share_code"].notna() & (df["a_share_code"] != "")]

    signals = []
    for _, row in df.iterrows():
        code = row["a_share_code"]
        hot_days = int(row["hot_days_2026_ytd"]) if pd.notna(row["hot_days_2026_ytd"]) else 0
        limit_events = int(row["limit_events_2026"]) if pd.notna(row["limit_events_2026"]) else 0
        net_flow = float(row["mf_total_net_wan"]) if pd.notna(row["mf_total_net_wan"]) else 0
        hsgt_days = int(row["hsgt_top10_days"]) if pd.notna(row["hsgt_top10_days"]) else 0
        margin_delta = float(row["margin_delta_rz_wan"]) if pd.notna(row["margin_delta_rz_wan"]) else 0

        # Divergence types
        diverge_reasons = []

        # net_flow is in 万元 from CSV. Convert to 元 for thresholds.
        net_flow_yuan = net_flow * 1e4  # 万元 → 元
        net_flow_yi = net_flow / 1e4    # 万元 → 亿元

        # Hot + net outflow = big divergence
        if hot_days >= 10 and net_flow_yuan < -1e9:  # -10亿元
            diverge_reasons.append("高热度+大额净流出")
        elif hot_days >= 20 and net_flow_yuan < -5e8:
            diverge_reasons.append("高热度+净流出")

        # Northbound >> hot = quiet accumulation
        if hsgt_days >= 20 and hot_days <= 10:
            diverge_reasons.append("北向安静吸筹")
        elif hsgt_days >= 30 and hot_days <= 20:
            diverge_reasons.append("北向活跃远超热榜")

        # Hot >> northbound = domestic driven
        if hot_days >= 30 and hsgt_days <= 5:
            diverge_reasons.append("纯内资热度")

        # Margin growing but net outflow
        if margin_delta > 1e10 and net_flow_yuan < -1e9:
            diverge_reasons.append("杠杆增仓+资金流出")

        # High limit-up but low hot = event driven
        if limit_events >= 5 and hot_days <= 5:
            diverge_reasons.append("涨停频繁但未上榜")

        # Consensus signal: hot + northbound + margin all high
        consensus_reasons = []
        if hot_days >= 30 and hsgt_days >= 20:
            consensus_reasons.append("极度拥挤共识")

        signals.append({
            "ts_code": code,
            "hot_days": hot_days,
            "net_flow_yi": net_flow_yi,
            "hsgt_days": hsgt_days,
            "margin_delta_yi": margin_delta / 1e8,
            "limit_events": limit_events,
            "diverge_tags": " | ".join(diverge_reasons) if diverge_reasons else "",
            "consensus_tags": " | ".join(consensus_reasons) if consensus_reasons else "",
            "diverge_score": len(diverge_reasons),
        })

    return pd.DataFrame(signals)


def format_pct(val, current, label):
    """Compute where current sits in the distribution, return a label."""
    if pd.isna(current) or pd.isna(val):
        return "N/A"
    if val == 0:
        return "N/A"
    ratio = current / val
    if ratio >= 2:
        return "[ALERT] >p90"
    elif ratio >= 1.5:
        return "[WARN] >p75"
    elif ratio >= 1.0:
        return ">p50"
    else:
        return "<p50"


# ── main ────────────────────────────────────────────────────────

def main():
    print("[1/5] Loading companies...")
    companies = load_company_list()
    print(f"  {len(companies)} companies loaded")

    print("[2/5] Computing PE/PB percentiles (3Y + 5Y)...")
    pe_3y, pe_5y, pb_3y, pb_5y = compute_pe_pb_percentiles(companies)
    current_val = compute_current_valuation(companies)
    print(f"  PE 3Y: {len(pe_3y)} stocks, PE 5Y: {len(pe_5y)} stocks")
    print(f"  PB 3Y: {len(pb_3y)} stocks, PB 5Y: {len(pb_5y)} stocks")

    print("[3/5] Computing cash flow quality...")
    cf_q1, cf_annual = compute_cashflow_quality(companies)
    print(f"  Q1 (20260331): {len(cf_q1)} stocks matched")
    print(f"  Annual (20251231): {len(cf_annual)} stocks matched")

    print("[4/5] Computing margin crowding...")
    margin = compute_margin_crowding(companies)
    print(f"  Margin: {len(margin)} stocks matched")

    print("[5/5] Computing divergence signals...")
    divergences = compute_divergence_signals(companies)

    print("[+] Computing PE/PB divergence patterns...")
    # Need to build intermediate report to compute PE/PB levels first
    # then classify, then merge

    print("[+] Computing AR/Inventory trends...")
    ar_inv = compute_ar_inventory_trend(companies)
    print(f"  AR/Inventory: {len(ar_inv)} stocks matched")

    # ── merge everything ────────────────────────────────────────
    report = companies.copy()
    report = report.merge(current_val, on="ts_code", how="left")
    report = report.merge(pe_3y, on="ts_code", how="left")
    report = report.merge(pe_5y, on="ts_code", how="left")
    report = report.merge(pb_3y, on="ts_code", how="left")
    report = report.merge(pb_5y, on="ts_code", how="left")

    # rename Q1 cf columns
    cf_q1_renamed = cf_q1.rename(columns={
        "n_income_attr_p": "q1_net_income",
        "n_cashflow_act": "q1_oper_cf",
        "cf_to_ni": "q1_cf_to_ni",
    })
    report = report.merge(cf_q1_renamed, on="ts_code", how="left")

    cf_annual_renamed = cf_annual.rename(columns={
        "n_income_attr_p": "fy_net_income",
        "n_cashflow_act": "fy_oper_cf",
        "cf_to_ni": "fy_cf_to_ni",
    })
    report = report.merge(cf_annual_renamed, on="ts_code", how="left")

    report = report.merge(margin, on="ts_code", how="left")
    report = report.merge(divergences, on="ts_code", how="left")

    # ── compute percentile labels ───────────────────────────────
    for _, row in report.iterrows():
        # PE 3Y pctl
        if pd.notna(row.get("pe_ttm")) and pd.notna(row.get("pe_3y_p50")):
            p90 = row.get("pe_3y_p90")
            p75 = row.get("pe_3y_p75")
            p50 = row.get("pe_3y_p50")
            cur = row["pe_ttm"]
            if pd.notna(p90) and cur >= p90:
                report.at[_, "pe_3y_level"] = ">p90"
            elif pd.notna(p75) and cur >= p75:
                report.at[_, "pe_3y_level"] = "p75-p90"
            elif cur >= p50:
                report.at[_, "pe_3y_level"] = "p50-p75"
            else:
                report.at[_, "pe_3y_level"] = "<p50"
        else:
            report.at[_, "pe_3y_level"] = "N/A"

        # PB 3Y pctl
        if pd.notna(row.get("pb")) and pd.notna(row.get("pb_3y_p50")):
            p90 = row.get("pb_3y_p90")
            p75 = row.get("pb_3y_p75")
            p50 = row.get("pb_3y_p50")
            cur = row["pb"]
            if pd.notna(p90) and cur >= p90:
                report.at[_, "pb_3y_level"] = ">p90"
            elif pd.notna(p75) and cur >= p75:
                report.at[_, "pb_3y_level"] = "p75-p90"
            elif cur >= p50:
                report.at[_, "pb_3y_level"] = "p50-p75"
            else:
                report.at[_, "pb_3y_level"] = "<p50"
        else:
            report.at[_, "pb_3y_level"] = "N/A"

    # ── PE/PB divergence, AR/Inventory ───────────────────────────
    report["pe_pb_pattern"] = compute_pe_pb_divergence(report)
    report = report.merge(ar_inv, on="ts_code", how="left")

    # ── generate markdown ───────────────────────────────────────
    lines = []
    lines.append("# 增强初筛报告")
    lines.append(f"")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"数据截止：每日估值 {REFERENCE_DATE}，融资融券 {MARGIN_DATE}，财务 {FIN_DATE}")
    lines.append(f"")
    lines.append(f"## 读法")
    lines.append(f"")
    lines.append(f"- PE/PB 分位基于最近 3 年历史，`>p90` 表示当前估值处于近 3 年最高的 10% 区间。")
    lines.append(f"- 现金流质量 = 经营活动现金流净额 / 归母净利润。Q1 为单季，FY 为全年。比率持续 < 0.5 需警惕利润质量。")
    lines.append(f"- 融资拥挤度 = 融资余额 / 流通市值。> 3% 为较高杠杆，> 5% 为拥挤。")
    lines.append(f"- 背离标签表示市场行为存在矛盾（如热度高但资金流出），共识标签表示多维度信号一致。")
    lines.append(f"")
    lines.append(f"## 摘要统计")
    lines.append(f"")

    # Summary stats
    n_total = len(report)
    n_pe_high = len(report[report["pe_3y_level"] == ">p90"])
    n_pb_high = len(report[report["pb_3y_level"] == ">p90"])
    n_cf_warn = len(report[(report["q1_cf_to_ni"].notna()) & (report["q1_cf_to_ni"] < 0)])
    n_margin_high = len(report[(report["rz_to_float"].notna()) & (report["rz_to_float"] > 0.03)])
    n_diverge = len(report[report["diverge_score"] > 0])

    lines.append(f"| 指标 | 数量 | 占比 |")
    lines.append(f"| --- | ---: | ---: |")
    lines.append(f"| 覆盖 A 股 | {n_total} | 100% |")
    lines.append(f"| PE 3Y > p90 | {n_pe_high} | {n_pe_high/n_total*100:.0f}% |")
    lines.append(f"| PB 3Y > p90 | {n_pb_high} | {n_pb_high/n_total*100:.0f}% |")
    lines.append(f"| Q1 经营现金流为负 | {n_cf_warn} | {n_cf_warn/(n_total or 1)*100:.0f}% |")
    lines.append(f"| 融资占流通市值 > 3% | {n_margin_high} | {n_margin_high/(n_total or 1)*100:.0f}% |")
    lines.append(f"| 存在背离信号 | {n_diverge} | {n_diverge/(n_total or 1)*100:.0f}% |")
    lines.append(f"")

    # ── Section 1: Valuation alerts ─────────────────────────────
    lines.append(f"## 1. 估值预警（PE/PB 分位）")
    lines.append(f"")
    pe_alert = report[report["pe_3y_level"].isin([">p90", "p75-p90"])].sort_values("pe_ttm", ascending=False)
    if not pe_alert.empty:
        lines.append(f"### PE TTM 处于 3 年高位（top 25%）")
        lines.append(f"")
        lines.append(f"| 公司 | 优先级 | PE TTM | PE 3Y p50 | PE 3Y p75 | PE 3Y p90 | 分位 | PB 3Y 分位 |")
        lines.append(f"| --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
        for _, r in pe_alert.iterrows():
            pe = f"{r['pe_ttm']:.1f}" if pd.notna(r.get("pe_ttm")) else "N/A"
            p50 = f"{r.get('pe_3y_p50', 0):.1f}" if pd.notna(r.get("pe_3y_p50")) else "N/A"
            p75 = f"{r.get('pe_3y_p75', 0):.1f}" if pd.notna(r.get("pe_3y_p75")) else "N/A"
            p90 = f"{r.get('pe_3y_p90', 0):.1f}" if pd.notna(r.get("pe_3y_p90")) else "N/A"
            lines.append(f"| {r['company']} | {r['priority']} | {pe} | {p50} | {p75} | {p90} | {r.get('pe_3y_level','')} | {r.get('pb_3y_level','')} |")
        lines.append(f"")

    pb_alert = report[report["pb_3y_level"] == ">p90"]
    if not pb_alert.empty:
        lines.append(f"### PB 处于 3 年极高位（> p90）")
        lines.append(f"")
        lines.append(f"| 公司 | 优先级 | PB | PB 3Y p50 | PB 3Y p90 | PE 3Y 分位 |")
        lines.append(f"| --- | --- | ---: | ---: | ---: | --- |")
        for _, r in pb_alert.sort_values("pb", ascending=False).iterrows():
            pb = f"{r['pb']:.1f}" if pd.notna(r.get("pb")) else "N/A"
            p50 = f"{r.get('pb_3y_p50', 0):.1f}" if pd.notna(r.get("pb_3y_p50")) else "N/A"
            p90 = f"{r.get('pb_3y_p90', 0):.1f}" if pd.notna(r.get("pb_3y_p90")) else "N/A"
            lines.append(f"| {r['company']} | {r['priority']} | {pb} | {p50} | {p90} | {r.get('pe_3y_level','')} |")
        lines.append(f"")

    # ── Section 1b: PE/PB divergence ─────────────────────────────
    lines.append(f"### PE/PB 背离分析")
    lines.append(f"")
    lines.append(f"PE 与 PB 分位不一致时，估值信号的含义不同：")
    lines.append(f"")
    lines.append(f"- **多重扩张**（PE 和 PB 均 > p90）：市场定价繁荣，估值容错空间极小。")
    lines.append(f"- **利润压缩型**（PE > p90 但 PB 正常）：高 PE 来自利润处于周期底部，利润恢复后 PE 自然回落，可能是低估信号。")
    lines.append(f"- **资产重估型**（PB > p90 但 PE 正常）：资产已被重估但利润尚未跟上，需验证利润能否兑现。")
    lines.append(f"")

    patterns = report[report["pe_pb_pattern"].notna()]
    for pattern_name, desc in [
        ("多重扩张", "PE 和 PB 均处于 3 年极高位"),
        ("利润压缩型", "PE 极高位但 PB 未到极端"),
        ("资产重估型", "PB 极高位但 PE 未到极端"),
    ]:
        subset = patterns[patterns["pe_pb_pattern"] == pattern_name].sort_values("pe_ttm", ascending=False)
        if not subset.empty:
            lines.append(f"#### {pattern_name}（{desc}）")
            lines.append(f"")
            lines.append(f"| 公司 | 优先级 | PE TTM | PE 3Y 分位 | PB | PB 3Y 分位 |")
            lines.append(f"| --- | --- | ---: | --- | ---: | --- |")
            for _, r in subset.iterrows():
                pe = f"{r['pe_ttm']:.1f}" if pd.notna(r.get("pe_ttm")) else "N/A"
                pb = f"{r['pb']:.1f}" if pd.notna(r.get("pb")) else "N/A"
                lines.append(f"| {r['company']} | {r['priority']} | {pe} | {r.get('pe_3y_level','')} | {pb} | {r.get('pb_3y_level','')} |")
            lines.append(f"")

    # ── Section 2: Cash flow quality ────────────────────────────
    lines.append(f"## 2. 现金流质量")
    lines.append(f"")

    # Q1
    cf_q1_data = report[report["q1_cf_to_ni"].notna()].copy()
    lines.append(f"### Q1 2026 经营现金流 / 净利润")
    lines.append(f"")
    lines.append(f"注：Q1 单季现金流季节性波动大，负值不一定是结构性恶化，但值得核对。")
    lines.append(f"")
    lines.append(f"| 公司 | 优先级 | Q1 净利润(亿) | Q1 经营CF(亿) | CF/NI | 评估 |")
    lines.append(f"| --- | --- | ---: | ---: | ---: | --- |")
    for _, r in cf_q1_data.sort_values("q1_cf_to_ni").iterrows():
        ni = f"{r['q1_net_income']/1e8:.2f}" if pd.notna(r.get("q1_net_income")) else "N/A"
        cf = f"{r['q1_oper_cf']/1e8:.2f}" if pd.notna(r.get("q1_oper_cf")) else "N/A"
        ratio = r["q1_cf_to_ni"]
        ratio_str = f"{ratio:.2f}"
        if pd.isna(ratio):
            ratio_str = "N/A"
            assessment = "N/A"
        elif ratio < 0:
            assessment = "[ALERT] 现金流方向与利润相反"
        elif ratio < 0.5:
            assessment = "[WARN] 利润质量偏低"
        elif ratio < 1.0:
            assessment = "偏低"
        else:
            assessment = "健康"
        lines.append(f"| {r['company']} | {r['priority']} | {ni} | {cf} | {ratio_str} | {assessment} |")
    lines.append(f"")

    # FY2025
    cf_fy_data = report[report["fy_cf_to_ni"].notna()].copy()
    if not cf_fy_data.empty:
        lines.append(f"### FY2025 全年经营现金流 / 净利润")
        lines.append(f"")
        lines.append(f"| 公司 | 优先级 | FY 净利润(亿) | FY 经营CF(亿) | CF/NI | 评估 |")
        lines.append(f"| --- | --- | ---: | ---: | ---: | --- |")
        for _, r in cf_fy_data.sort_values("fy_cf_to_ni").iterrows():
            ni = f"{r['fy_net_income']/1e8:.2f}" if pd.notna(r.get("fy_net_income")) else "N/A"
            cf = f"{r['fy_oper_cf']/1e8:.2f}" if pd.notna(r.get("fy_oper_cf")) else "N/A"
            ratio = r["fy_cf_to_ni"]
            ratio_str = f"{ratio:.2f}"
            if pd.isna(ratio):
                ratio_str = "N/A"
                assessment = "N/A"
            elif ratio < 0:
                assessment = "[ALERT] 全年利润无现金流支持"
            elif ratio < 0.5:
                assessment = "[WARN] 利润质量偏低"
            elif ratio < 1.0:
                assessment = "偏低"
            else:
                assessment = "健康"
            lines.append(f"| {r['company']} | {r['priority']} | {ni} | {cf} | {ratio_str} | {assessment} |")
        lines.append(f"")

    # ── Section 2b: AR/Inventory trends ──────────────────────────
    lines.append(f"## 2b. 应收与存货趋势（Q1 2026 vs Q1 2025）")
    lines.append(f"")
    lines.append(f"注：应收/存货同比超过 50% 标为「暴增」，超过 30% 标为「偏快」。应收/单季收入 > 1.0 标为「应收超单季收入」。")
    lines.append(f"")

    ar_inv_data = report[report["ar_yoy"].notna()].sort_values("ar_yoy", ascending=False)
    if not ar_inv_data.empty:
        lines.append(f"| 公司 | 优先级 | 应收同比 | 存货同比 | 应收/单季收入 | 存货/单季收入 | 预警 |")
        lines.append(f"| --- | --- | ---: | ---: | ---: | ---: | --- |")
        for _, r in ar_inv_data.iterrows():
            ar_y = f"{r['ar_yoy']*100:.0f}%" if pd.notna(r.get("ar_yoy")) else "N/A"
            inv_y = f"{r['inv_yoy']*100:.0f}%" if pd.notna(r.get("inv_yoy")) else "N/A"
            ar_r = f"{r.get('ar_to_rev', 0):.2f}" if pd.notna(r.get("ar_to_rev")) else "N/A"
            inv_r = f"{r.get('inv_to_rev', 0):.2f}" if pd.notna(r.get("inv_to_rev")) else "N/A"
            warn = r.get("bs_warning", "")
            lines.append(f"| {r['company']} | {r['priority']} | {ar_y} | {inv_y} | {ar_r} | {inv_r} | {warn} |")
        lines.append(f"")

    # ── Section 3: Margin crowding ──────────────────────────────
    lines.append(f"## 3. 融资拥挤度")
    lines.append(f"")
    margin_data = report[report["rz_to_float"].notna()].sort_values("rz_to_float", ascending=False)
    lines.append(f"| 公司 | 优先级 | 融资余额(亿) | 流通市值(亿) | 融资/流通市值 | 拥挤度 |")
    lines.append(f"| --- | --- | ---: | ---: | ---: | --- |")
    for _, r in margin_data.iterrows():
        rz = f"{r['rzye']/1e8:.1f}" if pd.notna(r.get("rzye")) else "N/A"
        mv = f"{r.get('circ_mv_yuan', 0)/1e8:.0f}" if pd.notna(r.get("circ_mv_yuan")) else "N/A"
        ratio = r["rz_to_float"]
        ratio_str = f"{ratio*100:.1f}%"
        if ratio > 0.05:
            crowd = "[ALERT] 高度拥挤"
        elif ratio > 0.03:
            crowd = "[WARN] 较高杠杆"
        else:
            crowd = "正常"
        lines.append(f"| {r['company']} | {r['priority']} | {rz} | {mv} | {ratio_str} | {crowd} |")
    lines.append(f"")

    # ── Section 4: Divergence signals ───────────────────────────
    lines.append(f"## 4. 背离与共识信号")
    lines.append(f"")

    # Divergences
    diverge_data = report[report["diverge_score"] > 0].sort_values("diverge_score", ascending=False)
    if not diverge_data.empty:
        lines.append(f"### 存在背离信号的公司（研究价值较高）")
        lines.append(f"")
        lines.append(f"背离信号提示市场行为存在矛盾，往往是预期差的来源。")
        lines.append(f"")
        lines.append(f"| 公司 | 优先级 | 背离标签 | 热榜天 | 净流入(亿) | 北向天 | 融资变化(亿) |")
        lines.append(f"| --- | --- | --- | ---: | ---: | ---: | ---: |")
        for _, r in diverge_data.iterrows():
            nf = f"{r.get('net_flow_yi', 0):.1f}"
            md = f"{r.get('margin_delta_yi', 0):.1f}"
            lines.append(f"| {r['company']} | {r['priority']} | {r['diverge_tags']} | {r['hot_days']} | {nf} | {r['hsgt_days']} | {md} |")
        lines.append(f"")

    # Consensus (crowded)
    consensus_data = report[report["consensus_tags"].notna() & (report["consensus_tags"] != "")]
    if not consensus_data.empty:
        lines.append(f"### 极度拥挤共识（多维度信号一致看多）")
        lines.append(f"")
        lines.append(f"共识拥挤不等于看空，但意味着预期差空间被压缩，需做估值反推。")
        lines.append(f"")
        lines.append(f"| 公司 | 优先级 | 共识标签 | 热榜天 | 北向天 | 融资变化(亿) | PE 3Y 分位 |")
        lines.append(f"| --- | --- | --- | ---: | ---: | ---: | --- |")
        for _, r in consensus_data.iterrows():
            md = f"{r.get('margin_delta_yi', 0):.1f}"
            lines.append(f"| {r['company']} | {r['priority']} | {r['consensus_tags']} | {r['hot_days']} | {r['hsgt_days']} | {md} | {r.get('pe_3y_level','')} |")
        lines.append(f"")

    # ── Section 5: Research value ranking ───────────────────────
    lines.append(f"## 5. 研究价值排序（背离信号加权）")
    lines.append(f"")
    lines.append(f"排序逻辑：背离信号 > 共识信号。得分 = 背离分 × 3 + 共识分 + (PE/PB 高位分) + (现金流预警分)")
    lines.append(f"")

    # Calculate research value score
    scores = []
    for _, r in report.iterrows():
        score = 0
        # Divergence (high weight)
        diverge = r.get("diverge_score", 0) or 0
        score += diverge * 3

        # Consensus (lower weight)
        if r.get("consensus_tags") and r["consensus_tags"] != "":
            score += 1

        # PE/PB extreme
        if r.get("pe_3y_level") == ">p90":
            score += 1
        if r.get("pb_3y_level") == ">p90":
            score += 1

        # Cash flow warning
        if pd.notna(r.get("q1_cf_to_ni")) and r["q1_cf_to_ni"] < 0:
            score += 1

        # Margin crowding
        if pd.notna(r.get("rz_to_float")) and r["rz_to_float"] > 0.05:
            score += 1

        scores.append({
            "ts_code": r["ts_code"],
            "company": r["company"],
            "priority": r["priority"],
            "score": score,
            "diverge_tags": r.get("diverge_tags", ""),
            "consensus_tags": r.get("consensus_tags", ""),
        })

    score_df = pd.DataFrame(scores).sort_values("score", ascending=False)

    lines.append(f"| 排名 | 公司 | 优先级 | 研究价值分 | 信号 |")
    lines.append(f"| ---: | --- | --- | ---: | --- |")
    for i, (_, r) in enumerate(score_df.head(25).iterrows()):
        tags = r["diverge_tags"]
        if r["consensus_tags"]:
            tags += (" | " if tags else "") + r["consensus_tags"]
        lines.append(f"| {i+1} | {r['company']} | {r['priority']} | {r['score']} | {tags} |")
    lines.append(f"")

    # ── write output ────────────────────────────────────────────
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[DONE] Report written to {OUT_PATH}")
    print(f"  Total companies: {n_total}")
    print(f"  PE alerts: {n_pe_high}, PB alerts: {n_pb_high}")
    print(f"  CF warnings: {n_cf_warn}, Margin high: {n_margin_high}")
    print(f"  Divergence signals: {n_diverge}")


if __name__ == "__main__":
    main()
