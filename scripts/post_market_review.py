#!/usr/bin/env python3
"""Post-market daily review — 盘后点评.

Reads market-data-platform parquet assets and produces a structured
multi-dimensional market summary for the given trade date.

Usage:
    DATA_PLATFORM_ROOT=/home/richard/data/market-data-platform \\
        uv run python scripts/post_market_review.py                 # latest trade date
    uv run python scripts/post_market_review.py --date 20260625
    uv run python scripts/post_market_review.py --date 20260625 --json

Units note (from Tushare docs):
    daily.amount        → 千元
    moneyflow_hsgt.*    → 万元
    moneyflow_ths.*     → 万元
    margin.*            → 元

Requirements: pandas, pyarrow (in mdp venv).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

DATA_ROOT = Path(
    os.environ.get("DATA_PLATFORM_ROOT", "/home/richard/data/market-data-platform")
) / "assets" / "tushare" / "a_share"


def _latest_date(dataset: str) -> str:
    p = DATA_ROOT / dataset
    if not p.exists():
        return ""
    dirs = sorted(
        [
            d.name
            for d in (p / list(p.glob("*_latest"))[0] / "data").iterdir()
            if d.is_dir() and d.name.startswith("trade_date=")
        ],
        reverse=True,
    )
    return dirs[0].split("=")[1] if dirs else ""


def _read(dataset: str, trade_date: str) -> pd.DataFrame:
    p = (
        DATA_ROOT
        / dataset
        / list((DATA_ROOT / dataset).glob("*_latest"))[0].name
        / "data"
        / f"trade_date={trade_date}"
        / "part.parquet"
    )
    return pd.read_parquet(p)


def _fmt_yuan(n: float) -> str:
    """Format CNY amount — input is 元."""
    if abs(n) >= 1e12:
        return f"{n / 1e12:.2f}万亿"
    if abs(n) >= 1e8:
        return f"{n / 1e8:.2f}亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.2f}万"
    return f"{n:.0f}"


def _pct(v: float) -> str:
    if v > 0:
        return f"+{v:.2f}%"
    return f"{v:.2f}%"


def _sign(n: float) -> str:
    if n > 0:
        return f"+{_fmt_yuan(n)}"
    return f"-{_fmt_yuan(abs(n))}"


# ---------------------------------------------------------------------------
# data loaders
# ---------------------------------------------------------------------------

def load_market_overview(trade_date: str) -> dict[str, Any]:
    """Market aggregates from individual stocks (no index-level data available)."""
    daily = _read("daily", trade_date)

    # Filter to individual stocks only — exclude indices and funds
    stocks = daily[
        daily["ts_code"].str.endswith(".SH")
        | daily["ts_code"].str.endswith(".SZ")
        | daily["ts_code"].str.endswith(".BJ")
    ].copy()

    # Exclude indices (codes like 000001.SH but not 000001.SZ which is a stock)
    def _is_index(code: str) -> bool:
        if code.endswith(".SH"):
            return code[:6] in {
                "000001", "000002", "000003", "000004", "000005", "000006", "000007",
                "000008", "000009", "000010", "000011", "000012", "000013", "000014",
                "000015", "000016", "000017", "000018", "000019", "000020",
                "000300", "000688", "000852", "000905",
            }
        if code.endswith(".SZ"):
            return code[:6] in {
                "399001", "399005", "399006", "399016", "399102", "399106", "399300",
                "399303", "399905", "399852",
            }
        return False

    stocks = stocks[~stocks["ts_code"].apply(_is_index)]

    # Use numeric pct_chg
    stocks["pct_chg"] = pd.to_numeric(stocks["pct_chg"], errors="coerce")
    stocks["amount"] = pd.to_numeric(stocks["amount"], errors="coerce")

    up_count = int((stocks["pct_chg"] > 0).sum())
    down_count = int((stocks["pct_chg"] < 0).sum())
    flat_count = int((stocks["pct_chg"] == 0).sum())
    total = len(stocks)

    # Market metrics
    total_amount = float(stocks["amount"].sum())  # 千元
    median_pct = float(stocks["pct_chg"].median())
    avg_pct = float(stocks["pct_chg"].mean())
    # Amount-weighted (biased by large-caps, but useful for market-cap perspective)
    wavg_pct = float((stocks["pct_chg"] * stocks["amount"]).sum() / stocks["amount"].sum()) if total_amount > 0 else 0.0

    # Distribution
    bins = [(-100, -9.9), (-9.9, -7), (-7, -5), (-5, -3), (-3, -1), (-1, 0),
            (0, 1), (1, 3), (3, 5), (5, 7), (7, 9.9), (9.9, 100)]
    dist = {}
    for lo, hi in bins:
        cnt = int(((stocks["pct_chg"] >= lo) & (stocks["pct_chg"] < hi)).sum())
        if cnt > 0:
            dist[f"{lo}~{hi}%"] = cnt

    # Top movers — exclude IPOs (pct_chg > 30%) and delisting anomalies (< -30%)
    stocks_clean = stocks[stocks["pct_chg"].between(-30, 30)]
    top_up = stocks_clean.nlargest(5, "pct_chg")[["ts_code", "pct_chg", "close"]].to_dict("records")
    top_down = stocks_clean.nsmallest(5, "pct_chg")[["ts_code", "pct_chg", "close"]].to_dict("records")

    return {
        "median_pct_chg": median_pct,
        "mean_pct_chg": avg_pct,
        "wavg_pct_chg": wavg_pct,
        "breadth": {
            "up": up_count, "down": down_count, "flat": flat_count, "total": total,
            "up_ratio": round(up_count / total * 100, 1) if total else 0,
        },
        "turnover_total": total_amount,  # 千元
        "distribution": dist,
        "top_gainers": top_up,
        "top_losers": top_down,
    }


def load_limit_analysis(trade_date: str) -> dict[str, Any]:
    """Limit-up/down statistics. Note: limit_list_ths only has 涨停池 (no 跌停)."""
    try:
        df = _read("limit_list_ths", trade_date)
    except Exception:
        return {"error": "limit_list_ths not available"}

    # 涨停池 is the only type
    up = df[df["limit_type"] == "涨停池"]

    # Status counts
    status_counts = up["status"].value_counts().to_dict() if not up.empty and "status" in df.columns else {}

    return {
        "limit_up": {"count": int(len(up))},
        "limit_up_names": up["name"].tolist()[:15] if not up.empty else [],
        "status_breakdown": status_counts,
        "limit_down_note": "limit_list_ths 不含跌停数据",
    }


def load_moneyflow(trade_date: str) -> dict[str, Any]:
    """Northbound + sector money flow."""
    result: dict[str, Any] = {}

    # Northbound (万元)
    try:
        hsgt = _read("moneyflow_hsgt", trade_date)
        if not hsgt.empty:
            r = hsgt.iloc[0]
            result["northbound"] = {
                "north_net": float(r.get("north_money", 0)) * 1e4,   # 万→元
                "south_net": float(r.get("south_money", 0)) * 1e4,
                "hgt": float(r.get("hgt", 0)) * 1e4,
                "sgt": float(r.get("sgt", 0)) * 1e4,
            }
    except Exception:
        pass

    # HSGT top 10 active
    try:
        top10 = _read("hsgt_top10", trade_date)
        if not top10.empty:
            top10["change_n"] = pd.to_numeric(top10["change"], errors="coerce")
            buy = top10.nlargest(5, "change_n")[["name", "change_n", "market_type"]].to_dict("records")
            result["north_active_buy"] = [
                {"name": r["name"], "change": r["change_n"]} for r in buy
            ]
    except Exception:
        pass

    # Moneyflow THS (万元 → 元)
    try:
        mf = _read("moneyflow_ths", trade_date)
        if not mf.empty:
            mf["net_amount"] = pd.to_numeric(mf["net_amount"], errors="coerce")
            net_in = float(mf[mf["net_amount"] > 0]["net_amount"].sum()) * 1e4
            net_out = float(mf[mf["net_amount"] < 0]["net_amount"].sum()) * 1e4
            result["moneyflow"] = {
                "net_in": net_in,
                "net_out": net_out,
                "net_total": net_in + net_out,
                "inflow_stocks": int((mf["net_amount"] > 0).sum()),
                "outflow_stocks": int((mf["net_amount"] < 0).sum()),
            }
    except Exception:
        pass

    return result


def load_margin(trade_date: str) -> dict[str, Any]:
    """Margin trading (元)."""
    try:
        df = _read("margin", trade_date)
        if df.empty:
            return {}
        total_rz = float(df["rzye"].sum())
        total_rq = float(df["rqye"].sum())
        return {
            "margin_balance": total_rz + total_rq,
            "financing_balance": total_rz,
            "short_balance": total_rq,
        }
    except Exception:
        return {}


def load_hot_sectors(trade_date: str) -> dict[str, Any]:
    """Hot concept sectors (dc_concept)."""
    try:
        df = _read("dc_concept", trade_date)
        if df.empty:
            return {}

        # Convert all relevant columns
        for col in ["pct_change", "lead_stock_pct_change", "z_t_num", "main_change", "hot"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        top_change = df.nlargest(10, "pct_change")[
            ["name", "pct_change", "lead_stock", "lead_stock_pct_change", "z_t_num"]
        ].to_dict("records")

        # Top by main capital inflow
        top_fund_in = df.nlargest(5, "main_change")[
            ["name", "main_change", "lead_stock"]
        ].to_dict("records") if "main_change" in df.columns else []

        return {
            "top_by_change": top_change,
            "top_by_fund": top_fund_in,
            "total_concepts": int(len(df)),
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# report builder
# ---------------------------------------------------------------------------

def build_report(trade_date: str) -> str:
    overview = load_market_overview(trade_date)
    limit = load_limit_analysis(trade_date)
    flow = load_moneyflow(trade_date)
    margin = load_margin(trade_date)
    sectors = load_hot_sectors(trade_date)

    lines: list[str] = []

    dt = datetime.strptime(trade_date, "%Y%m%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    lines.append(f"## {trade_date} {weekday} 盘后点评")
    lines.append("")

    # ── 一、市场总览 ──
    median = overview.get("median_pct_chg", 0)
    wavg = overview.get("wavg_pct_chg", 0)
    tag_mkt = "[OK]" if median > 0 else "[WARN]"
    turnover = overview.get("turnover_total", 0) * 1000  # 千元→元
    b = overview.get("breadth", {})

    lines.append("### 一、市场总览")
    lines.append("")
    lines.append(
        f"全市场中位数涨跌 {tag_mkt} **{_pct(median)}** | "
        f"加权涨跌 **{_pct(wavg)}** | "
        f"总成交 **{_fmt_yuan(turnover)}**"
    )
    lines.append(f"> 加权偏正说明大市值股强于中小盘，注意风格分化")
    lines.append("")
    lines.append(
        f"上涨 **{b['up']}** 家 | 下跌 **{b['down']}** 家 | 平盘 **{b['flat']}** 家 | "
        f"上涨率 **{b.get('up_ratio', 0)}%**"
    )
    lines.append("")

    # Distribution
    dist = overview.get("distribution", {})
    if dist:
        items = "  ".join(f"{k}:{v}" for k, v in dist.items())
        lines.append(f"涨跌分布: {items}")
        lines.append("")

    # ── 二、涨跌停 ──
    lines.append("### 二、涨跌停")
    lines.append("")
    lu = limit.get("limit_up", {})
    lines.append(f"涨停 **{lu.get('count', 0)}** 家" + (f" ({', '.join(f'{k}:{v}' for k,v in limit.get('status_breakdown', {}).items())})" if limit.get('status_breakdown') else ""))
    lines.append("")
    if limit.get("limit_up_names"):
        lines.append(f"涨停代表: {'、'.join(limit['limit_up_names'][:12])}")
        lines.append("")
    ld_note = limit.get("limit_down_note", "")
    if ld_note:
        lines.append(f"> {ld_note}")
        lines.append("")

    # ── 三、资金动向 ──
    lines.append("### 三、资金动向")
    lines.append("")

    nb = flow.get("northbound", {})
    if nb:
        lines.append(
            f"北向净流入 **{_sign(nb.get('north_net', 0))}** | "
            f"沪股通 {_sign(nb.get('hgt', 0))} | "
            f"深股通 {_sign(nb.get('sgt', 0))}"
        )
        lines.append("")

    mf = flow.get("moneyflow", {})
    if mf:
        net = mf.get("net_total", 0)
        tag_mf = "[OK]" if net > 0 else "[WARN]"
        lines.append(
            f"全市场主力资金 {tag_mf} **{_sign(net)}** | "
            f"净流入 {mf.get('inflow_stocks', 0)} 家 / 净流出 {mf.get('outflow_stocks', 0)} 家"
        )
        lines.append("")

    active = flow.get("north_active_buy", [])
    if active:
        items = ", ".join(f"{a['name']}({_pct(a['change'])})" for a in active)
        lines.append(f"北向活跃买入: {items}")
        lines.append("")

    # ── 四、融资融券 ──
    lines.append("### 四、融资融券")
    lines.append("")
    if margin:
        lines.append(
            f"融资余额 **{_fmt_yuan(margin.get('financing_balance', 0))}** | "
            f"融券余额 **{_fmt_yuan(margin.get('short_balance', 0))}** | "
            f"两融总额 **{_fmt_yuan(margin.get('margin_balance', 0))}**"
        )
        lines.append("")
    else:
        lines.append("两融数据暂缺")
        lines.append("")

    # ── 五、热门概念 ──
    lines.append("### 五、热门概念板块 TOP5")
    lines.append("")
    top_c = sectors.get("top_by_change", [])[:5]
    if top_c:
        lines.append("| 概念 | 涨幅 | 龙头 | 涨停数 |")
        lines.append("|------|------|------|--------|")
        for c in top_c:
            lines.append(
                f"| {c['name']} | {_pct(c.get('pct_change', 0))} | "
                f"{c.get('lead_stock', '-')}({_pct(c.get('lead_stock_pct_change', 0))}) | "
                f"{int(c.get('z_t_num', 0))} |"
            )
        lines.append("")

    top_f = sectors.get("top_by_fund", [])[:3]
    if top_f:
        items = ", ".join(
            f"{c['name']}({_fmt_yuan(c.get('main_change', 0))})"
            for c in top_f
        )
        lines.append(f"主力资金净流入前三概念: {items}")
        lines.append("")

    # ── 六、极端异动 ──
    lines.append("### 六、极端异动")
    lines.append("")
    top_up = overview.get("top_gainers", [])[:5]
    top_down = overview.get("top_losers", [])[:5]
    if top_up:
        items = "、".join(f"{r['ts_code']}({_pct(r['pct_chg'])})" for r in top_up)
        lines.append(f"涨幅前五: {items}")
        lines.append("")
    if top_down:
        items = "、".join(f"{r['ts_code']}({_pct(r['pct_chg'])})" for r in top_down)
        lines.append(f"跌幅前五: {items}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"*数据: Tushare / market-data-platform | 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
    )

    return "\n".join(lines)


def build_json(trade_date: str) -> str:
    overview = load_market_overview(trade_date)
    report = {
        "trade_date": trade_date,
        "generated_at": datetime.now().isoformat(),
        "overview": overview,
        "limits": load_limit_analysis(trade_date),
        "moneyflow": load_moneyflow(trade_date),
        "margin": load_margin(trade_date),
        "hot_sectors": load_hot_sectors(trade_date),
    }
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="盘后点评 — post-market daily review")
    parser.add_argument("--date", help="Trade date YYYYMMDD (default: latest available)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.date:
        trade_date = args.date
    else:
        trade_date = _latest_date("daily")
        if not trade_date:
            print("[FAIL] 无法确定最新交易日，请用 --date 指定", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(build_json(trade_date))
    else:
        print(build_report(trade_date))


if __name__ == "__main__":
    main()
