# Lightweight Knowledge Manager Implementation Audit

本文件不再作为“待实现计划”使用。当前仓库里 `knowledge-manager/` 已有可运行实现；这里记录的是已实现状态审计和后续待办，避免继续按旧计划补不存在的缺口。

## 当前实现状态

### 已实现能力

- CLI 已提供 `init`、`list`、`stats`、`search`、`rebuild`、`delete`、`show`、`config {set,get,list}`、`add`、`review`、`serve`
- MCP 服务已暴露 `knowledge://index` 资源，以及 `load_module`、`search_modules`、`list_categories` 三个工具
- 知识库存储采用分类目录 + `index.json` + `.staging/`，模块为独立 JSON 文件
- 提取链路支持多 LLM provider 配置（DeepSeek、Claude、OpenAI）
- `add` 已支持大文档分块提取，提取结果先进入 `.staging/`
- `review` 已支持人工 approve / reject / skip，并在审核后重建索引
- 搜索已实现精确词匹配、词干匹配和短查询部分匹配
- 代码库包含缓存、schema 验证、CLI、MCP、存储、LLM client、集成测试

### 已验证事实

- `pytest` 当前共有 75 个测试用例
- 真实知识库验证文档见 `knowledge-manager/docs/validation-report-2026-05-29.md`
- MCP 协议兼容性摘要见 `knowledge-manager/test-results/test-summary.md`
- 性能摘要显示当前线性扫描搜索在 50-200 模块规模内仍满足目标

## 与旧计划相比需要修正的点

- 旧文档把系统描述为“待构建”，但核心 CLI、MCP、存储和提取流程都已落地
- 旧文档列出了 `km edit`，当前实现里并不存在该命令，不应继续按“缺失功能”理解
- 旧文档默认提取是单次处理，但当前实现已经加入长文档分块参数与相关验证
- 旧文档把很多验收标准写成目标值；现在应优先以仓库内测试和验证报告为准

## 剩余待办

- 持续清理运行验证暴露的技术债，例如 Python 新版本弃用告警与时间处理一致性问题
- 补充文档，使 README、验证报告和计划审计三者保持一致，避免后续误判项目状态
- 若后续需要新增能力，应基于当前实现重新开专项计划，而不是回到这份旧的“初始实现计划”

## 使用方式

- 把这份文档当作状态审计和 TODO 入口
- 新的功能开发请单独建新计划文档
- 发现本文与实际代码不一致时，以仓库现状和测试结果为准，并同步更新本文
