"""Agent/tool routing eval on MetaTool ToolE (known catalog, pick the right tool).

Data (data/metatool/):
- all_clean_data.csv   : single-tool queries with their correct tool
- plugin_des.json      : tool name -> description (catalog)

Two distractor modes:
- random : correct tool + random tools from the catalog (easy)
- similar: correct tool + most similar tools by BM25 over descriptions (hard,
           matches MetaTool's "similar choices" subtask)
"""

import argparse
import csv
import json
import random
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401
from typesafe_sdk import Choice, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data" / "metatool"
RESULTS = Path(__file__).resolve().parent / "results"

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def load_catalog() -> dict[str, str]:
    path = DATA / "plugin_des.json"
    if not path.exists():
        raise SystemExit(f"missing {path}; download MetaTool dataset first")
    catalog = json.loads(path.read_text())
    return {str(name): str(desc) for name, desc in catalog.items()}


def load_queries() -> list[dict]:
    path = DATA / "all_clean_data.csv"
    if not path.exists():
        raise SystemExit(f"missing {path}; download MetaTool dataset first")
    with path.open() as f:
        rows = list(csv.DictReader(f))
    columns = {c.lower(): c for c in rows[0]}
    query_col = next((c for name, c in columns.items() if "query" in name), None) or next(
        (c for name, c in columns.items() if "instruction" in name or "prompt" in name), None
    )
    tool_col = next((c for name, c in columns.items() if "tool" in name and "desc" not in name), None)
    if not query_col or not tool_col:
        print("columns:", list(rows[0]), file=sys.stderr)
        raise SystemExit("cannot identify query/tool columns")
    out = []
    for row in rows:
        query = (row.get(query_col) or "").strip()
        tool = (row.get(tool_col) or "").strip()
        if query and tool:
            out.append({"query": query, "tool": tool})
    return out


def build_dataset(k: int, queries: int, modes: list[str], seed: int = 42) -> list[dict]:
    catalog = load_catalog()
    names = list(catalog)
    rng = random.Random(seed)
    rows = [row for row in load_queries() if row["tool"] in catalog]
    rng.shuffle(rows)
    rows = rows[:queries]

    bm25 = None
    if "similar" in modes:
        tokenized = [_tokens(catalog[name]) or [name.lower()] for name in names]
        bm25 = BM25Okapi(tokenized)

    records = []
    for index, row in enumerate(rows):
        correct = row["tool"]
        for mode in modes:
            others = [name for name in names if name != correct]
            if mode == "random":
                distractors = rng.sample(others, k - 1)
            else:
                scores = bm25.get_scores(_tokens(row["query"]))
                others.sort(key=lambda name: -scores[names.index(name)])
                distractors = others[: k - 1]
            options = [correct, *distractors]
            rng.shuffle(options)
            records.append(
                {
                    "id": f"ar-{mode}-{index}",
                    "mode": mode,
                    "query": row["query"],
                    "correct": correct,
                    "options": options,
                    "catalog_size": len(names),
                }
            )
    return records


def build_questions(example: dict) -> dict:
    catalog = load_catalog()
    criteria = {}
    for name in example["options"]:
        description = catalog.get(name, "")
        criteria[name] = description[:200] if description else name
    return {
        "tool": Choice(
            instructions="Which tool should handle `user_request`? Pick the tool whose stated purpose best matches the request.",
            criteria=criteria,
        )
    }


def run_one(example: dict) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state={"user_request": example["query"]},
        questions=build_questions(example),
    )
    latency = time.perf_counter() - started
    answer = response.answers["tool"]
    return {
        **example,
        "predicted": answer.choice,
        "correct_choice": int(answer.choice == example["correct"]),
        "confidence": answer.confidence,
        "latency_s": round(latency, 3),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": response.model,
    }


def load_done(path: Path) -> dict:
    done = {}
    if path.exists():
        with path.open() as f:
            for line in f:
                record = json.loads(line)
                done[record["id"]] = record
    return done


def run(examples: list[dict], out_path: Path, concurrency: int, limit: int | None) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path)
    todo = [e for e in examples if e["id"] not in done]
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        print(f"nothing to run ({len(done)} cached)")
        return done

    print(f"running {len(todo)} examples (concurrency={concurrency}, cached={len(done)})")
    lock = threading.Lock()
    with out_path.open("a") as f, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(run_one, e): e["id"] for e in todo}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
            except Exception as exc:
                print(f"  FAILED {futures[future]}: {exc}")
                continue
            with lock:
                f.write(json.dumps(record) + "\n")
                f.flush()
                done[record["id"]] = record
            if i % 100 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}")
    return done


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report(records: list[dict]) -> str:
    groups: dict[tuple[str, int], list[dict]] = {}
    for record in records:
        groups.setdefault((record["mode"], len(record["options"])), []).append(record)

    lines = [
        "# Jev Agent/工具路由评测（MetaTool ToolE，已知目录）",
        "",
        f"- 样本数：{len(records)}",
        f"- catalog 规模：{records[0]['catalog_size']} 个工具",
        f"- 模型：{records[0]['model']}",
        "",
        "## 路由准确率（选对正确工具）",
        "",
        "| 模式 | 选项数 | 样本 | Top-1 准确率 | 随机基线 | 关键指标 |",
        "|---|---|---|---|---|---|",
    ]
    for (mode, k), group in sorted(groups.items()):
        correct = sum(r["correct_choice"] for r in group)
        coverage_rows = [r for r in group if r["confidence"] >= 0.8]
        covered_acc = (
            sum(r["correct_choice"] for r in coverage_rows) / len(coverage_rows) if coverage_rows else 0.0
        )
        lines.append(
            f"| {mode} | {k} | {len(group)} | **{_pct(correct / len(group))}** | {_pct(1 / k)} | "
            f"conf≥0.8：覆盖 {_pct(len(coverage_rows) / len(group))}，准确率 {_pct(covered_acc)} |"
        )

    lines += [
        "",
        "## 错例（前 10）",
        "",
        "| 模式 | 请求 | 正确 | 预测 | 置信度 |",
        "|---|---|---|---|---|",
    ]
    wrong = [r for r in records if not r["correct_choice"]][:10]
    for record in wrong:
        lines.append(
            f"| {record['mode']} | {record['query'][:50]} | `{record['correct']}` | "
            f"`{record['predicted']}` | {record['confidence']:.2f} |"
        )
    if not wrong:
        lines.append("| — | 无 | | | |")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev agent/tool routing eval (MetaTool)")
    parser.add_argument("--k", type=int, default=10, help="options per query")
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--modes", default="random,similar")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    examples = build_dataset(k=args.k, queries=args.queries, modes=modes)
    out_path = RESULTS / f"agent-route-k{args.k}.jsonl"
    records = run(examples, out_path, args.concurrency, args.limit)
    ordered = [records[e["id"]] for e in examples if e["id"] in records]

    report = build_report(ordered)
    report_path = RESULTS / f"agent-route-k{args.k}-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
