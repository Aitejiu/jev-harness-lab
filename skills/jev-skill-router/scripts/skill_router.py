"""Route a task to the best installed skill with one TypeSafe Jev call.

Standalone: reads TYPESAFE_API_KEY from the environment or a nearby .env file.
Requires: typesafe-sdk (pip install typesafe-sdk)

Usage:
    python skill_router.py --query "help me read a Feishu doc" [--load] [--top-k 3]
    python skill_router.py --list
"""

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_DIRS = [
    ".opencode/skills",
    ".agents/skills",
    ".claude/skills",
]

NONE_OPTION = "none"
NONE_DESCRIPTION = "No skill applies; answer or act directly without loading a skill"
DESC_LIMIT = 220


def _load_env() -> None:
    cwd = Path.cwd()
    for base in (cwd, cwd.parent, cwd.parent.parent):
        env_file = base / ".env"
        if not env_file.exists():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)
        return


_load_env()

try:
    import yaml  # noqa: E402
    from typesafe_sdk import Choice, TypeSafeClient  # noqa: E402
except ImportError as exc:  # pragma: no cover
    print(f"Missing dependency: {exc}. Install with: pip install typesafe-sdk pyyaml", file=sys.stderr)
    raise SystemExit(2)

HOME = Path.home()
CWD = Path.cwd()


def _client() -> TypeSafeClient:
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY is not set (env or .env).", file=sys.stderr)
        raise SystemExit(2)
    return TypeSafeClient()


def catalog_dirs() -> list[Path]:
    dirs = [CWD / rel for rel in SKILL_DIRS]
    dirs += [HOME / ".config/opencode/skills", HOME / ".agents/skills", HOME / ".claude/skills"]
    return [d for d in dirs if d.is_dir()]


def parse_skill(path: Path) -> dict | None:
    text = path.read_text(errors="ignore")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    name = str(front.get("name") or path.parent.name).strip()
    description = str(front.get("description") or "").strip().replace("\n", " ")
    if not name or not description:
        return None
    return {"name": name, "description": description, "path": str(path), "content": text}


def load_catalog() -> list[dict]:
    seen: dict[str, dict] = {}
    for directory in catalog_dirs():
        for path in sorted(directory.glob("*/SKILL.md")):
            skill = parse_skill(path)
            if skill and skill["name"] not in seen:
                seen[skill["name"]] = skill
    return list(seen.values())


def route(query: str, top_k: int = 3) -> dict:
    catalog = load_catalog()
    criteria = {skill["name"]: skill["description"][:DESC_LIMIT] for skill in catalog}
    criteria[NONE_OPTION] = NONE_DESCRIPTION

    response = _client().system_one(
        state={"task": query, "available_skills": sorted(criteria)},
        questions={
            "skill": Choice(
                instructions="Which skill's stated purpose best matches `task`? Pick `none` if no skill applies.",
                criteria={name: (desc or name) for name, desc in criteria.items()},
            )
        },
    )
    answer = response.answers["skill"]
    ranked = sorted(answer.probabilities.items(), key=lambda kv: -kv[1])
    result = {
        "skill": answer.choice,
        "confidence": round(answer.confidence, 3),
        "probability": round(answer.probabilities.get(answer.choice, 0.0), 3),
        "alternatives": [name for name, _ in ranked if name != answer.choice][:top_k],
        "catalog_size": len(catalog),
    }
    if answer.choice != NONE_OPTION:
        match = next((s for s in catalog if s["name"] == answer.choice), None)
        if match:
            result["path"] = match["path"]
            result["content"] = match["content"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev skill router")
    parser.add_argument("--query", default=None)
    parser.add_argument("--load", action="store_true", help="include the full SKILL.md content")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--list", action="store_true", help="print the catalog and exit")
    args = parser.parse_args()

    if args.list:
        catalog = load_catalog()
        print(json.dumps([{"name": s["name"], "path": s["path"]} for s in catalog], ensure_ascii=False, indent=2))
        return

    if not args.query:
        parser.error("--query is required unless --list is used")

    result = route(args.query, top_k=args.top_k)
    if not args.load:
        result.pop("content", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
