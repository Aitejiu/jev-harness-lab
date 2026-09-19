# Jev Agent/工具路由评测（MetaTool ToolE，已知目录）

- 样本数：400
- catalog 规模：199 个工具
- 模型：jev-1.13.0

## 路由准确率（选对正确工具）

| 模式 | 选项数 | 样本 | Top-1 准确率 | 随机基线 | 关键指标 |
|---|---|---|---|---|---|
| random | 20 | 200 | **92.5%** | 5.0% | conf≥0.8：覆盖 93.5%，准确率 95.2% |
| similar | 20 | 200 | **88.5%** | 5.0% | conf≥0.8：覆盖 88.5%，准确率 93.8% |

## 错例（前 10）

| 模式 | 请求 | 正确 | 预测 | 置信度 |
|---|---|---|---|---|
| similar | I want to learn more about the solar system, can y | `stellarexplorer` | `NASATool` | 0.95 |
| random | The GoFynd plugin provides a comprehensive range o | `ProductSearch` | `ShoppingAssistant` | 1.00 |
| similar | The GoFynd plugin provides a comprehensive range o | `ProductSearch` | `ShoppingAssistant` | 1.00 |
| random | Please find the complete and accurate lyrics of th | `web_requests` | `MusicTool` | 0.54 |
| random | Could you assist me in finding a trustworthy attor | `LawTool` | `jini` | 0.33 |
| similar | Can you recommend some champions that are strong i | `champdex` | `GameTool` | 0.64 |
| random | Can you recommend a family-friendly lakeside cotta | `TripTool` | `TripAdviceTool` | 0.49 |
| similar | Cryptocurrency is a scam! Show me some news articl | `FinanceTool` | `NewsTool` | 0.53 |
| random | I'm planning a trip to Paris. Could you give me a  | `PDF&URLTool` | `TripAdviceTool` | 1.00 |
| similar | I'm planning a trip to Paris. Could you give me a  | `PDF&URLTool` | `find_agency` | 0.82 |
