import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401
from metrics import confusion_at, threshold_sweep
from typesafe_sdk import Noul, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data" / "whowhen"
RESULTS = Path(__file__).resolve().parent / "results"

STEPS_PER_TRAJECTORY = 8

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def load_trajectories() -> list[dict]:
    trajectories = []
    for split in ("ag", "hc"):
        for path in sorted((DATA / split).glob("*.json"), key=lambda p: int(p.stem)):
            data = json.loads(path.read_text())
            history = data.get("history") or []
            try:
                mistake_step = int(data.get("mistake_step"))
            except (TypeError, ValueError):
                continue
            if not history or mistake_step < 0 or mistake_step >= len(history):
                continue
            trajectories.append(
                {
                    "id": f"ww-{split}-{path.stem}",
                    "split": split,
                    "task": str(data.get("question", "")),
                    "history": history,
                    "failure_index": mistake_step,
                    "reason": str(data.get("mistake_reason", ""))[:300],
                }
            )
    return trajectories


def build_dataset() -> list[dict]:
    rng = random.Random(42)
    records = []
    for trajectory in load_trajectories():
        history = trajectory["history"]
        failure_index = trajectory["failure_index"]
        other_indexes = [i for i in range(len(history)) if i != failure_index]
        sampled_others = rng.sample(other_indexes, min(STEPS_PER_TRAJECTORY - 1, len(other_indexes)))
        for step_index in sorted([failure_index, *sampled_others]):
            step = history[step_index]
            records.append(
                {
                    "id": f"{trajectory['id']}-s{step_index}",
                    "trajectory": trajectory["id"],
                    "split": trajectory["split"],
                    "step_index": step_index,
                    "label": int(step_index == failure_index),
                    "task": trajectory["task"][:1500],
                    "agent": str(step.get("name", "")),
                    "role": str(step.get("role", "")),
                    "step": str(step.get("content", ""))[:1200],
                }
            )
    return records


def build_questions() -> dict:
    return {
        "is_failure_step": Noul(
            instructions="Does `step` contain the decisive mistake that causes the whole task to fail?",
            criteria={
                "true": "The step introduces an error, wrong assumption, or wrong action that is never corrected and directly leads to the final wrong result",
                "false": "The step is correct, or any issue in it is later corrected, or it does not decide the final outcome",
            },
        )
    }


def run_one(example: dict) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state={
            "task": example["task"],
            "agent": example["agent"],
            "role": example["role"],
            "step": example["step"],
        },
        questions=build_questions(),
    )
    latency = time.perf_counter() - started
    return {
        **example,
        "score": response.answers["is_failure_step"].noul,
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
            if i % 200 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}")
    return done


def auroc(records: list[dict]) -> float:
    positives = [r["score"] for r in records if r["label"]]
    negatives = [r["score"] for r in records if not r["label"]]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report(records: list[dict]) -> str:
    n = len(records)
    base = confusion_at(records, 0.5)
    sweep = threshold_sweep(records)
    best_f1 = max(sweep, key=lambda r: r["f1"])
    area = auroc(records)

    by_trajectory: dict[str, list[dict]] = {}
    for record in records:
        by_trajectory.setdefault(record["trajectory"], []).append(record)

    top1_hits = 0
    failure_ranks = []
    for group in by_trajectory.values():
        ranked = sorted(group, key=lambda r: -r["score"])
        failure = next(r for r in group if r["label"])
        best_score = ranked[0]["score"]
        if failure["score"] >= best_score:
            top1_hits += 1
        rank = 1 + sum(1 for r in group if r["score"] > failure["score"])
        failure_ranks.append(rank)
    top1 = top1_hits / len(by_trajectory)
    mean_rank = sum(failure_ranks) / len(failure_ranks)
    random_top1 = 1 / STEPS_PER_TRAJECTORY

    failure_mean = sum(r["score"] for r in records if r["label"]) / sum(1 for r in records if r["label"])
    normal_mean = sum(r["score"] for r in records if not r["label"]) / sum(1 for r in records if not r["label"])

    lines = [
        "# Jev Agent 轨迹失败步骤定位评测（Who&When）",
        "",
        f"- 轨迹数：{len(by_trajectory)}（每条采样 {STEPS_PER_TRAJECTORY} 步：1 个标注失败步 + 7 个随机步），共 {n} 步",
        f"- 任务：给定任务 + 单个步骤，判断该步骤是否是导致失败的决策性错误",
        f"- 模型：{records[0]['model']}",
        "",
        "## 步骤级判定",
        "",
        f"- AUROC：**{area:.3f}**",
        f"- 阈值 0.50：精确率 {_pct(base.precision)}，召回率 {_pct(base.recall)}，F1 {_pct(base.f1)}",
        f"- 最佳 F1：阈值 {best_f1['threshold']:.2f}，F1 {_pct(best_f1['f1'])}（精确率 {_pct(best_f1['precision'])}，召回率 {_pct(best_f1['recall'])}）",
        f"- 平均分：失败步 {failure_mean:.2f} vs 普通步 {normal_mean:.2f}",
        "",
        "## 轨迹级定位（top-1）",
        "",
        f"- Jev top-1 命中率：**{_pct(top1)}**（随机基线 {_pct(random_top1)}）",
        f"- 失败步骤平均排名：{mean_rank:.2f} / {STEPS_PER_TRAJECTORY}",
        "",
        "## 阈值扫描",
        "",
        "| 阈值 | 精确率 | 召回率 | F1 |",
        "|---|---|---|---|",
    ]
    for row in sweep:
        if row["threshold"] in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            lines.append(
                f"| {row['threshold']:.2f} | {_pct(row['precision'])} | {_pct(row['recall'])} | {_pct(row['f1'])} |"
            )
    lines += [
        "",
        "## 按数据集拆分",
        "",
        "| 来源 | 轨迹数 | 步骤级 AUROC | 轨迹级 top-1 |",
        "|---|---|---|---|",
    ]
    for split, label in (("ag", "Algorithm-Generated"), ("hc", "Hand-Crafted")):
        group = [r for r in records if r["split"] == split]
        if not group:
            continue
        split_trajectories = {}
        for record in group:
            split_trajectories.setdefault(record["trajectory"], []).append(record)
        split_top1 = 0
        for steps in split_trajectories.values():
            failure = next(r for r in steps if r["label"])
            if failure["score"] >= max(r["score"] for r in steps):
                split_top1 += 1
        lines.append(
            f"| {label} | {len(split_trajectories)} | {auroc(group):.3f} | "
            f"{_pct(split_top1 / len(split_trajectories))} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev failure-step localization on Who&When")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    examples = build_dataset()
    out_path = RESULTS / "whowhen.jsonl"
    records = run(examples, out_path, args.concurrency, args.limit)
    ordered = [records[e["id"]] for e in examples if e["id"] in records]

    report = build_report(ordered)
    report_path = RESULTS / "whowhen-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
