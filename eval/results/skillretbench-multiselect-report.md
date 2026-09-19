# Jev SkillRetBench 对比（variant=multiselect，每设置 20 条）

指标与官方 baseline 同口径（R@k / nDCG@10 / MRR；Jev 排名由 choice 概率合并得出，截断 top-10）。

## recall@1

| 方法 | single skill | multi skill composition | distractor | outdated redundant | budget constrained | macro |
|---|---|---|---|---|---|---|
| BM25 | 49.5 | 26.6 | 27.0 | 86.7 | 0.4 | 38.0 |
| Dense | 16.5 | 14.6 | 5.3 | 22.0 | 0.5 | 11.8 |
| Hybrid | 30.8 | 21.7 | 12.3 | 48.7 | 0.4 | 22.8 |
| NaiveLLM | 36.8 | 32.7 | 17.3 | 55.7 | 8.4 | 30.2 |
| SADO | 32.8 | 24.7 | 17.3 | 54.7 | 3.4 | 26.6 |
| **Jev** | — | 15.0 | — | — | — | **15.0** |

## recall@3

| 方法 | single skill | multi skill composition | distractor | outdated redundant | budget constrained | macro |
|---|---|---|---|---|---|---|
| BM25 | 61.3 | 50.2 | 37.0 | 96.0 | 1.4 | 49.2 |
| Dense | 27.0 | 30.4 | 12.0 | 40.7 | 1.1 | 22.2 |
| Hybrid | 43.0 | 40.0 | 19.3 | 60.7 | 1.9 | 33.0 |
| NaiveLLM | 49.0 | 51.0 | 24.3 | 67.7 | 9.9 | 40.4 |
| SADO | 45.0 | 43.0 | 24.3 | 66.7 | 4.9 | 36.8 |
| **Jev** | — | 22.0 | — | — | — | **22.0** |

## recall@10

| 方法 | single skill | multi skill composition | distractor | outdated redundant | budget constrained | macro |
|---|---|---|---|---|---|---|
| BM25 | 70.2 | 76.1 | 50.3 | 100.0 | 2.2 | 59.8 |
| Dense | 42.5 | 55.5 | 21.3 | 61.3 | 1.9 | 36.5 |
| Hybrid | 57.2 | 65.5 | 30.3 | 85.3 | 2.5 | 48.2 |
| NaiveLLM | 63.2 | 76.5 | 35.3 | 92.3 | 10.5 | 55.6 |
| SADO | 59.2 | 68.5 | 35.3 | 91.3 | 5.5 | 52.0 |
| **Jev** | — | 32.0 | — | — | — | **32.0** |

## ndcg@10

| 方法 | single skill | multi skill composition | distractor | outdated redundant | budget constrained | macro |
|---|---|---|---|---|---|---|
| BM25 | 59.7 | 69.3 | 37.6 | 93.5 | 7.1 | 53.4 |
| Dense | 28.2 | 46.7 | 12.1 | 40.9 | 6.2 | 26.8 |
| Hybrid | 43.2 | 58.7 | 20.3 | 64.8 | 8.5 | 39.1 |
| NaiveLLM | 48.2 | 67.7 | 24.3 | 70.9 | 14.5 | 45.1 |
| SADO | 45.2 | 61.7 | 25.3 | 70.9 | 11.5 | 42.9 |
| **Jev** | — | 11.9 | — | — | — | **11.9** |

## mrr@10

| 方法 | single skill | multi skill composition | distractor | outdated redundant | budget constrained | macro |
|---|---|---|---|---|---|---|
| BM25 | 56.4 | 85.0 | 33.7 | 91.3 | 20.0 | 57.3 |
| Dense | 23.8 | 60.7 | 9.3 | 34.4 | 17.0 | 29.1 |
| Hybrid | 38.9 | 75.3 | 17.2 | 58.5 | 22.9 | 42.5 |
| NaiveLLM | 45.9 | 85.3 | 22.2 | 66.5 | 29.9 | 50.0 |
| SADO | 40.9 | 78.3 | 23.2 | 65.5 | 25.9 | 46.8 |
| **Jev** | — | 19.6 | — | — | — | **19.6** |

Jev 调用：100 条查询，6406565 input tokens ≈ $0.269，P50 2.00s / P95 3.03s
