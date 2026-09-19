# Jev Skill Router 评测（SkillRet：6,660 个真实 skills）

- 查询数：300（多目标查询 152 条），skills 池：6006
- 架构：BM25 召回 top-10 → Jev choice 选择（与生产 skill router 同构）
- 模型：jev-1.13.0
- 延迟：P50 0.32s / P95 0.89s
- 成本：342636 input tokens ≈ $0.0144

## 关键指标

| 阶段 | 指标 | 结果 |
|---|---|---|
| 1. BM25 全库 | Hit@1 | 52.7% |
| 1. BM25 召回 | 短名单含正确 skill（Recall@10） | 71.3% |
| 2. Jev 选择 | Hit@1（端到端） | **63.7%** |
| 2. Jev 选择 | 条件 Hit@1（金标在短名单内时） | **89.3%** |

## 置信度门控

| confidence ≥ | 覆盖率 | 准确率（覆盖内） | 转人工 |
|---|---|---|---|
| 0.50 | 87.0% | 68.6% | 13.0% |
| 0.60 | 81.3% | 70.1% | 18.7% |
| 0.70 | 73.0% | 73.5% | 27.0% |
| 0.80 | 66.0% | 75.8% | 34.0% |
| 0.90 | 55.7% | 79.6% | 44.3% |
| 0.95 | 45.3% | 85.3% | 54.7% |
| 0.99 | 35.3% | 90.6% | 64.7% |

## 错例（前 10）

| 查询 | 金标 skills | Jev 预测 | 在短名单 | 置信度 |
|---|---|---|---|---|
| We have a Python microservice at `~/repos/orde | Retry, Timeout & Backoff Strategies | api-rate-limiting | 否 | 1.00 |
| We're a 4-person dev team that just got greenl | Product Manager | prd-maker | 否 | 0.68 |
| We have a background automation called "CodeSe | hook-sdk-integration, mcp-mastery | agent-tool-builder | 否 | 0.56 |
| Search arXiv and PubMed for recent papers (202 | excel-pivot-wizard, paper-search-usa | Academic Researcher | 是 | 0.32 |
| We're building a tabletop RPG companion app in | Component-Aware Test Gap Analysis, d | qa-lead | 是 | 0.28 |
| Our marketing agency is building a portfolio s | create-issue, stitch-loop | subagent | 否 | 0.57 |
| Our monorepo at `~/repos/fintech-core` (Python | codex-delegator-skill | debugger | 否 | 0.80 |
| Our multi-tenant SaaS analytics platform on GK | autoscaling-configuration | gcp-cloud-run | 否 | 0.98 |
| We're doing a major overhaul of our Python mon | swarm-workflow | atlas-full | 否 | 0.80 |
| We need to build an automated competitor intel | when-orchestrating-swarm-use-swarm-o | multi-agent-composition | 否 | 0.79 |
