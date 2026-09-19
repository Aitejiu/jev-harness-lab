# Jev 评测 Harness

统一的评测框架：加载数据集 → 构造 questions → 调用 Jev → 输出指标报告（可断点续跑，JSONL 缓存）。

## 结构

```
eval/
├── sources.py     # 数据集加载器（目前：neuralchemy core、zachz）
├── guardrail.py   # 护栏任务：noul 判定 prompt injection
├── runner.py      # 并发调用 + JSONL 缓存（线程级 client，中断可续跑）
├── metrics.py     # 阈值扫描、覆盖率曲线、校准、subtype 拆分、延迟/成本
├── report.py      # 生成 Markdown 报告
├── run.py         # 入口
├── data/          # 下载的数据（gitignore）
└── results/       # 评测结果 JSONL + 报告
```

## 运行

```bash
cd eval
../.venv/bin/python run.py --dataset neuralchemy-test --concurrency 6
../.venv/bin/python run.py --dataset zachz --limit 50      # 小样本
```

结果缓存在 `results/<dataset>.jsonl`，重复运行只补缺失样本；报告写到 `results/<dataset>-report.md`。

## 数据集

| 名称 | 规模 | 说明 | 来源 |
|---|---|---|---|
| neuralchemy-test | 942（552 恶意/390 良性） | 29 类攻击 + hard negatives，无泄漏切分 | HF `neuralchemy/Prompt-injection-dataset`（Apache-2.0） |
| zachz | 303（200 注入/100 良性） | 带 severity 标签，规模小，适合冒烟 | HF `zachz/prompt-injection-benchmark`（MIT） |

注：原计划的 OWASP LLM01 V2（600 条，300 攻击/300 良性对照）需要 HF 登录授权（401），暂未使用。

## 指标口径

- **阈值扫描**：noul 概率 → 判定，扫描 0.05~0.95 的 precision/recall/F1/FPR
- **置信度门控**：`certainty = max(p, 1-p)`（noul 无 confidence 字段，用概率本身的极端程度代理），低于阈值视为"不确定 → 转人工"，输出覆盖率-准确率曲线
- **校准**：按预测分数分桶，对比实际恶意比例
- **成本/延迟**：input tokens × $42/B 估算 + P50/P90/P95

## 首轮结果（neuralchemy-test，2026-09-18）

- 942 次调用，39.5 万 input tokens ≈ **$0.0166**，延迟 **P50 0.29s / P95 0.59s**

| 阈值 | 精确率 | 召回率 | F1 | FPR |
|---|---|---|---|---|
| 0.50 | 97.4% | 55.1% | 70.4% | 2.1% |
| 0.05（最佳 F1） | 95.6% | 94.2% | 94.9% | — |

置信度门控（自动处理 vs 转人工）：

| certainty ≥ | 覆盖率 | 自动处理准确率 |
|---|---|---|
| 0.90 | 67.6% | 87.8% |
| 0.98 | 47.6% | 96.7% |

按攻击类型（阈值 0.50）：direct_injection 召回 62.7%、jailbreak 56%、training_extraction 60%、adversarial 17.7%、encoding 6.7%。

## 发现

1. **criteria 决定任务边界**：该数据集把"请求有害内容"也标为恶意（如 "Explain how to use violence…"），而我们的 criteria 只问"是否覆盖/提取系统指令"——召回低的主因是任务定义不匹配，不是模型能力边界
2. **Jev 高分区非常精确**：分数 ≥0.1 的样本里 90%+ 是恶意（校准表），适合做高置信自动处置；但 **低分区不等于安全**：0~0.1 桶里仍有 16.6% 恶意，不能"低分直接放行"
3. **门控可用**：certainty ≥0.98 时自动处理 47.6% 流量、准确率 96.7%；≥0.90 时覆盖率 67.6%、准确率 87.8%
4. **成本/速度**：全量评测 1.7 美分、亚秒级响应，具备跑大数据集的经济性

## 下一步

- 修订护栏 criteria：拆成 3 个正交 noul（指令覆盖 / 越狱与有害请求 / 数据外泄与编码绕过），复测召回与 FPR
- 用 zachz（更聚焦注入）交叉验证
- 按覆盖-准确率曲线选定生产阈值并文档化

## 意图分类评测（擅长领域）

用 `run_intent.py` 在标准意图数据集上测分类能力（单阶段 choice，选项为意图名 + 人类可读描述）。

| 数据集 | 类别数 | Top-1 | Top-3 | 置信度门控 |
|---|---|---|---|---|
| SNIPS（1,400 条） | 7 | **97.9%** | 99.7% | conf≥0.90：覆盖 93.6%、准确率 99.1% |
| Banking77（3,080 条） | 77 | **80.3%** | 91.7% | conf≥0.90：覆盖 67.8%、准确率 92.8%；conf≥0.99：覆盖 46.1%、准确率 97.0% |

- 成本：SNIPS $0.026 / 1400 次；Banking77 $0.22 / 3080 次。延迟 P50 0.30~0.36s
- 参考：41 个开源模型零样本平均约 38.8%、Sonnet 教师约 81%（口径不同，仅供参考）——Jev 在 77 类上已接近强 LLM 教师，但成本/延迟低 2~3 个数量级
- 校准：Banking77 中段区间偏乐观（conf 0.55 → 实际 40%），高置信区可靠（conf 0.98 → 92.8%）；生产上应从高阈值起步
- 最差类别成对混淆（`get_physical_card` 0% vs `order_physical_card` 12.5%），属于 criteria 描述未划清边界，可通过补 rubric 修复

```bash
../.venv/bin/python run_intent.py --dataset snips --concurrency 6
../.venv/bin/python run_intent.py --dataset banking77 --concurrency 6
```

## Harness 实验：Bash 风险门控（v2，130 条命令）

数据集：`datasets/bash_commands.jsonl`（allow 55 / review 35 / deny 40，自建）。
任务：4 个正交 noul（破坏性 / 触密 / 外发 / 不可逆）+ 代码组合 → allow/review/deny。

| 指标 | v1（宽松 criteria） | v2（收紧 criteria） | 单问句 choice 基线 |
|---|---|---|---|
| 危险命令拦截率 | 85.0% | **100.0%** | 100.0% |
| 正常命令放行率 | 87.3% | **98.2%** | 85.5% |
| 三分类一致率 | 66.2% | **78.5%** | 77.7% |

- 结论：**正交拆分 + 代码组合 > 单问句**——两者都能拦住危险命令，但组合方案的误伤率从 14.5% 降到 1.8%
- v1 的教训：criteria 只写"销毁数据"会漏掉"可用性破坏"（fork bomb/reboot/iptables 锁死），收紧后全部拦到
- 阈值扫描显示 review 档还有 10~12 条错位，属于 review 语义本身模糊，不是阈值问题
- 运行：`../.venv/bin/python run_bash.py --variant v2`

## Harness 实验：工具输出注入扫描（合成，121 条）

构造：80 条注入（zachz + neuralchemy 间接类型）与 41 条良性（仓库文档分片 + 依赖包 LICENSE/METADATA）包进 WebFetch/Read/GitHub/Email 四种工具返回模板。
任务：noul（`tool_output` 是否包含针对助手的指令）。

| 阈值 | 精确率 | 召回率 | F1 | 良性误报率 |
|---|---|---|---|---|
| 0.50 | 97.1% | 85.0% | 90.7% | 4.9% |
| 0.15（最佳 F1） | 93.0% | 100.0% | 96.4% | 14.6% |

- 门控：certainty ≥0.90 时自动处置 62% 流量、准确率 100%
- 漏报集中在**编码绕过**（西里尔同形字、代码片段伪装成 whoami/hash 调用）
- 运行：`../.venv/bin/python run_toolinject.py`

## Harness 实验：模型路由（RouterBench 0-shot，负结果）

数据：RouterBench 825 条分层抽样，oracle = 最便宜的答对模型；标签 = oracle 是否超出 cheap 模型集合。
任务：Jev 判断"小模型能否搞定"，代码据此选 cheap/mid。

| 策略 | 平均质量 | 平均成本 |
|---|---|---|
| 永远 cheap | 42.0% | $0.00005 |
| 永远 mid | 60.9% | $0.00013 |
| 永远 strong | 80.3% | $0.00249 |
| Jev 路由 @0.50 | 42.4% | $0.00005 |
| Jev 路由 @0.05 | 60.8% | $0.00013 |
| oracle（上界） | 100% | $0.00044 |

- **路由判断准确率 51%（无信号）**；分数中位数 0.11，系统性偏向"小模型能搞定"
- 中文任务准确率 14.6%，英文 57.7%——语言短板 + 任务本身难（从 prompt 文本预测"某个小模型会不会错"依赖模型特性，不是自然语言属性）
- 结论：**"预测模型难度"不是 Jev 的合适用法**；若要路由，改成可观察属性更靠谱：代码/长上下文/工具需求、语言与领域、风险等级
- 运行：`../.venv/bin/python run_router.py`

## 真实 harness 数据：InjecAgent 间接注入（1,105 条）

真实数据（17 个用户工具模板 × 62 条攻击指令，含 direct_harm / data_stealing 两类；良性样本用无害文本填同一模板）。

| 阈值 | 精确率 | 召回率 | F1 | 良性误报率 |
|---|---|---|---|---|
| 0.50 | 100.0% | 89.8% | 94.7% | 0.0% |
| 0.10 | **100.0%** | **100.0%** | **100.0%** | 0.0% |

- 分类表现：data_stealing 召回 98.5%、direct_harm 80.6%、良性平均分 0.03
- 门控：certainty ≥0.90 时自动处置 41.1% 流量、准确率 100%
- 成本 $0.0213 / 1105 次，P50 0.30s——**间接注入检测是 Jev 的强项**（注意 InjecAgent 的注入较模板化，enhanced 设置和其他数据集会更难）
- 运行：`../.venv/bin/python run_injecagent.py`

## 真实 harness 数据：BFCL 工具相关性判定（1,140 条，迭代后可用）

任务：给定用户请求 + 可用函数列表，判断"是否至少有一个函数应该被调用"。不可调用样本 1,122 条（classic 240 + live 882），应调用 18 条。

三个版本的迭代对比：

| 版本 | 方法 | classic 准确率 | live_irrelevance 准确率 | live_relevance 准确率 | 整体误报率 @0.5 |
|---|---|---|---|---|---|
| v1 | 单 noul："是否相关" | 84.2% | 59.5% | 94.4% | 35.2% |
| v2 | 收紧 criteria："用途直接匹配，而非技术上可用" | 89.6% | 67.3% | 94.4% | 27.9% |
| v2c | 两步组合：`purpose_match` × (1 − `incidental_only`) | **90.8%** | **77.0%** | 88.9% | **20.1%** |

- v2c 门控：certainty ≥0.95 时自动处置 61.8% 流量、准确率 99.1%；≥0.98 时覆盖 39.5%、准确率 100%
- 失败模式（v1）：**把"技术上能用"当成"语义上该用"**（通用 `requests.get` 被判为相关）
- 结论：这类边界模糊的语义判断，**正交拆分 + 代码组合**再次显著优于单问句（与 Bash 门控实验同一规律）
- 代价：v2c 在 18 条正例上召回从 94.4% 降到 88.9%，适合"宁可少调工具也别乱调"的策略；反之用 v2
- 运行：`../.venv/bin/python run_bfcl.py --variant v2c`

## 真实 harness 数据：SciFact 检索重排（C，成功）

数据：BEIR SciFact，60 个查询 × 15 候选（BM25 top-15 混入标注相关文档），共 900 对；Jev 对每对打 0-3 相关性分后重排。

| 排序器 | Recall@5 | Precision@5 | MRR | nDCG@5 | Hit@1 |
|---|---|---|---|---|---|
| BM25 | 74.2% | 15.7% | 0.622 | 0.632 | 50.0% |
| **Jev 重排** | **90.0%** | **19.3%** | **0.843** | **0.848** | **78.3%** |

- 相关性分数均值：相关文档 2.38 vs 不相关 0.65（区分度好）
- 成本 $0.028 / 900 对，P50 0.31s——**重排是 Jev 的强项**（官方 rerank cookbook 的同类任务）
- 运行：`../.venv/bin/python run_rerank.py --queries 60`

## 真实 harness 数据：Who&When 失败步骤定位（E，负结果）

数据：184 条失败轨迹（Who&When），每条采样 8 步（1 个标注失败步 + 7 个随机步），共 1,403 步。
任务：给定任务 + 单个步骤，判断是否是导致失败的决策性错误。

| 指标 | 结果 | 基线 |
|---|---|---|
| 步骤级 AUROC | 0.560 | 0.5（随机） |
| 轨迹级 top-1 定位 | 16.3% | 12.5%（随机） |
| 失败步均分 vs 普通步 | 0.42 vs 0.37 | — |

- Hand-Crafted 子集好一些（AUROC 0.641），但仍远不可用
- 原因：失败归因是"跨步骤因果 + 长程上下文"任务（失败定义包含"从未被纠正"，必须看后续步骤），不是单步文本里可观察的模式——超出 System One 的定位
- 结论：**不要用 Jev 做长轨迹归因**；如果要做轨迹类任务，应改问"有局部可观察信号"的问题（工具报错、重复动作、格式违规），由 LLM/人工做因果归因
- 运行：`../.venv/bin/python run_whowhen.py`

## 真实 harness 数据：MetaTool 工具/Agent 路由（成功）

数据：MetaTool ToolE（ICLR'24），20,614 条"用户请求 → 正确工具"，目录 199 个工具；每查询取 k 个选项（正确工具 + 干扰项）。

| 选项数 k | 干扰项 | Top-1 准确率 | 随机基线 | conf≥0.8 门控 |
|---|---|---|---|---|
| 5 | 随机 | **98.0%** | 20% | 覆盖 97.5%、准确率 98.5% |
| 5 | 最相似（BM25） | **96.5%** | 20% | 覆盖 97.0%、准确率 97.4% |
| 10 | 随机 | 96.0% | 10% | 覆盖 96.5%、准确率 98.4% |
| 10 | 最相似 | 92.0% | 10% | 覆盖 92.0%、准确率 95.7% |
| 20 | 随机 | 92.5% | 5% | 覆盖 93.5%、准确率 95.2% |
| 20 | 最相似 | 88.5% | 5% | 覆盖 88.5%、准确率 93.8% |

- 对比 MetaTool 论文 similar 子任务：ChatGPT 69.1%、Baichuan2 59.1%、Vicuna-33b 54.0%（评测口径不完全相同，仅作量级参考）
- 错例集中在近义工具对：`VideoSummarizeTool` vs `video_highlight`、`FinanceTool` vs `NewsTool`、`SEOTool` vs `seoanalysis`
- 少数高置信错例（conf 1.0）说明存在真正语义重叠的工具，需在目录描述上做消歧
- 运行：`../.venv/bin/python run_agentroute.py --k 5 --queries 200 --modes random,similar`

## 真实 harness 数据：SkillRet Skill Router（成功）

数据：SkillRet（HF `ThakiCloud/SKILLRET`），6,006 个真实开源 agent skills + 4,997 条查询 + qrels 标注；随机抽 300 条查询。
架构：BM25 召回 top-K → Jev choice 从短名单选一个（与生产 skill router 同构）。

| 配置 | BM25 Hit@1 | 短名单召回 | Jev 端到端 Hit@1 | 条件 Hit@1* |
|---|---|---|---|---|
| k=10，仅名称+描述 | 52.7% | 71.3% | 63.7% | **89.3%** |
| k=10，criteria 带 body | 52.7% | 71.3% | 63.0% | 88.3% |
| k=20，criteria 带 body | 52.7% | 77.3% | 65.3% | 84.5% |
| k=10，**BM25 索引含 body** | 58.3% | 78.7% | **68.3%** | 86.9% |

\* 条件 Hit@1 = 金标 skill 已在短名单内时 Jev 选中的比例。

- 关键结论：**Jev 作为 selector 很强（条件命中 85~89%），瓶颈在召回阶段**——提升检索（body 进索引）直接抬高端到端
- criteria 里塞 body 对 Jev 无增益（说明它按描述判断已足够），但 body 进 BM25 索引有效
- 置信度门控：conf≥0.95 时覆盖 ~53%、准确率 ~83%；conf≥0.99 时覆盖 37%、准确率 90%（可作升级人工的阈值）
- 对比文献：SkillRouter 论文的 1.2B 专用模型在 ~80K 池上 74% top-1；Jev 零训练 + BM25 在 6K 池上 68.3%，而 selector 部分已接近上限
- 运行：`../.venv/bin/python run_skillret.py --k 10 --queries 300 --bm25-with-body`

### 与文献对比（selector 阶段）

| 方案 | 候选集 | Hit@1 | 备注 |
|---|---|---|---|
| GPT-4o-mini（listwise judge） | SkillRouter top-20 | 67.3% | 论文原文："LLM-as-judge baselines are not competitive" |
| GPT-5.4-mini（listwise judge） | 同上 | 66.0% | 同上 |
| Qwen3-Reranker-8B（通用 reranker） | 同上 | 71.4% | base reranker |
| SkillRouter 1.2B（专用微调流水线） | 同上 | **74.0%** | ~80K 池，13x 更小/5.8x 更快 |
| R3（腾讯，专用微调，中英双语） | R3-Skill | **77.1%** | NDCG@10 0.833 |
| SkillRet-Reranker-0.6B（专用微调） | SkillRet top-20 | 82.2 NDCG@10（Recall@10 87.6%） | 通用 reranker 在强一阶段下反而掉点（83.5→74~78 NDCG@10） |
| **Jev（零样本，本评测）** | BM25 top-10（6K 池） | **条件 Hit@1 86.9~89.3%** | 口径不同：条件=金标在短名单内；池更小、候选更少 |

**结论（谨慎口径）**：

- 同一候选集下，**通用 LLM judge 明显弱于专用微调重排器**（67.3% vs 74.0%）——说明"让通用模型排序"本身不够看
- Jev 的条件命中率（86.9~89.3%）与专用重排器报告水平**同档或更高**，且零样本、无训练；但池规模（6K vs 80K）、候选数（10 vs 20）、数据集和指标口径均不同，严格结论需要跑同一候选集
- SkillRet 的发现对架构有直接影响：**强一阶段会压缩通用重排器的增益甚至造成掉点**；若把 Jev 接在强 embedding 召回后面，其边际价值需要重新测

## 真实 harness 数据：SkillRetBench 同数据集对比（重大结果）

数据：`thaki-AI/SkillRetBench` —— **501 个 skills 全库、1,250 条查询、5 种设置**，官方附带 baseline 结果（BM25/Dense/Hybrid/NaiveLLM/SADO），指标口径统一。Jev 变体：
- `chunked`：501 个候选分 5 块（API 上限 255 选项）逐块选择 + `none`，概率合并排名
- `bm25top50`：BM25 召回 top-50 → Jev 选择（生产同构、便宜）

每设置 100 条，**同数据集同指标**对比（macro 平均）：

| 指标 | BM25（最强真实检索） | NaiveLLM（官方 LLM 基线） | Jev chunked | **Jev hybrid（推荐）** |
|---|---|---|---|---|
| Recall@1 | 38.0% | 30.2% | 60.4% | **75.8%** |
| Recall@3 | 49.2% | 40.4% | 75.4% | **87.6%** |
| Recall@10 | 59.8% | 55.6% | 87.6% | **93.0%** |
| nDCG@10 | 53.4% | 45.1% | 60.3% | **70.2%** |
| MRR@10 | 57.3% | 50.0% | 69.3% | **82.4%** |
| 成本（500 条） | — | — | $0.606 | $0.650 |

**hybrid 变体（推荐架构）**：分块 choice 取每块 top-3（15 候选，竞争性概率）→ 对这 15 个候选逐一问 noul"是否该进集合"（一次请求 15 问）→ 按 noul 合并。三级演进：

| 设置 R@1 | chunked（纯单选） | multiselect（全库逐问 noul） | **hybrid（choice+noul）** | 最佳基线 |
|---|---|---|---|---|
| single_skill | 65.0% | — | 69.0% | 49.5% |
| **multi_skill_composition** | 9.0% | 15.0% | **81.0%** | 32.7% |
| distractor | 66.0% | — | 74.0% | 27.0% |
| outdated_redundant | 84.0% | — | 92.0% | 86.7% |
| budget_constrained | 78.0% | — | 63.0% | 8.4% |

- **多技能组合从 9% 修到 81%**：教训是"逐问 noul 缺竞争性"（分数全在 0.5x，排名变噪声），必须**先 competition（choice）再 verification（noul）**
- Set completeness（全部金标进集合）：multi 25%、single 65%、outdated 91%——组合场景的"选全"仍是弱项，但 top-10 口径已全面领先
- 语言拆分：韩语 R@1 48.9%（n=45） vs 英语 61.5%（chunked 口径）——非英语折扣复现
- 注意：官方 README 声明 NaiveLLM/SADO 可能是**模拟基线**（无真实 API 调用），对比仅作参考；BM25/Dense/Hybrid 为真实检索器

- 中文注入样本小规模摸底（Jev 英语为主）
