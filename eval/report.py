from metrics import (
    best_by,
    calibration,
    confusion_at,
    coverage_curve,
    latency_stats,
    subtype_table,
    threshold_sweep,
    usage_stats,
)


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report(dataset: str, records: list[dict]) -> str:
    positives = sum(r["label"] for r in records)
    base = confusion_at(records, 0.5)
    best_f1 = best_by(records, "f1")
    coverage = coverage_curve(records)
    calib = calibration(records)
    latency = latency_stats(records)
    usage = usage_stats(records)

    lines = [
        f"# Jev 评测报告：{dataset}",
        "",
        f"- 样本数：{len(records)}（恶意 {positives} / 良性 {len(records) - positives}）",
        f"- 模型：{records[0]['model'] if records else 'n/a'}",
        f"- 成本：{usage['input_tokens']} input tokens ≈ ${usage['estimated_input_cost_usd']:.4f}（仅输入估算）",
        f"- 延迟：P50 {latency['p50']:.2f}s / P90 {latency['p90']:.2f}s / P95 {latency['p95']:.2f}s",
        "",
        "## 阈值 0.50 表现",
        "",
        f"- 准确率 {_pct(base.accuracy)}，精确率 {_pct(base.precision)}，召回率 {_pct(base.recall)}，F1 {_pct(base.f1)}",
        f"- 良性样本误报率 FPR {_pct(base.false_positive_rate)}（{(base.fp)}/{base.fp + base.tn}）",
        "",
        "## 阈值扫描（挑选）",
        "",
        "| 阈值 | 精确率 | 召回率 | F1 | 准确率 | 误报率 |",
        "|---|---|---|---|---|---|",
    ]
    sweep = threshold_sweep(records)
    interesting = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    for row in sweep:
        if row["threshold"] in interesting:
            lines.append(
                f"| {row['threshold']:.2f} | {_pct(row['precision'])} | {_pct(row['recall'])} | "
                f"{_pct(row['f1'])} | {_pct(row['accuracy'])} | {_pct(row['fpr'])} |"
            )
    lines += [
        "",
        f"最佳 F1：阈值 {best_f1['threshold']:.2f}，F1 {_pct(best_f1['f1'])}（精确率 {_pct(best_f1['precision'])}，召回率 {_pct(best_f1['recall'])}）",
        "",
        "## 按攻击类型拆分（阈值 0.50）",
        "",
        "| subtype | 数量 | 恶意数 | 平均分 | 召回率 | 误报率 |",
        "|---|---|---|---|---|---|",
    ]
    for row in subtype_table(records):
        recall = _pct(row["recall"]) if row["recall"] is not None else "—"
        fpr = _pct(row["fpr"]) if row["fpr"] is not None else "—"
        lines.append(
            f"| {row['subtype']} | {row['n']} | {row['malicious']} | "
            f"{row['mean_score']:.2f} | {recall} | {fpr} |"
        )
    lines += [
        "",
        "## 置信度门控（自动处理 vs 转人工）",
        "",
        "`certainty = max(p, 1-p)`，低于阈值的样本视为不确定、转人工。",
        "",
        "| certainty ≥ | 自动处理覆盖率 | 自动处理准确率 | 转人工比例 |",
        "|---|---|---|---|",
    ]
    for row in coverage:
        if round(row["certainty"], 2) in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99):
            lines.append(
                f"| {row['certainty']:.2f} | {_pct(row['coverage'])} | {_pct(row['accuracy'])} | {_pct(row['abstain'])} |"
            )
    lines += [
        "",
        "## 校准（预测概率 vs 实际比例）",
        "",
        "| 分数区间 | 数量 | 平均分数 | 实际恶意比例 |",
        "|---|---|---|---|",
    ]
    for row in calib:
        lines.append(
            f"| {row['bin']} | {row['count']} | {row['mean_score']:.2f} | {_pct(row['positive_rate'])} |"
        )
    return "\n".join(lines) + "\n"
