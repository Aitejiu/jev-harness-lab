import argparse
import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pyarrow.parquet as pq

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401  (loads ../../.env)
from typesafe_sdk import Choice, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def load_snips() -> list[tuple[str, str, str]]:
    rows = pq.read_table(DATA / "snips_test.parquet").to_pylist()
    return [(f"s-{i}", row["text"], row["category"]) for i, row in enumerate(rows)]


def load_banking77() -> list[tuple[str, str, str]]:
    with (DATA / "banking77_test.csv").open() as f:
        rows = list(csv.DictReader(f))
    return [(f"b-{i}", row["text"], row["category"]) for i, row in enumerate(rows)]


LOADERS = {
    "snips": load_snips,
    "banking77": load_banking77,
}


def humanize(label: str) -> str:
    return label.replace("_", " ")


def build_questions(labels: list[str]) -> dict:
    return {
        "intent": Choice(
            instructions="Which intent best matches `user_utterance`?",
            criteria={label: humanize(label) for label in labels},
        )
    }


def run_one(labels: list[str], example_id: str, text: str, label: str) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state={"user_utterance": text},
        questions=build_questions(labels),
    )
    latency = time.perf_counter() - started
    answer = response.answers["intent"]
    top3 = sorted(answer.probabilities.items(), key=lambda kv: -kv[1])[:3]
    return {
        "id": example_id,
        "text": text,
        "label": label,
        "predicted": answer.choice,
        "confidence": answer.confidence,
        "top3": [{"label": k, "probability": v} for k, v in top3],
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


def run(examples, labels, out_path: Path, concurrency: int, limit: int | None) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path)
    todo = [e for e in examples if e[0] not in done]
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        print(f"nothing to run ({len(done)} cached)")
        return done

    print(f"running {len(todo)} examples (concurrency={concurrency}, cached={len(done)})")
    lock = threading.Lock()
    with out_path.open("a") as f, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(run_one, labels, example_id, text, label): example_id
            for example_id, text, label in todo
        }
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
            if i % 200 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}")
    return done


def per_label_accuracy(records: list[dict]) -> list[tuple[str, int, int]]:
    stats: dict[str, list[int]] = {}
    for record in records:
        hit, total = stats.setdefault(record["label"], [0, 0])
        stats[record["label"]] = [hit + int(record["predicted"] == record["label"]), total + 1]
    return sorted(
        [(label, hit, total) for label, (hit, total) in stats.items()],
        key=lambda row: row[1] / row[2],
    )


def build_report(dataset: str, records: list[dict], label_count: int) -> str:
    n = len(records)
    correct = sum(1 for r in records if r["predicted"] == r["label"])
    top3_hits = sum(1 for r in records if any(t["label"] == r["label"] for t in r["top3"]))
    latencies = sorted(r["latency_s"] for r in records)
    input_tokens = sum(r["input_tokens"] for r in records)

    lines = [
        f"# Jev 意图分类评测：{dataset}",
        "",
        f"- 样本数：{n}，类别数：{label_count}（随机基线 {1 / label_count:.1%}）",
        f"- 模型：{records[0]['model']}",
        f"- Top-1 准确率：**{correct / n:.1%}**（{correct}/{n}）",
        f"- Top-3 命中率：{top3_hits / n:.1%}",
        f"- 延迟：P50 {latencies[len(latencies) // 2]:.2f}s / P95 {latencies[int(len(latencies) * 0.95)]:.2f}s",
        f"- 成本：{input_tokens} input tokens ≈ ${input_tokens / 1e9 * 42:.4f}",
        "",
        "## 置信度门控",
        "",
        "| confidence ≥ | 自动处理覆盖率 | 自动处理准确率 | 转人工比例 |",
        "|---|---|---|---|",
    ]
    for threshold in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99):
        covered = [r for r in records if r["confidence"] >= threshold]
        if not covered:
            continue
        covered_correct = sum(1 for r in covered if r["predicted"] == r["label"])
        lines.append(
            f"| {threshold:.2f} | {len(covered) / n:.1%} | {covered_correct / len(covered):.1%} | "
            f"{1 - len(covered) / n:.1%} |"
        )

    lines += [
        "",
        "## 校准（置信度 vs 实际正确率）",
        "",
        "| 置信度区间 | 数量 | 平均置信度 | 实际准确率 |",
        "|---|---|---|---|",
    ]
    for i in range(10):
        low, high = i / 10, (i + 1) / 10
        bucket = [
            r for r in records
            if (low <= r["confidence"] < high)
            or (i == 9 and r["confidence"] == 1.0)
        ]
        if not bucket:
            continue
        bucket_correct = sum(1 for r in bucket if r["predicted"] == r["label"])
        lines.append(
            f"| {low:.1f}-{high:.1f} | {len(bucket)} | "
            f"{sum(r['confidence'] for r in bucket) / len(bucket):.2f} | "
            f"{bucket_correct / len(bucket):.1%} |"
        )

    lines += [
        "",
        "## 最差 10 个类别",
        "",
        "| 类别 | 准确率 | 样本数 |",
        "|---|---|---|",
    ]
    for label, hit, total in per_label_accuracy(records)[:10]:
        lines.append(f"| {label} | {hit / total:.1%} | {total} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev intent classification eval")
    parser.add_argument("--dataset", choices=sorted(LOADERS), default="snips")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    examples = LOADERS[args.dataset]()
    labels = sorted({label for _, _, label in examples})
    out_path = RESULTS / f"{args.dataset}-intent.jsonl"
    records = run(examples, labels, out_path, args.concurrency, args.limit)
    ordered = [records[e[0]] for e in examples if e[0] in records]

    report = build_report(args.dataset, ordered, len(labels))
    report_path = RESULTS / f"{args.dataset}-intent-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
