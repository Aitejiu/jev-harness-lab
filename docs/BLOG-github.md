# Jev 工程评测：决策模型在 Agent Harness 中的应用边界

> **版本**：`jev-1.13.0` · **日期**：2026-09 · **代码与原始数据**：[github.com/Aitejiu/jev-harness-lab](https://github.com/Aitejiu/jev-harness-lab)
>
> 本文是一份黑盒工程评测记录：在 10 个公开数据集上、以约 22,500 次 API 调用（52.2M input tokens，总成本 $2.19）测得的 Jev 能力边界、适用场景、工程规律与复现方法。

---

## 摘要

Jev 是 TypeSafe AI 的 System One 决策模型：输入 `state` + 类型化 `questions`，输出带概率与置信度的结构化判断，不生成文本。本次评测覆盖 7 类任务，结论：

**适合（可直接用于 agent harness）**

| 能力 | 数据集 | 关键结果 |
|---|---|---|
| 间接注入检测 | InjecAgent（1,105 条） | 阈值 0.10：精确率/召回率 **100%**，良性误报 0% |
| 检索重排 | BEIR SciFact（900 对） | BM25 → Jev：MRR **0.622 → 0.843**，Hit@1 **50% → 78.3%** |
| 意图分类 | SNIPS / Banking77 | 7 类 **97.9%** / 77 类 **80.3%** |
| 工具目录路由 | MetaTool（199 工具） | 相似干扰 k=5 **96.5%** |
| Skill 路由 | SkillRetBench（501 skills） | hybrid 架构 R@1 **75.8%**（最强基线 38.0%） |
| 命令风险门控 | 自建 130 条 | 危险拦截 **100%**、正常放行 **98.2%** |
| 工具相关性判定 | BFCL（1,140 条） | 两段式后 live 准确率 **77.0%**（初版 59.5%） |

**不适合（负结果）**

| 任务 | 结果 | 原因 |
|---|---|---|
| 模型难度路由 | RouterBench：准确率 **51%**（无信号） | 需要预测"另一个模型会不会错"，属元推理 |
| 长轨迹失败归因 | Who&When：AUROC **0.560** ≈ 随机 | 需要跨步骤因果与长上下文 |
| 非英语任务 | 韩语 R@1 48.9% vs 英语 61.5%；中文路由 14.6% vs 英语 57.7% | 官方明示英语为主 |

**核心工程结论（两条）**

1. 边界模糊的语义判断，**正交拆分 + 代码组合**显著优于单问句（命令门控误伤率 14.5% → 1.8%；工具相关性 59.5% → 77.0%）。
2. 多标签判断遵循 **先 competition（choice 竞争出候选），再 verification（noul 验证集合成员）**，SkillRetBench 多技能组合 R@1 从 9.0% 提升到 81.0%。

> 一句话：**模型提供校准过的局部判断，代码持有控制流。**

---

## 1. 背景与对象

### 1.1 为什么关注"决策模型"

Agent harness 的循环里充满高频、边界明确的窄判断：输入是否安全、请求属于哪类、该加载哪个 skill、命令能否执行、哪些片段进入上下文。若每个判断都调用前沿大模型，延迟与成本不可接受。Jev 的定位是这些判断的"快思考层"（System One）。

### 1.2 Jev 的接口形态

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer $TYPESAFE_API_KEY

{
  "state": "...",                // 字符串 / 对象 / 数组，仅文本
  "model": "jev-latest",
  "questions": { "..." : Question }
}
```

| 原语 | 语义 | 返回字段 |
|---|---|---|
| `noul` | 是/否 | `noul`：0~1 概率（**无 confidence 字段**） |
| `choice` | 闭集单选 | `choice` + `probabilities` + `confidence` |
| `score` | 有序 rubric 评分 | `score`（概率加权，可取小数）+ `legend` + `probabilities` + `confidence` |

### 1.3 已知限制（评测中均验证）

- `choice` 选项上限 **255**；超出需分块或两阶段（SkillRouterBench 即使用 5×~101 分块）。
- `state` + `questions` 共享约 **32k tokens**；语料规模大时必须先检索。
- **仅文本**输入；主训练语言为英语。
- 参考成本：$42 / billion input tokens；实测单次调用 P50 约 0.3s、约 $0.00004。

---

## 2. 评测方法

### 2.1 框架

统一流程（`eval/` 目录，全部脚本开源）：

```
数据集加载 → 构造 state/questions → 并发调用（JSONL 缓存，可断点续跑）
          → 指标计算（阈值扫描 / 覆盖率曲线 / 校准 / 成本）→ Markdown 报告
```

### 2.2 指标定义（重要，避免口径混淆）

- **阈值扫描**：将 `noul` 概率或 `choice` 概率作为分数，扫描判定阈值，报告 precision / recall / F1 / FPR。
- **置信度门控曲线**：`noul` 无 confidence 字段，采用 `certainty = max(p, 1-p)` 代理；低于阈值视为"不确定 → 转人工"，输出**覆盖率 vs 覆盖内准确率**。
- **条件 Hit@1**（SkillRet 实验）：金标候选在短名单内时，模型选中金标的比例；用于隔离"选择器"能力与"召回"能力。
- **macro 平均**（SkillRetBench）：对 5 个设置分别计算后取算术平均。
- **成本**：按 usage.input_tokens × $42/B 估算（不含输出 token 计费项，若官方另行计费则实际略高）。

### 2.3 数据集清单

| 数据集 | 规模 | 用途 | 来源 |
|---|---|---|---|
| InjecAgent | 1,054 注入 + 51 良性 | 间接注入检测 | GitHub `uiuc-kang-lab/InjecAgent` |
| neuralchemy prompt-injection | 942 | 注入检测（对照） | HF `neuralchemy/Prompt-injection-dataset` |
| 合成工具输出注入 | 80 注入 + 41 良性 | 注入检测（工具输出包装） | 本仓库构造 |
| BEIR SciFact | 60 查询 × 15 候选 | 检索重排 | BEIR / SciFact |
| SNIPS | 1,400 | 意图分类（7 类） | HF `benayas/snips` |
| Banking77 | 3,080 | 意图分类（77 类） | `PolyAI-LDN/task-specific-datasets` |
| MetaTool ToolE | 20,614 查询 / 199 工具 | 工具路由 | GitHub `HowieHwong/MetaTool` |
| BFCL v3 | 1,140（irrelevance/relevance） | 工具相关性判定 | HF `gorilla-llm/Berkeley-Function-Calling-Leaderboard` |
| SkillRet | 6,006 skills / 300 查询 | Skill 召回+选择 | HF `ThakiCloud/SKILLRET` |
| SkillRetBench | 501 skills / 1,250 查询 | Skill 路由（含官方基线） | HF `thaki-AI/SkillRetBench` |
| RouterBench | 825 抽样 | 模型难度路由（负） | HF `withmartian/routerbench` |
| Who&When | 184 轨迹 × 8 步 | 失败步骤归因（负） | GitHub `ag2ai/Agents_Failure_Attribution` |
| 自建 shell 命令集 | 130（allow 55/review 35/deny 40） | 命令风险门控 | 本仓库 `eval/datasets/bash_commands.jsonl` |

---

## 3. 实验与结果

### 3.1 间接注入检测

**InjecAgent（真实数据：17 个用户工具 × 62 条攻击指令）**

| 阈值 | 精确率 | 召回率 | F1 | 良性误报率 |
|---|---|---|---|---|
| 0.50 | 100% | 89.8% | 94.7% | 0% |
| **0.10** | **100%** | **100%** | **100%** | **0%** |

- 分类型召回（阈值 0.5）：data_stealing 98.5%、direct_harm 80.6%；良性样本均分 0.03。
- 门控：certainty ≥ 0.90 时自动处置 41.1% 流量，覆盖内准确率 100%。
- 成本 $0.0213 / 1,105 次；P50 0.30s、P95 0.41s。

**合成工具输出（把注入文本包进 WebFetch/Read/GitHub/Email 返回模板）**

| 阈值 | 精确率 | 召回率 | F1 | 良性误报率 |
|---|---|---|---|---|
| 0.50 | 97.1% | 85.0% | 90.7% | 4.9% |
| 0.15（最佳 F1） | 93.0% | 100% | 96.4% | 14.6% |

- 漏报集中在**编码绕过**（西里尔同形字、代码片段伪装）。
- certainty ≥ 0.90：覆盖率 62.0%、覆盖内准确率 100%。

**对照：neuralchemy（任务不匹配的教训）**

| 阈值 | 精确率 | 召回率 | F1 | 良性误报率 |
|---|---|---|---|---|
| 0.50 | 97.4% | 55.1% | 70.4% | 2.1% |
| 0.05（最佳 F1） | 95.6% | 94.2% | 94.9% | — |

该数据集将"请求有害内容"也标为恶意，而我们的 criteria 只问"是否覆盖/提取系统指令"——召回低的主因是**任务定义不匹配**，而非能力上限。另注意校准：0~0.1 分桶中仍有 16.6% 恶意样本，**低分不等于安全**。

### 3.2 检索重排（BEIR SciFact）

60 查询 × 15 候选（BM25 top-15 内混入标注相关文档），Jev 对每个 (query, document) 打 0-3 相关性分后重排：

| 排序器 | Recall@5 | Precision@5 | MRR | nDCG@5 | Hit@1 |
|---|---|---|---|---|---|
| BM25 | 74.2% | 15.7% | 0.622 | 0.632 | 50.0% |
| **Jev** | **90.0%** | **19.3%** | **0.843** | **0.848** | **78.3%** |

- 相关文档均分 2.38 vs 不相关 0.65。
- 成本 $0.028 / 900 对；P50 0.31s。

### 3.3 意图与目录路由

| 数据集 | 类别/目录 | Top-1 | Top-3 | 门控 |
|---|---|---|---|---|
| SNIPS（1,400） | 7 类 | **97.9%** | 99.7% | conf≥0.90：覆盖 93.6%、准确率 99.1% |
| Banking77（3,080） | 77 类 | **80.3%** | 91.7% | conf≥0.90：覆盖 67.8%、准确率 92.8%；conf≥0.99：46.1% / 97.0% |

**MetaTool（199 工具目录，干扰项用 BM25 选最相似工具）**

| 选项数 k | 随机干扰 Top-1 | 相似干扰 Top-1 | 随机基线 |
|---|---|---|---|
| 5 | 98.0% | **96.5%** | 20% |
| 10 | 96.0% | 92.0% | 10% |
| 20 | 92.5% | 88.5% | 5% |

- 参考：MetaTool 论文 similar 子任务 ChatGPT 69.1%、Baichuan2 59.1%、Vicuna-33b 54.0%（评测口径不完全相同，量级参考）。
- 错例集中在近义工具对（如 `VideoSummarizeTool` vs `video_highlight`），少量高置信错误——**目录描述需显式写边界（not_for）**。

### 3.4 命令风险门控（自建 130 条）

设计：4 个正交 `noul`（破坏性 / 触密 / 外发 / 不可逆）+ 代码组合决策（deny/review/allow）。

| 方案 | 三分类一致率 | 危险命令拦截率 | 正常命令放行率 |
|---|---|---|---|
| v1（宽松 criteria） | 66.2% | 85.0% | 87.3% |
| **v2（收紧 criteria）** | 78.5% | **100%** | **98.2%** |
| 单问句 choice 基线 | 77.7% | 100% | 85.5% |

- v1 漏掉"可用性破坏"类（fork bomb、reboot、iptables 锁死）；criteria 补上"失去可用性"后全部拦截。
- 阈值网格搜索最优三分类一致率仅 79.2%——余下误差来自 review 语义本身的模糊，非阈值问题。
- **正交拆分的收益体现在误伤率**：14.5% → 1.8%。

### 3.5 工具相关性判定（BFCL，三版迭代）

任务：给定用户请求 + 函数列表，判断"是否至少有一个函数应被调用"。样本 1,140（不可调用 1,122 / 应调用 18）。

| 版本 | 方法 | classic 准确率 | live_irrelevance 准确率 | 整体误报率 |
|---|---|---|---|---|
| v1 | 单 noul："是否相关" | 84.2% | 59.5% | 35.2% |
| v2 | criteria 收紧为"用途直接匹配" | 89.6% | 67.3% | 27.9% |
| **v2c** | 两步组合：`purpose_match × (1 − incidental_only)` | **90.8%** | **77.0%** | **20.1%** |

- v2c 门控：certainty ≥ 0.95 → 覆盖率 61.8%、覆盖内准确率 99.1%；≥ 0.98 → 39.5% / 100%。
- 典型失败模式："技术上能用"被当成"语义上该用"（通用 `requests.get` 被判相关）。

### 3.6 Skill Router（SkillRet + SkillRetBench）

**背景**：skill 目录持续膨胀，全部注入主模型上下文既昂贵又干扰。目标：请求进入时用一次 Jev 判断"加载哪个 skill"。

**SkillRet（6,006 skills，300 查询）——隔离召回与选择**

| 配置 | BM25 Hit@1 | 短名单召回 | Jev 端到端 Hit@1 | 条件 Hit@1* |
|---|---|---|---|---|
| k=10 仅名称+描述 | 52.7% | 71.3% | 63.7% | **89.3%** |
| k=10 criteria 带 body | 52.7% | 71.3% | 63.0% | 88.3% |
| k=20 criteria 带 body | 52.7% | 77.3% | 65.3% | 84.5% |
| k=10 **BM25 索引含 body** | 58.3% | 78.7% | **68.3%** | 86.9% |

\* 条件 Hit@1 = 金标在短名单内时选中比例。结论：**选择器强（85~89%），瓶颈在召回**；把 body 加入检索索引直接抬高端到端。

**SkillRetBench（501 skills、5 设置 × 100 查询，与官方基线同口径）**

| 指标（macro） | BM25 | Dense | Hybrid | NaiveLLM | SADO | Jev chunked | **Jev hybrid** |
|---|---|---|---|---|---|---|---|
| Recall@1 | 38.0% | 11.8% | 22.8% | 30.2% | 26.6% | 60.4% | **75.8%** |
| Recall@3 | 49.2% | 22.2% | 33.0% | 40.4% | 36.8% | 75.4% | **87.6%** |
| Recall@10 | 59.8% | 36.5% | 48.2% | 55.6% | 52.0% | 87.6% | **93.0%** |
| nDCG@10 | 53.4% | 26.8% | 39.1% | 45.1% | 42.9% | 60.3% | **70.2%** |
| MRR@10 | 57.3% | 29.1% | 42.5% | 50.0% | 46.8% | 69.3% | **82.4%** |

（部分官方基线为模拟实现，见 SkillRetBench 数据集说明；BM25/Dense/Hybrid 为真实检索器。）

**三版架构建模（多技能组合是分水岭）**

| 设置 R@1 | v1 chunked（每块单选） | v2 multiselect（逐候选 noul） | **v3 hybrid（choice → noul 验证）** |
|---|---|---|---|
| single_skill | 65.0% | — | 69.0% |
| **multi_skill_composition** | **9.0%** | 15.0% | **81.0%** |
| distractor | 66.0% | — | 74.0% |
| outdated_redundant | 84.0% | — | 92.0% |
| budget_constrained | 78.0% | — | 63.0% |

- v2 失败的诊断：逐问 `noul` 分数集中在 0.5x（top10 均分 0.56），**独立打分缺竞争性，合并排名成为噪声**。
- v3 结构：分块 `choice` 取每块 top-3（15 候选，概率有区分度）→ 一次请求内对 15 个候选逐问 `noul`"是否入集合" → 合并排序。
- Set completeness（全部金标进入集合）：single 65%、multi 25%、outdated 91%——**"选全"仍是弱项**，下一步方向。
- 成本：hybrid $0.650 / 500 查询、P50 2.07s；生产同构的 bm25top50 $0.072 / 500 查询、P50 0.33s（R@1 54.8%）。

### 3.7 负结果

**模型难度路由（RouterBench，825 条）**

| 策略 | 平均质量 | 平均成本 |
|---|---|---|
| 永远 cheap | 42.0% | $0.00005 |
| 永远 strong | 80.3% | $0.00249 |
| Jev 路由 @0.50 | 42.4% | $0.00005 |

- 判断准确率 **51.3%**（无信号）；分数中位数 0.11，系统性偏向"小模型能搞定"。
- 语言拆分：中文任务 14.6%（n=123） vs 英文 57.7%（n=702）。
- 结论：从文本预测"某个具体模型会不会错"依赖模型特性，**不是自然语言属性**。

**长轨迹失败归因（Who&When，184 轨迹 × 8 步 = 1,403 步）**

| 指标 | 结果 | 随机基线 |
|---|---|---|
| 步骤级 AUROC | 0.560 | 0.5 |
| 轨迹级 top-1 定位 | 16.3% | 12.5% |
| 失败步均分 vs 普通步 | 0.42 vs 0.37 | — |

- 子集拆分：Algorithm-Generated 0.532 / Hand-Crafted 0.641，均不可用。
- 失败定义包含"从未被纠正"，需要跨步骤因果推理——超出 System One 的形态。轨迹类任务若要使用 Jev，应改问**局部可观察信号**（工具报错、重复动作、格式违规）。

---

## 4. 与公开基准/文献的对照

**同候选集对比（SkillRouter 论文，~80K skills，top-20 候选）**

| 方案 | Hit@1 | 性质 |
|---|---|---|
| GPT-4o-mini（listwise judge） | 67.3% | 通用 LLM 直接排序 |
| GPT-5.4-mini（listwise judge） | 66.0% | 同上 |
| Qwen3-Reranker-8B | 71.4% | 通用 reranker |
| SkillRouter 1.2B | **74.0%** | 专用微调流水线 |
| R3（腾讯，中英双语） | **77.1%** | 专用微调（R3-Skill 上 NDCG@10 0.833） |

论文原话：LLM-as-judge 基线 "not competitive"。**通用大模型直接排序弱于专用重排器**；Jev 零样本、无训练，条件命中 86.9~89.3%（池规模与指标口径不同，仅作同档参考）。

**SkillRet 论文重排实验（top-20 候选，nDCG@10）**：jina-reranker-v2 73.1、Qwen3-Reranker-0.6B/4B/8B 75.8~76.2、SkillRouter-Reranker 81.9、SkillRet-Reranker 82.2。重要发现：**通用 reranker 接在强一阶段之后会掉点**（83.45 → 74~78）——若将 Jev 接强 embedding 召回，其边际价值需重测。

---

## 5. 工程规律（六条）

1. **criteria 即决策边界**。同一句话："physical harm **or retaliation**"混合 criteria 得 0.47 的模糊概率；拆成两个正交问题后为 0.04 / 0.96。
2. **正交拆分 + 代码组合优于单问句**。命令门控误伤 14.5% → 1.8%；工具相关性 live 59.5% → 77.0%。
3. **高分区可信，低分区不等于安全**。注入检测 ≥0.1 分样本 90%+ 为恶意，但 0~0.1 分桶仍有 16.6% 恶意——生产策略必须保留人工复核带。
4. **confidence ≠ correctness**。高置信只表示模型确信其在按你的定义判断；criteria 有误时同样自信（评测中出现 conf=1.0 的错误路由）。
5. **多标签：先 competition 后 verification**（见 §3.6）。独立 `noul` 组硬打会把"模糊相关"与"真正需要"混在一起。
6. **能力边界纪律**。只问文本中局部可观察的模式；不问模型能力（51%），不问跨步因果（AUROC 0.56）。

---

## 6. 集成与工具化

仓库提供两个可直接使用的集成（均为本次评测的直接产物）：

**MCP Server**（`mcp_server.py`，stdio）

| 工具 | 输入 → 输出 | 实测 |
|---|---|---|
| `scan_injection` | tool_output → `action`(block/review/pass) + 概率 | 注入文本 → block，p=0.98 |
| `bash_risk` | command → `action` + 四维分数 | `rm -rf /` → deny |
| `rank_candidates` | query + candidates(≤10) → 排序 | 密码重置文档排第一 |

**Skill Router**（`skill_router.py` + opencode 插件 `integrations/opencode/jev-skill-router.ts`）
请求进入时用 Jev 从本地 skill 目录选一个并返回完整 SKILL.md；参考配置 `agent.build.tools.skill = false`（主模型上下文不再携带 skill 目录）。本地 35 个 skill 的中文查询路由全部正确，无匹配时正确返回"无需 skill"。

---

## 7. 复现指南

```bash
git clone https://github.com/Aitejiu/jev-harness-lab
cd jev-harness-lab
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
echo "TYPESAFE_API_KEY=<your-key>" > .env
```

数据下载（脚本内注释含来源；`eval/data/` 已 gitignore）：

- InjecAgent / neuralchemy / SNIPS / Banking77 / MetaTool / SkillRet / SkillRetBench / RouterBench / Who&When：按 `eval/README.md` 中对应小节下载；
- 自建数据集（shell 命令集）已随仓库提交。

运行示例：

```bash
# 注入检测（InjecAgent）
.venv/bin/python eval/run_injecagent.py --concurrency 6
# 检索重排
.venv/bin/python eval/run_rerank.py --queries 60
# 命令风险门控（v2）
.venv/bin/python eval/run_bash.py --variant v2
# Skill Router（同数据集对比，hybrid 架构）
.venv/bin/python eval/run_skillretbench.py --variant hybrid --per-setting 100
```

结果缓存在 `eval/results/*.jsonl`（已提交），重复运行只补缺失样本；加 `--report-only` 可直接用缓存重新生成报告。

---

## 8. 局限与版本说明

- 结论基于 **`jev-1.13.0`** 单一版本；模型更新后建议按本文流程复测。
- 部分数据集为抽样或自建（shell 命令集 130 条、合成注入 121 条、SciFact 60 查询），存在选择偏差。
- 阈值均为评测参考值，生产阈值必须在自有数据上标定（建议用覆盖率-准确率曲线选点）。
- 成本按 input token 估算；若官方对 output token 单独计费，实际成本略高。
- 英语为主：中文/韩文任务在放量前需专项验证。
- SkillRetBench 的 NaiveLLM/SADO 基线为模拟实现（数据集方声明），对比仅作参考。

---

## 附录：关键源文件

| 内容 | 文件 |
|---|---|
| 注入检测 | `eval/run_injecagent.py`、`eval/run_toolinject.py` |
| 检索重排 | `eval/run_rerank.py` |
| 意图/目录路由 | `eval/run_intent.py`、`eval/run_agentroute.py` |
| 命令门控 | `eval/run_bash.py`、`eval/datasets/bash_commands.jsonl` |
| 工具相关性 | `eval/run_bfcl.py` |
| Skill 路由 | `eval/run_skillret.py`、`eval/run_skillretbench.py` |
| 负结果 | `eval/run_router.py`、`eval/run_whowhen.py` |
| 全线报告 | `eval/results/*.md`（24 份） |
| 集成 | `mcp_server.py`、`skill_router.py`、`integrations/opencode/` |

**数据集与参考**

- InjecAgent：https://github.com/uiuc-kang-lab/InjecAgent
- BEIR SciFact：https://github.com/beir-cellar/beir
- MetaTool：https://github.com/HowieHwong/MetaTool
- BFCL：https://gorilla.cs.berkeley.edu/leaderboard.html
- SkillRet：https://huggingface.co/datasets/ThakiCloud/SKILLRET
- SkillRetBench：https://huggingface.co/datasets/thaki-AI/SkillRetBench
- RouterBench：https://huggingface.co/datasets/withmartian/routerbench
- Who&When：https://github.com/ag2ai/Agents_Failure_Attribution
- SkillRouter 论文：arXiv:2603.22455
- R3-Skill 论文：arXiv:2606.03565
- TypeSafe 文档：https://docs.typesafe.ai
