from dataclasses import asdict, dataclass


@dataclass
class Confusion:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def false_positive_rate(self) -> float:
        return self.fp / (self.fp + self.tn) if self.fp + self.tn else 0.0


def confusion_at(records: list[dict], threshold: float) -> Confusion:
    tp = fp = tn = fn = 0
    for record in records:
        positive = record["score"] >= threshold
        if positive and record["label"]:
            tp += 1
        elif positive and not record["label"]:
            fp += 1
        elif not positive and record["label"]:
            fn += 1
        else:
            tn += 1
    return Confusion(tp, fp, tn, fn)


def threshold_sweep(records: list[dict], step: float = 0.05) -> list[dict]:
    thresholds = [round(step * i, 2) for i in range(1, int(1 / step))]
    out = []
    for threshold in thresholds:
        c = confusion_at(records, threshold)
        out.append({"threshold": threshold, **asdict(c), "precision": c.precision,
                    "recall": c.recall, "f1": c.f1, "accuracy": c.accuracy,
                    "fpr": c.false_positive_rate})
    return out


def best_by(records: list[dict], key: str) -> dict:
    return max(threshold_sweep(records), key=lambda row: (row[key], row["threshold"]))


def coverage_curve(records: list[dict]) -> list[dict]:
    """Auto-decide only when certainty (max(p, 1-p)) >= threshold; abstain otherwise."""
    out = []
    for certainty in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99):
        covered = [r for r in records if max(r["score"], 1 - r["score"]) >= certainty - 1e-9]
        if not covered:
            continue
        correct = sum(1 for r in covered if (r["score"] >= 0.5) == bool(r["label"]))
        out.append(
            {
                "certainty": certainty,
                "coverage": len(covered) / len(records),
                "accuracy": correct / len(covered),
                "abstain": 1 - len(covered) / len(records),
            }
        )
    return out


def calibration(records: list[dict], bins: int = 10) -> list[dict]:
    out = []
    for i in range(bins):
        low, high = i / bins, (i + 1) / bins
        bucket = [
            r for r in records
            if (low <= r["score"] < high) or (i == bins - 1 and r["score"] == 1.0)
        ]
        if not bucket:
            continue
        out.append(
            {
                "bin": f"{low:.1f}-{high:.1f}",
                "count": len(bucket),
                "mean_score": sum(r["score"] for r in bucket) / len(bucket),
                "positive_rate": sum(r["label"] for r in bucket) / len(bucket),
            }
        )
    return out


def subtype_table(records: list[dict], threshold: float = 0.5, min_count: int = 10) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record["subtype"] or "unknown", []).append(record)

    rows = []
    for subtype, group in groups.items():
        malicious = [r for r in group if r["label"]]
        benign = [r for r in group if not r["label"]]
        rows.append(
            {
                "subtype": subtype,
                "n": len(group),
                "malicious": len(malicious),
                "mean_score": sum(r["score"] for r in group) / len(group),
                "recall": (
                    sum(1 for r in malicious if r["score"] >= threshold) / len(malicious)
                    if malicious
                    else None
                ),
                "fpr": (
                    sum(1 for r in benign if r["score"] >= threshold) / len(benign)
                    if benign
                    else None
                ),
            }
        )
    return sorted((r for r in rows if r["n"] >= min_count), key=lambda r: -r["n"])


def latency_stats(records: list[dict]) -> dict:
    latencies = sorted(r["latency_s"] for r in records)
    n = len(latencies)

    def pct(p: float) -> float:
        return latencies[min(n - 1, int(p * n))]

    return {"p50": pct(0.5), "p90": pct(0.9), "p95": pct(0.95), "max": latencies[-1]}


def usage_stats(records: list[dict]) -> dict:
    input_tokens = sum(r["input_tokens"] for r in records)
    output_tokens = sum(r["output_tokens"] for r in records)
    return {
        "calls": len(records),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_input_cost_usd": input_tokens / 1e9 * 42,
    }
