# 金融研报核验仓库（电子行业 80 家样本）

本仓库用于把一份 26Q2 电子行业研究草稿转成可复核的文本与数据资产，并提供一次性核验脚本。当前覆盖样本为 80 家公司，含 75 家 A 股代表和 5 家港股标的。

## 当前文件与职责

### 根目录说明文档

- `company-analysis-todo.md`  
  主研究清单，记录 P0 与 P1 两组目标公司的深度研究任务、任务模板与完成记录。
- `company-analysis-initial-screen.md`  
  第一轮定量核验结果，包含数据口径、缺失说明、初筛结论与待核验清单。
- `company-hotspot-analysis.md`  
  热点与资金流分析底稿，定义样本信号、主题分组、排序规则与优先研究依据。
- `original-analytic-report.md`  
  原始研报内容提取版本，保留原始观点结构，便于与新核验结果对照。
- `company-hotspot-data.csv`  
  可复用的机器可读明细，含概念快照、命中日期和热度指标。
- `scripts/chart_hotspot.py`  
  用于生成热度分析图表并输出 `charts/hotspot-dashboard.html` 的脚本。
- `charts/hotspot-dashboard.html`  
  最近一次可视化输出结果。

### 文档目录

- `docs/README.md`  
  说明文档入口与本仓库文档使用场景。  

### 说明文件

- `AGENTS.md`  
  本仓库文档和复核约定。
- `README.md`  
  当前文件，说明项目范围、运行方式与测试情况。

## 数据来源与更新范围

已落地的数据链路主要来自 TuShare 的同花顺系列接口：

- `ths_hot`、`ths_member`、`ths_index`
- `limit_list_ths`
- `moneyflow_ths`
- `margin_detail`
- `hsgt_top10`

其中部分资产在 `company-hotspot-analysis.md` 已注明已持久化状态和缺口。

## 运行方式

- 生成热点图表（需要 `pandas`）  
  `python scripts/chart_hotspot.py`  
  输出为 `charts/hotspot-dashboard.html`。未安装 `pandas` 时会直接报错并退出。
- 读取/核验数据可先查看 `company-hotspot-data.csv`，再按 `company-hotspot-analysis.md` 的口径说明核对。

## 测试脚本与自动化检查

当前仓库没有独立的自动化测试套件，仓库也未接入 `pytest`、`unittest`、`npm test` 等持续测试入口。  

建议在每次更新后做以下手动检查，替代自动化测试：

1. 先运行 `python scripts/chart_hotspot.py`，确认 `charts/hotspot-dashboard.html` 能生成且不报错。  
2. 抽查 `company-analysis-initial-screen.md` 与 `company-hotspot-analysis.md` 中列出的关键字段是否与 `company-hotspot-data.csv` 对齐。  
3. 核对原始来源链接可访问，补充核验日期并写入更新说明。

## 目前事实一致性说明

仓库目前是中文说明文档为主，代码文件仅一份图表脚本。  
说明文档中新增了对“港股一手披露”与“A 股同花顺口径”边界的区分。  
`company-analysis-todo.md` 与 `company-analysis-initial-screen.md` 已同步使用 `original-analytic-report.md` 作为原始来源文件，避免了已失效的 `analytic-report.md` 引用。
