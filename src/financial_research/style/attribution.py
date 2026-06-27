"""Strategy attribution — OLS regression of strategy returns against factor returns."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def run_strategy_attribution(
    factor_results: dict,
    strategy_returns: Optional[pd.Series] = None,
    strategy_name: str = "strategy",
) -> dict:
    """Regress strategy daily returns against factor long-short returns."""
    if strategy_returns is None or len(strategy_returns) < 20:
        return {"error": "no strategy returns provided"}

    sr = strategy_returns.dropna().copy()
    if isinstance(sr.index, pd.DatetimeIndex):
        sr.index = sr.index.normalize()

    factor_df = pd.DataFrame({
        name: res["long_short"].dropna() for name, res in factor_results.items()
    })
    factor_df.index = factor_df.index.normalize()

    merged = factor_df.join(sr.rename(strategy_name), how="inner")
    if len(merged) < 20:
        return {"error": "insufficient overlapping dates"}

    y = merged[strategy_name]
    X = merged[list(factor_results.keys())].fillna(0)

    X_aug = np.column_stack([np.ones(len(X)), X.values])
    beta = np.linalg.lstsq(X_aug, y.values, rcond=None)[0]
    intercept, coefs = beta[0], beta[1:]

    y_pred = X_aug @ beta
    residuals = y.values - y_pred
    r2 = 1 - residuals.var() / y.var() if y.var() > 0 else 0

    n_years = (y.index.max() - y.index.min()).days / 365.25
    ann_ret = ((1 + y.mean()) ** 252 - 1) * 100
    ann_alpha = ((1 + pd.Series(residuals).mean()) ** 252 - 1) * 100

    return {
        "strategy": strategy_name,
        "days": len(y), "years": round(n_years, 1),
        "r_squared": round(r2, 4),
        "annual_return": round(ann_ret, 2),
        "annual_alpha": round(ann_alpha, 2),
        "intercept": round(intercept * 252 * 100, 4),
        "betas": dict(zip(X.columns, coefs.round(6))),
    }
