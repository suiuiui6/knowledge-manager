# Knowledge Manager 投稿就绪度审计

日期：2026-06-17

## 当前结论

当前版本已经具备“带图 Word 投稿型初稿”的形态，但尚未达到“完全可投终稿”。主要原因不是格式，而是主实验对比证据仍未补齐。

## 已完成

| 项目 | 证据 | 状态 |
|---|---|---|
| Word 初稿 | `paper-assets/deliverables/knowledge-manager-paper-v3-submission-draft.docx` | 已完成 |
| 正式图片 | 图 1 系统流转图、图 2 MCP 序列图，PNG 已嵌入 Word | 已完成 |
| 主稿结构 | 摘要、引言、相关工作、设计、实现、评估、结果、局限、讨论、结论、参考文献 | 已完成 |
| 高风险词清理 | 主稿和 Word 正文未检出过强优势、终局式解决、首创性口号等风险表述 | 已完成 |
| 内部路径清理 | Word XML 未检出 `test-results/` 或 `D:\tyh` | 已完成 |
| 主线锁定 | `storyline.md` | 已完成 |
| Claim-Evidence 锁定 | `claim-evidence-lock.md` | 已完成 |
| 评测材料模板 | `eval/` 与 `results/` 下的 schema、CSV、JSONL、结果模板 | 已完成 |
| candidate baseline dry-run | 已生成 `candidate-baseline-eval-result.json/md`，覆盖结构化模块检索、BM25/关键词 chunk baseline 和 chunk-only keyword baseline | 已完成但不可作为主结果 |
| judged query 作者审阅包 | 已生成 `judged-queries.author-review.csv/md/json` 与 `deliverables/knowledge-manager-query-review-packet.docx` | 已完成，用于人工确认标签 |
| 作者审阅应用脚本 | 已生成 `scripts/apply_author_review.py`，只有明确 `accept` 或 `revise` 的条目才会写入 `judged-queries.author-labeled.jsonl` | 已完成，当前因 30 条均未审阅而拒绝输出 |
| 内置 KB smoke eval | `results/km-smoke-eval-result.json` 与 `results/km-smoke-eval-result.md` | 已完成，仅证明评测链路可运行 |

## 未完成

| 项目 | 为什么影响投稿 | 下一步 |
|---|---|---|
| 多语料 judged baseline 对比 | 不能证明相对 chunk-only retrieval 的实际收益与代价 | 先审阅 `knowledge-manager-query-review-packet.docx`，确认或修订 30 条 candidate queries |
| 主实验结果表 | 北大核心等强普刊应用系统论文通常需要对照结果 | 填写 `author_decision` 后运行 `scripts/apply_author_review.py`，再用输出的 `judged-queries.author-labeled.jsonl` 填充 `results/main-comparison.csv` 并写入第 6 节 |
| 长文档专项 | 目前只有实现增强，没有质量验证 | 填充 `long-doc-manifest.md` 和 `long-doc-results.csv` |
| 写路径 E2E | 当前证据弱于读路径和协议路径 | 运行并记录 `write-path-e2e.json` 中的步骤 |
| 路由扩展场景 | 5 个受控场景不足以支撑更强路由结论 | 扩展 `routing-results.csv` 到约 20 场景 |

## 投稿判断

若只作为内部评阅或导师/合作者审阅稿，当前 Word 初稿可以使用。

若目标是北大核心及同类较强期刊，建议至少补齐 2 类真实语料、30-50 个 judged queries、2 个 baseline 和主实验结果表。

若目标是 SCI 四区，建议进一步补 3 类语料、80-120 个 judged queries、3 个 baseline、消融、长文档专项和写路径 E2E。
