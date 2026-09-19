"""SkillRetBench eval: Jev as the skill selector, directly comparable to the
published baselines (BM25 / Dense / Hybrid / NaiveLLM / SADO).

Variants:
- chunked   : 501 skills split into 5 chunks of ~101 (API limit 255 options);
              each chunk returns a choice + probabilities with a `none` option,
              probabilities are merged into a global top-10 ranking.
- bm25top50 : BM25 shortlist of 50, Jev picks one.

Metrics per setting (R@1/3/5/10, nDCG@10, MRR@10) match the benchmark's
definitions; compare against data/skillretbench/baseline_results.json.
"""

import argparse
import json
import random
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401
from typesafe_sdk import Choice, Noul, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data" / "skillretbench"
RESULTS = Path(__file__).resolve().parent / "results"

SETTINGS = [
    "single_skill",
    "multi_skill_composition",
    "distractor",
    "outdated_redundant",
    "budget_constrained",
]

NONE_ID = "__none__"
NONE_TEXT = "No skill in this list matches the task"
CHUNKS = 5

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def load_data() -> tuple[list[dict], list[dict]]:
    corpus = json.loads((DATA / "skill_corpus.json").read_text())["skills"]
    queries = json.loads((DATA / "skillretbench_queries_annotated.json").read_text())["queries"]
    return corpus, queries


def build_dataset(variant: str, per_setting: int, settings: list[str] | None = None, seed: int = 42) -> list[dict]:
    corpus, queries = load_data()
    rng = random.Random(seed)

    by_setting: dict[str, list[dict]] = defaultdict(list)
    for q in queries:
        by_setting[q["setting"]].append(q)

    shortlist_by_query: dict[str, list[dict]] = {}
    if variant == "bm25top50":
        bm25 = BM25Okapi([_tokens(f"{s['skill_name']} {s['description']}") for s in corpus])
        for q in queries:
            scores = bm25.get_scores(_tokens(q["query"]))
            ranked = sorted(range(len(corpus)), key=lambda i: -scores[i])[:50]
            shortlist_by_query[q["query_id"]] = [corpus[i] for i in ranked]

    selected_settings = settings or SETTINGS
    records = []
    for setting in selected_settings:
        pool = by_setting.get(setting, [])
        rng.shuffle(pool)
        for q in pool[:per_setting]:
            if variant in ("chunked", "multiselect", "hybrid"):
                chunks = [corpus[i::CHUNKS] for i in range(CHUNKS)]
                option_groups = [
                    [{"id": s["skill_id"], "text": f"{s['skill_name']}: {s['description'][:150]}"} for s in chunk]
                    for chunk in chunks
                ]
            else:
                option_groups = [
                    [
                        {
                            "id": s["skill_id"],
                            "text": f"{s['skill_name']}: {s['description'][:200]}",
                        }
                        for s in shortlist_by_query[q["query_id"]]
                    ]
                ]
            records.append(
                {
                    "id": f"srb-{variant}-{q['query_id']}",
                    "variant": variant,
                    "query_id": q["query_id"],
                    "setting": setting,
                    "query": q["query"],
                    "gold_ids": q["gold_skills"],
                    "option_groups": option_groups,
                }
            )
    return records


def _ask(query: str, options: list[dict], allow_none: bool) -> tuple[dict, dict]:
    criteria = {opt["id"]: opt["text"] for opt in options}
    if allow_none:
        criteria[NONE_ID] = NONE_TEXT
    response = _client().system_one(
        state={"task": query},
        questions={
            "skill": Choice(
                instructions=(
                    "Which skill should handle `task`? Pick the skill whose stated purpose best matches the task"
                    + (", or `__none__` if no listed skill matches." if allow_none else ".")
                ),
                criteria=criteria,
            )
        },
    )
    return response.answers["skill"], response.usage.model_dump()


def _ask_multiselect(query: str, options: list[dict]) -> tuple[dict[str, float], int]:
    questions = {}
    for i, _ in enumerate(options):
        questions[f"s{i}"] = Noul(
            instructions=f"Is `chunk_skills[{i}]` required as part of the skill set for `task`?",
            criteria={
                "true": "This skill is one of the skills needed to handle the task",
                "false": "This skill is not needed for the task",
            },
        )
    response = _client().system_one(
        state={
            "task": query,
            "chunk_skills": [{"id": opt["id"], "text": opt["text"]} for opt in options],
        },
        questions=questions,
    )
    scores = {opt["id"]: response.answers[f"s{i}"].noul for i, opt in enumerate(options)}
    return scores, response.usage.input_tokens


def _ask_need_set(query: str, options: list[dict]) -> tuple[dict[str, float], int]:
    questions = {}
    for i, _ in enumerate(options):
        questions[f"s{i}"] = Noul(
            instructions=f"Is `candidates[{i}]` required to handle `task`?",
            criteria={
                "true": "This skill is needed (alone or together with others) to handle the task",
                "false": "This skill is not needed for the task",
            },
        )
    response = _client().system_one(
        state={
            "task": query,
            "candidates": [{"id": opt["id"], "text": opt["text"]} for opt in options],
        },
        questions=questions,
    )
    scores = {opt["id"]: response.answers[f"s{i}"].noul for i, opt in enumerate(options)}
    return scores, response.usage.input_tokens


def run_one(example: dict) -> dict:
    started = time.perf_counter()
    probabilities: dict[str, float] = {}
    chunk_choices = []
    tokens = 0
    variant = example.get("variant")

    if variant == "multiselect":
        for options in example["option_groups"]:
            scores, used = _ask_multiselect(example["query"], options)
            tokens += used
            for skill_id, score in scores.items():
                if score > probabilities.get(skill_id, 0.0):
                    probabilities[skill_id] = score
        chunk_choices = sorted(probabilities, key=lambda k: -probabilities[k])[:5]
    else:
        for options in example["option_groups"]:
            answer, usage = _ask(example["query"], options, allow_none=len(example["option_groups"]) > 1)
            tokens += usage["input_tokens"]
            chunk_choices.append(answer.choice)
            for skill_id, probability in answer.probabilities.items():
                if skill_id == NONE_ID:
                    continue
                if probability > probabilities.get(skill_id, 0.0):
                    probabilities[skill_id] = probability

    if variant == "hybrid":
        top_ids = [k for k, _ in sorted(probabilities.items(), key=lambda kv: -kv[1])[:15]]
        text_by_id = {}
        for options in example["option_groups"]:
            for opt in options:
                text_by_id[opt["id"]] = opt["text"]
        candidates = [{"id": i, "text": text_by_id.get(i, i)} for i in top_ids]
        need_scores, used = _ask_need_set(example["query"], candidates)
        tokens += used
        combined = {}
        for skill_id in top_ids:
            combined[skill_id] = need_scores.get(skill_id, 0.0)
        for skill_id, probability in probabilities.items():
            if skill_id not in combined:
                combined[skill_id] = 0.0
        probabilities = combined

    ranked = sorted(probabilities.items(), key=lambda kv: -kv[1])[:10]
    latency = time.perf_counter() - started
    return {
        "id": example["id"],
        "query_id": example["query_id"],
        "setting": example["setting"],
        "query": example["query"],
        "gold_ids": example["gold_ids"],
        "predicted": ranked[0][0] if ranked else NONE_ID,
        "chunk_choices": chunk_choices,
        "top10": [{"id": k, "p": v} for k, v in ranked],
        "set_selected": [k for k, v in probabilities.items() if v >= 0.5][:20],
        "latency_s": round(latency, 3),
        "input_tokens": tokens,
        "model": "jev-1.13.0",
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
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}")
    return done


def ranking_metrics(record: dict) -> dict:
    gold = set(record["gold_ids"])
    ranked_ids = [item["id"] for item in record["top10"]]
    metrics = {}
    for k in (1, 3, 5, 10):
        metrics[f"recall@{k}"] = 1.0 if any(i in gold for i in ranked_ids[:k]) else 0.0
    dcg = sum(1 / (1 + i) if rid in gold else 0.0 for i, rid in enumerate(ranked_ids[:10]))
    idcg = sum(1 / (1 + i) for i in range(min(len(gold), 10)))
    metrics["ndcg@10"] = dcg / idcg if idcg else 0.0
    mrr = 0.0
    for i, rid in enumerate(ranked_ids[:10], 1):
        if rid in gold:
            mrr = 1 / i
            break
    metrics["mrr@10"] = mrr
    return metrics


def aggregate(records: list[dict]) -> dict[str, dict]:
    by_setting: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_setting[record["setting"]].append(record)
    per_setting = {}
    for setting, group in by_setting.items():
        keys = list(ranking_metrics(group[0]).keys())
        per_setting[setting] = {
            key: sum(ranking_metrics(r)[key] for r in group) / len(group) for key in keys
        }
    return per_setting


def _pct(x: float) -> str:
    return f"{x * 100:.1f}"


def build_comparison(variant: str, records: list[dict]) -> str:
    baselines = json.loads((DATA / "baseline_results.json").read_text())["baselines"]
    jev = aggregate(records)

    lines = [
        f"# Jev SkillRetBench 对比（variant={variant}，每设置 {len(records) // len(SETTINGS)} 条）",
        "",
        "指标与官方 baseline 同口径（R@k / nDCG@10 / MRR；Jev 排名由 choice 概率合并得出，截断 top-10）。",
        "",
    ]
    for metric in ("recall@1", "recall@3", "recall@10", "ndcg@10", "mrr@10"):
        lines += [
            f"## {metric}",
            "",
            "| 方法 | " + " | ".join(s.replace("_", " ") for s in SETTINGS) + " | macro |",
            "|---" * (len(SETTINGS) + 2) + "|",
        ]
        for method in ("BM25", "Dense", "Hybrid", "NaiveLLM", "SADO"):
            row, values = [], []
            for setting in SETTINGS:
                value = baselines.get(method, {}).get(setting, {}).get(metric)
                if value is None and metric == "mrr@10":
                    value = baselines.get(method, {}).get(setting, {}).get("mrr")
                row.append(_pct(value) if value is not None else "—")
                if value is not None:
                    values.append(value)
            macro = _pct(sum(values) / len(values)) if values else "—"
            lines.append(f"| {method} | " + " | ".join(row) + f" | {macro} |")
        row, values = [], []
        for setting in SETTINGS:
            value = jev.get(setting, {}).get(metric)
            row.append(_pct(value) if value is not None else "—")
            if value is not None:
                values.append(value)
        macro = _pct(sum(values) / len(values)) if values else "—"
        lines.append(f"| **Jev** | " + " | ".join(row) + f" | **{macro}** |")
        lines.append("")

    if records:
        tokens = sum(r["input_tokens"] for r in records)
        latencies = sorted(r["latency_s"] for r in records)
        with_sets = [r for r in records if r.get("set_selected") is not None]
        completeness_line = ""
        if with_sets:
            by_setting: dict[str, list[dict]] = defaultdict(list)
            for record in with_sets:
                by_setting[record["setting"]].append(record)
            parts = []
            for setting in SETTINGS:
                group = by_setting.get(setting)
                if not group:
                    continue
                complete = sum(
                    1 for r in group if set(r["gold_ids"]) <= set(r["set_selected"])
                ) / len(group)
                parts.append(f"{setting.replace('_', ' ')}: {_pct(complete)}")
            completeness_line = "\n**Set completeness（全部金标都进集合的比例）**：" + "；".join(parts)
        lines += [
            f"Jev 调用：{len(records)} 条查询，{tokens} input tokens ≈ ${tokens / 1e9 * 42:.3f}，"
            f"P50 {latencies[len(latencies) // 2]:.2f}s / P95 {latencies[int(len(latencies) * 0.95)]:.2f}s"
            + completeness_line,
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev SkillRetBench eval")
    parser.add_argument("--variant", choices=("chunked", "multiselect", "hybrid", "bm25top50"), default="chunked")
    parser.add_argument("--per-setting", type=int, default=100)
    parser.add_argument("--settings", default=None, help="comma-separated settings filter")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    out_path = RESULTS / f"skillretbench-{args.variant}.jsonl"
    if args.report_only:
        records = load_done(out_path)
    else:
        settings = [s.strip() for s in args.settings.split(",")] if args.settings else None
        examples = build_dataset(args.variant, args.per_setting, settings=settings)
        records = run(examples, out_path, args.concurrency, args.limit)

    ordered = list(records.values())
    report = build_comparison(args.variant, ordered)
    report_path = RESULTS / f"skillretbench-{args.variant}-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
