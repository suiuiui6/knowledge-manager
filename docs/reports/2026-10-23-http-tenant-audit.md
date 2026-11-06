# 2026-10-23 HTTP 审核与租户范围核查

## 结论

本次为核查，未改动业务源码或现有测试。四个历史失败均复现，但并非四个产品缺陷：HTTP 审核 422 和策略抑制列表断言属于测试前提不匹配，搜索字段断言依赖 JSON 空格；MCP 关联 ID 存在实际跨租户暴露。额外验证确认 workspace 正文隔离和运维统计缓存也存在问题。

## 已确认的问题（修复优先级）

### P1：同租户不同 workspace 的模块正文可见

`src/knowledge_manager/tenancy.py:14` 的公共可见性函数只检查 tenant_id，未检查 workspace_id；`src/knowledge_manager/mcp_server.py:73` 的投影可见性同样遗漏 workspace。

合成请求持有 `team-a/ws-a` 身份，读取 `team-a/ws-other` 模块：HTTP `/api/modules/ops/other-workspace` 返回 200，MCP `load_module` 返回该模块独有正文，`deep_search` 也将其列入结果。显式请求 `workspace_id=ws-other` 返回 403，但省略覆盖参数即可命中跨 workspace 数据。因此覆盖参数校验不能代替资源本身的 workspace 检查。

影响：部署需要 workspace 隔离时，具有相同 tenant_id 的不同 workspace 用户可以读取彼此正文。此次未对所有写接口做穷举；不能推断只读面受影响，也不能据此宣称已覆盖全部权限边界。

修复方向：将 workspace 约束纳入模型与投影的公共可见性判定；同步检查 HTTP 审核的资源访问判断、MCP 查询及加载；先补同租户不同 workspace 的正反例，保留明确允许的共享语义。

### P1：租户运维报告带入全库计数，且共享缓存污染 staging 统计

`src/knowledge_manager/tenant_views.py:238` 把已筛选的 staging_meta 传给全局 `generate_ops_report`，但报告中的模块集合仍来自全库；返回时在第 264 行原样复用 `lifecycle_backlog`。`src/knowledge_manager/storage.py:2326` 只按知识库和 `ops` 名称缓存，未区分传入 staging_meta 或 tenant/workspace。

合成数据：A 有 published 模块及 pending 审核项，B 有 draft 模块及 changes-requested 审核项，A 的另一 workspace 还有一个 published 模块。

- A 冷缓存报告返回全库 `draft=1, published=2`，包含 B 的状态计数。
- A 先请求后，B 的 staging 统计返回 `pending=1`，并非 B 实际的 changes-requested。
- A 请求后，全局报告也只剩 A 的 `pending=1`，证明租户局部统计写入了全局缓存。
- 全局报告先预热后，A 的 staging 统计带入 `pending=1, changes-requested=1`。

影响：聚合信息跨租户暴露，且报表随请求顺序出现漏计/错计。本次没有观察到通过该字段暴露另一租户的模块正文。

修复方向：租户报告在聚合前筛选模块、staging 和源相关模块计数；全局缓存仅存全局输入，或以完整安全上下文区分缓存。验证 A→B、B→A、全局→A、A→全局及 workspace 组合。

### P2：MCP 搜索响应暴露其他租户关联模块 ID

`src/knowledge_manager/mcp_server.py:574` 在 deep_search 结果中直接复制 `related_modules`。合成响应的 `visible-a` 对象包含 `ops/hidden-b`，该关联目标属于 B；`neighbors` 为空，说明目标正文已被过滤，但引用标识未被过滤。普通 search_modules 的第 449 行也直接复制关联列表，合成响应同样保留该 ID。

影响：模块 ID/关联结构的元数据泄漏。本次未观察到 deep_search 返回 B 模块标题或正文；与上述 workspace 正文暴露区别记录。

修复方向：对结构化关联标识按目标可见性筛选，统一检查 search、deep_search、load/expand/graph 和 HTTP 对应输出；保留同租户及明确授权的共享关联。不能仅删除失败断言。

## 历史失败的逐项归因

| 测试 | 核查结果 |
|---|---|
| `test_staging_approve_does_not_require_full_rebuild` | 未配置认证却提交 reviewer=alice；服务端身份为 anonymous，与客户端 reviewer 不同，按现有规则返回 422。不是审核发布链路整体不可用。 |
| `test_ops_report_uses_authenticated_tenant_scope` | source_backlog 已正确筛出 A；失败在 policy_suppressed_modules。该 fixture 没配置 high 风险允许状态，默认策略不会仅因为 draft 就抑制，故列表为空。不能把这条断言失败直接认定为租户过滤失效；但另行发现了以上真实统计问题。 |
| `test_tool_search_modules` | 期望 `"source": "direct"`，实际采用 compact JSON `"source":"direct"`；字段值正常。测试应解析 MCP TextContent 中的 JSON，再断言结构和值。 |
| `test_tool_deep_search_honors_trusted_session_tenant` | 真实关联 ID 暴露；另一租户未出现在 neighbors 正文中，但仍在 related_modules 中。 |

独立审核验证：登录审核人 reviewer-a，不传客户端 reviewer，只提交 comment，返回 200/merged；审计事件 user 为 reviewer-a，含 tenant_id、request_id。伪造 reviewer=forged 返回 422，错误为 `reviewer is server-assigned`。此验证不代表所有审核并发、审批次数或策略场景均已通过。

## 验证与证据

- 环境：Windows，CPython 3.14.3，前一批最终锁定 Poetry 虚拟环境；`audit-only-windows`。
- 源码 HEAD：`4683d463c538bf186e9d643f9b0a13a7e33b0078`。既有 pyproject/lock 未提交修改保留，本次未改动。
- 使用 systematic-debugging 技能进行复现、读取契约、最小合成输入和范围验证。
- 四个历史用例单独重跑：4 failed，退出码 1；原始日志 `km-audit-http-repro.log` 在工作区父目录，副本位于本证据目录。
- 全范围命令：隔离解释器 `-m pytest -q tests/test_http_server.py tests/test_mcp_server.py tests/test_tenancy.py --basetemp <新建独立目录> --junitxml test-results/http-tenant-audit-20261023/pytest.xml`。结果 **126 passed, 4 failed, 9027 warnings**，退出码 1。环境变量为 `PYTHONUTF8=1`、`PYTHONPATH=src`，TEMP/TMP 为专用安装临时目录。未替换 tmp_path fixture 或跳过失败用例。
- 合成探针：隔离解释器运行 `test-results/http-tenant-audit-20261023/probe.py`，退出码 0。该退出码表示采集完成，**不是隔离检查通过**；观测到的越界响应见 `probe.json`，其中记录所有源码文件 SHA256。
- 所有探针只操作新建合成 KB，结束后清理该临时 KB；未读取用户实际知识内容。
- 证据目录：`test-results/http-tenant-audit-20261023/`，含 probe.py、probe.json、probe.log、pytest.log、pytest.xml、单独复现日志。
- 本次未执行整体 pytest、格式、类型、安装冒烟或部署验证：没有业务代码变更。前一批的整体失败记录仍有效，不能用本轮专项结果替代整体验收。

## 交付状态

- 已修改：新增本核查报告与可复现证据；未修改业务源码及既有测试。
- 已验证：正常审核路径可用，伪造审核人被拒绝；三个真实隔离/统计问题已复现，尚未修复。
- 已提交：本批未提交。
- 已部署：未执行。
- 下一步：先修 workspace 正文隔离与租户聚合/缓存，再修关联 ID 输出，最后纠正三个不匹配的测试前提；不得削弱授权规则换取测试通过。
