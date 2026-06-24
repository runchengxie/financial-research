# 仪表盘数据契约与图表口径

## 输出与刷新顺序

```text
scripts/enhanced_screen.py
  ├─ docs/research/enhanced-screening-report.md
  └─ artifacts/research-snapshot.csv

scripts/chart_hotspot.py
  └─ artifacts/hotspot-dashboard.html

scripts/chart_research.py
  └─ artifacts/research-cockpit.html
```

运行研究驾驶舱前必须先生成 `research-snapshot.csv`。热点页只依赖 `data/company-hotspot-data.csv`，可独立重建。

## 两页职责

| 页面 | 主问题 | 主数据 | 不应推断的内容 |
| --- | --- | --- | --- |
| `hotspot-dashboard.html` | 市场在交易什么，信号是否持续或矛盾？ | 热榜、涨停、资金流、融资与沪深港通 Top10 上榜次数 | 净买入主体、客户订单、实际经营改善 |
| `research-cockpit.html` | 哪些公司需要优先回到经营与估值假设核验？ | 估值分位、Q1 财务、现金流、营运资本、融资拥挤度及交易背离 | 投资评级、目标价或 26Q2 实际业绩 |

## 图表映射

| 页面区块 | 图形 | 分析问题 | 数据粒度 | 关键限制 |
| --- | --- | --- | --- | --- |
| 热榜关注度 vs 融资杠杆 | 散点图 | 热度、融资变化与 Top10 活跃度是否错位？ | 公司 | Top10 只代表上榜次数，不代表资金方向 |
| 综合排名 Top 15 | 横向条形图 | 热榜与涨停事件最集中在哪些公司？ | 公司 | 分数不是投资评分 |
| 热榜时间线 | 点状时间线 | 头部热度是持续还是分段出现？ | 公司—日期 | 仅有 3 家头部公司的命中日期 |
| 概念覆盖 | 精确表格 | 哪些平台叙事在热股中覆盖最广？ | 概念 | 覆盖公司数不等于收入、利润或真实业务规模 |
| 风险覆盖 | 横向条形图 | 高估值、现金流、融资和背离风险的样本覆盖度如何？ | 75 家 A 股代表 | 指标可重叠，不能相加为风险总数 |
| 核验优先名单 | 横向条形图与明细表 | 哪些公司应先补经营证据？ | 公司 | 分数只用于研究排期 |

## `research-snapshot.csv` 字段

| 字段组 | 代表字段 | 来源 | 用途 |
| --- | --- | --- | --- |
| 身份 | `company`、`ts_code`、`priority` | 公司清单 | 统一公司粒度与原研报优先级 |
| 估值 | `pe_ttm`、`pb`、`pe_3y_level`、`pb_3y_level` | `daily_basic` | 估值高位核验 |
| 财务质量 | `q1_cf_to_ni`、`ar_yoy`、`inv_yoy`、`bs_warning` | `normalized_fundamentals` | 现金流和营运资本风险 |
| 融资 | `rzye`、`circ_mv_yuan`、`rz_to_float` | `margin_detail` 与 `daily_basic` | 杠杆拥挤度 |
| 市场行为 | `hot_days`、`net_flow_yi`、`hsgt_days`、`margin_delta_yi` | `company-hotspot-data.csv` | 交易活跃度与背离识别 |
| 排期 | `research_priority_score`、`diverge_tags` | 增强初筛计算 | 研究队列，不是投资信号 |

快照内同时保存估值、融资、财务的各自数据截止日。任何新页面或图表必须显示这些日期，不能用同一「截至日期」掩盖不同源的更新节奏。
