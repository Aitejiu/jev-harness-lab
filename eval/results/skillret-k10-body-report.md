# Jev Skill Router 评测（SkillRet：6,660 个真实 skills）

- 查询数：300（多目标查询 152 条），skills 池：6006
- 架构：BM25 召回 top-10 → Jev choice 选择（与生产 skill router 同构）
- 模型：jev-1.13.0
- 延迟：P50 0.32s / P95 0.45s
- 成本：684049 input tokens ≈ $0.0287

## 关键指标

| 阶段 | 指标 | 结果 |
|---|---|---|
| 1. BM25 全库 | Hit@1 | 52.7% |
| 1. BM25 召回 | 短名单含正确 skill（Recall@10） | 71.3% |
| 2. Jev 选择 | Hit@1（端到端） | **63.0%** |
| 2. Jev 选择 | 条件 Hit@1（金标在短名单内时） | **88.3%** |

## 置信度门控

| confidence ≥ | 覆盖率 | 准确率（覆盖内） | 转人工 |
|---|---|---|---|
| 0.50 | 90.3% | 66.1% | 9.7% |
| 0.60 | 82.3% | 70.0% | 17.7% |
| 0.70 | 76.0% | 73.7% | 24.0% |
| 0.80 | 68.3% | 77.6% | 31.7% |
| 0.90 | 58.3% | 81.1% | 41.7% |
| 0.95 | 52.7% | 82.9% | 47.3% |
| 0.99 | 37.0% | 90.1% | 63.0% |

## 错例（前 10）

| 查询 | 金标 skills | Jev 预测 | 在短名单 | 置信度 |
|---|---|---|---|---|
| We have a Python microservice at `~/repos/orde | Retry, Timeout & Backoff Strategies | api-rate-limiting | 否 | 0.96 |
| We're a 4-person dev team that just got greenl | Product Manager | prd-maker | 否 | 0.99 |
| We have a background automation called "CodeSe | hook-sdk-integration, mcp-mastery | agent-tool-builder | 否 | 0.69 |
| Search arXiv and PubMed for recent papers (202 | excel-pivot-wizard, paper-search-usa | Academic Researcher | 是 | 0.57 |
| We're preparing to launch "TerraSync," a new d | cursor-agent, launch-tiering | launch-strategy | 是 | 0.46 |
| We're building a tabletop RPG companion app in | Component-Aware Test Gap Analysis, d | qa-lead | 是 | 0.39 |
| Our marketing agency is building a portfolio s | create-issue, stitch-loop | subagent | 否 | 0.70 |
| Our monorepo at `~/repos/fintech-core` (Python | codex-delegator-skill | debugger | 否 | 0.28 |
| Our multi-tenant SaaS analytics platform on GK | autoscaling-configuration | gcp-cloud-run | 否 | 0.96 |
| We're doing a major overhaul of our Python mon | swarm-workflow | atlas-full | 否 | 0.92 |
