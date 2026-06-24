# 金融研报核验仓库（电子行业 80 家样本）

本仓库将一份 26Q2 电子行业卖方研报转成可复核的文本与数据资产，支持多轮自动化核验。当前覆盖 80 家公司，含 75 家 A 股和 5 家港股。

## 当前文件与职责

### 核心分析文档

- `company-analysis-todo.md`
  主研究清单，含 P0/P1 优先级、深度研究任务模板与完成记录。模板已升级为 9 节，包含「市场共识与分歧」模块。
- `company-analysis-initial-screen.md`
  第一轮定量核验，覆盖行情、估值、最新财报和港股一手披露。说明数据口径、缺失情况和待核验项。
- `company-hotspot-analysis.md`
  热点与资金流分析底稿，包含热榜、涨停、资金流、北向、融资数据和概念快照。已加入背离信号框架。
- `enhanced-screening-report.md`
  增强初筛报告（由脚本自动生成）。覆盖 PE/PB 历史分位、PE/PB 背离分类、现金流质量、应收存货趋势、融资拥挤度和背离信号检测。
- `original-analytic-report.md`
  原始研报提取文本，保留原文结构和预测数字，用于与新核验结果对照。

### 数据与脚本

- `company-hotspot-data.csv`
  机器可读明细，含每家公司的概念快照、热榜命中日期、涨停次数、资金流和融资变化。
- `scripts/enhanced_screen/`
  增强初筛包，包含 `data.py`（计算函数）、`report.py`（报告生成）、`__init__.py`（入口编排）。
- `scripts/enhanced_screen.py`
  薄入口脚本，直接调用 `enhanced_screen` 包。
- `scripts/test_enhanced_screen.py`
  冒烟测试，验证数据加载和核心计算函数。
- `scripts/chart_hotspot.py`
  热度可视化脚本，读取 `company-hotspot-data.csv` 生成 SVG 图表，输出 `charts/hotspot-dashboard.html`。
- `charts/hotspot-dashboard.html`
  最近一次可视化仪表盘。

### 说明文件

- `AGENTS.md`
  文档写作规范与维护公约。
- `README.md`
  当前文件，说明项目范围、运行方式与核验流程。
- `docs/README.md`
  文档目录索引。

## 数据来源

增强初筛涉及的数据资产均在 market-data-platform 内持久化，来源如下：

| 数据 | 平台资产 | TuShare 接口 |
| --- | --- | --- |
| 历史日线估值（PE/PB/市值） | `daily_basic` | `daily_basic` |
| 标准化财务报表（利润/现金流/资产负债） | `normalized_fundamentals` | `income` / `cashflow` / `balancesheet` |
| 融资融券明细 | `margin_detail` | `margin_detail` |
| 同花顺热榜 | `ths_hot` | `ths_hot` |
| 同花顺涨停明细 | `limit_list_ths` | `limit_list_ths` |
| 同花顺资金流 | `moneyflow_ths` | `moneyflow_ths` |
| 同花顺概念指数 | `ths_index` | `ths_index` |
| 沪深港通十大成交 | `hsgt_top10` | `hsgt_top10` |

部分概念成分数据受限于代理接口不支持过滤查询，沿用初版 CSV 快照。

## 运行方式

### 增强初筛

从 market-data-platform 的 venv 运行，需要 `pandas`、`pyarrow`：

```bash
cd ~/code/research-workspace/market-data-platform
uv run --extra dev python ~/code/financial-research/scripts/enhanced_screen.py
```

输出为仓库根目录的 `enhanced-screening-report.md`。

### 冒烟测试

```bash
cd ~/code/research-workspace/market-data-platform
uv run --extra dev python ~/code/financial-research/scripts/test_enhanced_screen.py
```

### 热度仪表盘

需要 `pandas`：

```bash
python scripts/chart_hotspot.py
```

输出为 `charts/hotspot-dashboard.html`。未安装 `pandas` 时直接报错退出。

### 数据核验

读取 `company-hotspot-data.csv` 后，按 `company-hotspot-analysis.md` 的口径说明核对字段和覆盖范围。

## 手工核验清单

仓库暂未接入自动化测试框架。每次更新后建议做以下检查：

1. 运行 `python scripts/chart_hotspot.py`，确认仪表盘正常生成。
2. 抽查 `company-analysis-initial-screen.md` 与 `company-hotspot-analysis.md` 中的字段是否与 `company-hotspot-data.csv` 对齐。
3. 在原报告假设或市场数据更新后，重新运行 `scripts/enhanced_screen.py` 生成最新初筛报告。
4. 核对原始来源链接可访问，补充核验日期。
