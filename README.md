# 金融研报核验仓库（电子行业 80 家样本）

本仓库将一份 26Q2 电子行业卖方研报转为可复核的研究资产。它提供原始预期、财务与估值初筛、市场行为核验、专题比较和单公司深研模板；不将研报预测、概念标签或交易活跃度直接视为投资结论。

## 目录结构

```text
docs/
  archive/       原始研报文本与截图
  research/      研究地图、专题底稿、初筛与热点分析
data/            可随仓库分发的输入数据
src/financial_research/
                 可复用的初筛、仪表盘与打包逻辑
scripts/         兼容命令入口与冒烟测试
artifacts/       可再生 HTML 等输出
```

## 核心文档

- [`docs/archive/original-analytic-report.md`](docs/archive/original-analytic-report.md)
  原始研报提取文本，保留当时预测数字，只作为待核验假设。
- [`docs/research/company-analysis-todo.md`](docs/research/company-analysis-todo.md)
  80 家公司研究清单、单公司深研模板与完成记录。
- [`docs/research/company-analysis-initial-screen.md`](docs/research/company-analysis-initial-screen.md)
  第一轮行情、估值、财务和港股披露核验。
- [`docs/research/company-hotspot-analysis.md`](docs/research/company-hotspot-analysis.md)
  热榜、涨停、资金流、沪深港通 Top10 交易活跃度与融资数据的口径说明。
- [`docs/research/enhanced-screening-report.md`](docs/research/enhanced-screening-report.md)
  自动生成的估值分位、现金流、营运资本、融资与背离信号报告。
- [`docs/research/research-map.md`](docs/research/research-map.md)
  专题到单公司的研究路由、证据标准与复盘机制。
- [`docs/research/topic-ccl-ai-pcb.md`](docs/research/topic-ccl-ai-pcb.md)、[`topic-storage-price.md`](docs/research/topic-storage-price.md)、[`topic-advanced-packaging.md`](docs/research/topic-advanced-packaging.md)
  第一轮专题比较底稿，明确现有证据和待补数据。

完整索引见 [`docs/README.md`](docs/README.md)。

## 数据与代码

- `data/company-hotspot-data.csv`：80 家公司的概念快照、热榜命中、涨停、资金流、沪深港通 Top10 上榜次数和融资变化。
- `src/financial_research/enhanced_screen/`：增强初筛的计算与 Markdown 生成逻辑。
- `src/financial_research/hotspot_dashboard.py`：热度仪表盘生成逻辑。
- `src/financial_research/bundle.py`：可分发 ZIP 包与 SHA-256 清单生成逻辑。
- `artifacts/hotspot-dashboard.html`：最近一次生成的热点仪表盘。

增强初筛依赖 market-data-platform 中已持久化的 `daily_basic`、`normalized_fundamentals` 与 `margin_detail` 等资产；这些大型外部资产不复制到本仓库。可分发 CSV 与其字段口径见 [热点底稿](docs/research/company-hotspot-analysis.md)。

## 运行与核验

增强初筛与冒烟测试应从 market-data-platform 环境运行：

```bash
cd ~/code/research-workspace/market-data-platform
uv run --extra dev python ~/code/financial-research/scripts/test_enhanced_screen.py
uv run --extra dev python ~/code/financial-research/scripts/enhanced_screen.py
```

增强初筛输出到 `docs/research/enhanced-screening-report.md`。

生成热点仪表盘：

```bash
python scripts/chart_hotspot.py
```

输出为 `artifacts/hotspot-dashboard.html`。仪表盘把 `hsgt_top10` 解释为「沪深港通 Top10 上榜次数」；它不表示净买入、持仓变化或投资者身份。

## 分发项目与数据

```bash
python scripts/export_bundle.py \
  --output-dir /mnt/c/Users/gbyha/Downloads \
  --name financial-research.zip
```

压缩包包含文档、`data/` 内 CSV、源代码、脚本和已生成物，并在 `BUNDLE_MANIFEST.json` 中记录每个文件的 SHA-256。market-data-platform 的外部持久化资产及需要联网刷新的数据不会被打包，清单会明确列出该边界。

如需让接收者在本地复跑增强初筛，可先预检体积，再显式加入当前所需的五类平台资产：

```bash
python scripts/export_bundle.py --include-platform-assets --dry-run
python scripts/export_bundle.py \
  --output-dir /mnt/c/Users/gbyha/Downloads \
  --name financial-research-with-data.zip \
  --include-platform-assets
```

截至当前数据快照，全量复现包的未压缩输入约为 1.6 GiB。解压后将 `FIN_RESEARCH_DATA_ROOT` 指向包内 `financial-research/platform-data`，再从 market-data-platform 环境运行增强初筛。`*_latest` 资产在包内被展开为普通目录，因此 Windows 用户无需创建符号链接。该模式仍不包含用来刷新同花顺热点、资金流和沪深港通数据的全部上游资产；当前快照由 `data/company-hotspot-data.csv` 提供。
