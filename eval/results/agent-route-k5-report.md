# Jev Agent/工具路由评测（MetaTool ToolE，已知目录）

- 样本数：400
- catalog 规模：199 个工具
- 模型：jev-1.13.0

## 路由准确率（选对正确工具）

| 模式 | 选项数 | 样本 | Top-1 准确率 | 随机基线 | 关键指标 |
|---|---|---|---|---|---|
| random | 5 | 200 | **98.0%** | 20.0% | conf≥0.8：覆盖 97.5%，准确率 98.5% |
| similar | 5 | 200 | **96.5%** | 20.0% | conf≥0.8：覆盖 97.0%，准确率 97.4% |

## 错例（前 10）

| 模式 | 请求 | 正确 | 预测 | 置信度 |
|---|---|---|---|---|
| random | The GoFynd plugin provides a comprehensive range o | `ProductSearch` | `tira` | 0.81 |
| similar | The GoFynd plugin provides a comprehensive range o | `ProductSearch` | `ShoppingAssistant` | 1.00 |
| random | I'm planning a trip to Paris. Could you give me a  | `PDF&URLTool` | `internetSearch` | 1.00 |
| similar | I'm launching a new online store for handmade jewe | `SEOTool` | `seoanalysis` | 0.88 |
| similar | I love watching videos on Youtube! Can you help me | `VideoSummarizeTool` | `video_highlight` | 0.73 |
| similar | Can you retrieve the most recent and up-to-date to | `FinanceTool` | `NewsTool` | 0.95 |
| similar | Tell me about the key information related to the N | `FinanceTool` | `DataRetrievalTool` | 0.61 |
| random | Could you find me some beginner-friendly tutorials | `PDF&URLTool` | `search` | 0.52 |
| similar | Hi! I'm in the mood for some retail therapy. Can y | `TripAdviceTool` | `local` | 0.87 |
| random | Guide me through the process of assembling an IKEA | `rephrase` | `MixerBox_WebSearchG_web_search` | 0.96 |
