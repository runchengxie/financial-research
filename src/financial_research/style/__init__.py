"""全市场风格因子分析 — 5 因子 (Size, Value, Momentum, Quality, LowVol)."""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

matplotlib.use("Agg")

# ── CJK font & style ──
CJK = fm.FontProperties(fname="/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc")
BG, FG, LG = "#1a1a2e", "#e0e0e0", "#333"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG,
    "axes.edgecolor": LG, "axes.labelcolor": FG,
    "text.color": FG, "xtick.color": "#999", "ytick.color": "#999",
})

FACTOR_LABELS = {
    "size": "Size 大市值",
    "value": "Value 低估值",
    "momentum": "Momentum 动量",
    "quality": "Quality 盈利",
    "lowvol": "LowVol 低波动",
}

COLORS = ["#ff6b6b", "#00d4aa", "#ffd93d", "#6c5ce7", "#a8e6cf"]
