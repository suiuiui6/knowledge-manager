# GitHub CI 与公开提交接续记录（2026-11-06）

## 分支判断

当前最成熟的分支是 `feat/knowledge-manager-phase2`：

- `1280749`（2026-10-25）是该仓库最新提交，包含 108 个提交。
- 该分支包含 Ubuntu CI、M-scale 证据工作流、可靠性证据工作流和后续性能修复。
- 发布前 `origin/main` 停留在 `f655946`（2026-09-09，27 个提交）；发布后 `main` 已同步到 `e0aed95`。
- `origin/main` 有 3 个提交不在 phase2 中：公开面检查、示例凭据移除、pytest 导入隔离。本次已合并进 phase2，保留 phase2 的 README 和后续实现。

## 本次修改

- 合并 `origin/main`，引入 `LICENSE`、`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`、Issue/PR 模板、`tools/check_public_surface.py` 和公开面工作流。
- 保留 phase2 的完整 README，补充 CI/公开面徽章、实际 clone 地址、Contributing 段落和公开面检查命令。
- 允许 `.env.production.example` 等脱敏 `.env.*.example` 模板通过公开面检查；真实 `.env`、私钥和日志仍被拒绝。
- 公开面工作流覆盖 `feat/**` 和 `codex/**`，与当前开发分支策略一致。
- 引入 pytest 仓库源码导入隔离，避免测试误用已安装包。
- 停止跟踪本地 dogfood 知识库 `kb/`，保留工作区文件；公开示例知识库继续使用 `examples/sample_knowledge_base/`。
- 停止跟踪根目录手工 smoke/debug 脚本，保留本地文件，并加入 `.gitignore`；公开测试入口继续使用 `tests/` 和 `scripts/`。
- 将历史计划与验证文档中的本机绝对路径替换为 `<workspace>` / `<user-home>`；测试中的假路径改为相对路径。
- 忽略 `.pytest-tmp-*` 本地测试临时目录。

## 已验证

- `python -B tools/check_public_surface.py`：PASS，退出码 0。
- 全部 GitHub Actions YAML 解析：通过，退出码 0。
- `git diff --check`：退出码 0。
- `python -m poetry check --lock`：退出码 0（仅有 Poetry 2.4.1 的弃用警告）。
- 跟踪范围内无 `developer-kit`、`test-results`、`tmp`、`.pytest`、`.mypy` 或嵌套 `.git` 路径；凭据模式扫描无命中。
- `python -m poetry run pytest -q tests/test_import_isolation.py`：1 passed，退出码 0。
- `python -m poetry run pytest -q tests/test_cli.py::test_cli_uses_runtime_env_kb_path_when_flag_is_omitted`：1 passed，退出码 0。
- Windows 全量 pytest：共 866 项，229 passed，2 failed，635 errors。637 个非通过项全部为 `PermissionError` / `WinError 5` 临时目录权限问题，未发现非环境原因的业务失败。本次结果按 `audit-only-windows` 记录，不能视为全量通过。
- Mypy：`poetry run mypy src` 退出码 1，31 个文件共 113 个历史类型错误；按设计仍为非阻断质量报告。
- Black：新文件已由 Black 格式化；`black --check` 在当前 Windows 沙箱中输出结果后进程未正常退出，因此不记录为通过。

## 发布结果

- 通过 GitHub Git Data API 发布：tree-identical commit `9e52162`，merge commit `e0aed95a94ab7e48c6130e78aade4411b97d4ea1`。
- `main` 和 `feat/knowledge-manager-phase2` 均指向 `e0aed95`；默认分支为 `feat/knowledge-manager-phase2`。
- 本地 `main` 和 phase2 已同步到 `e0aed95`；旧本地提交保存在 `backup/local-release-20261106` 和 `backup/local-main-20261106`。
- GitHub Actions（提交 `e0aed95`）：
  - Public surface：success（runs `42210245091`、`42210245103`）
  - CI：success（runs `42210245068`、`42210245056`）
  - Reliability evidence：success（runs `42210245054`、`42210245088`）
  - M-scale：failure（run `42210663318`，50k 模块基准发生 segmentation fault，exit 139）
- 未创建 PR；本次直接更新分支。
- 未执行部署、生产性能矩阵或备份恢复演练。

## 环境限制

- Git smart HTTP push 在当前机器上失败：默认 schannel 报 `SEC_E_NO_CREDENTIALS`；Steam++ 拦截 TLS（issuer=`SteamTools Certificate`）；Git 凭证 helper 依赖的 `sh.exe` 在沙箱中无法创建 signal pipe。
- 关闭 Steam++ 后直连 GitHub 被拒绝；当前环境依赖该加速器出网。
- 最终通过 GitHub API 上传 Git objects 完成发布，不依赖 Git smart HTTP push。
- 当前 shell 默认注入 `127.0.0.1:9` 代理变量；后续常规 Git push 仍需可用网络和认证。
- M-scale 已改为手动、非阻断证据工作流；50k 模块运行仍有已知 segfault，不能作为生产规模通过的证据。

## 下一步

1. 排查 M-scale 50k 模块 segfault；在修复前保持手动、非阻断。
2. 在 GitHub 页面确认默认分支展示 `0.5.2` README、CI 徽章和 runbook。
3. 后续用可用网络验证常规 `git push` 路径，避免依赖 Git Data API。
4. 继续把 Black/Mypy 历史债务作为独立质量工作处理，不提前提升为阻断门禁。
