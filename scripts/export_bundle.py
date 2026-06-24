"""兼容入口：导出可分发的项目 ZIP 包。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_research.bundle import main


if __name__ == "__main__":
    main()
