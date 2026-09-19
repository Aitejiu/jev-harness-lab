import argparse
import json
import math
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rank_bm25 import BM25Okapi

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401
from typesafe_sdk import Score, TypeSafeClient

DATA = Path(__file__).resolve().parent / "data" / "scifact" / "scifact"
RESULTS = Path(__file__).resolve().parent / "results"

CANDIDATES_PER_QUERY = 15
MAX_RELEVANT_PER_QUERY = 5

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def load_corpus() -> dict[str, str]:
    corpus = {}
    with (DATA / "corpus.jsonl").open() as f:
        for line in f:
            doc = json.loads(line)
            corpus[doc["_id"]] = f"{doc.get('title', '')}. {doc.get('text', '')}".strip()
    return corpus


def load_queries() -> dict[str, str]:
    queries = {}
    with (DATA / "queries.jsonl").open() as f:
        for line in f:
            query = json.loads(line)
            queries[query["_id"]] = query["text"]
    return queries


def load_qrels() -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = {}
    with (DATA / "qrels" / "test.tsv").open() as f:
        next(f)
        for line in f:
            qid, docid, score = line.strip().split("\t")
            qrels.setdefault(qid, {})[docid] = int(score)
    return qrels


def build_dataset(limit_queries: int, seed: int = 42) -> list[dict]:
    corpus = load_corpus()
    queries = load_queries()
    qrels = load_qrels()
    doc_ids = list(corpus)
    tokenized = [_tokens(corpus[doc_id]) for doc_id in doc_ids]
    bm25 = BM25Okapi(tokenized)

    qids = sorted(q for q in queries if q in qrels and qrels[q])
    random.Random(seed).shuffle(qids)
    qids = qids[:limit_queries]

    records = []
    for qid in qids:
        query = queries[qid]
        relevant = sorted(qrels[qid], key=lambda d: -qrels[qid][d])[:MAX_RELEVANT_PER_QUERY]
        relevant = [d for d in relevant if d in corpus]
        scores = bm25.get_scores(_tokens(query))
        ranked = sorted(range(len(doc_ids)), key=lambda i: -scores[i])
        candidates = list(relevant)
        for i in ranked:
            if len(candidates) >= CANDIDATES_PER_QUERY:
                break
            doc_id = doc_ids[i]
            if doc_id not in candidates:
                candidates.append(doc_id)
        for doc_id in candidates:
            records.append(
                {
                    "id": f"{qid}::{doc_id}",
                    "qid": qid,
                    "query": query,
                    "doc_id": doc_id,
                    "document": corpus[doc_id][:2000],
                    "relevant": int(doc_id in qrels[qid]),
                    "bm25_score": float(scores[doc_ids.index(doc_id)]),
                }
            )
    return records


def build_questions() -> dict:
    return {
        "relevance": Score(
            instructions="How relevant is `document` to `query`?",
            criteria=[
                "Not relevant: unrelated topic or does not address the query",
                "Tangential: same domain but does not provide the information asked for",
                "Partially relevant: contains some supporting information but not the answer",
                "Relevant: directly provides the information needed to answer the query",
            ],
        )
    }


def run_one(example: dict) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state={"query": example["query"], "document": example["document"]},
        questions=build_questions(),
    )
    latency = time.perf_counter() - started
    return {
        **example,
        "jev_score": response.answers["relevance"].score,
        "jev_confidence": response.answers["relevance"].confidence,
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


def _ranking_metrics(group: list[dict], score_key: str, k: int = 5) -> dict:
    ranked = sorted(group, key=lambda r: -r[score_key])
    top_k = ranked[:k]
    relevant_total = sum(1 for r in group if r["relevant"])
    hits = sum(1 for r in top_k if r["relevant"])
    recall = hits / relevant_total if relevant_total else 0.0
    precision = hits / k
    mrr = 0.0
    for rank, record in enumerate(ranked, 1):
        if record["relevant"]:
            mrr = 1 / rank
            break
    dcg = sum(
        (1 / math.log2(rank + 1)) if record["relevant"] else 0.0
        for rank, record in enumerate(top_k, 1)
    )
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(relevant_total, k) + 1))
    ndcg = dcg / ideal if ideal else 0.0
    hit1 = 1.0 if ranked and ranked[0]["relevant"] else 0.0
    return {"recall@5": recall, "precision@5": precision, "mrr": mrr, "ndcg@5": ndcg, "hit@1": hit1}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report(records: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record["qid"], []).append(record)

    def aggregate(score_key: str) -> dict:
        metrics = [ _ranking_metrics(group, score_key) for group in groups.values()]
        return {key: sum(m[key] for m in metrics) / len(metrics) for key in metrics[0]}

    jev = aggregate("jev_score")
    bm25 = aggregate("bm25_score")

    relevant_scores = [r["jev_score"] for r in records if r["relevant"]]
    irrelevant_scores = [r["jev_score"] for r in records if not r["relevant"]]
    ju_mean = sum(relevant_scores) / len(relevant_scores)
    ju_irr = sum(irrelevant_scores) / len(irrelevant_scores)
    input_tokens = sum(r["input_tokens"] for r in records)
    latencies = sorted(r["latency_s"] for r in records)

    lines = [
        "# Jev 检索重排评测（SciFact / BEIR）",
        "",
        f"- 查询数：{len(groups)}，候选对：{len(records)}（每查询 BM25 top-{CANDIDATES_PER_QUERY} 内混入标注相关文档）",
        f"- 任务：对每个 (query, document) 打 0-3 相关性分，重排候选",
        f"- 模型：{records[0]['model']}",
        f"- 延迟：P50 {latencies[len(latencies) // 2]:.2f}s",
        f"- 成本：{input_tokens} input tokens ≈ ${input_tokens / 1e9 * 42:.4f}",
        "",
        f"- 相关性分数均值：相关文档 {ju_mean:.2f} vs 不相关 {ju_irr:.2f}",
        "",
        "## 排序指标（候选集内）",
        "",
        "| 排序器 | Recall@5 | Precision@5 | MRR | nDCG@5 | Hit@1 |",
        "|---|---|---|---|---|---|",
        f"| BM25 | {_pct(bm25['recall@5'])} | {_pct(bm25['precision@5'])} | {bm25['mrr']:.3f} | {bm25['ndcg@5']:.3f} | {_pct(bm25['hit@1'])} |",
        f"| **Jev 重排** | {_pct(jev['recall@5'])} | {_pct(jev['precision@5'])} | {jev['mrr']:.3f} | {jev['ndcg@5']:.3f} | {_pct(jev['hit@1'])} |",
        "",
        "| 指标 | BM25 → Jev 变化 |",
        "|---|---|",
        f"| Recall@5 | {_pct(bm25['recall@5'])} → {_pct(jev['recall@5'])} |",
        f"| MRR | {bm25['mrr']:.3f} → {jev['mrr']:.3f} |",
        f"| nDCG@5 | {bm25['ndcg@5']:.3f} → {jev['ndcg@5']:.3f} |",
        "",
        "## 各查询明细（Jev 提升/回退最大的 5 个）",
        "",
        "| query | BM25 MRR | Jev MRR | 变化 |",
        "|---|---|---|---|",
    ]
    deltas = []
    for qid, group in groups.items():
        b = _ranking_metrics(group, "bm25_score")["mrr"]
        j = _ranking_metrics(group, "jev_score")["mrr"]
        deltas.append((j - b, qid, b, j))
    deltas.sort(reverse=True)
    for delta, qid, b, j in deltas[:5]:
        query_text = next(r["query"] for r in groups[qid])[:60]
        lines.append(f"| {qid} {query_text}… | {b:.2f} | {j:.2f} | {'+' if delta >= 0 else ''}{delta:.2f} |")
    for delta, qid, b, j in deltas[-5:]:
        query_text = next(r["query"] for r in groups[qid])[:60]
        lines.append(f"| {qid} {query_text}… | {b:.2f} | {j:.2f} | {delta:.2f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev rerank eval on SciFact")
    parser.add_argument("--queries", type=int, default=60)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    examples = build_dataset(limit_queries=args.queries)
    out_path = RESULTS / "scifact-rerank.jsonl"
    records = run(examples, out_path, args.concurrency, args.limit)
    ordered = [records[e["id"]] for e in examples if e["id"] in records]

    report = build_report(ordered)
    report_path = RESULTS / "scifact-rerank-report.md"
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
