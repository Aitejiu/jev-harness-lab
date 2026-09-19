# Jev Agent/工具路由评测（MetaTool ToolE，已知目录）

- 样本数：400
- catalog 规模：199 个工具
- 模型：jev-1.13.0

## 路由准确率（选对正确工具）

| 模式 | 选项数 | 样本 | Top-1 准确率 | 随机基线 | 关键指标 |
|---|---|---|---|---|---|
| random | 10 | 200 | **96.0%** | 10.0% | conf≥0.8：覆盖 96.5%，准确率 98.4% |
| similar | 10 | 200 | **92.0%** | 10.0% | conf≥0.8：覆盖 92.0%，准确率 95.7% |

## 错例（前 10）

| 模式 | 请求 | 正确 | 预测 | 置信度 |
|---|---|---|---|---|
| random | The GoFynd plugin provides a comprehensive range o | `ProductSearch` | `DataRetrievalTool` | 0.46 |
| similar | The GoFynd plugin provides a comprehensive range o | `ProductSearch` | `ShoppingAssistant` | 1.00 |
| random | Please find the complete and accurate lyrics of th | `web_requests` | `jini` | 0.72 |
| similar | Can you recommend some champions that are strong i | `champdex` | `GameTool` | 0.68 |
| similar | Cryptocurrency is a scam! Show me some news articl | `FinanceTool` | `NewsTool` | 0.92 |
| random | I'm planning a trip to Paris. Could you give me a  | `PDF&URLTool` | `aiAgents` | 0.58 |
| random | I heard about a newly released smartphone, but I c | `PDF&URLTool` | `ProductComparison` | 0.82 |
| similar | I heard about a newly released smartphone, but I c | `PDF&URLTool` | `ResearchHelper` | 0.93 |
| similar | I'm launching a new online store for handmade jewe | `SEOTool` | `seoanalysis` | 0.80 |
| similar | I love watching videos on Youtube! Can you help me | `VideoSummarizeTool` | `video_highlight` | 0.52 |
