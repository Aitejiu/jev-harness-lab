# jev-harness-lab

用 [TypeSafe Jev](https://docs.typesafe.ai)（System One 决策模型）做 agent harness 工程实验的技术仓库：评测框架、基准报告、可运行的集成工具（MCP server、skill router）。

Jev 的形态：输入 `state` + 类型化 `questions`（`choice` / `noul` / `score`），返回带概率与置信度的结构化判断，不生成文本。本仓库用它验证 harness 中的判断类任务：注入检测、检索重排、意图/技能路由、命令风险门控等。

[![skills.sh](https://skills.sh/b/Aitejiu/jev-harness-lab)](https://skills.sh/Aitejiu/jev-harness-lab)

## Install as an agent skill

`skills/jev-skill-router/` 是一个可安装的 agent skill（skills.sh 生态）：用 Jev 把任务路由到已安装的 skill，并且只加载选中那一个的完整指令，避免把整个 skill 目录塞进主模型上下文。

```bash
npx skills add Aitejiu/jev-harness-lab --skill jev-skill-router
```

## 目录

```
.
├── examples/            # 最小可运行示例（三原语、state、路由、护栏、抽取）
├── eval/                # 评测框架：11 个基准脚本 + 24 份报告 + 原始结果
│   └── datasets/        # 手工构造的数据集（如 130 条 shell 命令风险集）
├── integrations/
│   └── opencode/        # opencode 插件：jev_route_skill（skill 门控）
├── skills/
│   └── jev-skill-router/  # 可安装的 agent skill（SKILL.md + 独立脚本，skills.sh）
├── docs/
│   └── REPORT.md        # 技术评估报告（数据与结论）
├── mcp_server.py        # MCP 工具：scan_injection / bash_risk / rank_candidates
├── skill_router.py      # 本地 skill 目录路由（Jev 选择并加载 SKILL.md）
├── common.py            # .env 加载 + 共享 client
└── requirements.txt
```

## 快速开始

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt
echo "TYPESAFE_API_KEY=<your-key>" > .env
```

```bash
# 最小示例
.venv/bin/python examples/quickstart.py
.venv/bin/python examples/noul.py          # criteria 对判断的影响
.venv/bin/python examples/routing.py       # 阈值路由

# 跑评测（示例：skill router，501 个真实 skills）
.venv/bin/python eval/run_skillretbench.py --variant hybrid --per-setting 100
```

评测结果缓存在 `eval/results/*.jsonl`（已随仓库提交，可 `--report-only` 直接出报告）；原始数据集在 `eval/data/`，需按 `eval/README.md` 的说明下载（已 gitignore）。

## 集成工具

### MCP server

```bash
.venv/bin/python mcp_server.py   # stdio
```

| 工具 | 作用 | 输入 → 输出 |
|---|---|---|
| `scan_injection` | 扫描工具输出中的注入指令 | tool_output → `action`(block/review/pass) + 概率 |
| `bash_risk` | shell 命令四维风险打分 | command → `action`(deny/review/allow) + 破坏性/触密/外发/不可逆分数 |
| `rank_candidates` | 候选片段相关性重排 | query + candidates(≤10) → 排序后的 index/score |

接入 opencode 的配置示例（项目 `.opencode/opencode.json`）：

```json
{
  "mcp": {
    "jev": {
      "type": "local",
      "command": ["/absolute/path/to/jev-harness-lab/.venv/bin/python", "/absolute/path/to/jev-harness-lab/mcp_server.py"],
      "enabled": true
    }
  }
}
```

### Skill router

```bash
.venv/bin/python skill_router.py --query "帮我查飞书文档" --load
```

opencode 插件在 `integrations/opencode/jev-skill-router.ts`：注册 `jev_route_skill(task)` 工具，请求进来时用 Jev 从本地 skill 目录选出最合适的一个并返回其完整指令。参考做法是配合 `agent.build.tools.skill = false` 关闭内置 skill 工具，使主模型上下文不再携带整个 skill 目录。

## 主要基准结果（详见 docs/REPORT.md）

| 任务 | 数据 | 结果 |
|---|---|---|
| 间接注入检测 | InjecAgent 1,105 条 | 阈值 0.10：P/R **100%**，良性误报 0% |
| 检索重排 | BEIR SciFact 900 对 | BM25 → Jev：MRR 0.622 → **0.843**，Hit@1 50% → 78.3% |
| 意图分类 | SNIPS / Banking77 | 7 类 **97.9%** / 77 类 **80.3%** |
| 工具目录路由 | MetaTool 199 工具 | 相似干扰 k=5 **96.5%** |
| Skill router | SkillRetBench 501 库 | hybrid 架构 R@1 **75.8%**（最强基线 38.0%） |
| 命令风险门控 | 自建 130 条 | 危险拦截 **100%**、正常放行 98.2% |
| 模型难度路由 | RouterBench | 51%（无信号，负结果） |
| 轨迹失败归因 | Who&When 1,403 步 | AUROC 0.56（负结果） |

总计约 22,500 次 API 调用、52.2M input tokens、$2.19。

## 说明

- 所有 benchmark 使用公开数据集；原始结果 JSONL 已提交，报告可复现。
- 部分官方基线为模拟实现（在报告中已标注）。
- Jev 已知限制：`choice` 最多 255 个选项、仅文本输入、state+questions 共享约 32k tokens、英语为主。
- 版本：`jev-1.13.0`，模型升级后建议重新评测。
