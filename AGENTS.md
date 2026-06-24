# 项目说明（AGENTS）

## 适用范围

本文件说明仓库内中文文档、数据资产与核验脚本的写作和维护规则，适用于 `docs/`、`data/`、`src/`、`scripts/` 与 `artifacts/`。

## 项目状态

- 仓库以研究核验文档和辅助脚本为主，未按 Python 包结构组织。
- 样本规模 80 家公司，当前口径以 2026-06-24 前后状态为准。
- 增强初筛数据来自 market-data-platform 中已持久化的 `daily_basic`、`normalized_fundamentals`、`margin_detail` 等资产；热点数据来自 `ths_hot`、`limit_list_ths`、`moneyflow_ths` 等同花顺系列接口。部分概念成分沿用 CSV 快照。
- `docs/archive/` 存放原始材料，`docs/research/` 存放研究底稿与自动报告，`data/` 存放可分发输入，`src/financial_research/` 存放业务逻辑，`scripts/` 仅保留命令入口，`artifacts/` 仅存放可再生输出。

## 写作约定

- 文档以中文为主，使用中文标点（（）「」：，。），行内代码用反引号 `` 包裹。
- 避免中英混杂、翻译腔和多余从句。先写结论，再补边界条件。
- 涉及数据缺失或不可用时，先说明事实边界，再给出可执行的验证动作。
- 不使用双引号「“”」做强调，改用「」标注引用或特定称谓。
- 引用文件路径、字段名、命令时用反引号行内代码。

## 文件更新规则

- 修改 `docs/research/` 下的研究文档或 `docs/archive/original-analytic-report.md` 后，同步更新根目录 `README.md` 与 `docs/README.md` 中的文件说明。
- 数据口径变更时同步更新 `docs/research/company-hotspot-analysis.md` 的口径与限制说明。
- 首次补全港股披露、A 股热度或财报口径时，同步更新样本一致性说明。
- `docs/research/enhanced-screening-report.md` 由 `scripts/enhanced_screen.py` 自动生成，不应手动编辑。修改初筛逻辑直接改 `src/financial_research/enhanced_screen/` 并重新运行。
- `artifacts/` 内的文件均为生成物；修改逻辑后必须重新生成，不应手工修订。
- `docs/README.md` 需与根目录文件列表保持同步。

## 运行与核验

- 增强初筛：从 market-data-platform venv 运行 `scripts/enhanced_screen.py`，输出 `docs/research/enhanced-screening-report.md`。
- 热度仪表盘：运行 `python scripts/chart_hotspot.py`，确认 `artifacts/hotspot-dashboard.html` 正常写入。
- 研究驾驶舱：增强初筛完成后运行 `python scripts/chart_research.py`，确认 `artifacts/research-cockpit.html` 与 `artifacts/research-snapshot.csv` 正常写入。
- 初筛代码至少运行 `scripts/test_enhanced_screen.py` 冒烟核验。每次更新后至少运行一轮增强初筛和热度仪表盘。
- 项目分发：运行 `python scripts/export_bundle.py --output-dir <目录>`；仅在需要接收者复跑增强初筛时添加 `--include-platform-assets`，并先运行 `--dry-run` 确认体积。
