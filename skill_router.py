"""Route a task to the best installed skill using a fast Jev judgment.

Scans skill catalogs (project + global), asks Jev to pick the matching skill,
and can return the full SKILL.md so the harness never needs the whole catalog
in the main model context.

Usage:
    python skill_router.py --query "帮我查一下飞书文档" [--load] [--top-k 3]
Output: JSON on stdout {skill, confidence, alternatives, catalog_size, content?}
"""

import argparse
import json
import os
import socket
import sys
from pathlib import Path

SKILL_DIRS = [
    ".opencode/skills",
    ".agents/skills",
    ".claude/skills",
]


def _ensure_proxy() -> None:
    if os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"):
        return
    with socket.socket() as s:
        s.settimeout(0.2)
        if s.connect_ex(("127.0.0.1", 7897)) == 0:
            os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:7897"
            os.environ["NO_PROXY"] = "127.0.0.1,localhost"


_ensure_proxy()

import yaml  # noqa: E402

sys.path.append(str(Path(__file__).resolve().parent))

from common import client  # noqa: E402
from typesafe_sdk import Choice  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
HOME = Path.home()

NONE_OPTION = "none"
NONE_DESCRIPTION = "No skill applies; answer or act directly without loading a skill"


def catalog_dirs() -> list[Path]:
    dirs = [PROJECT_ROOT / rel for rel in SKILL_DIRS]
    dirs += [WORKSPACE_ROOT / rel for rel in SKILL_DIRS]
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
    return {
        "name": name,
        "description": description,
        "path": str(path),
        "content": text,
    }


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
    criteria = {skill["name"]: skill["description"][:220] for skill in catalog}
    criteria[NONE_OPTION] = NONE_DESCRIPTION
    criteria = {name: (desc or name) for name, desc in criteria.items()}

    response = client.system_one(
        state={"task": query, "available_skills": sorted(criteria)},
        questions={
            "skill": Choice(
                instructions="Which skill's stated purpose best matches `task`? Pick `none` if no skill applies.",
                criteria=criteria,
            )
        },
    )
    answer = response.answers["skill"]
    ranked = sorted(answer.probabilities.items(), key=lambda kv: -kv[1])
    alternatives = [name for name, _ in ranked if name != answer.choice][:top_k]
    result = {
        "skill": answer.choice,
        "confidence": round(answer.confidence, 3),
        "probability": round(answer.probabilities.get(answer.choice, 0.0), 3),
        "alternatives": alternatives,
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
    parser.add_argument("--load", action="store_true", help="include full SKILL.md content")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--list", action="store_true", help="print catalog and exit")
    args = parser.parse_args()

    if args.list:
        catalog = load_catalog()
        print(json.dumps([{k: s[k] for k in ("name", "path")} for s in catalog], ensure_ascii=False, indent=2))
        return

    if not args.query:
        parser.error("--query is required unless --list is used")

    result = route(args.query, top_k=args.top_k)
    if not args.load:
        result.pop("content", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
