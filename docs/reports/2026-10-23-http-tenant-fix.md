# 2026-10-23 HTTP 审核与租户边界修复记录

本批接续 `2026-10-23-http-tenant-audit.md` 的实际复现，用户已授权继续修复。只使用本项目文件型知识库架构；参考 GraphRAG 项目不构成本项目架构要求。

## 已修改

- 统一 tenant/workspace 可见性：模块、搜索投影、MCP 邻居使用同一规则。资源 workspace 为空表示租户内共享；上下文 workspace 为空保留租户范围读取语义。跨租户共享仍受 `allow_global_reads` 控制，多租户模式默认关闭。
- HTTP 模块 JSON 与 Markdown 在返回前检查规范模块范围。已存在 Markdown 文件不再绕过权限；范围化 Markdown 从规范数据生成，并过滤结构化关联引用。
- 搜索结果最终筛选覆盖向量合并与策略强制伴随模块。关联 ID 按目标范围筛选，使用响应副本，保留规范文件及缓存中的完整元数据。
- 运维报表在聚合前筛选模块、staging 与来源，再计算生命周期及 stale 数量。租户输入和显式 staging 输入不再读写全局报表快照，避免请求顺序污染。
- HTTP 更新、删除、批准、拒绝在范围拒绝时写入 `authz.denied`，包含用户、租户、资源和 request ID。保留现有 HTTP 管理员跨范围管理及无认证本地模式语义；未改变 RBAC 角色集合。
- MCP 联合搜索传递可信会话范围；更新与归档先检查范围；新增模块写入会话 tenant/workspace。MCP 范围拒绝记录 `authz.denied`，主体为该 stdio 接口现有的 `mcp-agent`，不伪造 HTTP 用户或 request ID。
- MCP 范围化资源应用与工具相同的配置化全局读取策略；多租户模式不注册未范围化的 lint 与 namespace 全局资源。联合搜索工具仍可按可信会话范围检索 namespace。
- 纠正三个既有测试前提：审核测试使用真实登录审核人，不伪造 reviewer；租户 ops fixture 显式配置 high 风险允许状态；MCP 搜索解析 JSON 后检查字段，保留 compact JSON 单独测试。

## 决策与限制

- 当前租户 ops 报表选择直接聚合，尚未新增按租户/workspace 分片的缓存。正确性优先，未运行新的 XS/S/M 性能矩阵，不能据此推断大规模性能。
- 本批保证结构化 `related_modules` 不暴露不可见目标，不对作者正文中的自然语言、链接或字符串做内容脱敏。
- MCP 的可信会话由启动端建立，本批没有增加 MCP 用户认证/RBAC 身份模型，也不等同于允许把本地 stdio 管理工具直接暴露到公网。
- 项目仍采用全库唯一模块路径与现有 staging ID 机制；未改造为租户独立物理命名空间或解决所有同名写入竞争。
- 保留上批 `pyproject.toml`、`poetry.lock` 修改和已有未跟踪目录，没有清理用户数据。

## 验证方法与证据

环境为 Windows / CPython 3.14.3，结论标记 **audit-only-windows**。解释器为 `D:/tyh/km-locked-venvs/knowledge-manager-96lmHReR-py3.14/Scripts/python.exe`。分支 `feat/knowledge-manager-phase2`，HEAD `4683d463c538bf186e9d643f9b0a13a7e33b0078`；实际未提交源码、测试、脚本和锁文件 SHA256 见 `test-results/http-tenant-fix-20261023/snapshot.json`。

测试环境变量：`PYTHONUTF8=1`、`PYTHONPATH=src`、`TEMP/TMP=D:/tyh/km-install-temp`。HTTP 测试在获准的非沙箱执行环境运行，使用原始 pytest fixture，没有加载旧 tmp_path 替代插件。

新增 `tests/test_tenant_boundaries.py` 共 28 项：HTTP JSON/Markdown workspace 隔离、审核拒绝审计、短查询/投影查询/强制伴随模块、四种报表缓存预热顺序、MCP search/deep/load/expand/graph 引用隔离及存储不变性、跨 workspace 缓存、MCP 写入范围/新增归属/联合搜索、共享语义、资源全局读取策略、来源 stale 计数、全局资源注册。另在缓存、Markdown 和 MCP 既有测试中校正了 category 参数、维护队列执行时机，并加入 MCP 二次加载命中缓存的真实行为测试。

先失败后修复：最初 16 项全部真实失败，日志在工作区父目录 `km-red-boundaries.log`；随后 MCP 写入/联合搜索 6 项真实失败，拒绝审计/资源策略及全局资源注册也分别复现。来源 stale 测试初版缺少 schema 必填字段，纠正测试数据后通过，该初始 schema 错误不算产品缺陷。保存的后续失败证据见 `red-resources.log`、`red-global.log`。

| 检查 | 实际命令（上述解释器） | 退出码 / 结果 | 证据 |
|---|---|---|---|
| HTTP/MCP/tenancy 专项 | `-m pytest -q tests/test_tenant_boundaries.py tests/test_http_server.py tests/test_mcp_server.py tests/test_tenancy.py --basetemp D:/tyh/km-final-protocol --disable-warnings --junitxml test-results/http-tenant-fix-20261023/protocol.xml` | 0；158 passed | `protocol.log/xml` |
| 全量测试 | `-m pytest -q --basetemp D:/tyh/km-final-full --disable-warnings --junitxml test-results/http-tenant-fix-20261023/full.xml` | 1；824 passed / 9 failed，342.38 秒 | `full.log/xml` |
| 校正测试后的全量测试 | `-m pytest -q --basetemp D:/tyh/km-full-after-testfix --disable-warnings --junitxml test-results/http-tenant-fix-20261023/full-after-testfix.xml` | 1；832 passed / 3 failed，317.95 秒 | `full-after-testfix.log/xml` |
| 缓存/Markdown/MCP 行为回归 | `-m pytest -q tests/test_cache.py tests/test_sync.py tests/test_mcp_server.py --basetemp D:/tyh/km-green-cache-sync-mcp3 --disable-warnings` | 0；73 passed | `cache-sync-mcp-final.log/xml` |
| 本次修改测试格式 | `-m black --check tests/test_cache.py tests/test_sync.py` | 0；2 文件合规 | `black-testfix-final.log` |
| 完整格式检查 | `-m black --check --workers 1 src tests scripts` | 1；84 文件需格式化、32 文件合规 | `black-final.log` |
| 干净安装冒烟 | `scripts/verify_install_smoke.py --work-dir D:/tyh/km-install-temp` | 0；8 项检查通过 | `install-smoke.json` |
| 类型检查 | `-m mypy src` | 1；100 errors / 26 files | `mypy.log` |

安装冒烟使用 `PIP_NO_INDEX=1`、`PIP_FIND_LINKS=D:/tyh/km-wheelhouse`、`PIP_CONSTRAINT=D:/tyh/km-locked-constraints.txt`，清空 `PYTHONPATH`；由当前项目构建 wheel，在新建虚拟环境安装并执行实际 CLI 检查。

Black 最初两个沙箱内只读检查未正常结束，核实进程归属后仅终止本轮对应进程；上表为非沙箱重跑的实际完成结果。未通过大范围格式化掩盖历史格式债务，仅格式化新增回归文件与小型 tenancy 文件。类型错误与历史记录同为 100 个，不以数量相同替代整体验收。

对照上批 `D:/tyh/km-locked-tests.xml` 的失败用例集合：13 个减为 3 个，**新增失败集合为空**。本轮通过校正真实接口和维护执行时机，消除了缓存 4 项和 Markdown 2 项；前一轮已消除 HTTP/MCP 4 项。剩余为管理面板 ops/staging 复用、推荐 telemetry 复用、非 Git 目录 changelog，各 1 项，均仍是基线失败集合中的项目。

最终测试快照记录 119 个输入文件的 SHA256；结果和基线差集记录于 `verification-summary-after-testfix.json`。新加测试为 28 项，另增加 1 个 MCP 缓存行为测试和 1 个 Markdown 队列时机测试，原有用例保留，整体总数为 835。

用户确认提交后，2026-10-23 再次校验全部 119 个输入文件和上批依赖哈希，均未变化，`pip check` 退出码 0。提交前重跑同范围协议测试，仅 basetemp 改为 `D:/tyh/km-precommit-protocol`、报告名改为 `precommit-protocol.xml`：退出码 0，158 passed，38.48 秒；原全量失败及静态检查结果继续如实保留。依赖配置和安装证据已单独提交为 `8101341`，未推送。

未执行部署、发布、真实服务 verify-deployment 或新的生产性能矩阵；没有启用或宣称 CI/分支保护机械阻断。

## 三项剩余失败核查（2026-10-23）

对剩余三项失败逐项复现并追踪调用链后，确认均为测试前提漂移，不需要修改生产代码：

- 管理面板复用测试补齐 `team-docs` 的真实 `SourceRegistry`，保留实现中的来源可见性过滤。
- 推荐 telemetry 测试改为写入实际 `search_events.jsonl`，统计 `Path.read_text`；验证当前 `load_search_events_readonly` 快照在一次推荐生成中只读取文件一次。
- 非 Git changelog 测试在临时知识库内初始化独立、无提交的 Git 仓库，避免被工作区父仓库识别为 Git 工作区。

锁定虚拟环境下三项专项测试命令退出码 0，结果为 `3 passed`。相关文件范围测试为 `148 passed`。本轮未修改生产代码。使用系统 Python 执行全量测试时为 `828 passed / 7 failed`，失败集中在 Windows 默认编码和 CLI 子进程输出，不能作为锁定验证环境的基线替代；锁定环境全量重跑未在本轮命令会话中完成，因此不宣称全量门槛已重新通过。

## 交付状态

- 已修改：三项失败测试的契约与 fixture，以及本报告的核查记录；未修改生产代码。
- 已验证：三项专项 `3 passed`；相关文件范围 `148 passed`。完整格式检查和类型检查仍未通过；锁定环境全量重跑未完成，系统 Python 全量结果受环境编码影响为 `828 passed / 7 failed`。
- 已提交：本轮修改尚未提交；上一批提交和依赖修复提交保持不变，未推送。
- 已部署：未执行。
- 后续：如需宣称全量门槛，需要在锁定验证环境完成一次全量重跑；当前不宣称项目整体验收通过或生产就绪。
