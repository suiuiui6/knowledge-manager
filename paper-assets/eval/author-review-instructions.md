# Knowledge Manager judged query 作者审阅说明

本文件说明如何把 `judged-queries.author-review.csv` 从候选标注表转换为正式 judged queries。该流程用于准备主 baseline 实验，不是论文结果。

## 1. 审阅入口

优先使用以下两个文件之一审阅：

- `paper-assets/deliverables/knowledge-manager-query-review-packet.docx`
- `paper-assets/eval/judged-queries.author-review.csv`

Word 文件适合逐条阅读，CSV 文件适合批量填写并进入脚本处理。

## 2. 必填字段

每一行至少填写 `author_decision`。可选值如下：

| author_decision | 含义 | 是否进入正式 judged queries |
|---|---|---|
| `accept` | 当前 query、required modules、boundary 与证据短语可接受 | 是 |
| `revise` | 当前 query 可用，但需要修订模块标签或边界说明 | 是 |
| `exclude` | 当前 query 不适合作为正式评测项 | 否，进入 excluded 记录 |
| `needs_discussion` | 需要再讨论，暂不定稿 | 否，脚本会拒绝输出正式 JSONL |

空白 `author_decision` 会阻止正式输出。

## 3. revise 的填写方式

如果填写 `revise`，建议同时检查以下字段：

- `author_corrected_required_modules`：用分号分隔模块 ID，例如 `auth/authorization-code-flow; auth/token-exchange-endpoint`。
- `author_boundary_revision`：如果边界说明需要调整，在这里写最终版本。
- `author_notes`：说明为什么修订，便于后续复核。

如果 `revise` 但 `author_corrected_required_modules` 为空，脚本会沿用原 `required_modules`。

## 4. 生成正式 JSONL

当所有行都完成 `accept`、`revise` 或 `exclude` 后运行：

```powershell
python D:\tyh\paper-assets\scripts\apply_author_review.py
```

脚本会生成：

- `paper-assets/eval/judged-queries.author-labeled.jsonl`
- `paper-assets/eval/judged-queries.excluded.jsonl`
- `paper-assets/eval/judged-queries.author-labeled.summary.json`

如果仍有空白或 `needs_discussion`，脚本会拒绝生成正式 JSONL。

## 5. 进入主实验前的边界

`judged-queries.author-labeled.jsonl` 生成后，才能重新运行 baseline 并填充 `results/main-comparison.csv`。在此之前，`candidate-baseline-eval-result.*` 只能作为评测链路 dry-run，不能写入论文主结果表。
