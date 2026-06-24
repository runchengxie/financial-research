"""Data loading and computation functions for enhanced screening.

All functions accept a companies DataFrame (ts_code, priority) and return
computed DataFrames.  No markdown generation or side effects.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── config ────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = REPO_ROOT / "data/company-hotspot-data.csv"

DATA_ROOT = Path(
    os.environ.get(
        "FIN_RESEARCH_DATA_ROOT",
        os.path.expanduser("~/data/market-data-platform"),
    )
) / "assets/tushare/a_share"

# Date limits are auto-detected from available data on first call.
_cache: dict[str, str] = {}


def _latest_partition_date(asset_dir: Path) -> Optional[str]:
    """Return the latest partition date string from a hive-partitioned directory."""
    if not asset_dir.exists():
        return None
    data_dir = asset_dir / "data"
    if not data_dir.exists():
        return None
    partitions = sorted(
        p.name.replace("trade_date=", "")
        for p in data_dir.iterdir()
        if p.is_dir() and p.name.startswith("trade_date=")
    )
    return partitions[-1] if partitions else None


def _find_partition(asset_dir: Path, target_date: str) -> Path:
    """Return path to the partition file for target_date or the nearest earlier date."""
    data_dir = asset_dir / "data"
    partitions = sorted(
        p.name for p in data_dir.iterdir()
        if p.is_dir() and p.name.startswith("trade_date=")
    )
    target_key = f"trade_date={target_date}"
    if target_key in partitions:
        return data_dir / target_key / "part.parquet"
    # Find nearest earlier
    key = target_key
    while key not in partitions:
        earlier = [k for k in partitions if k <= key]
        if not earlier:
            raise FileNotFoundError(f"No partition found <= {target_key} in {data_dir}")
        key = earlier[-1]
    return data_dir / key / "part.parquet"


def _load_parquet_safe(path: Path) -> Optional[pd.DataFrame]:
    """Load parquet with basic error handling. Returns None on failure."""
    try:
        return pd.read_parquet(path)
    except Exception:
        logger.warning("Failed to read %s, skipping", path, exc_info=True)
        return None


# ── reference date helpers ─────────────────────────────────────────

def get_reference_date() -> str:
    """Latest available date in daily_basic (YYYY-MM-DD)."""
    if "ref_date" not in _cache:
        asset = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest"
        d = _latest_partition_date(asset)
        if d and len(d) == 8:
            _cache["ref_date"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        else:
            _cache["ref_date"] = "2026-06-22"  # fallback
    return _cache["ref_date"]


def get_margin_date() -> str:
    """Latest available date in margin_detail (YYYYMMDD)."""
    if "margin_date" not in _cache:
        asset = DATA_ROOT / "margin_detail/a_share_all_margin_detail_latest"
        d = _latest_partition_date(asset)
        _cache["margin_date"] = d or "20260623"
    return _cache["margin_date"]


def get_fin_date() -> str:
    """Latest quarter-end date in normalized_fundamentals income (YYYYMMDD)."""
    if "fin_date" not in _cache:
        inc_path = (
            DATA_ROOT
            / "normalized_fundamentals/a_share_top800_union_20150227_20260529_income/data/part.parquet"
        )
        try:
            inc = pd.read_parquet(inc_path)
            inc["end_date"] = pd.to_datetime(inc["end_date"])
            _cache["fin_date"] = inc["end_date"].max().strftime("%Y%m%d")
        except Exception:
            _cache["fin_date"] = "20260331"
    return _cache["fin_date"]


# ── data loading ───────────────────────────────────────────────────

def load_company_list() -> pd.DataFrame:
    """Load 75 A-share companies from the hotspot CSV.

    Returns DataFrame with columns: company, ts_code, priority.
    """
    df = pd.read_csv(CSV_PATH)
    mask = df["a_share_code"].notna() & (df["a_share_code"] != "")
    companies = df[mask][["company", "a_share_code", "priority"]].copy()
    companies["ts_code"] = companies["a_share_code"]
    return companies[["company", "ts_code", "priority"]].drop_duplicates("ts_code").reset_index(drop=True)


# ── PE / PB percentiles ────────────────────────────────────────────

def compute_pe_pb_percentiles(companies: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute 3-year PE_TTM and PB percentiles for each company.

    Returns (pe_3y_df, pb_3y_df).
    """
    asset_dir = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest"
    ref_date = get_reference_date()
    cutoff = f"{int(ref_date[:4]) - 3}{ref_date[4:]}".replace("-", "")

    target_codes = set(companies["ts_code"])

    pe_collect: list[pd.DataFrame] = []
    pb_collect: list[pd.DataFrame] = []

    data_dir = asset_dir / "data"
    if not data_dir.exists():
        logger.warning("daily_basic data dir not found: %s", data_dir)
        return pd.DataFrame(), pd.DataFrame()

    for p_name in sorted(d.name for d in data_dir.iterdir() if d.is_dir()):
        trade_date = p_name.replace("trade_date=", "")
        if trade_date < cutoff:
            continue
        fp = data_dir / p_name / "part.parquet"
        df = _load_parquet_safe(fp)
        if df is None:
            continue
        df = df[df["ts_code"].isin(target_codes)]
        if df.empty:
            continue
        df = df[["ts_code", "pe_ttm", "pb"]].copy()
        df = df[(df["pe_ttm"] > 0) & (df["pb"] > 0)]

        pe_collect.append(df[["ts_code", "pe_ttm"]])
        pb_collect.append(df[["ts_code", "pb"]])

    def _calc_pctls(collected: list[pd.DataFrame], col_name: str) -> pd.DataFrame:
        if not collected:
            return pd.DataFrame()
        all_data = pd.concat(collected, ignore_index=True)

        def _pctl(grp: pd.DataFrame) -> pd.Series:
            vals = grp[col_name].dropna().values
            if len(vals) == 0:
                return pd.Series({"p25": None, "p50": None, "p75": None, "p90": None, "n_obs": 0})
            return pd.Series({
                "p25": float(pd.Series(vals).quantile(0.25)),
                "p50": float(pd.Series(vals).quantile(0.50)),
                "p75": float(pd.Series(vals).quantile(0.75)),
                "p90": float(pd.Series(vals).quantile(0.90)),
                "n_obs": len(vals),
            })

        stats = all_data.groupby("ts_code")[col_name].agg(["mean", "min", "max"]).reset_index()
        pctls = all_data.groupby("ts_code", group_keys=False).apply(_pctl).reset_index()
        return stats.merge(pctls, on="ts_code", how="left")

    pe_3y = _calc_pctls(pe_collect, "pe_ttm")
    pe_3y = pe_3y.rename(columns=lambda c: f"pe_3y_{c}" if c != "ts_code" else c)

    pb_3y = _calc_pctls(pb_collect, "pb")
    pb_3y = pb_3y.rename(columns=lambda c: f"pb_3y_{c}" if c != "ts_code" else c)

    return pe_3y, pb_3y


# ── current valuation ──────────────────────────────────────────────

def compute_current_valuation(companies: pd.DataFrame) -> pd.DataFrame:
    """Get latest PE_TTM, PB, total_mv, circ_mv from daily_basic."""
    asset_dir = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest"
    ref_date = get_reference_date().replace("-", "")
    fp = _find_partition(asset_dir, ref_date)

    target_codes = set(companies["ts_code"])
    df = _load_parquet_safe(fp)
    if df is None:
        return pd.DataFrame(columns=["ts_code", "pe_ttm", "pb", "total_mv", "circ_mv"])
    df = df[df["ts_code"].isin(target_codes)]
    return df[["ts_code", "pe_ttm", "pb", "total_mv", "circ_mv"]].copy()


# ── cash flow quality ──────────────────────────────────────────────

def compute_cashflow_quality(companies: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute operating CF / net income for Q1 and FY.

    Returns (q1_df, annual_df).
    """
    fin_date = get_fin_date()
    target_codes = set(companies["ts_code"])

    base = DATA_ROOT / "normalized_fundamentals"

    inc_path = base / "a_share_top800_union_20150227_20260529_income/data/part.parquet"
    inc = _load_parquet_safe(inc_path)
    if inc is None:
        return pd.DataFrame(), pd.DataFrame()
    inc = inc[inc["ts_code"].isin(target_codes)][["ts_code", "end_date", "n_income_attr_p", "total_revenue", "report_type"]].copy()
    inc["end_date"] = inc["end_date"].astype(str)

    cf_path = base / "a_share_top800_union_20150227_20260529_cashflow/data/part.parquet"
    cf = _load_parquet_safe(cf_path)
    if cf is None:
        return pd.DataFrame(), pd.DataFrame()
    cf = cf[cf["ts_code"].isin(target_codes)][["ts_code", "end_date", "n_cashflow_act", "report_type"]].copy()
    cf["end_date"] = cf["end_date"].astype(str)

    merged = inc.merge(cf, on=["ts_code", "end_date", "report_type"], how="inner")

    latest = merged[merged["end_date"] == fin_date].copy()
    latest = latest.dropna(subset=["n_income_attr_p", "n_cashflow_act"])
    latest = latest[latest["n_income_attr_p"] != 0]
    latest["cf_to_ni"] = latest["n_cashflow_act"] / latest["n_income_attr_p"]

    annual = merged[merged["end_date"] == f"{int(fin_date[:4]) - 1}1231"].copy()
    if annual.empty:
        annual = merged[merged["end_date"] == "20251231"].copy()
    annual = annual.dropna(subset=["n_income_attr_p", "n_cashflow_act"])
    annual = annual[annual["n_income_attr_p"] != 0]
    annual["cf_to_ni"] = annual["n_cashflow_act"] / annual["n_income_attr_p"]

    return (
        latest[["ts_code", "n_income_attr_p", "n_cashflow_act", "cf_to_ni"]],
        annual[["ts_code", "n_income_attr_p", "n_cashflow_act", "cf_to_ni", "end_date"]],
    )


# ── margin crowding ────────────────────────────────────────────────

def compute_margin_crowding(companies: pd.DataFrame) -> pd.DataFrame:
    """Compute financing balance / float market cap ratio.

    rzye (margin_detail) is in 元.  circ_mv (daily_basic) is in 万元.
    """
    target_codes = set(companies["ts_code"])

    # margin
    md_asset = DATA_ROOT / "margin_detail/a_share_all_margin_detail_latest"
    md_date = get_margin_date()
    fp = _find_partition(md_asset, md_date)
    margin = _load_parquet_safe(fp)
    if margin is None:
        return pd.DataFrame()

    margin = margin[margin["ts_code"].isin(target_codes)][["ts_code", "rzye"]].copy()

    # daily_basic for circ_mv
    db_asset = DATA_ROOT / "daily_basic/a_share_all_daily_basic_latest"
    ref_date = get_reference_date().replace("-", "")
    fp = _find_partition(db_asset, ref_date)
    db = _load_parquet_safe(fp)
    if db is None:
        return pd.DataFrame()

    db = db[db["ts_code"].isin(target_codes)][["ts_code", "circ_mv"]].copy()

    merged = margin.merge(db, on="ts_code", how="inner")
    if merged.empty:
        return pd.DataFrame()

    merged["circ_mv_yuan"] = merged["circ_mv"] * 1e4
    merged["rz_to_float"] = merged["rzye"] / merged["circ_mv_yuan"]
    return merged[["ts_code", "rzye", "circ_mv_yuan", "rz_to_float"]]


# ── PE/PB divergence ───────────────────────────────────────────────

def compute_pe_pb_divergence(report_df: pd.DataFrame) -> pd.Series:
    """Classify PE/PB divergence patterns.

    Labels:
      - 多重扩张:  PE and PB both > p90
      - 利润压缩型: PE > p90 but PB not extreme
      - 资产重估型: PB > p90 but PE not extreme
      - 估值健康:   neither extreme
      - N/A:        insufficient data
    """
    def _classify(row: pd.Series) -> str:
        pe = row.get("pe_3y_level", "N/A")
        pb = row.get("pb_3y_level", "N/A")
        if pe == "N/A" or pb == "N/A":
            return "N/A"
        if pe == ">p90" and pb == ">p90":
            return "多重扩张"
        if pe == ">p90":
            return "利润压缩型"
        if pb == ">p90":
            return "资产重估型"
        if pe in ("p75-p90", ">p90") and pb in ("p75-p90", ">p90"):
            return "偏高共识"
        return "估值健康"

    return report_df.apply(_classify, axis=1)


# ── AR / inventory trends ──────────────────────────────────────────

def compute_ar_inventory_trend(companies: pd.DataFrame) -> pd.DataFrame:
    """Compare Q1 current vs Q1 prior year accounts receivable and inventory.

    Returns DataFrame with ts_code, ar_yoy, inv_yoy, ar_to_rev, inv_to_rev, bs_warning.
    """
    fin_date = get_fin_date()
    prior_date = f"{int(fin_date[:4]) - 1}0331"
    target_codes = set(companies["ts_code"])

    base = DATA_ROOT / "normalized_fundamentals"

    # balance sheet
    bs_path = base / "a_share_top800_union_20150227_20260529_balancesheet/data/part.parquet"
    bs = _load_parquet_safe(bs_path)
    if bs is None:
        return pd.DataFrame()
    bs = bs[bs["ts_code"].isin(target_codes)].copy()
    bs["end_date_str"] = bs["end_date"].astype(str)

    q1_p = bs[bs["end_date_str"] == prior_date][["ts_code", "accounts_receiv", "inventories"]].copy()
    q1_c = bs[bs["end_date_str"] == fin_date][["ts_code", "accounts_receiv", "inventories"]].copy()

    q1_p = q1_p.rename(columns={"accounts_receiv": "ar_25", "inventories": "inv_25"})
    q1_c = q1_c.rename(columns={"accounts_receiv": "ar_26", "inventories": "inv_26"})

    merged = q1_p.merge(q1_c, on="ts_code", how="inner")
    if merged.empty:
        return pd.DataFrame()

    merged["ar_yoy"] = (merged["ar_26"] - merged["ar_25"]) / merged["ar_25"].abs().replace(0, float("nan"))
    merged["inv_yoy"] = (merged["inv_26"] - merged["inv_25"]) / merged["inv_25"].abs().replace(0, float("nan"))

    # Q1 revenue for ratios
    inc_path = base / "a_share_top800_union_20150227_20260529_income/data/part.parquet"
    inc = _load_parquet_safe(inc_path)
    if inc is not None:
        inc = inc[inc["ts_code"].isin(target_codes)].copy()
        inc["end_date_str"] = inc["end_date"].astype(str)
        rev = inc[inc["end_date_str"] == fin_date][["ts_code", "total_revenue"]].copy()
        rev = rev.rename(columns={"total_revenue": "q1_revenue"})
        merged = merged.merge(rev, on="ts_code", how="left")
        merged["ar_to_rev"] = merged["ar_26"] / merged["q1_revenue"]
        merged["inv_to_rev"] = merged["inv_26"] / merged["q1_revenue"]
    else:
        merged["ar_to_rev"] = float("nan")
        merged["inv_to_rev"] = float("nan")

    def _flag(row: pd.Series) -> str:
        tags = []
        ar_y = row["ar_yoy"]
        inv_y = row["inv_yoy"]
        if pd.notna(ar_y) and ar_y > 0.5:
            tags.append("应收暴增")
        elif pd.notna(ar_y) and ar_y > 0.3:
            tags.append("应收增长偏快")
        if pd.notna(inv_y) and inv_y > 0.5:
            tags.append("存货暴增")
        elif pd.notna(inv_y) and inv_y > 0.3:
            tags.append("存货增长偏快")
        if pd.notna(row.get("ar_to_rev")) and row["ar_to_rev"] > 1.0:
            tags.append("应收超单季收入")
        return " | ".join(tags) if tags else ""

    merged["bs_warning"] = merged.apply(_flag, axis=1)
    return merged[["ts_code", "ar_yoy", "inv_yoy", "ar_to_rev", "inv_to_rev", "bs_warning"]]


# ── divergence signals ─────────────────────────────────────────────

def compute_divergence_signals(companies: pd.DataFrame) -> pd.DataFrame:
    """Generate divergence scores and tags from hotspot CSV data."""
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

        net_flow_yuan = net_flow * 1e4
        net_flow_yi = net_flow / 1e4

        diverge_reasons = []
        if hot_days >= 10 and net_flow_yuan < -1e9:
            diverge_reasons.append("高热度+大额净流出")
        elif hot_days >= 20 and net_flow_yuan < -5e8:
            diverge_reasons.append("高热度+净流出")
        # `hsgt_top10_days` only records appearances in the daily top-10
        # trading list. It has no net-buy or holding-change direction, so it
        # must not be described as accumulation or as an investor identity.
        if hsgt_days >= 20 and hot_days <= 10:
            diverge_reasons.append("沪深港通 Top10 活跃、热榜较低")
        elif hsgt_days >= 30 and hot_days <= 20:
            diverge_reasons.append("沪深港通 Top10 显著高于热榜")
        if hot_days >= 30 and hsgt_days <= 5:
            diverge_reasons.append("热榜活跃、沪深港通 Top10 较低")
        if margin_delta > 1e10 and net_flow_yuan < -1e9:
            diverge_reasons.append("杠杆增仓+资金流出")
        if limit_events >= 5 and hot_days <= 5:
            diverge_reasons.append("涨停频繁但未上榜")

        consensus_reasons = []
        if hot_days >= 30 and hsgt_days >= 20:
            consensus_reasons.append("热榜与沪深港通 Top10 同时活跃")

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


# ── percentile label helpers ───────────────────────────────────────

def compute_percentile_labels(report: pd.DataFrame) -> pd.DataFrame:
    """Add pe_3y_level and pb_3y_level columns based on current vs historical percentiles."""
    report = report.copy()
    report["pe_3y_level"] = "N/A"
    report["pb_3y_level"] = "N/A"

    for idx, row in report.iterrows():
        cur_pe = row.get("pe_ttm")
        cur_pb = row.get("pb")
        p50_pe = row.get("pe_3y_p50")
        p75_pe = row.get("pe_3y_p75")
        p90_pe = row.get("pe_3y_p90")
        p50_pb = row.get("pb_3y_p50")
        p75_pb = row.get("pb_3y_p75")
        p90_pb = row.get("pb_3y_p90")

        if pd.notna(cur_pe) and pd.notna(p50_pe):
            if pd.notna(p90_pe) and cur_pe >= p90_pe:
                report.at[idx, "pe_3y_level"] = ">p90"
            elif pd.notna(p75_pe) and cur_pe >= p75_pe:
                report.at[idx, "pe_3y_level"] = "p75-p90"
            elif cur_pe >= p50_pe:
                report.at[idx, "pe_3y_level"] = "p50-p75"
            else:
                report.at[idx, "pe_3y_level"] = "<p50"

        if pd.notna(cur_pb) and pd.notna(p50_pb):
            if pd.notna(p90_pb) and cur_pb >= p90_pb:
                report.at[idx, "pb_3y_level"] = ">p90"
            elif pd.notna(p75_pb) and cur_pb >= p75_pb:
                report.at[idx, "pb_3y_level"] = "p75-p90"
            elif cur_pb >= p50_pb:
                report.at[idx, "pb_3y_level"] = "p50-p75"
            else:
                report.at[idx, "pb_3y_level"] = "<p50"

    return report
