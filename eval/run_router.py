import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401
from typesafe_sdk import Noul, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data" / "routerbench_0shot.pkl"
RESULTS = Path(__file__).resolve().parent / "results"

CHEAP_SET = {
    "mistralai/mistral-7b-chat",
    "WizardLM/WizardLM-13B-V1.2",
    "meta/llama-2-70b-chat",
    "meta/code-llama-instruct-34b-chat",
}
REP_CHEAP = "WizardLM/WizardLM-13B-V1.2"
REP_MID = "zero-one-ai/Yi-34B-Chat"
REP_STRONG = "gpt-4-1106-preview"

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def load_sample(per_dataset: int = 10, seed: int = 42) -> list[dict]:
    df = pd.read_pickle(DATA)
    df = df[df["oracle_model_to_route_to"] != "no_model_correct"]
    sampled = df.groupby("eval_name", group_keys=False).head(per_dataset)
    sampled = sampled.sample(frac=1.0, random_state=seed)

    rows = []
    for _, row in sampled.iterrows():
        oracle = row["oracle_model_to_route_to"]
        rows.append(
            {
                "id": f"r-{row['sample_id']}",
                "prompt": row["prompt"],
                "eval_name": row["eval_name"],
                "oracle": oracle,
                "label": int(oracle not in CHEAP_SET),
                "score_cheap": float(row[REP_CHEAP]),
                "score_mid": float(row[REP_MID]),
                "score_strong": float(row[REP_STRONG]),
                "cost_cheap": float(row[f"{REP_CHEAP}|total_cost"]),
                "cost_mid": float(row[f"{REP_MID}|total_cost"]),
                "cost_strong": float(row[f"{REP_STRONG}|total_cost"]),
            }
        )
    return rows


def build_questions() -> dict:
    return {
        "needs_capable": Noul(
            instructions="Does `prompt` need a large, capable model, or can a small fast model handle it?",
            criteria={
                "true": "Requires strong reasoning, multi-step math, difficult coding, or specialized knowledge that small 7B-13B models typically get wrong",
                "false": "Simple, common, or pattern-based; a small fast model would typically answer correctly",
            },
        )
    }


def run_one(example: dict) -> dict:
    started = time.perf_counter()
    response = _client().system_one(state={"prompt": example["prompt"]}, questions=build_questions())
    latency = time.perf_counter() - started
    return {
        **example,
        "needs_capable": response.answers["needs_capable"].noul,
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


def metrics_at(records: list[dict], threshold: float) -> dict:
    tp = fp = tn = fn = 0
    quality = cost = 0.0
    for record in records:
        needs = record["needs_capable"] >= threshold
        if needs and record["label"]:
            tp += 1
        elif needs and not record["label"]:
            fp += 1
        elif not needs and record["label"]:
            fn += 1
        else:
            tn += 1
        if needs:
            quality += record["score_mid"]
            cost += record["cost_mid"]
        else:
            quality += record["score_cheap"]
            cost += record["cost_cheap"]
    n = len(records)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "accuracy": (tp + tn) / n,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "quality": quality / n,
        "cost": cost / n,
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report(records: list[dict]) -> str:
    n = len(records)
    sweep = [metrics_at(records, t / 20) for t in range(1, 20)]
    best_f1 = max(sweep, key=lambda r: r["f1"])
    at_half = next(r for r in sweep if r["threshold"] == 0.5)

    always_cheap_q = sum(r["score_cheap"] for r in records) / n
    always_mid_q = sum(r["score_mid"] for r in records) / n
    always_strong_q = sum(r["score_strong"] for r in records) / n
    always_cheap_c = sum(r["cost_cheap"] for r in records) / n
    always_mid_c = sum(r["cost_mid"] for r in records) / n
    always_strong_c = sum(r["cost_strong"] for r in records) / n
    oracle_q = sum(1.0 for _ in records) / n
    oracle_c = sum(
        r["cost_cheap"] if r["oracle"] in CHEAP_SET else r["cost_mid"] if r["oracle"] not in CHEAP_SET and r["oracle"] not in {"claude-v1", "claude-v2", "gpt-4-1106-preview"} else r["cost_strong"]
        for r in records
    ) / n

    lines = [
        "# Jev 模型路由评测（RouterBench 0-shot）",
        "",
        f"- 样本数：{n}（按 eval_name 分层抽样，排除 no_model_correct）",
        f"- 任务：Jev 判断 `prompt` 是否需要大模型；代码据此选 cheap（{REP_CHEAP}）或 mid（{REP_MID}）",
        f"- 标签：oracle 路由目标不在 cheap 集合内 → 需要大模型（{sum(r['label'] for r in records)}/{n}）",
        f"- 模型：{records[0]['model']}",
        "",
        "## 路由判断质量",
        "",
        "| 阈值 | 准确率 | 精确率 | 召回率 | F1 |",
        "|---|---|---|---|---|",
    ]
    for row in sweep:
        if row["threshold"] in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
            lines.append(
                f"| {row['threshold']:.2f} | {_pct(row['accuracy'])} | {_pct(row['precision'])} | "
                f"{_pct(row['recall'])} | {_pct(row['f1'])} |"
            )
    lines += [
        "",
        f"最佳 F1：阈值 {best_f1['threshold']:.2f}，F1 {_pct(best_f1['f1'])}（准确率 {_pct(best_f1['accuracy'])}）",
        "",
        "## 成本-质量模拟（平均每条 prompt）",
        "",
        "| 策略 | 平均质量（准确率） | 平均成本（$） |",
        "|---|---|---|",
        f"| 永远 cheap（{REP_CHEAP.split('/')[-1]}） | {_pct(always_cheap_q)} | {always_cheap_c:.5f} |",
        f"| 永远 mid（{REP_MID.split('/')[-1]}） | {_pct(always_mid_q)} | {always_mid_c:.5f} |",
        f"| 永远 strong（{REP_STRONG}） | {_pct(always_strong_q)} | {always_strong_c:.5f} |",
        f"| Jev 路由 @0.50 | {_pct(at_half['quality'])} | {at_half['cost']:.5f} |",
        f"| Jev 路由 @{best_f1['threshold']:.2f}（最佳 F1） | {_pct(best_f1['quality'])} | {best_f1['cost']:.5f} |",
        f"| oracle 路由（上界） | 100.0% | {oracle_c:.5f} |",
        "",
        "## 按数据集拆解（阈值 0.50）",
        "",
        "| eval_name | 样本 | 需要大模型比例 | Jev 判断准确率 |",
        "|---|---|---|---|",
    ]
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record["eval_name"], []).append(record)
    for name, group in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:12]:
        accuracy = sum(1 for r in group if (r["needs_capable"] >= 0.5) == bool(r["label"])) / len(group)
        lines.append(
            f"| {name} | {len(group)} | {_pct(sum(r['label'] for r in group) / len(group))} | {_pct(accuracy)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev model-routing eval on RouterBench")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--per-dataset", type=int, default=10)
    args = parser.parse_args()

    examples = load_sample(per_dataset=args.per_dataset)
    out_path = RESULTS / "routerbench.jsonl"
    records = run(examples, out_path, args.concurrency, args.limit)
    ordered = [records[e["id"]] for e in examples if e["id"] in records]

    report = build_report(ordered)
    report_path = RESULTS / "routerbench-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
