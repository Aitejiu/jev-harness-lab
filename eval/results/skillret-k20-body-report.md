# Jev Skill Router 评测（SkillRet：6,660 个真实 skills）

- 查询数：300（多目标查询 152 条），skills 池：6006
- 架构：BM25 召回 top-20 → Jev choice 选择（与生产 skill router 同构）
- 模型：jev-1.13.0
- 延迟：P50 0.34s / P95 0.47s
- 成本：1196040 input tokens ≈ $0.0502

## 关键指标

| 阶段 | 指标 | 结果 |
|---|---|---|
| 1. BM25 全库 | Hit@1 | 52.7% |
| 1. BM25 召回 | 短名单含正确 skill（Recall@20） | 77.3% |
| 2. Jev 选择 | Hit@1（端到端） | **65.3%** |
| 2. Jev 选择 | 条件 Hit@1（金标在短名单内时） | **84.5%** |

## 置信度门控

| confidence ≥ | 覆盖率 | 准确率（覆盖内） | 转人工 |
|---|---|---|---|
| 0.50 | 84.7% | 72.4% | 15.3% |
| 0.60 | 77.3% | 75.4% | 22.7% |
| 0.70 | 67.0% | 78.6% | 33.0% |
| 0.80 | 60.7% | 81.3% | 39.3% |
| 0.90 | 51.0% | 85.0% | 49.0% |
| 0.95 | 44.7% | 89.6% | 55.3% |
| 0.99 | 31.0% | 94.6% | 69.0% |

## 错例（前 10）

| 查询 | 金标 skills | Jev 预测 | 在短名单 | 置信度 |
|---|---|---|---|---|
| We have a Python microservice at `~/repos/orde | Retry, Timeout & Backoff Strategies | api-rate-limiting | 是 | 0.85 |
| We have a background automation called "CodeSe | hook-sdk-integration, mcp-mastery | agent-tool-builder | 否 | 0.60 |
| Search arXiv and PubMed for recent papers (202 | excel-pivot-wizard, paper-search-usa | Academic Researcher | 是 | 0.59 |
| Build me a desktop system monitor app at `~/re | castella-core, claude-code-automatio | dev-orchestration | 是 | 0.72 |
| We're building a tabletop RPG companion app in | Component-Aware Test Gap Analysis, d | unit-test-generator | 是 | 0.29 |
| Our marketing agency is building a portfolio s | create-issue, stitch-loop | subagent | 否 | 0.53 |
| Our real estate tech company is building a Swi | axiom-swiftui-nav-ref, lease-complia | axiom-swiftui-nav | 是 | 0.46 |
| Our monorepo at `~/repos/fintech-core` (Python | codex-delegator-skill | bugfixforever | 否 | 0.30 |
| We're doing a major overhaul of our Python mon | swarm-workflow | atlas-full | 否 | 0.60 |
| We need to build an automated competitor intel | when-orchestrating-swarm-use-swarm-o | multi-agent-composition | 否 | 0.53 |
