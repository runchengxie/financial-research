"""Factor portfolio backtest — quintile long-short, summary, correlations, yearly breakdown."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .factor_calc import FACTOR_COLS

FACTOR_NAMES = ["size", "value", "momentum", "quality", "lowvol"]


def get_rebalance_dates(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Monthly rebalance: last trading day of each month."""
    df = pd.DataFrame({"date": dates})
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    return pd.DatetimeIndex(df.groupby(["year", "month"])["date"].max().sort_values())


def build_factor_returns(
    factors_df: pd.DataFrame,
    daily: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex,
    n_quantiles: int = 5,
) -> dict:
    """For each factor: quintile long-short monthly rebalance."""
    factor_z_cols = [f"factor_{n}_z" for n in FACTOR_NAMES]

    ret_df = daily[["trade_date", "symbol", "pct_chg"]].copy()
    ret_df["pct_chg"] = ret_df["pct_chg"] / 100.0
    ret_df["trade_date"] = pd.to_datetime(ret_df["trade_date"])

    all_dates = sorted(ret_df["trade_date"].unique())
    rd_list = sorted(rebalance_dates)

    results = {}
    for fname, fcol in zip(FACTOR_NAMES, factor_z_cols):
        print(f"[backtest] {fname} ...")
        long_ret, short_ret, ls_ret, dates_out = [], [], [], []

        for i, rd in enumerate(rd_list):
            if i == len(rd_list) - 1:
                break
            next_rd = rd_list[i + 1]

            rd_data = factors_df[factors_df["trade_date"] == rd].dropna(subset=[fcol])
            if len(rd_data) < n_quantiles * 10:
                continue

            rd_data = rd_data.sort_values(fcol)
            rd_data["quantile"] = pd.qcut(rd_data[fcol], n_quantiles, labels=False, duplicates="drop")
            if rd_data["quantile"].nunique() < n_quantiles:
                continue

            top_syms = rd_data[rd_data["quantile"] == n_quantiles - 1]["symbol"].tolist()
            bot_syms = rd_data[rd_data["quantile"] == 0]["symbol"].tolist()

            holding_dates = [d for d in all_dates if rd < d <= next_rd]
            if not holding_dates:
                continue

            for hd in holding_dates:
                day_ret = ret_df[ret_df["trade_date"] == hd]
                top_r = day_ret[day_ret["symbol"].isin(top_syms)]["pct_chg"].mean()
                bot_r = day_ret[day_ret["symbol"].isin(bot_syms)]["pct_chg"].mean()
                if pd.notna(top_r) and pd.notna(bot_r):
                    long_ret.append(top_r)
                    short_ret.append(bot_r)
                    ls_ret.append(top_r - bot_r)
                    dates_out.append(hd)

        idx = pd.DatetimeIndex(dates_out)
        results[fname] = {
            "long_short": pd.Series(ls_ret, index=idx, name=fname),
            "long": pd.Series(long_ret, index=idx),
            "short": pd.Series(short_ret, index=idx),
        }

    return results


def compute_summary(factor_results: dict, trading_days: int = 252) -> pd.DataFrame:
    rows = []
    for name, res in factor_results.items():
        ls = res["long_short"].dropna()
        if len(ls) < 20:
            continue
        dm = ls.mean()
        annual_ret = (1 + dm) ** trading_days - 1
        annual_vol = ls.std() * np.sqrt(trading_days)
        sharpe = dm / ls.std() * np.sqrt(trading_days) if ls.std() > 0 else 0
        cum = (1 + ls).cumprod()
        max_dd = ((cum - cum.cummax()) / cum.cummax()).min()
        hit_rate = (ls > 0).mean()
        n_years = (ls.index.max() - ls.index.min()).days / 365.25
        rows.append({
            "factor": name, "days": len(ls), "years": round(n_years, 1),
            "annual_ret": round(annual_ret * 100, 2),
            "annual_vol": round(annual_vol * 100, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "hit_rate": round(hit_rate * 100, 1),
        })
    return pd.DataFrame(rows).sort_values("sharpe", ascending=False)


def compute_factor_correlations(factor_results: dict) -> pd.DataFrame:
    series = {}
    for name, res in factor_results.items():
        s = res["long_short"].dropna()
        if len(s) > 20:
            series[name] = s
    return pd.DataFrame(series).corr()


def compute_yearly_breakdown(factor_results: dict) -> pd.DataFrame:
    rows = []
    for name, res in factor_results.items():
        s = res["long_short"].dropna()
        for year_end, group in s.resample("YE"):
            if len(group) < 50:
                continue
            annual_ret = (1 + group).prod() - 1
            ann_vol = group.std() * np.sqrt(252)
            sharpe = group.mean() / group.std() * np.sqrt(252) if group.std() > 0 else 0
            max_dd = ((1 + group).cumprod().cummin() / (1 + group).cumprod() - 1).min()
            rows.append({
                "year": year_end.year, "factor": name, "days": len(group),
                "annual_ret": round(annual_ret * 100, 2),
                "annual_vol": round(ann_vol * 100, 2),
                "sharpe": round(sharpe, 2),
                "max_drawdown": round(max_dd * 100, 2),
            })
    return pd.DataFrame(rows).sort_values(["year", "factor"])
