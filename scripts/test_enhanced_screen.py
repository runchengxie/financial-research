"""Smoke tests for enhanced_screen data loading functions.

Run with the market-data-platform venv:
    cd ~/code/research-workspace/market-data-platform
    uv run --extra dev python ~/code/financial-research/scripts/test_enhanced_screen.py
"""

import sys
from pathlib import Path

# Ensure the scripts dir is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from enhanced_screen import data

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}: {detail}")


def test_load_company_list() -> None:
    print("load_company_list()")
    companies = data.load_company_list()
    check(">= 70 companies", len(companies) >= 70, f"got {len(companies)}")
    check("has ts_code column", "ts_code" in companies.columns)
    check("ts_code format", companies["ts_code"].str.match(r"\d{6}\.(SH|SZ)").all())
    check("no duplicate ts_code", companies["ts_code"].is_unique)


def test_config() -> None:
    print("config")
    ref = data.get_reference_date()
    check("reference_date is string", isinstance(ref, str))
    check("reference_date format YYYY-MM-DD", len(ref) == 10 and ref[4] == "-", ref)

    fin = data.get_fin_date()
    check("fin_date is string", isinstance(fin, str))
    check("fin_date is 8 digits", len(fin) == 8 and fin.isdigit(), fin)

    root = data.DATA_ROOT
    check("DATA_ROOT exists", root.exists(), str(root))

    csv = data.CSV_PATH
    check("CSV_PATH exists", csv.exists(), str(csv))


def test_compute_current_valuation() -> None:
    print("compute_current_valuation()")
    companies = data.load_company_list()
    df = data.compute_current_valuation(companies)
    check("non-empty result", len(df) > 0, f"got {len(df)} rows")
    if len(df) > 0:
        check("has pe_ttm", "pe_ttm" in df.columns)
        check("has pb", "pb" in df.columns)
        check("has circ_mv", "circ_mv" in df.columns)


def test_compute_divergence_signals() -> None:
    print("compute_divergence_signals()")
    companies = data.load_company_list()
    df = data.compute_divergence_signals(companies)
    check("non-empty result", len(df) > 0, f"got {len(df)} rows")
    if len(df) > 0:
        check("has diverge_score", "diverge_score" in df.columns)
        check("has net_flow_yi", "net_flow_yi" in df.columns)
        check("net_flow_yi values reasonable", df["net_flow_yi"].abs().max() < 10000,
              f"max={df['net_flow_yi'].abs().max()}")


def main() -> None:
    print("Enhanced Screen Smoke Tests")
    print("=" * 50)

    for fn in [
        test_load_company_list,
        test_config,
        test_compute_current_valuation,
        test_compute_divergence_signals,
    ]:
        try:
            fn()
        except Exception as e:
            global FAIL
            FAIL += 1
            print(f"  [FAIL] {fn.__name__}: {e}")
        print()

    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
