"""Factor computation — 5 classic style factors from daily + daily_basic."""

from __future__ import annotations

import numpy as np
import pandas as pd


FACTOR_COLS = ["factor_size", "factor_value", "factor_momentum", "factor_quality", "factor_lowvol"]


def compute_factors(daily: pd.DataFrame, basics: pd.DataFrame) -> pd.DataFrame:
    """Compute 5 classic style factors per stock per date."""
    df = daily[["trade_date", "symbol", "close", "pct_chg", "amount"]].merge(
        basics[["trade_date", "symbol", "total_mv", "pb", "pe_ttm", "circ_mv"]],
        on=["trade_date", "symbol"], how="left",
    )

    df = df[df["total_mv"] > 0].copy()
    df = df[df["amount"] > 0].copy()
    df = df.sort_values(["symbol", "trade_date"]).reset_index(drop=True)

    # Size: ln(total_mv)
    df["factor_size"] = np.log(df["total_mv"] + 1)

    # Value: 1/pb (book-to-price)
    df["pb_clean"] = df["pb"].clip(lower=0.01, upper=100)
    df["factor_value"] = 1.0 / df["pb_clean"]

    # Quality: earnings yield = 1/pe_ttm
    df["pe_clean"] = df["pe_ttm"].clip(lower=1, upper=500)
    df["factor_quality"] = 1.0 / df["pe_clean"]

    # Momentum: 20-day return, skip t-1
    df["ret_1d"] = df.groupby("symbol")["close"].pct_change()
    df["factor_momentum"] = df.groupby("symbol")["close"].transform(
        lambda s: s.pct_change(periods=21).shift(1)
    )

    # Low Vol: negative of 20-day return std
    df["vol20"] = df.groupby("symbol")["ret_1d"].transform(
        lambda s: s.rolling(21, min_periods=10).std().shift(1)
    )
    df["factor_lowvol"] = -df["vol20"]

    df = df.dropna(subset=FACTOR_COLS).copy()

    # Winsorize each factor per date (1st / 99th percentile)
    for col in FACTOR_COLS:
        df[col] = df.groupby("trade_date")[col].transform(
            lambda s: s.clip(lower=s.quantile(0.01), upper=s.quantile(0.99))
        )

    # Cross-sectional z-score per date
    for col in FACTOR_COLS:
        mean = df.groupby("trade_date")[col].transform("mean")
        std = df.groupby("trade_date")[col].transform("std")
        df[f"{col}_z"] = (df[col] - mean) / std.replace(0, np.nan)

    print(f"[factors] {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}, "
          f"{len(df)} rows, {df['symbol'].nunique()} stocks")
    return df
