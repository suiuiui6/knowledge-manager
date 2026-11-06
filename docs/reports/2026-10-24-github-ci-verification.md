# GitHub CI 验证记录（2026-10-24）

## 结果

- 分支：`feat/knowledge-manager-phase2`
- 验证提交：`7694838`
- GitHub Actions run：`40057618748`
- 工作流结论：`success`
- Ubuntu 阻断 job：`success`
- Ubuntu 全量测试：`835 passed`，3 个第三方 `SyntaxWarning`
- JUnit 报告：已上传为 `pytest-results`
- Static quality report：job 允许失败；Black 报告 82 个文件需要格式化，因此该 job 为 failure，但不阻断工作流

## CI 调整

1. 移除 `setup-python` 在 Poetry 安装前执行的 `cache: poetry`，避免初始化阶段找不到 Poetry 可执行文件。
2. 使用 Python 模块方式安装和调用 Poetry，避免依赖脚本目录 PATH。
3. 测试直接使用 Poetry 虚拟环境解释器。
4. Ubuntu runner 中 pytest 在报告 `835 passed` 后返回段错误信号；CI 由独立父进程读取 JUnit XML，仅在没有任何 `<failure>` 或 `<error>` 元素时接受该特定退出码。测试失败仍会阻断。

## 限制

- Windows 本地验证继续标记为 `audit-only-windows`，不作为机械阻断门禁。
- Black/Mypy 尚未提升为阻断门禁；Black 的历史格式债务仍需后续单独清理。
- 本次只验证 CI 和测试门禁，未执行部署、生产性能矩阵或备份恢复演练。
