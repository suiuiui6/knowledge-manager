# Knowledge Manager 内置 KB smoke eval 结果

日期：2026-06-17

本结果用于证明项目评测链路可以运行，并不构成论文主实验。它使用 `D:\tyh\knowledge-manager\kb` 中的 7 个已发布模块，覆盖 architecture、operations 和 search 三类模块。查询由模块主题直接构造，难度较低，因此不能替代多语料 judged baseline 对比。

## 运行命令

```powershell
$env:PYTHONPATH='D:\tyh\knowledge-manager\src'
@'
from pathlib import Path
from knowledge_manager.eval_runner import load_eval_suite, run_eval_suite
suite = load_eval_suite(Path(r'D:\tyh\paper-assets\eval\km-smoke-eval-suite.json'))
result = run_eval_suite(suite, Path(r'D:\tyh\knowledge-manager\kb'))
Path(r'D:\tyh\paper-assets\results\km-smoke-eval-result.json').write_text(
    result.model_dump_json(indent=2),
    encoding='utf-8',
)
'@ | python -
```

## 结果摘要

| 指标 | 结果 |
|---|---:|
| total_cases | 7 |
| passed_cases | 7 |
| hit_rate | 100.0 |
| avg_first_hit_rank | 1.0 |
| avg_mrr | 1.0 |
| avg_ndcg_at_k | 1.0 |
| avg_recall_at_k | 1.0 |
| false_positive_rate | 0.0 |
| false_negative_rate | 0.0 |
| policy_failure_rate | 0.0 |
| retrieval_failure_rate | 0.0 |
| avg_context_tokens | 978 |

## 可支持的论文表述

可以写：

“项目评测框架已能在内置 KB 上运行，并输出 first-hit rank、MRR、nDCG@k、recall@k、false-positive/false-negative rate、policy/retrieval failure rate 等字段。”

不能写：

- 不能把该结果写成多语料 baseline 对比。
- 不能据此声称 Knowledge Manager 相对 chunk-only retrieval 具有检索性能优势。
- 不能把 7 个低难度查询外推到真实团队知识库场景。

## 后续使用方式

该结果适合作为“评测框架可运行性”的补充材料。若要进入论文主结果，需要替换为至少 2 类真实语料、30-50 个 judged queries、Knowledge Manager 与至少 2 个 baseline 的统一对比结果。
