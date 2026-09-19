import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import common  # noqa: F401  (loads ../.env)
from report import build_report
from runner import run
from sources import LOADERS


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev eval harness")
    parser.add_argument("--dataset", choices=sorted(LOADERS), default="neuralchemy-test")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    out_path = args.out or Path("results") / f"{args.dataset}.jsonl"
    report_path = args.report or Path("results") / f"{args.dataset}-report.md"

    examples = LOADERS[args.dataset]()
    records = run(examples, out_path, concurrency=args.concurrency, limit=args.limit)
    ordered = [records[e.id] for e in examples if e.id in records]

    report = build_report(args.dataset, ordered)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(report)
    print(f"results: {out_path}\nreport:  {report_path}")


if __name__ == "__main__":
    main()
