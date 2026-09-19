# Jev 模型路由评测（RouterBench 0-shot）

- 样本数：825（按 eval_name 分层抽样，排除 no_model_correct）
- 任务：Jev 判断 `prompt` 是否需要大模型；代码据此选 cheap（WizardLM/WizardLM-13B-V1.2）或 mid（zero-one-ai/Yi-34B-Chat）
- 标签：oracle 路由目标不在 cheap 集合内 → 需要大模型（405/825）
- 模型：jev-1.13.0

## 路由判断质量

| 阈值 | 准确率 | 精确率 | 召回率 | F1 |
|---|---|---|---|---|
| 0.20 | 52.1% | 53.3% | 20.0% | 29.1% |
| 0.30 | 52.0% | 56.5% | 9.6% | 16.5% |
| 0.40 | 51.9% | 62.5% | 4.9% | 9.2% |
| 0.50 | 51.3% | 60.0% | 2.2% | 4.3% |
| 0.60 | 51.0% | 60.0% | 0.7% | 1.5% |
| 0.70 | 50.8% | 0.0% | 0.0% | 0.0% |
| 0.80 | 50.8% | 0.0% | 0.0% | 0.0% |

最佳 F1：阈值 0.05，F1 65.9%（准确率 49.3%）

## 成本-质量模拟（平均每条 prompt）

| 策略 | 平均质量（准确率） | 平均成本（$） |
|---|---|---|
| 永远 cheap（WizardLM-13B-V1.2） | 42.0% | 0.00005 |
| 永远 mid（Yi-34B-Chat） | 60.9% | 0.00013 |
| 永远 strong（gpt-4-1106-preview） | 80.3% | 0.00249 |
| Jev 路由 @0.50 | 42.4% | 0.00005 |
| Jev 路由 @0.05（最佳 F1） | 60.8% | 0.00013 |
| oracle 路由（上界） | 100.0% | 0.00044 |

## 按数据集拆解（阈值 0.50）

| eval_name | 样本 | 需要大模型比例 | Jev 判断准确率 |
|---|---|---|---|
| mmlu-marketing | 10 | 40.0% | 60.0% |
| consensus_summary | 10 | 40.0% | 60.0% |
| chinese_zodiac | 10 | 100.0% | 0.0% |
| mmlu-college-chemistry | 10 | 40.0% | 70.0% |
| mmlu-conceptual-physics | 10 | 60.0% | 40.0% |
| mtbench | 10 | 60.0% | 20.0% |
| chinese_famous_novel | 10 | 100.0% | 0.0% |
| mmlu-human-aging | 10 | 30.0% | 70.0% |
| mmlu-professional-psychology | 10 | 50.0% | 50.0% |
| mmlu-high-school-geography | 10 | 20.0% | 80.0% |
| mmlu-college-biology | 10 | 20.0% | 80.0% |
| mmlu-high-school-chemistry | 10 | 40.0% | 60.0% |
