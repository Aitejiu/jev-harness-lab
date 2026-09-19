import argparse
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401
from metrics import (
    calibration,
    confusion_at,
    coverage_curve,
    latency_stats,
    threshold_sweep,
    usage_stats,
)
from typesafe_sdk import Noul, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"

FILES = {
    "irrelevance": ("BFCL_v3_irrelevance.json", 0),
    "live_irrelevance": ("BFCL_v3_live_irrelevance.json", 0),
    "live_relevance": ("BFCL_v3_live_relevance.json", 1),
}

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def _user_text(question) -> str:
    parts = []
    for turn in question:
        for message in turn:
            if message.get("role") == "user":
                parts.append(str(message.get("content", "")))
    return "\n".join(parts)


def _function_text(function: dict) -> str:
    description = str(function.get("description", ""))[:300]
    parameters = function.get("parameters") or {}
    required = set(parameters.get("required") or [])
    properties = parameters.get("properties") or {}
    params = ", ".join(
        f"{name}{'*' if name in required else ''}" for name in properties
    )
    return f"- {function.get('name')}: {description} (params: {params})"


def build_dataset() -> list[dict]:
    records = []
    for source, (filename, label) in FILES.items():
        path = DATA / filename
        for i, line in enumerate(path.read_text().splitlines()):
            if not line.strip():
                continue
            entry = json.loads(line)
            records.append(
                {
                    "id": f"bfcl-{source}-{i}",
                    "source": source,
                    "user_query": _user_text(entry["question"]),
                    "functions_text": "\n".join(_function_text(f) for f in entry["function"]),
                    "function_count": len(entry["function"]),
                    "label": label,
                }
            )
    return records


def build_questions_v1() -> dict:
    return {
        "relevant": Noul(
            instructions="Should at least one of the functions in `available_functions` be called to satisfy `user_query`?",
            criteria={
                "true": "At least one listed function is relevant: it can perform or directly help with what the user asks",
                "false": "None of the listed functions are relevant to the user query; they cannot perform or directly help with the request",
            },
        )
    }


def build_questions_v2() -> dict:
    return {
        "relevant": Noul(
            instructions="Is one of the listed functions the expected tool for `user_query`?",
            criteria={
                "true": {"what": "A listed function's stated purpose directly matches the user's request, so calling it is the expected action", "not_for": "Functions that are merely related, adjacent, or reusable in a workaround"},
                "false": {"what": "No listed function is purpose-built for the request; any plausible use would be generic, incidental, or a workaround", "examples": ["A general HTTP request helper when a dedicated API function is what the task calls for"]},
            },
        )
    }


def build_questions_v2c() -> dict:
    return {
        "purpose_match": Noul(
            instructions="Does any listed function's stated purpose directly cover the action `user_query` asks for?",
            criteria={
                "true": "A function exists specifically to perform this kind of task; its description names the operation or resource the user requests",
                "false": "No function's stated purpose is this operation; the closest functions serve a different primary purpose",
            },
        ),
        "incidental_only": Noul(
            instructions="Would using a listed function for this request be only a generic workaround rather than its intended purpose?",
            criteria={
                "true": "The function is general-purpose (e.g., generic HTTP request, generic search, raw shell) and would only be reused incidentally to approximate the request",
                "false": "The function is purpose-built for this request, or the request cannot be served by any listed function even generically",
            },
        ),
    }


BUILDERS = {
    "v1": build_questions_v1,
    "v2": build_questions_v2,
    "v2c": build_questions_v2c,
}


def run_one(example: dict, variant: str) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state={"user_query": example["user_query"], "available_functions": example["functions_text"]},
        questions=BUILDERS[variant](),
    )
    latency = time.perf_counter() - started
    answers = response.answers
    extra = {}
    if variant == "v2c":
        purpose = answers["purpose_match"].noul
        incidental = answers["incidental_only"].noul
        score = purpose * (1 - incidental)
        extra = {"purpose_match": purpose, "incidental_only": incidental}
    else:
        score = answers["relevant"].noul
    return {
        **example,
        **extra,
        "variant": variant,
        "score": score,
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


def run(examples: list[dict], out_path: Path, concurrency: int, limit: int | None, variant: str) -> dict:
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
        futures = {pool.submit(run_one, e, variant): e["id"] for e in todo}
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
    n = len(records)
    base = confusion_at(records, 0.5)
    sweep = threshold_sweep(records)
    best_f1 = max(sweep, key=lambda r: r["f1"])
    coverage = coverage_curve(records)
    latency = latency_stats(records)
    usage = usage_stats(records)

    lines = [
        "# Jev 工具相关性判定评测（BFCL）",
        "",
        f"- 样本数：{n}（不可调用 {sum(1 for r in records if r['label'] == 0)} / 应调用 {sum(1 for r in records if r['label'] == 1)}）",
        f"- 任务：给定 `user_query` 和可用函数列表，判断是否至少有一个函数应被调用",
        f"- 模型：{records[0]['model']}",
        f"- 延迟：P50 {latency['p50']:.2f}s / P95 {latency['p95']:.2f}s（输入更长）",
        f"- 成本：{usage['input_tokens']} input tokens ≈ ${usage['estimated_input_cost_usd']:.4f}",
        "",
        "## 判定表现（难点在不可调用样本的误报）",
        "",
        f"- 阈值 0.50：精确率 {_pct(base.precision)}，召回率 {_pct(base.recall)}，F1 {_pct(base.f1)}，误报率 {_pct(base.false_positive_rate)}",
        f"- 最佳 F1：阈值 {best_f1['threshold']:.2f}，F1 {_pct(best_f1['f1'])}（精确率 {_pct(best_f1['precision'])}，召回率 {_pct(best_f1['recall'])}，误报率 {_pct(best_f1['fpr'])}）",
        "",
        "## 阈值扫描",
        "",
        "| 阈值 | 精确率 | 召回率 | F1 | 误报率 |",
        "|---|---|---|---|---|",
    ]
    for row in sweep:
        if row["threshold"] in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            lines.append(
                f"| {row['threshold']:.2f} | {_pct(row['precision'])} | {_pct(row['recall'])} | "
                f"{_pct(row['f1'])} | {_pct(row['fpr'])} |"
            )
    lines += [
        "",
        "## 置信度门控",
        "",
        "| certainty ≥ | 覆盖率 | 自动处理准确率 | 转人工 |",
        "|---|---|---|---|",
    ]
    for row in coverage:
        lines.append(
            f"| {row['certainty']:.2f} | {_pct(row['coverage'])} | {_pct(row['accuracy'])} | {_pct(row['abstain'])} |"
        )
    lines += [
        "",
        "## 按来源拆分（阈值 0.5）",
        "",
        "| 来源 | 标签 | 数量 | 准确率 | 平均分 | 平均函数数 |",
        "|---|---|---|---|---|---|",
    ]
    for source, label in (("irrelevance", 0), ("live_irrelevance", 0), ("live_relevance", 1)):
        group = [r for r in records if r["source"] == source]
        if not group:
            continue
        accuracy = sum(1 for r in group if (r["score"] >= 0.5) == bool(r["label"])) / len(group)
        lines.append(
            f"| {source} | {'应调用' if label else '不可调用'} | {len(group)} | {_pct(accuracy)} | "
            f"{sum(r['score'] for r in group) / len(group):.2f} | {sum(r['function_count'] for r in group) / len(group):.1f} |"
        )
    lines += [
        "",
        "## 校准",
        "",
        "| 分数区间 | 数量 | 实际应调用比例 |",
        "|---|---|---|",
    ]
    for row in calibration(records):
        lines.append(f"| {row['bin']} | {row['count']} | {_pct(row['positive_rate'])} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev tool-relevance eval on BFCL")
    parser.add_argument("--variant", choices=sorted(BUILDERS), default="v2")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    examples = build_dataset()
    out_path = RESULTS / f"bfcl-relevance-{args.variant}.jsonl"
    records = run(examples, out_path, args.concurrency, args.limit, args.variant)
    ordered = [records[e["id"]] for e in examples if e["id"] in records]

    report = build_report(ordered)
    report_path = RESULTS / f"bfcl-relevance-{args.variant}-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
