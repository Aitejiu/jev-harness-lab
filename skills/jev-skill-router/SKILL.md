---
name: jev-skill-router
description: >
  Route a task to the right locally installed agent skill using TypeSafe Jev's fast,
  structured judgment, then load only the selected skill's instructions. Use when a
  request may match one of many installed skills (Feishu/Lark operations, browser
  automation, TypeSafe/Jev, frontend design, skill discovery, etc.) and you want to
  avoid putting the whole skill catalog into the model context. Requires a
  TYPESAFE_API_KEY; when no skill matches it returns "none" and the agent proceeds
  normally.
license: MIT
---

# Jev Skill Router

Route a task to the best installed skill with one fast decision-model call, then load
only that skill's `SKILL.md` — instead of paying for the whole skill catalog in context.

## What it does

1. Scans the standard skill directories (project + user level).
2. Asks TypeSafe Jev one `choice` question: *which skill's stated purpose best matches the task?* — with a `none` option.
3. Returns the selected skill (name, confidence, alternatives) and, with `--load`, its full instructions.

The judgment is a single sub-second call (~$0.00004). No generation, no catalog in the main context.

## When to use

- The task may map to a reusable skill and several skills are installed.
- You want to keep the main model's context small (no full skill directory in the system prompt).
- You want a confidence signal before loading a skill (low confidence → let the model decide or ask).

## When not to use

- Only one or two skills are installed (just read them directly).
- The catalog is larger than ~200 skills: `choice` is capped at 255 options — pre-filter first (e.g. BM25 shortlist) and route over the shortlist.
- No network / no `TYPESAFE_API_KEY`: the script exits with a clear message and the agent proceeds without a skill.

## Setup

```bash
pip install typesafe-sdk        # or: uv pip install typesafe-sdk
export TYPESAFE_API_KEY=...
```

The script also reads a `.env` file from the current directory (or up to two parents).

## Usage

```bash
# route only
python scripts/skill_router.py --query "帮我查飞书文档"

# route and load the selected skill's full instructions
python scripts/skill_router.py --query "把会议纪要整理成周报" --load

# list the catalog the router sees
python scripts/skill_router.py --list
```

Output (JSON):

```json
{
  "skill": "lark-doc",
  "confidence": 0.88,
  "probability": 0.89,
  "alternatives": ["lark-wiki", "none"],
  "catalog_size": 35,
  "path": "/path/to/lark-doc/SKILL.md",
  "content": "---\nname: lark-doc\n..."
}
```

Decision policy:

- `confidence >= 0.5` and `skill != "none"` → load and follow the skill.
- otherwise → proceed without a skill (the model may still pick one itself).

## How it works

- Catalogs scanned: `./.opencode/skills/*/SKILL.md`, `./.agents/skills/*/SKILL.md`, `./.claude/skills/*/SKILL.md`, plus `~/.config/opencode/skills`, `~/.agents/skills`, `~/.claude/skills`.
- Only `name` and `description` frontmatter are used as routing metadata; each description is truncated to 220 characters for the question.
- The question is a `choice` over all skill names plus `none`; probabilities and confidence come back from the model.

## Evidence

Measured on public benchmarks (details: `docs/REPORT.md` in the repository):

| Benchmark | Setup | Result |
|---|---|---|
| SkillRet (6,006 skills) | selector conditional Hit@1 | 86.9 – 89.3% |
| SkillRetBench (501 skills) | two-stage `choice → noul` | R@1 **75.8%** vs 38.0% best baseline |
| MetaTool (199 tools) | k=5, similar distractors | 96.5% |

## Limits

- English-primary model: non-English queries route correctly but with lower accuracy.
- Needs network access and a TypeSafe API key.
- Routing quality depends on skill descriptions: near-duplicate skills should document boundaries (`not_for`) in their descriptions.

## Integrations

See `references/integration.md` for wiring the same router into an MCP server or an
opencode plugin (`agent.build.tools.skill = false` toggle).
