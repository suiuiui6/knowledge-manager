# 代码质量与工程可靠性修复计划

日期：2026-11-23。
状态：A–D 已实现，本地适用验证完成；Python 3.10.20/3.12.13 全套退出0，旧3.12.8退出兼容问题保留，远端CI未执行。
依据：仓库根目录 `review-engineering-report.md`、`review_engineering_probe.py` 及对应日志。
基准快照：`86144a18405160bc176ee4dfe2c3fc62ededce63`。

## 目标与范围

修复审查中已复现的数据校验、图索引、任务接管、持续恢复及重复审核问题；使依赖安装、类型检查和 CI 结果能准确表达实际质量。

本轮仅涉及代码质量、业务流程和工程可靠性，不包含网安审查或相关功能改造。保留现有文件型单节点架构，不引入数据库、消息队列、微服务或全项目重写。不启用 goal/Harness，不创建定时任务。

用户随后显式调用 subagent-driven-development 并要求继续，已授权修复及子 Agent 协作。产品修复已实施；提交、推送、PR、发布和部署未执行，也未取得相应授权。最终证据见 ../../reports/2026-11-23-code-quality-remediation.md。

## 执行准备与事实核对

- [x] 在实际实施目录重新读取 AGENTS.md，检查分支、工作区和当前 HEAD；保留其他任务修改。
- [x] 确认实施快照与本计划基准的差异，仅重查受变化影响的发现。当前目录是独立审查克隆；不能把根目录旧版本或另一克隆当作相同代码。
- [x] 阅读相关既有测试、runbook 与历史计划。`2026-10-23-github-ci-release-plan.md` 明确选择过非阻断静态检查，本轮收紧是新的改进目标，实施时同步更新当前文档，保留历史记录。
- [x] 在项目目录使用锁定依赖的隔离环境建立修复前基线，记录 Python、Poetry、安装清单及各项退出码。先运行 `poetry check --lock`，再运行 `poetry install --no-interaction`。首次确定兼容当前锁文件的 Poetry 版本后，在 CI 中固定同一版本；不照搬未验证版本。
- [x] 把审查探针中的代表场景转换为现有测试套件中的行为回归测试，逐项确认其在修复前暴露预期缺陷。探针当前退出 0 只代表复现成功，不是验收通过。

已知环境差异：此前审查使用 Windows/Python 3.14.3 的已有环境，869 项测试通过，但不是锁文件环境；不能推导 Python 3.10/3.12 或 Linux 结果。

## 实施顺序

| 阶段 | 产出 | 前置关系 |
| --- | --- | --- |
| A | 合法更新与图索引一致性 | 完成基线 |
| B | 执行尝试隔离与持续恢复 | 完成基线；恢复依赖执行尝试约束 |
| C | 审核请求幂等 | 复用 A 的变更边界 |
| D | 锁定安装、类型覆盖和可信 CI | 汇总 A–C 的最终实现 |
| E | 整体验证与交接 | A–D 适用检查通过 |

按用户后续授权采用子 Agent 分工：模块/审核一致性、任务可靠性、质量交付，主 Agent 集成并独立验证。遇到新证据只调整受影响任务。

## A1：更新成功必须对应可重新加载的合法模块

影响文件：`src/knowledge_manager/http_server.py`、`schemas.py`、`storage.py`；`tests/test_http_server.py`、`test_schemas.py`、`test_storage.py`。

- [x] 先新增行为测试：合法模块接受合法的部分更新；过短 title/summary、非法枚举和错误嵌套类型被拒绝；失败前后模块与索引文件内容不变。
- [x] 使用明确的部分更新模型区分未提供字段、显式空字符串和 null；按既有字段合同定义允许清空的字段，不再用 truthiness 决定是否更新。
- [x] 从原对象构造独立候选数据，合并后重新验证完整 Module。避免只对已有实例调用 `model_validate` 而未触发重新校验；不得在验证完成前修改原对象或缓存引用。
- [x] 审核所有实际写入调用者，在公共持久化边界保证不合法对象不能落盘；HTTP 将输入错误转换为 422，CLI/MCP 保持各自既有错误表达。
- [x] 同步受影响消费者，验证成功写入后列表、详情和检索仍能读到该模块。

验证：

```text
poetry run pytest -q tests/test_http_server.py tests/test_schemas.py tests/test_storage.py tests/test_cli.py tests/test_mcp_server.py
```

验收：非法更新返回明确错误，磁盘与可见状态保持原样；合法更新可重新通过 Module 校验；可清空字段支持显式清空。

## A2：内容更新保留入边，增量结果与重建一致

影响文件：`src/knowledge_manager/schemas.py` 的 Index、`storage.py` 的 `_upsert_index_entry`；`tests/test_schemas.py`、`test_storage.py`、`test_tree.py`。

- [x] 增加 source→target 回归：只更新 target.summary，source 的入边引用保持不变；覆盖多来源、双向关系和无关系节点。
- [x] 把索引条目更新与模块删除分开，更新已有条目不调用具有关系清理副作用的删除操作。正确刷新摘要、字数和类别统计。
- [x] 覆盖更新出边、移除出边、删除目标和重复保存。真正删除目标时继续执行约定的关系清理。
- [x] 对同一模块集合比较增量索引和全量重建结果，规范化时间戳与无语义顺序后比较条目、图与统计；检查树及关联消费者。
- [x] 若历史索引已漂移，复用现有 rebuild 命令提供修复指引，不自动改写用户知识库。验证连续两次重建结果等价。

验证：

```text
poetry run pytest -q tests/test_schemas.py tests/test_storage.py tests/test_tree.py tests/test_reliability.py
```

验收：非关系编辑不改变图结构；关系编辑仅改变预期出边；正常删除行为保留；增量索引等价于重建。

## B1：任务状态与结果属于当前执行尝试

影响文件：`src/knowledge_manager/ingestion_jobs.py`、`job_worker.py`、`source_ingestion.py`、`cli.py`、`performance_benchmarks.py` 及调用者；`tests/test_ingestion_jobs.py`、`test_source_ingestion.py`、`test_reliability.py`。

- [x] 先绘制现有调用链：领取、续租、阶段更新、checkpoint、结果模块、完成、失败及人工恢复。检查 CLI 同步入口和性能脚本，不能只修 worker。
- [x] 优先复用现有 attempt_count，定义不可混淆的执行尝试标识；领取在写锁内递增并返回标识。若需要额外标识，先证明现有字段不足，不重复创建编排状态。
- [x] 所有执行态写入在同一锁内核对当前尝试、状态和租约合同。旧尝试不能续租、写 checkpoint、写结果、完成或标记新尝试失败。
- [x] 将尝试标识传到心跳线程与真实执行调用者；失去当前尝试资格后停止提交。冲突异常不能被通用 except 转换为对当前新任务的 failed 写入。
- [x] 检查实际模块/staging 写入、临时输入删除等副作用的位置；在本地提交边界核对尝试归属。租约约束不承诺外部 LLM 调用恰好执行一次，允许外部调用重试，但旧尝试不得提交本地结果。
- [x] 检查 queued→completed 等历史直接调用，区分执行与维护入口；同步修改真实消费者，不能保留一个不校验的默认分支仅供旧测试通过。
- [x] 定义旧任务文件兼容方式：缺失新增字段时仍可读取；旧 running 任务必须经明确恢复流程后重新领取；终态任务不能被迟到结果反向改写。
- [x] 增加 A 领取、A 过期、B 接管、A 恢复的多进程测试，以事件/barrier 控制顺序；验证磁盘终态和 staging 产物属于 B。避免依赖碰运气的 sleep。

验证：

```text
poetry run pytest -q tests/test_ingestion_jobs.py tests/test_source_ingestion.py tests/test_reliability.py tests/test_ingestion_recovery_drill.py tests/test_performance_benchmarks.py
```

验收：旧尝试的所有变更被明确拒绝且不改变 B 的状态或产物；正常续租、失败重试和恢复仍能完成；旧格式任务读取兼容。

并发验证补充：本快照未发现项目验证技能或形式模型。实施 B1/B2 时按用户约定使用 create-verification-skill 建立可复跑的真实任务恢复入口；针对租约接管和恢复竞态使用 create-formal-verification-skill 建立最小 TLA+ 模型，复用新增真实测试，不另写重复驱动。用 statechart 解读 TLC 结果，记录状态空间、假设、命令和退出码。模型需覆盖旧尝试不可提交、终态不倒退和满足明确公平性/重试假设时的恢复；不得以模型通过代替多进程测试。

## B2：运行期间持续恢复过期任务，避免覆盖新心跳

依赖 B1。

影响文件：`src/knowledge_manager/worker_service.py`、`ingestion_jobs.py`；`tests/test_worker_service.py`、`test_ingestion_jobs.py`、`test_ingestion_recovery_drill.py`。

- [x] 将过期回收纳入轮询周期，保留 once 模式的明确语义。使用可控时钟测试，避免等待真实长租约。
- [x] 把重新读取、判断当前状态/尝试/租约及重新排队合为原子条件更新；扫描到的旧快照不能覆盖新心跳、已完成状态或新尝试。
- [x] 验证 worker 启动后才过期的任务会被发现、重新领取并完成；覆盖两个恢复者同时发现、扫描后续租和正常运行未过期三种情况。
- [x] 明确恢复与重试上限的关系：检查既有合同后复用；若没有具体上限约定，记录待确认的业务选择，不能擅自把无限重试写成完成条件。
- [x] 同步 B1 的真实验证技能和形式模型，复跑受影响性质。

验证：

```text
poetry run pytest -q tests/test_worker_service.py tests/test_ingestion_jobs.py tests/test_ingestion_recovery_drill.py tests/test_reliability.py
```

验收：运行中产生的过期任务在约定回收周期内重新处理；新心跳不会被旧扫描结果覆盖；并发恢复不产生多个有效执行尝试。

## C：审核重试幂等，HTTP 与 CLI 使用同一业务合同

影响文件：`src/knowledge_manager/schemas.py`、`storage.py`、`http_server.py`、`cli.py`；`tests/test_http_server.py`、`test_cli.py`、`test_enterprise.py`。

- [x] 将有效批准定义为当前内容版本上不同 reviewer 的最新有效意见。同一 reviewer 重复批准不增加计数；保留历史意见用于解释结果，不直接统计事件条数。
- [x] 同一 reviewer 的后续 changes-requested 应使其旧批准不再有效；当前内容发生变化后旧批准不能自动应用于新版本。使用确定的内容版本/摘要，排除仅因操作时间变化引起的失效。
- [x] 在现有业务层内提供共同审核操作，HTTP 和 CLI 复用；用知识库写锁覆盖读取、记录意见、计数与发布，避免并发重复发布。
- [x] 兼容旧 StagingMeta：可以读取；无法确认意见对应当前内容版本时，明确标记需重新审核，不静默计为有效批准。更新相关文档。
- [x] 覆盖重复批准、两位独立 reviewer、意见撤回、内容修改、并发重试以及发布后重试；发布后重复请求按可读取的持久化结果返回既定结果，若现有数据无法判断，明确返回已处理，不凭空增加批准。

验证：

```text
poetry run pytest -q tests/test_http_server.py tests/test_cli.py tests/test_enterprise.py tests/test_storage.py
```

验收：required_approvals=2 时，同一 reviewer 重复请求始终只有一份有效意见；两份当前版本的独立批准才满足门槛；HTTP/CLI 结果一致，旧文件兼容有说明。

## D1：依赖与 Python 版本验证可复现

影响文件：`.github/workflows/ci.yml`、`reliability-evidence.yml`、其他安装相同项目的工作流、`pyproject.toml`、必要时 `poetry.lock`、`CONTRIBUTING.md`。

- [x] 将主要回归工作流改为使用已验证且固定版本的 Poetry 与锁文件安装，移除后续覆盖项目锁定依赖的安装步骤。记录实际依赖清单和锁文件哈希。
- [x] 至少覆盖声明的最低 Python 3.10 与主要验证版本 3.12；先证明锁文件在两者可安装。若不兼容，查明依赖或实现原因，不能为通过 CI 擅自收窄公开支持范围。
- [x] wheel job 在干净环境验证构建产物；明确它验证分发安装，与锁定环境回归的范围不同，不能由后者替代。
- [x] 除非兼容性验证确有需要，不在本轮顺带更新依赖版本。必要变更同时更新锁文件，记录原因与实际安装结果。

验收：相同锁文件的回归环境可重建；声明最低版本实际通过测试；wheel 安装冒烟通过；未运行的远端 job 明确标注未验证。

## D2：类型约束先覆盖本轮变化，CI 如实报告失败

影响文件：`pyproject.toml`、`.github/workflows/ci.yml`、本轮修改的核心模块与子进程驱动；`scripts/verify_install_smoke.py` 及受影响测试；开发说明。

- [x] 分别检查本轮触及的忽略模块，优先移除 ingestion_jobs、worker_service 等可独立收紧模块的全模块忽略。复杂模块若遗留错误较多，建立显式错误基线或局部已知豁免，使新增错误可见；不把其他模块加入 ignore_errors。
- [x] 新的更新模型、索引操作和尝试状态合同必须进入实际类型检查覆盖。不得仅让新增薄封装通过而忽略业务实现。
- [x] 移除把测试进程段错误改判成功的规则，保留原退出状态。若锁定环境仍出现异常，定位到依赖/解释器并在代表性真实输入输出下验证修复；未解决前保持失败可见。
- [x] 让格式和适用类型门槛成为阻断 job，分开运行或确保能分别取得结果；修改当前说明，历史非阻断计划保留为历史选择。
- [x] 定位审查中三个后台读取线程解码异常的具体子进程调用，显式定义调用双方编码。不要只通过父进程设置 UTF-8 环境变量掩盖未定义的协议。
- [x] 对相关测试将 PytestUnhandledThreadExceptionWarning 提升为失败，验证正常编码和异常输出；不要统一屏蔽所有警告。第三方弃用警告单独记录兼容性债务。

验收：测试非零退出保持失败；格式与类型门槛确实执行并阻断；受修改合同的类型错误能被检出；相关子进程不再产生未处理线程异常。工作流配置通过不等于 GitHub 分支保护已启用。

## E：整体验证、证据与交接

- [x] 在最终产品代码、测试、配置与锁文件固定后执行以下适用命令，记录实际命令、环境、退出码及报告，不填入预计结果：

```text
poetry check --lock
poetry run pytest -q --junitxml=test-results/code-quality-remediation-junit.xml
poetry run black --check src tests scripts
poetry run mypy src
poetry run python scripts/verify_install_smoke.py
git diff --check
```

- [x] 运行新增真实任务恢复验证技能、TLC 检查和当前快照的检索/恢复演练。命令必须从实际技能与脚本参数确认后记录，不虚构尚未创建的入口。
- [x] 复验 HTTP 更新→读取→检索、CLI 审核→发布→MCP 读取，以及任务接管→staging→结果状态的完整场景；后两者继续复用现有协议测试和真实驱动。
- [x] 在 Windows 仅报告 audit-only-windows；远端 Ubuntu 与 Python 版本矩阵只有实际执行后才能标为通过。本阶段不以历史 869 passed 代替最终回归。
- [x] 若最终实现改变性能关键路径，使用既有基准检查受影响规模；没有运行完整规模矩阵时不作整体性能或生产就绪声明。
- [x] 更新本计划各项状态、审查发现对应的处理说明、实际验证结果和未决项；架构拆分仅限本轮行为所需的共同服务，避免无关重构。
- [x] 交接分别列出已修改、已验证、已提交、已部署。当前提交与部署均未授权；后续如获提交授权，先检查 .gitignore 和暂存清单，排除临时审查日志、环境及缓存。

## 退出与回退边界

实施不能通过删除失败测试、扩大类型忽略、改变退出码或降低功能要求制造通过。发生新失败时定位受影响合同，再修改相关计划项。

运行态持久化字段变更必须保留旧格式读取与明确恢复路径；在恢复 B1 的旧实现前，先停止并排空相关 worker，防止新旧执行合同混用。用户数据修改不自动回退；必要恢复使用既有备份/恢复流程，并另行取得相应操作授权。

本轮无发布任务；不宣称生产验收或上线条件已满足。

## 当前记录

- 已实施并验证：A1/A2、B1/B2、C、D及交互审核快照竞态；Python3.10.20/3.12.13相同锁文件环境完整908项退出0。
- 静态与行为证据：Black、mypy、锁文件、diff及公开目录检查退出0；真实CLI/恢复演练退出0；TLC四规则通过，三个模型负控按预期失败，真实源码归属检查突变被回归检出。
- 保留问题：旧Python3.12.8最终GC原生崩溃仍未定位组件，绝不把原失败改判通过；25个模块既有类型忽略、第三方弃用提示、完整规模矩阵与远端UbuntuCI未验证。
- 没有提交、推送、PR或部署；Windows仅audit-only-windows。完整结果、复跑命令、证据与限制见最终修复记录。
