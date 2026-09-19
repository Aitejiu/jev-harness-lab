# Jev Skill Router 评测（SkillRet：6,660 个真实 skills）

- 查询数：300（多目标查询 152 条），skills 池：6006
- 架构：BM25 召回 top-10 → Jev choice 选择（与生产 skill router 同构）
- 模型：jev-1.13.0
- 延迟：P50 0.36s / P95 0.70s
- 成本：329768 input tokens ≈ $0.0139

## 关键指标

| 阶段 | 指标 | 结果 |
|---|---|---|
| 1. BM25 全库 | Hit@1 | 58.3% |
| 1. BM25 召回 | 短名单含正确 skill（Recall@10） | 78.7% |
| 2. Jev 选择 | Hit@1（端到端） | **68.3%** |
| 2. Jev 选择 | 条件 Hit@1（金标在短名单内时） | **86.9%** |

## 置信度门控

| confidence ≥ | 覆盖率 | 准确率（覆盖内） | 转人工 |
|---|---|---|---|
| 0.50 | 86.7% | 73.1% | 13.3% |
| 0.60 | 76.7% | 78.3% | 23.3% |
| 0.70 | 70.0% | 81.4% | 30.0% |
| 0.80 | 63.0% | 83.1% | 37.0% |
| 0.90 | 52.3% | 86.6% | 47.7% |
| 0.95 | 45.3% | 89.7% | 54.7% |
| 0.99 | 35.3% | 91.5% | 64.7% |

## 错例（前 10）

| 查询 | 金标 skills | Jev 预测 | 在短名单 | 置信度 |
|---|---|---|---|---|
| We have a Python microservice at `~/repos/orde | Retry, Timeout & Backoff Strategies | api-rate-limiting | 是 | 0.91 |
| We have a background automation called "CodeSe | hook-sdk-integration, mcp-mastery | tool-discovery | 否 | 0.91 |
| We're building a tabletop RPG companion app in | Component-Aware Test Gap Analysis, d | senior-qa | 是 | 0.48 |
| Our monorepo at `~/repos/fintech-core` (Python | codex-delegator-skill | python-database-patterns | 否 | 0.93 |
| We're doing a major overhaul of our Python mon | swarm-workflow | atlas-full | 否 | 0.58 |
| We need to build an automated competitor intel | when-orchestrating-swarm-use-swarm-o | multi-agent-composition | 否 | 0.64 |
| Our executive team is evaluating whether to ex | business-analyst, fetching-prices | prd-v03-feature-value-planning | 是 | 0.69 |
| Build me a full-featured interactive dashboard | frontend-design-react | ui-designer | 否 | 0.76 |
| We want to rebuild our legacy inventory manage | planning | deployment-verification-agent | 否 | 0.26 |
| Our company requires all developers to complet | Training navigation (vendor-agnostic | browser-automation | 否 | 1.00 |
