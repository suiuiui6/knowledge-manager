# 路由失败案例记录模板

本文件记录受控路由测试中的失败和边界案例。当前版本是模板，不包含新的测试结果。

## 案例记录格式

| 字段 | 内容 |
|---|---|
| scenario_id | TBD |
| query | TBD |
| expected behavior | 应加载哪些模块；是否需要边界提示或拒答 |
| observed behavior | 实际加载模块和输出行为 |
| failure type | boundary_confusion / troubleshooting_signal_weak / irrelevant_overload / missing_module |
| likely cause | 模块摘要不足、caveats 为空、索引标签弱、查询超出知识库范围等 |
| manuscript use | 是否进入正文失败分析 |

## 已知应保留的失败类型

- OAuth/JWT 类 near-scope 或 partial-scope 边界识别不足。
- redirect troubleshooting 类排障信号弱。
- 短词或缩略词查询导致检索空结果或召回不稳定。

上述类型只能在真实日志和模块证据齐全后写成结果，不应只凭记忆补数字。
