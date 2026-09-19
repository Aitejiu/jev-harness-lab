# Jev 检索重排评测（SciFact / BEIR）

- 查询数：60，候选对：900（每查询 BM25 top-15 内混入标注相关文档）
- 任务：对每个 (query, document) 打 0-3 相关性分，重排候选
- 模型：jev-1.13.0
- 延迟：P50 0.31s
- 成本：668830 input tokens ≈ $0.0281

- 相关性分数均值：相关文档 2.38 vs 不相关 0.65

## 排序指标（候选集内）

| 排序器 | Recall@5 | Precision@5 | MRR | nDCG@5 | Hit@1 |
|---|---|---|---|---|---|
| BM25 | 74.2% | 15.7% | 0.622 | 0.632 | 50.0% |
| **Jev 重排** | 90.0% | 19.3% | 0.843 | 0.848 | 78.3% |

| 指标 | BM25 → Jev 变化 |
|---|---|
| Recall@5 | 74.2% → 90.0% |
| MRR | 0.622 → 0.843 |
| nDCG@5 | 0.632 → 0.848 |

## 各查询明细（Jev 提升/回退最大的 5 个）

| query | BM25 MRR | Jev MRR | 变化 |
|---|---|---|---|
| 715 Low expression of miR7a does represses target genes and exer… | 0.07 | 1.00 | +0.93 |
| 577 In mice, P. chabaudi parasites are able to proliferate faste… | 0.07 | 1.00 | +0.93 |
| 575 In domesticated populations of Saccharomyces cerevisiae, who… | 0.07 | 1.00 | +0.93 |
| 1221 The genomic aberrations found in matasteses are very similar… | 0.07 | 1.00 | +0.93 |
| 1191 The amount of publicly available DNA data doubles every 10 y… | 0.07 | 1.00 | +0.93 |
| 75 Active H. pylori urease has a polymeric structure that compr… | 0.50 | 0.33 | -0.17 |
| 303 DMRT1 is a sex-determining gene that is epigenetically regul… | 0.50 | 0.33 | -0.17 |
| 727 Ly6C hi monocytes have a lower inflammatory capacity compare… | 0.50 | 0.14 | -0.36 |
| 237 Cells lacking clpC have a defect in sporulation efficiency i… | 1.00 | 0.50 | -0.50 |
| 163 Bariatric surgery has a positive impact on mental health.… | 1.00 | 0.50 | -0.50 |
