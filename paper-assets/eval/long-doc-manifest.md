# 长文档专项 manifest 模板

本文件用于记录 long-document handling 的专项验证输入。当前版本是模板，不包含已完成专项结果。

| doc_id | corpus_id | source_type | char_count | expected_chunk_count | observed_chunk_count | chunk_size | overlap | expected_modules | notes | status |
|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| LONG-001 | TBD | architecture/runbook/api | TBD | TBD | TBD | 4000 cap | TBD | TBD | Fill with a real long document before evaluation. | template_not_measured |

## 记录要求

- 保存原始输入或匿名化输入。
- 保存 chunk 数、chunk size、overlap、JSON retry 次数。
- 保存输出模块、重复模块、去重记录和人工质量判断。
- 只写“增强”或“专项验证结果”，不能写成终局式长文档结论。
