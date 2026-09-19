# Jev 技术评估报告

**模型**：TypeSafe AI Jev（`jev-latest` → `jev-1.13.0`）
**评估时间**：2026-09
**评估方式**：harness 化评测（`eval/`），全部使用公开数据集或可复现的构造数据，共 **~22,500 次 API 调用 / 52.2M input tokens ≈ $2.19**

---

## 摘要

Jev 是一个"决策模型"而非生成模型：输入 `state` + 类型化 `questions`，输出带概率与置信度的结构化判断。本次评估覆盖 7 个任务族，结论如下：

**强项（可直接用于 agent harness）**

| 能力 | 关键结果 | 证据 |
|---|---|---|
| 间接注入检测 | InjecAgent 真实数据：阈值 0.1 时 **P100% / R100% / FPR 0** | 1,105 条 |
| 检索重排 | BM25 → Jev：**MRR 0.622→0.843，Hit@1 50%→78.3%** | SciFact 900 对 |
| 意图分类 | 7 类 **97.9%**；77 类 **80.3%**（接近强 LLM 教师） | SNIPS / Banking77 |
| 命令风险门控 | 危险拦截 **100%**、正常放行 **98.2%** | 130 条构造命令 |
| Agent/工具路由 | 199 个工具目录，k=5 相似干扰 **96.5%**、k=20 仍 **88.5%** | MetaTool 1,200 条 |
| Skill Router | 6,006 个真实 skills：selector 条件命中 **85~89%**，端到端 **68.3%**（BM25 58.3%） | SkillRet 1,200 条 |
| Skill Router（同数据集） | SkillRetBench 501 库：R@1 **75.8%**，为最强基线（BM25 38.0%）的 **2 倍** | SkillRetBench 500 条 |
| 工具相关性判定 | 两步组合迭代后 live 准确率 **77.0%** | BFCL 1,140 条 |
| 抽取校验 | 字段级校验 + 结构化 instructions（demo 级） | 发票示例 |

**弱项（避免使用或必须重构问法）**

- 模型难度路由（RouterBench 准确率 51%，无信号）
- 长轨迹失败归因（Who&When AUROC 0.56 ≈ 随机）
- 中文任务（RouterBench 中文子集 14.6% vs 英文 57.7%）
- 长上下文（>32k）与跨步因果推理

**核心工程规律**：Jev 擅长**文本中局部可观察的模式判断**；凡是需要"跨步骤/跨时间/对模型自身能力的元推理"的任务，都不适合它。

---

## 1. 评估方法

- **框架**：`eval/`，统一流程 = 数据集加载 → 构造 state/questions → 并发调用（JSONL 缓存）→ 指标报告
- **指标口径**：
  - 阈值扫描（precision/recall/F1/FPR）
  - **置信度门控曲线**：`certainty = max(p, 1-p)`（noul 无 confidence 字段，用概率极端程度代理），输出"自动处理覆盖率 vs 准确率"
  - 校准（分数分桶 vs 实际比例）、延迟 P50/P95、input token 成本（$42/B）
- **规模**：13,616 次调用、$0.45、单次 P50 约 0.3s

---

## 2. 强项详述

### 2.1 间接注入检测（护栏）— 最强项

**InjecAgent（真实数据，1,105 条 = 1,054 注入 + 51 良性）**

| 阈值 | 精确率 | 召回率 | F1 | 良性误报率 |
|---|---|---|---|---|
| 0.50 | 100% | 89.8% | 94.7% | 0% |
| 0.10 | **100%** | **100%** | **100%** | **0%** |

- 分类表现：data_stealing 召回 98.5%、direct_harm 80.6%、良性均分 0.03
- 门控：certainty ≥0.90 → 自动处置 41.1% 流量、准确率 100%
- 成本 $0.0213 / 1,105 次，P50 0.30s

**合成工具输出注入（121 条，包装成 WebFetch/Read/GitHub/Email 返回）**

- 阈值 0.5：P97.1 / R85.0 / F1 90.7 / FPR 4.9%
- 漏报集中在**编码绕过**（西里尔同形字、代码片段伪装）
- certainty ≥0.90 → 覆盖率 62%、准确率 100%

**neuralchemy 注入检测（942 条）**：该数据集把"请求有害内容"也标为恶意，而 criteria 只问"覆盖/提取系统指令"，任务不匹配导致召回低（55.1%@0.5）。**这本身是一次 criteria 边界教训**，非能力上限。

### 2.2 检索重排 — 强项

**SciFact（BEIR），60 查询 × 15 候选 = 900 对**

| 排序器 | Recall@5 | Precision@5 | MRR | nDCG@5 | Hit@1 |
|---|---|---|---|---|---|
| BM25 | 74.2% | 15.7% | 0.622 | 0.632 | 50.0% |
| **Jev 重排** | **90.0%** | **19.3%** | **0.843** | **0.848** | **78.3%** |

- 相关文档均分 2.38 vs 不相关 0.65，区分度良好
- $0.028 / 900 对，P50 0.31s；适合作为 RAG/上下文选择的精排层

### 2.3 意图分类 — 强项

| 数据集 | 类别数 | Top-1 | Top-3 | 门控 |
|---|---|---|---|---|
| SNIPS（1,400 条） | 7 | **97.9%** | 99.7% | conf≥0.90：覆盖 93.6%、准确率 99.1% |
| Banking77（3,080 条） | 77 | **80.3%** | 91.7% | conf≥0.90：覆盖 67.8%、准确率 92.8%；conf≥0.99：46.1% / 97.0% |

- 参考：41 个开源模型零样本平均约 38.8%、Sonnet 教师约 81%（口径不同）——Jev 在 77 类上接近强 LLM 教师，成本低 2–3 个数量级
- 最差类别为成对混淆（`get_physical_card` 0% vs `order_physical_card` 12.5%），属 criteria 边界未划清，可通过 rubric 修复

### 2.4 命令风险门控 — 强项

数据集：130 条 shell 命令（allow 55 / review 35 / deny 40），4 个正交 noul（破坏性 / 触密 / 外发 / 不可逆）+ 代码组合。

| 指标 | v1 | v2（收紧 criteria） | 单问句基线 |
|---|---|---|---|
| 危险命令拦截率 | 85.0% | **100%** | 100% |
| 正常命令放行率 | 87.3% | **98.2%** | 85.5% |
| 三分类一致率 | 66.2% | 78.5% | 77.7% |

- 同样能拦住危险命令，**组合方案误伤率从 14.5% 降到 1.8%**
- v1 漏掉"可用性破坏"类（fork bomb/reboot/iptables）；criteria 补上"失去可用性"后全部拦截

### 2.5 工具相关性判定（BFCL）— 迭代后可用

任务：给定用户请求 + 可用函数列表，判断"是否至少有一个函数应被调用"（1,122 不可调用 / 18 应调用）。

| 版本 | 方法 | classic | live_irrelevance | 整体误报率 |
|---|---|---|---|---|
| v1 | 单 noul："是否相关" | 84.2% | 59.5% | 35.2% |
| v2 | criteria 收紧为"用途直接匹配" | 89.6% | 67.3% | 27.9% |
| **v2c** | 两步组合 `purpose × (1−incidental)` | **90.8%** | **77.0%** | **20.1%** |

- v2c 门控：certainty ≥0.95 → 覆盖率 61.8%、准确率 99.1%
- 失败模式：把"技术上能用"当成"语义上该用"（通用 `requests.get` 被判相关）

### 2.6 Agent/工具路由（MetaTool）— 强项

**条件：目录已知**（199 个工具，每个带描述），判断请求该路由给哪个工具/agent。每查询 k 个选项（正确工具 + 干扰项），干扰项分随机与最相似（BM25 over descriptions）。

| 选项数 k | 干扰项 | Top-1 准确率 | 随机基线 | conf≥0.8 门控 |
|---|---|---|---|---|
| 5 | 随机 | **98.0%** | 20% | 覆盖 97.5%、准确率 98.5% |
| 5 | 最相似 | **96.5%** | 20% | 覆盖 97.0%、准确率 97.4% |
| 10 | 随机 | 96.0% | 10% | 覆盖 96.5%、准确率 98.4% |
| 10 | 最相似 | 92.0% | 10% | 覆盖 92.0%、准确率 95.7% |
| 20 | 随机 | 92.5% | 5% | 覆盖 93.5%、准确率 95.2% |
| 20 | 最相似 | 88.5% | 5% | 覆盖 88.5%、准确率 93.8% |

- 对比 MetaTool 论文 similar 子任务：ChatGPT 69.1%、Baichuan2 59.1%、Vicuna-33b 54.0%（口径不完全相同，作量级参考）
- 与 3.1 模型路由对比：**"选哪个 agent"（语言语义判断）是强项；"哪个模型能答对"（能力边界预测）是弱项**
- 错例集中在近义工具对（`VideoSummarizeTool` vs `video_highlight`、`FinanceTool` vs `NewsTool`）；存在少量高置信错例，需在工具描述里显式写界

### 2.7 Skill Router（SkillRet）— 强项（selector 阶段接近上限）

数据：SkillRet 6,006 个真实开源 skills，300 条查询（含 qrels），两阶段 = BM25 召回 top-K → Jev choice 选择。

| 配置 | BM25 Hit@1 | 短名单召回 | Jev 端到端 | 条件 Hit@1* |
|---|---|---|---|---|
| k=10，仅名称+描述 | 52.7% | 71.3% | 63.7% | **89.3%** |
| k=10，criteria 带 body | 52.7% | 71.3% | 63.0% | 88.3% |
| k=20，criteria 带 body | 52.7% | 77.3% | 65.3% | 84.5% |
| k=10，BM25 索引含 body | 58.3% | 78.7% | **68.3%** | 86.9% |

\* 条件 Hit@1 = 金标 skill 在短名单内时 Jev 选中的比例。

- **瓶颈在召回不在选择**：Jev 的选择条件命中稳定 85~89%，提升检索（body 进 BM25 索引）直接抬高端到端
- criteria 里加 body 对 Jev 无增益（描述已足够），但 body 进检索索引有效——与 SkillRouter 论文"body 是检索关键信号"一致
- 对比：SkillRouter 论文 1.2B 专用模型 ~80K 池上 74% top-1；Jev 零训练 + BM25 6K 池 68.3%，selector 部分接近该架构上限
- 置信度门控：conf≥0.95 覆盖 ~53% / 准确率 ~83%；conf≥0.99 覆盖 37% / 准确率 90%

**与文献对比（selector 阶段）**：

| 方案 | 候选集 | Hit@1 |
|---|---|---|
| GPT-4o-mini（通用，listwise judge） | SkillRouter top-20 | 67.3% |
| GPT-5.4-mini（通用，listwise judge） | 同上 | 66.0% |
| Qwen3-Reranker-8B（通用 reranker） | 同上 | 71.4% |
| SkillRouter 1.2B（专用微调） | 同上 | **74.0%** |
| R3（专用微调，中英） | R3-Skill | **77.1%** |
| **Jev（零样本）** | BM25 top-10（条件口径） | **86.9~89.3%** |

- 同候选集下通用 LLM judge 明显弱于专用重排器；Jev 条件命中与专用重排器同档或更高，但池/候选数/指标口径不同，非严格可比
- SkillRet 的架构启示：强一阶段会压缩通用重排器增益（甚至掉点），Jev 接强召回后需重测边际价值

**同数据集同指标对比（SkillRetBench，501 库 / 1,250 查询 / 官方基线表）**：

| 指标（macro） | BM25 | NaiveLLM | Jev chunked | **Jev hybrid** |
|---|---|---|---|---|
| Recall@1 | 38.0% | 30.2% | 60.4% | **75.8%** |
| Recall@3 | 49.2% | 40.4% | 75.4% | **87.6%** |
| Recall@10 | 59.8% | 55.6% | 87.6% | **93.0%** |
| nDCG@10 | 53.4% | 45.1% | 60.3% | **70.2%** |
| MRR@10 | 57.3% | 50.0% | 69.3% | **82.4%** |

- hybrid 架构 = 分块 choice 竞争取 top-15 → 对候选逐一 noul 验证（"该不该进集合"）→ 合并
- **多技能组合 R@1 9.0% → 81.0%**：教训是"逐问 noul 缺竞争性"（分数集中在 0.5x，排名变噪声），必须"先 competition 后 verification"
- 成本：hybrid $0.650/500 查询、P50 2.07s；bm25top50 生产同构 $0.072/500 查询、P50 0.33s（R@1 54.8%）
- 非英语折扣复现：韩语 48.9% vs 英语 61.5%（chunked 口径 n=45）
- Set completeness（全部金标选全）：multi 25%——组合场景的"选全"仍待改进

### 2.8 结构化抽取与校验 — demo 级

- 发票字段抽取 + 结构化 instructions 校验：字段值选择 confidence 1.0、条款 score 精确命中、编号校验 0.91–0.93
- 模式：代码先抽候选（regex/LLM），Jev 用 `field + extracted_value + question` 校验，失败升级人工

---

## 3. 弱项与边界

### 3.1 模型路由（负结果）

RouterBench 825 条："该请求是否需要强模型"。

| 策略 | 平均质量 | 平均成本 |
|---|---|---|
| 永远 cheap | 42.0% | $0.00005 |
| 永远 strong | 80.3% | $0.00249 |
| Jev 路由 @0.50 | 42.4% | $0.00005 |

- 判断准确率 **51.3%**（无信号），分数中位数 0.11，系统性偏向"小模型能搞定"
- 中文子集 14.6% vs 英文 57.7%
- 根因：从文本预测"某个具体小模型会不会错"依赖模型特性，不是自然语言属性

### 3.2 轨迹失败归因（负结果）

Who&When 184 条失败轨迹 × 8 步 = 1,403 步。

| 指标 | 结果 | 随机基线 |
|---|---|---|
| 步骤级 AUROC | 0.560 | 0.5 |
| 轨迹级 top-1 | 16.3% | 12.5% |
| 失败步 vs 普通步均分 | 0.42 vs 0.37 | — |

- 失败定义包含"从未被纠正"，必须看后续步骤 → 跨步因果任务，超出快思考层
- 若要做轨迹任务，改问局部可观察信号（工具报错、重复动作、格式违规），因果归因留给 LLM/人工

### 3.3 其他边界

- **语言**：英语为主，CJK 准确率下降（官方声明 + 评测验证）
- **上下文**：state+questions 共享 ~32k tokens；长轨迹放不进去
- **输入类型**：仅文本，不支持图片/音频/视频
- **高基数**：77 类可用；官方建议 150+ 类走两阶段（先打分再选择）
- **criteria 正确性 ≠ confidence**：高 confidence 只代表模型确信它在按你的定义判断

---

## 4. 跨实验工程规律

1. **正交拆分 + 代码组合 > 单问句**（两次强验证）
   - Bash 门控：误伤率 14.5% → 1.8%
   - BFCL：live 准确率 59.5% → 77.0%
   - 规律：边界模糊的判断，先拆成互不重叠的维度，阈值与逻辑全部写在代码里
2. **criteria 决定任务边界**：混两个概念 → 模糊概率（同一句话 0.47）；漏一个维度 → 漏报（可用性破坏）；写得太宽 → 误报（把"技术可用"当"语义相关"）
3. **高分区可信，低分区不等于安全**：neuralchemy 中 ≥0.1 分桶 86–100% 为恶意，但 0–0.1 分桶仍有 16.6% 恶意混入——生产策略不能"低分直接放行"
4. **门控曲线的价值**：certainty 覆盖率-准确率曲线比固定阈值更能指导选点（大多数场景 ≥0.95 可拿到 ~99% 准确率）
5. **成本/延迟画像**：单次 P50 ~0.3s、约 $0.00004；全量过一遍（每条消息/每个工具输出）在经济上完全可行
6. **多标签判断用"竞争 + 验证"两段**：一组独立 noul 逐问打分缺竞争性（分数集中在 0.5x，排名变噪声，SkillRetBench 多技能组合 R@1 仅 15%）；先让小范围 choice 竞争出候选，再用 noul 验证集合成员，multi R@1 直接到 81%。单标签选择直接用 choice 即可

---

## 5. 实验索引

| 报告 | 数据集 | 规模 | 结论 |
|---|---|---|---|
| `../eval/results/injecagent-report.md` | InjecAgent（真实） | 1,105 | ✅ 强项 |
| `../eval/results/tool-injection-report.md` | 合成工具输出 | 121 | ✅ 强项（编码绕过待补） |
| `../eval/results/neuralchemy-test-report.md` | neuralchemy | 942 | ⚠️ criteria 不匹配的教训 |
| `../eval/results/scifact-rerank-report.md` | BEIR SciFact | 900 对 | ✅ 强项 |
| `../eval/results/snips-intent-report.md` | SNIPS | 1,400 | ✅ 强项 |
| `../eval/results/banking77-intent-report.md` | Banking77 | 3,080 | ✅ 强项（77 类） |
| `../eval/results/bash-gate-v2-report.md` | 自建命令集 | 130 | ✅ 强项 |
| `../eval/results/bfcl-relevance-v2c-report.md` | BFCL | 1,140 | ✅ 迭代后可用 |
| `../eval/results/agent-route-k5-report.md` | MetaTool（199 工具） | 400 | ✅ 强项 |
| `../eval/results/agent-route-k10-report.md` | MetaTool | 400 | ✅ 强项 |
| `../eval/results/agent-route-k20-report.md` | MetaTool | 400 | ✅ 强项 |
| `../eval/results/skillret-k10-report.md` | SkillRet（6,006 skills） | 300 | ✅ selector 强 |
| `../eval/results/skillret-k10-body-report.md` | SkillRet | 300 | ✅ 对照 |
| `../eval/results/skillret-k20-body-report.md` | SkillRet | 300 | ✅ 对照 |
| `../eval/results/skillret-k10-idxbody-report.md` | SkillRet | 300 | ✅ 最佳 68.3% |
| `../eval/results/skillretbench-chunked-report.md` | SkillRetBench（501 库 + 官方基线） | 500 | ✅ R@1 60.4%（基线 38.0%） |
| `../eval/results/skillretbench-multiselect-report.md` | SkillRetBench | 100 | ⚠️ 逐问 noul 缺竞争性 |
| `../eval/results/skillretbench-hybrid-report.md` | SkillRetBench | 500 | ✅ **R@1 75.8%，multi 81.0%** |
| `../eval/results/skillretbench-bm25top50-report.md` | SkillRetBench | 500 | ✅ R@1 54.8%、$0.00014/条 |
| `../eval/results/routerbench-report.md` | RouterBench | 825 | ❌ 负结果 |
| `../eval/results/whowhen-report.md` | Who&When | 1,403 步 | ❌ 负结果 |

脚本：`eval/run_injecagent.py`、`run_toolinject.py`、`run_rerank.py`、`run_intent.py`、`run_bash.py`、`run_bfcl.py`、`run_agentroute.py`、`run_skillret.py`、`run_skillretbench.py`、`run_router.py`、`run_whowhen.py`

---

## 6. 生产落地建议

1. **护栏层**：`scan_injection` 放在每个不可信输入（工具返回、网页、邮件）之前；高阈值拦、低阈值标、中间转人工
2. **检索层**：BM25/embedding 召回 → Jev 精排（成本低、效果稳定），再喂给生成模型
3. **权限层**：`bash_risk` 四维打分 + 代码门控（deny/review/allow），阈值按动作风险分级
4. **分类/路由层**：意图、主题、agent/工具/skill 路由用 choice；目录描述要写清用途与边界（近义项显式消歧）；规模大时用两阶段（检索 top-K → Jev 选择），Jev 的 selector 命中 85~89%，把预算花在提升召回上
5. **监控**：记录每次判断的分数与动作，按覆盖-准确率曲线持续校准阈值；模型版本升级后复测
6. **不要用它做**：难度路由、长轨迹归因、中文生意的关键路径（需先在自有数据上验证）
7. 已封装为 MCP 工具（`scan_injection` / `bash_risk` / `rank_candidates`），接入方式见 `../README.md` 集成工具

---

## 7. 局限声明

- 结果基于 **jev-1.13.0** 单一版本，模型更新后需复测
- 部分数据集为构造/抽样（bash 命令集、合成注入、SciFact 60 查询），存在选择偏差
- 阈值均为参考值，生产阈值必须在自有数据上标定
- 中文样本覆盖不足，结论以外语（英语）数据为主
