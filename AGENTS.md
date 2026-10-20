# knowledge-manager 项目规则

> 本项目是 Git 原生的结构化知识模块管理系统，提供 CLI、MCP 和 HTTP 服务。
> 规则以当前项目真实架构为准，不把 GraphRAG、向量数据库或 SaaS 架构假设带入本项目。

## 项目边界

1. 核心数据是可审查、可版本控制的 JSON 知识模块，不是大规模 GraphRAG 图数据库。
2. 默认目标规模是小到中型知识库；扩展到更大规模前，必须先用实际数据证明当前文件型架构的性能和一致性边界。
3. 标准内容流程是 `extract -> staging -> review -> publish -> serve`。自动提取不能绕过审核策略直接发布，除非产品规范明确允许。
4. 当前运行面包括 CLI、MCP stdio 服务和 FastAPI HTTP 服务；变更必须说明影响了哪些运行面。
5. 参考项目评估、历史报告和测试产物只能作为证据或借鉴，不能替代当前代码、当前配置和当前命令的验证。

## 启动与接续

每次开始工作依次读取：本文件、`README.md`、相关 `docs/` 规范和 runbook、当前任务涉及的代码与测试。先检查 Git 分支和工作区，保留其他任务未提交的修改，不覆盖、不回退、不清理无关文件。

如果任务涉及生产、租户、认证、备份、性能或发布，优先读取：

- `docs/runbooks/production-release-checklist.md`
- `docs/runbooks/enterprise-rollout.md`
- `docs/runbooks/observability-and-alerting.md`
- `docs/runbooks/backup-restore-drill.md`
- `docs/runbooks/enterprise-performance-test-plan.md`

结束或交接时记录实际修改、决策依据、验证命令和退出码、未完成事项及下一步。不要把历史报告、自报结果或推测写成当前完成事实。

## 架构与代码规则

1. 生产代码放在 `src/knowledge_manager/`，测试放在 `tests/`，运维和验证脚本放在 `scripts/`，规范与 runbook 放在 `docs/`。
2. 知识模块必须通过 `schemas.py` 的 Pydantic 模型校验；禁止在业务入口绕过 schema 写入不可验证的模块 JSON。
3. 写入知识库、索引、搜索投影、推荐索引和任务状态时，优先使用现有的原子写入、重建和失效机制；新增派生文件必须定义重建方式和漂移检查。
4. 多租户字段使用 `tenant_id` 和 `workspace_id`。HTTP、MCP、搜索、模块详情、任务和管理接口必须使用同一套授权语义。
5. 认证关闭只适用于明确的本地开发或单机模式。生产模式必须配置受支持的认证提供方；不能通过默认匿名行为绕过生产授权。
6. 新增或修改权限时，同时更新 RBAC 权限表、拒绝审计事件和对应测试；不得只在路由层增加检查而遗漏 MCP 或 CLI 入口。
7. 文件型存储适合单节点场景。任何多进程、多 worker 或多实例改动都必须说明锁、原子性、重复执行、恢复和冲突处理方式。
8. 不因参考 GraphRAG 项目建议而默认引入 Neo4j、Celery、向量数据库、LangGraph 或微服务；只有明确需求、能力边界验证和可复现基准都成立时才引入核心依赖。
9. 外部 LLM、Confluence、Notion 或其他 provider 调用必须使用环境变量或受控配置保存凭证；日志、审计和错误信息不得输出 API Key、Token 或完整敏感内容。

## 任务与数据可靠性

1. ingestion job 必须持久化状态、租约、心跳、阶段、尝试次数和错误信息。
2. 新任务必须考虑幂等键、重复领取、重试上限、失败状态、恢复和取消；不能用“进程仍在运行”作为唯一状态来源。
3. 任务完成只有在结果模块、staging 元数据和必要派生索引状态一致后才能标记成功。
4. 删除模块时同步处理索引、搜索投影、推荐索引、缓存、审计和待执行维护任务，并验证不会继续返回已删除内容。
5. 备份必须包含规范要求的知识库和运行状态；恢复默认只允许写入空目标目录，并在交付前完成恢复验证。

## 测试与验证门槛

变更后按影响范围执行验证，不能只运行静态检查或历史报告：

- Python 测试：`poetry run pytest -q`
- 格式检查：`poetry run black --check src tests scripts`
- 类型检查：`poetry run mypy src`
- 安装冒烟：`python scripts/verify_install_smoke.py`
- 真实 MCP/HTTP 变更：运行对应协议、接口和租户隔离测试
- 生产性能或发布变更：使用当前代码快照生成新的 matrix summary，并运行 `verify-production-readiness`、`verify-deployment` 或对应 release evidence 检查

验证要求：

1. 测试必须绑定最终代码快照、实际配置和实际命令；记录退出码和报告路径。
2. 生产门禁必须同时检查 readiness、完整性、性能、备份恢复和部署证据。`ready=true` 不能覆盖性能或完整性失败。
3. 规模测试至少区分 XS、S、M；不能用小规模通过推断大规模通过。
4. 当前 Windows 环境只能记录为 `audit-only-windows`，不能声称已经形成机械阻断；未执行的 CI 或分支保护不得宣称有效。
5. 完整测试因环境依赖失败时，必须说明失败原因和影响范围，不得把部分通过写成整体通过。

## 安全与生产规则

1. 生产服务必须使用受支持的认证提供方、明确的租户/workspace claims 和最小权限 RBAC。
2. 全局共享模块必须显式定义；涉及企业机密时默认采用租户隔离，不能依赖隐含的“空 tenant 可读”行为。
3. 健康检查区分 liveness 和 readiness；readiness 必须检查配置、索引、失败任务、过期租约、维护积压和完整性。
4. 日志和审计必须脱敏；审计记录应包含用户、租户、操作、资源、结果和 request ID。
5. 发布前必须有可验证的备份、恢复、回滚和容量证据；runbook 与实际部署命令不一致时，先修正权威文档或代码。
6. 依赖必须由 `poetry.lock` 锁定。新增运行时导入必须同步更新 `pyproject.toml` 和锁文件，并在干净环境执行安装冒烟。

## 文档唯一真相源

- 对外产品边界和运行方式：`README.md`
- 发布、部署、备份和运维：`docs/runbooks/`
- 数据结构和接口契约：`src/knowledge_manager/schemas.py`、`http_server.py`、`mcp_server.py` 及对应测试
- 性能和生产判定：当前运行生成的 matrix summary、release evidence 和验证报告

代码、测试、脚本和文档不一致时，必须在同一变更中修复或明确记录阻塞，不能保留已知漂移。

## 交付规则

最终报告分别说明：已修改、已验证、已提交、已部署。没有执行的项目标记为未执行；失败项目说明原因和影响。只有当适用门槛全部满足时，才可以使用“完成”“修复”或“可生产”表述。
