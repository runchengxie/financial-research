# Financial Research → 已迁移至 [daily-messenger](https://github.com/runchengxie/daily-messenger)

> **本仓库的所有分析模块已于 2026-06-28 迁入 [daily-messenger](https://github.com/runchengxie/daily-messenger) 的 `a_share_analysis` 子包。**
>
> daily-messenger 是统一的 A 股分析工具基座：ETL → 评分 → 日报 → 因子分析 → 飞书推送。迁移后的模块自带依赖管理、CLI 入口和 cron 调度，不再需要手动挂 venv。
>
> 本仓库保留为历史存档，**不再接受新提交**。原始电子行业研报核验部分已删除。

<details>
<summary>历史内容（存档）</summary>

## 目录结构

```text
scripts/
  post_market_review.py   盘后点评（全市场多维度日报）
  value_regime_weekly.py  价值因子周报（3 区制分类 + 前瞻收益）
  style_analysis.py       5 因子全市场 Long-short 回测 + 归因
src/financial_research/
  style/                  因子计算、回测、归因、图表、报告
artifacts/
  style_analysis/         预计算的因子日收益序列 + 图表
```

## 运行（历史方式，不再推荐）

所有脚本依赖 market-data-platform 环境：

```bash
cd ~/code/research-workspace/market-data-platform
source .venv/bin/activate
source .env.local

# 盘后点评
DATA_PLATFORM_ROOT=/home/richard/data/market-data-platform \
  python3 ~/code/financial-research/scripts/post_market_review.py

# 风格因子分析
DATA_PLATFORM_ROOT=/home/richard/data/market-data-platform \
  python3 ~/code/financial-research/scripts/style_analysis.py
```

## 新用法（推荐）

在 daily-messenger 仓库中：

```bash
cd ~/code/daily-messenger
uv sync

# 盘后点评
DATA_PLATFORM_ROOT=/home/richard/data/market-data-platform \
  uv run python src/a_share_analysis/post_market_review.py

# 价值因子周报
uv run python src/a_share_analysis/value_regime_weekly.py

# 5 因子回测
DATA_PLATFORM_ROOT=/home/richard/data/market-data-platform \
  uv run python src/a_share_analysis/style_analysis.py
```

</details>
