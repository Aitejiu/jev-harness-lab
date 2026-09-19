"""Skill router eval on SkillRet (ThakiCloud/SKILLRET).

Two-stage shape matching the production skill router:
  1. BM25 retrieval over 6,660 real skills (name + description) -> shortlist
  2. Jev choice over the shortlist (criteria = name -> description)

Reports BM25 Hit@1, shortlist recall@K, Jev Hit@1 (overall + conditional on
gold-in-shortlist) and confidence-gated coverage.
"""

import argparse
import json
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

DATA = Path(__file__).resolve().parent / "data" / "skillret"
RESULTS = Path(__file__).resolve().parent / "results"
SKILLS_FILE = DATA / "skills_test.jsonl"
SLIM_FILE = DATA / "skills_slim_v2.json"

DESC_LEN = 240
BODY_LEN = 500

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def load_skills() -> list[dict]:
    if SLIM_FILE.exists():
        return json.loads(SLIM_FILE.read_text())
    skills = []
    with SKILLS_FILE.open() as f:
        for line in f:
            raw = json.loads(line)
            body = (raw.get("body") or raw.get("skill_md") or "").strip()
            skills.append(
                {
                    "id": raw["id"],
                    "name": raw.get("name") or raw["id"],
                    "description": (raw.get("description") or "").strip(),
                    "body": body[:BODY_LEN],
                }
            )
    SLIM_FILE.write_text(json.dumps(skills, ensure_ascii=False))
    return skills


def load_qrels() -> dict[str, set[str]]:
    qrels: dict[str, set[str]] = {}
    with (DATA / "qrels_test.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            if row.get("relevance", 0) > 0:
                qrels.setdefault(row["query_id"], set()).add(row["skill_id"])
    return qrels


def load_queries() -> list[dict]:
    queries = []
    with (DATA / "queries_test.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            queries.append({"id": row["id"], "query": row["query"]})
    return queries


def build_dataset(k: int, limit: int, with_body: bool, bm25_with_body: bool, seed: int = 42) -> list[dict]:
    import random

    rng = random.Random(seed)
    skills = load_skills()
    qrels = load_qrels()
    queries = [q for q in load_queries() if q["id"] in qrels]
    rng.shuffle(queries)
    queries = queries[:limit]

    doc_tokens = [
        _tokens(
            f"{s['name']} {s['description']}"
            + (f" {s['body']}" if bm25_with_body else "")
        )
        for s in skills
    ]
    bm25 = BM25Okapi(doc_tokens)
    by_id = {s["id"]: s for s in skills}

    records = []
    for query in queries:
        scores = bm25.get_scores(_tokens(query["query"]))
        ranked = sorted(range(len(skills)), key=lambda i: -scores[i])
        shortlist = [skills[i] for i in ranked[:k]]
        gold = qrels[query["id"]]
        records.append(
            {
                "id": f"sr-{query['id']}",
                "query": query["query"],
                "gold_ids": sorted(gold),
                "gold_names": sorted(by_id[g]["name"] for g in gold if g in by_id),
                "shortlist": [
                    {
                        "id": s["id"],
                        "name": s["name"],
                        "description": s["description"][:DESC_LEN],
                        "body": s["body"][:BODY_LEN] if with_body else "",
                    }
                    for s in shortlist
                ],
                "bm25_top1": shortlist[0]["id"],
                "bm25_top1_correct": int(shortlist[0]["id"] in gold),
                "gold_in_shortlist": int(any(s["id"] in gold for s in shortlist)),
            }
        )
    return records


def build_questions(example: dict) -> dict:
    criteria = {}
    for candidate in example["shortlist"]:
        text = candidate["description"] or candidate["name"]
        if candidate.get("body"):
            text = f"{text}\n{candidate['body']}"
        criteria[candidate["name"]] = text
    return {
        "skill": Choice(
            instructions="Which skill should handle `task`? Pick the skill whose stated purpose best matches the task.",
            criteria=criteria,
        )
    }


def run_one(example: dict) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state={"task": example["query"]},
        questions=build_questions(example),
    )
    latency = time.perf_counter() - started
    answer = response.answers["skill"]
    predicted = next((c for c in example["shortlist"] if c["name"] == answer.choice), None)
    return {
        **example,
        "predicted_name": answer.choice,
        "predicted_id": predicted["id"] if predicted else None,
        "jev_correct": int(predicted is not None and predicted["id"] in set(example["gold_ids"])),
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


def build_report(records: list[dict], k: int, catalog_size: int) -> str:
    n = len(records)
    bm25_hit1 = sum(r["bm25_top1_correct"] for r in records) / n
    shortlist_recall = sum(r["gold_in_shortlist"] for r in records) / n
    jev_hit1 = sum(r["jev_correct"] for r in records) / n
    conditional = [r for r in records if r["gold_in_shortlist"]]
    conditional_hit1 = sum(r["jev_correct"] for r in conditional) / len(conditional) if conditional else 0.0
    multi = [r for r in records if len(r["gold_ids"]) > 1]

    input_tokens = sum(r["input_tokens"] for r in records)
    latencies = sorted(r["latency_s"] for r in records)

    lines = [
        "# Jev Skill Router 评测（SkillRet：6,660 个真实 skills）",
        "",
        f"- 查询数：{n}（多目标查询 {len(multi)} 条），skills 池：{catalog_size}",
        f"- 架构：BM25 召回 top-{k} → Jev choice 选择（与生产 skill router 同构）",
        f"- 模型：{records[0]['model']}",
        f"- 延迟：P50 {latencies[len(latencies) // 2]:.2f}s / P95 {latencies[int(len(latencies) * 0.95)]:.2f}s",
        f"- 成本：{input_tokens} input tokens ≈ ${input_tokens / 1e9 * 42:.4f}",
        "",
        "## 关键指标",
        "",
        "| 阶段 | 指标 | 结果 |",
        "|---|---|---|",
        f"| 1. BM25 全库 | Hit@1 | {_pct(bm25_hit1)} |",
        f"| 1. BM25 召回 | 短名单含正确 skill（Recall@{k}） | {_pct(shortlist_recall)} |",
        f"| 2. Jev 选择 | Hit@1（端到端） | **{_pct(jev_hit1)}** |",
        f"| 2. Jev 选择 | 条件 Hit@1（金标在短名单内时） | **{_pct(conditional_hit1)}** |",
        "",
        "## 置信度门控",
        "",
        "| confidence ≥ | 覆盖率 | 准确率（覆盖内） | 转人工 |",
        "|---|---|---|---|",
    ]
    for threshold in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99):
        covered = [r for r in records if r["confidence"] >= threshold]
        if not covered:
            continue
        acc = sum(r["jev_correct"] for r in covered) / len(covered)
        lines.append(
            f"| {threshold:.2f} | {_pct(len(covered) / n)} | {_pct(acc)} | {_pct(1 - len(covered) / n)} |"
        )

    lines += [
        "",
        "## 错例（前 10）",
        "",
        "| 查询 | 金标 skills | Jev 预测 | 在短名单 | 置信度 |",
        "|---|---|---|---|---|",
    ]
    for record in [r for r in records if not r["jev_correct"]][:10]:
        lines.append(
            f"| {record['query'][:46]} | {', '.join(record['gold_names'])[:36]} | "
            f"{record['predicted_name']} | {'是' if record['gold_in_shortlist'] else '否'} | {record['confidence']:.2f} |"
        )
    if all(r["jev_correct"] for r in records):
        lines.append("| — | 无 | | | |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev skill router eval on SkillRet")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--queries", type=int, default=300)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--with-body", action="store_true", help="include skill body excerpt in criteria")
    parser.add_argument("--bm25-with-body", action="store_true", help="index skill body in BM25 retrieval")
    args = parser.parse_args()

    skills = load_skills()
    examples = build_dataset(
        k=args.k, limit=args.queries, with_body=args.with_body, bm25_with_body=args.bm25_with_body
    )
    variant = f"k{args.k}" + ("-body" if args.with_body else "") + ("-idxbody" if args.bm25_with_body else "")
    out_path = RESULTS / f"skillret-{variant}.jsonl"
    records = run(examples, out_path, args.concurrency, args.limit)
    ordered = [records[e["id"]] for e in examples if e["id"] in records]

    report = build_report(ordered, args.k, len(skills))
    report_path = RESULTS / f"skillret-{variant}-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
