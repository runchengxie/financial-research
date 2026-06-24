"""兼容入口：生成电子行业研究驾驶舱。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_research.research_cockpit import main


if __name__ == "__main__":
    main()
