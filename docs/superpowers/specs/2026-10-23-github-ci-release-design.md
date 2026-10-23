# GitHub CI 与公开提交设计

## 目标

将 `knowledge-manager` 整理为可公开提交到 GitHub 的项目：安装依赖可复现，核心功能回归由 GitHub Actions 自动验证，测试失败能够阻止合并，项目边界和已知限制对外清晰可见。

## 已确认的门禁策略

- GitHub Actions 使用 Ubuntu runner。
- 使用项目 `poetry.lock` 安装完整依赖，不根据系统环境漂移版本。
- 全量 pytest 是阻断门禁；pytest 失败时工作流失败。
- Black 和 Mypy 暂作为独立质量报告，不阻断合并。当前仓库仍有历史格式和类型债务，清理完成后再提升为阻断门禁。
- Windows 验证保留为 `audit-only-windows`，不作为 GitHub 机械阻断条件。

## 工作流结构

工作流放在 `.github/workflows/`，至少包含一个 Ubuntu 测试 job：

1. checkout 当前提交；
2. 配置项目支持的 Python 版本；
3. 安装固定版本的 Poetry；
4. 使用 `poetry.lock` 完整安装项目和开发依赖；
5. 执行全量 `poetry run pytest -q`；
6. 上传失败时可定位的 pytest/JUnit 结果；
7. 只有测试 job 通过时，工作流才成功。

质量检查可以放在同一工作流的独立 job 中，但必须明确标注为报告性质，不能让历史 Black/Mypy 债务伪装成阻断结果。

## 发布范围

公开仓库应包含：

- `src/knowledge_manager/`、`tests/`、`scripts/`；
- `pyproject.toml`、`poetry.lock`、README、部署示例和 runbook；
- 脱敏后的示例知识库和配置模板；
- 当前评估报告中对架构边界、测试状态和 Windows 限制的说明。

本地知识库、缓存、临时目录、性能历史产物、嵌套独立仓库和包含运行痕迹的验证目录不进入发布提交。忽略规则只阻止后续误提交，不删除开发者本地文件。

## 项目边界

本次公开提交不引入 GraphRAG、Neo4j、向量数据库、Celery、LangGraph 或微服务。项目继续以 Git 原生 JSON 知识模块、`extract -> staging -> review -> publish -> serve` 流程以及 CLI、MCP、HTTP 三个运行面为核心。

## 验收标准

- 干净 Ubuntu runner 能依据 `poetry.lock` 完成安装；
- 全量 pytest 在 GitHub Actions 中有明确退出码和报告；
- pytest 失败会使工作流失败；
- Black/Mypy 结果单独可见，当前不阻断；
- README 能说明安装、配置、运行面、审核流程和已知限制；
- 发布提交不包含本地密钥、缓存、临时验证产物或嵌套仓库；
- Windows 限制和未完成的生产门槛不会被写成已通过。

## 非目标

- 不在本阶段清理全部 Mypy 和 Black 历史债务；
- 不在本阶段部署生产服务或创建发布版本；
- 不把 Windows 沙箱测试结果改写为 GitHub CI 通过；
- 不因公开提交目标扩大项目架构或引入新的核心依赖。
