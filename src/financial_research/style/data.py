"""Data loading — daily + daily_basic from market-data-platform parquet."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_data(data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load daily and daily_basic parquet files into memory."""
    daily_dir = data_root / "assets/tushare/a_share/daily/a_share_all_daily_latest/data"
    basic_dir = data_root / "assets/tushare/a_share/daily_basic/a_share_all_daily_basic_latest/data"

    daily_parts = sorted(daily_dir.glob("trade_date=*"))
    basic_parts = sorted(basic_dir.glob("trade_date=*"))

    print(f"[load] daily: {len(daily_parts)} partitions, basic: {len(basic_parts)} partitions")

    daily = pd.concat(
        [pd.read_parquet(p).assign(trade_date=lambda df: pd.to_datetime(df["trade_date"]))
         for p in daily_parts],
        ignore_index=True,
    )

    basics = pd.concat(
        [pd.read_parquet(p).assign(trade_date=lambda df: pd.to_datetime(df["trade_date"]))
         for p in basic_parts],
        ignore_index=True,
    )

    daily = daily.drop_duplicates(["trade_date", "symbol"]).copy()
    basics = basics.drop_duplicates(["trade_date", "symbol"]).copy()

    print(f"[load] daily: {len(daily)} rows, {daily['symbol'].nunique()} stocks")
    print(f"[load] basic: {len(basics)} rows, {basics['symbol'].nunique()} stocks")
    return daily, basics
