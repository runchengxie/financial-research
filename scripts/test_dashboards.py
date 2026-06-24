"""热点页和研究驾驶舱的可再生输出冒烟核验。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_research import hotspot_dashboard, research_cockpit


def check(condition: bool, label: str) -> int:
    if condition:
        print(f"  [OK] {label}")
        return 0
    print(f"  [FAIL] {label}")
    return 1


def main() -> int:
    failures = 0
    print("Dashboard Smoke Tests")
    print("=" * 50)

    hotspot = hotspot_dashboard.load_data()
    failures += check(len(hotspot) == 80, "hotspot CSV covers 80 companies")
    failures += check(
        {"average_net", "positive_flow_days", "best_rank", "latest_rank"}.issubset(hotspot.columns),
        "hotspot detail fields are available",
    )
    hotspot_html = hotspot_dashboard.build_html(
        hotspot,
        {
            "scatter": hotspot_dashboard.svg_scatter(hotspot),
            "bar": hotspot_dashboard.svg_bar(hotspot),
            "timeline": hotspot_dashboard.svg_timeline(hotspot),
        },
    )
    for phrase in ["日均（亿）", "热榜持续性、排名与融资余额", "热榜命中概念覆盖"]:
        failures += check(phrase in hotspot_html, f"hotspot HTML contains {phrase}")

    snapshot = research_cockpit.load_snapshot()
    failures += check(len(snapshot) >= 70, "research snapshot covers A-share sample")
    required_snapshot_columns = {
        "research_priority_score", "pe_3y_level", "q1_cf_to_ni", "rz_to_float", "diverge_tags",
    }
    failures += check(
        required_snapshot_columns.issubset(snapshot.columns),
        "research snapshot contains risk fields",
    )
    cockpit_html = research_cockpit.build_html(snapshot)
    for phrase in ["估值、现金流与杠杆风险覆盖", "研究核验优先名单", "公司级风险与待核验项"]:
        failures += check(phrase in cockpit_html, f"cockpit HTML contains {phrase}")

    print(f"\nResults: {10 - failures} passed, {failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
