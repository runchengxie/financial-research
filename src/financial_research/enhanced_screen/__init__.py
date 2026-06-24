"""Enhanced screening: PE/PB percentiles, cash flow quality, margin crowding, divergence signals.

Reads from market-data-platform data assets and the hotspot CSV.
Output: docs/research/enhanced-screening-report.md.

Usage:
    cd ~/code/research-workspace/market-data-platform
    uv run --extra dev python ~/code/financial-research/scripts/enhanced_screen.py
"""

from __future__ import annotations

import logging

from . import data, report

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def main() -> None:
    print("[1/5] Loading companies...")
    companies = data.load_company_list()
    n = len(companies)
    print(f"  {n} companies loaded")

    print("[2/5] Computing PE/PB percentiles (3Y)...")
    pe_3y, pb_3y = data.compute_pe_pb_percentiles(companies)
    current_val = data.compute_current_valuation(companies)
    print(f"  PE 3Y: {len(pe_3y)} stocks, PB 3Y: {len(pb_3y)} stocks")

    print("[3/5] Computing cash flow quality...")
    cf_q1, cf_annual = data.compute_cashflow_quality(companies)
    print(f"  Q1: {len(cf_q1)} stocks, FY: {len(cf_annual)} stocks")

    print("[4/5] Computing margin crowding...")
    margin = data.compute_margin_crowding(companies)
    print(f"  Margin: {len(margin)} stocks matched")

    print("[5/5] Computing divergence signals...")
    divergences = data.compute_divergence_signals(companies)

    print("[+] Computing AR/Inventory trends...")
    ar_inv = data.compute_ar_inventory_trend(companies)
    print(f"  AR/Inventory: {len(ar_inv)} stocks matched")

    # Merge everything
    rpt = companies.copy()
    rpt = rpt.merge(current_val, on="ts_code", how="left")
    rpt = rpt.merge(pe_3y, on="ts_code", how="left")
    rpt = rpt.merge(pb_3y, on="ts_code", how="left")

    if not cf_q1.empty:
        cf_q1_r = cf_q1.rename(columns={
            "n_income_attr_p": "q1_net_income",
            "n_cashflow_act": "q1_oper_cf",
            "cf_to_ni": "q1_cf_to_ni",
        })
        rpt = rpt.merge(cf_q1_r, on="ts_code", how="left")

    if not cf_annual.empty:
        cf_ar = cf_annual.rename(columns={
            "n_income_attr_p": "fy_net_income",
            "n_cashflow_act": "fy_oper_cf",
            "cf_to_ni": "fy_cf_to_ni",
        })
        rpt = rpt.merge(cf_ar, on="ts_code", how="left")

    rpt = rpt.merge(margin, on="ts_code", how="left")
    rpt = rpt.merge(divergences, on="ts_code", how="left")

    # Compute labels and patterns
    rpt = data.compute_percentile_labels(rpt)
    rpt["pe_pb_pattern"] = data.compute_pe_pb_divergence(rpt)
    rpt = rpt.merge(ar_inv, on="ts_code", how="left")

    # Generate report
    md = report.generate_report(rpt)
    out_path = data.REPO_ROOT / "docs/research/enhanced-screening-report.md"
    out_path.write_text(md, encoding="utf-8")

    # Summary
    n_pe = (rpt["pe_3y_level"] == ">p90").sum()
    n_pb = (rpt["pb_3y_level"] == ">p90").sum()
    n_cf = (rpt["q1_cf_to_ni"].notna() & (rpt["q1_cf_to_ni"] < 0)).sum()
    n_mg = (rpt["rz_to_float"].notna() & (rpt["rz_to_float"] > 0.03)).sum()
    n_dv = (rpt["diverge_score"] > 0).sum()

    print(f"\n[DONE] Report written to {out_path}")
    print(f"  Total companies: {n}")
    print(f"  PE alerts: {n_pe}, PB alerts: {n_pb}")
    print(f"  CF warnings: {n_cf}, Margin high: {n_mg}")
    print(f"  Divergence signals: {n_dv}")


if __name__ == "__main__":
    main()
