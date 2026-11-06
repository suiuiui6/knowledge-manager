# GitHub CI 与公开提交接续记录（2026-11-06）

## 分支判断

当前最成熟的分支是 `feat/knowledge-manager-phase2`：

- `1280749`（2026-10-25）是该仓库最新提交，包含 108 个提交。
- 该分支包含 Ubuntu CI、M-scale 证据工作流、可靠性证据工作流和后续性能修复。
- `origin/main` 停留在 `f655946`（2026-09-09，27 个提交），本地 `main` 更旧。
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

## 未执行

- 本地 `main` 已快进到 `a778f5f`，与 `feat/knowledge-manager-phase2` 指向同一提交；旧本地 `main`（`198f900`）已保存到 `backup/local-main-20261106`。
- 本机到 GitHub 的 TLS 连接被第三方加速器证书拦截（issuer=`SteamTools Certificate`）。Git 的 OpenSSL CA bundle 不信任该证书，schannel 返回 `SEC_E_NO_CREDENTIALS`。只读 `ls-remote` 在显式信任该 CA 后可通，但不应将 GitHub 凭据通过该 MITM 发送。
- 关闭 Steam++ 后，本机直连 GitHub 被拒绝（`ConnectionRefusedError` / `Failed to connect`）；当前环境实际依赖该加速器出网。
- 当前 shell 仍默认注入 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 和 Git 代理变量，值为 `http://127.0.0.1:9`；清空变量后直连仍不可用。
- 推送未成功：凭证管理器没有返回可用凭据；`gh auth status` 显示 keyring token 无效，`git credential fill` 退出码 128。远端 `main` / `feat/knowledge-manager-phase2` 仍为 `f655946` / `1280749`，未发生变更。
- 未创建 PR。
- 未重新触发 Ubuntu GitHub Actions；历史成功记录为 run `40057618748`（提交 `7694838`，835 passed）。
- 未执行部署、生产性能矩阵、备份恢复演练或 M-scale 重新运行。

## 下一步

1. 优先切换到不拦截 TLS 的网络路径，并确认 `git ls-remote origin main` 能直接通过。
2. 如果当前环境只能通过 Steam++ 出网，恢复加速器后显式信任其 CA；该路径会让 GitHub 凭据经过该 MITM，需明确接受风险。
3. 运行 `gh auth login` 或 `gh auth refresh -h github.com`，再执行 `gh auth setup-git`。
4. 使用以下命令推送（Steam++ 路径需要 combined CA）：

   ```powershell
   $env:HTTP_PROXY=''; $env:HTTPS_PROXY=''; $env:ALL_PROXY=''
   $env:GIT_HTTP_PROXY=''; $env:GIT_HTTPS_PROXY=''
   git -c http.proxy= -c https.proxy= -c http.sslBackend=openssl `
     -c http.sslCAInfo="$env:TEMP\km-ca\combined-ca.pem" `
     push origin main feat/knowledge-manager-phase2
   ```

5. 推送成功后确认 GitHub 默认分支 `main` 展示 `0.5.2` README 和 CI 徽章。
6. 在 Ubuntu CI 上重新运行全量 pytest，确认当前 HEAD 的阻断门禁结果。
7. 继续把 Black/Mypy 历史债务作为独立质量工作处理，不提前提升为阻断门禁。
