import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from typesafe_sdk import TypeSafeClient

from guardrail import QUESTION_NAME, build_questions, build_state

_thread_local = threading.local()


def _client() -> TypeSafeClient:
    if not hasattr(_thread_local, "client"):
        _thread_local.client = TypeSafeClient()
    return _thread_local.client


def _run_one(example) -> dict:
    started = time.perf_counter()
    response = _client().system_one(
        state=build_state(example.text),
        questions=build_questions(),
    )
    latency = time.perf_counter() - started
    answer = response.answers[QUESTION_NAME]
    return {
        "id": example.id,
        "text": example.text,
        "label": example.label,
        "subtype": example.subtype,
        "severity": example.severity,
        "score": answer.noul,
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


def run(examples, out_path: Path, concurrency: int = 4, limit: int | None = None) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path)

    todo = [e for e in examples if e.id not in done]
    if limit is not None:
        todo = todo[:limit]
    total = len(todo)
    if total == 0:
        print(f"nothing to run ({len(done)} cached)")
        return done

    print(f"running {total} examples (concurrency={concurrency}, cached={len(done)})")
    write_lock = threading.Lock()
    with out_path.open("a") as f, ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_run_one, e): e for e in todo}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
            except Exception as exc:
                example = futures[future]
                print(f"  FAILED {example.id}: {exc}")
                continue
            with write_lock:
                f.write(json.dumps(record) + "\n")
                f.flush()
                done[record["id"]] = record
            if i % 100 == 0 or i == total:
                print(f"  {i}/{total}")
    return done
