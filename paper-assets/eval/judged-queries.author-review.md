# Knowledge Manager judged queries 作者审阅包

本文件用于逐条确认 candidate judged queries。它不是实验结果，也不能替代正式 baseline 结果表。

作者审阅时建议填写 `author_decision`：`accept`、`revise`、`exclude` 或 `needs_discussion`。

## 汇总

| 项目 | 数量 |
|---|---:|
| 待审阅 query | 30 |

## 审阅清单

### 1. KM-ARCH-001

- corpus_id: `km_methodology`
- query: KM 为什么明确不引入向量数据库、SQL、Web server 和消息队列？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `architecture/design-boundaries`
- required_module_titles: architecture/design-boundaries :: Design Boundaries: What KM Will Never Introduce
- nice_to_have_modules: `architecture/git-native-storage`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: anti-goals: no vector databases, no SQL, no web servers, no message queues
- judge_notes: Candidate derived from the design-boundaries module; author must verify wording and required modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 2. KM-ARCH-002

- corpus_id: `km_methodology`
- query: Knowledge Manager 为什么选择 Git 原生 JSON 文件，而不是数据库存储知识模块？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `architecture/git-native-storage`
- required_module_titles: architecture/git-native-storage :: Git-Native Storage: Why JSON Files Over Databases
- nice_to_have_modules: `architecture/design-boundaries`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: JSON files in Git repository; Git for versioning, sync, audit
- judge_notes: Candidate derived from git-native-storage module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 3. KM-ARCH-003

- corpus_id: `km_methodology`
- query: KM 通过 MCP stdio 接入代理，而不是启动 HTTP server，这个设计边界是什么？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `architecture/mcp-protocol`
- required_module_titles: architecture/mcp-protocol :: MCP Protocol: Why Stdio Over HTTP Server
- nice_to_have_modules: `architecture/design-boundaries`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: MCP over stdio; no REST API, GraphQL, gRPC
- judge_notes: Candidate derived from mcp-protocol module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 4. KM-ARCH-004

- corpus_id: `km_methodology`
- query: 多个知识库 federation 时如何用 namespace 隔离团队知识？
- task_type / scope_type / difficulty: `factual` / `in_scope` / `medium`
- required_modules: `architecture/federation`
- required_module_titles: architecture/federation :: Multi-KB Federation: Namespace Isolation for Team Knowledge
- nice_to_have_modules: `architecture/mcp-protocol`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: namespace prefixes; independent search, index, health resources
- judge_notes: Candidate derived from federation module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 5. KM-OPS-001

- corpus_id: `km_methodology`
- query: 知识模块从 draft 到 archived 的生命周期有哪些状态和转换？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `easy`
- required_modules: `operations/module-lifecycle`
- required_module_titles: operations/module-lifecycle :: Module Lifecycle: Draft → Published → Deprecated → Archived
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: draft -> reviewed -> published -> deprecated -> archived
- judge_notes: Candidate derived from module-lifecycle module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 6. KM-SEARCH-001

- corpus_id: `km_methodology`
- query: KM 的搜索排序如何结合字段权重、confidence、Bayesian prior 和 BM25？
- task_type / scope_type / difficulty: `factual` / `in_scope` / `medium`
- required_modules: `search/ranking-pipeline`
- required_module_titles: search/ranking-pipeline :: Search Ranking Pipeline: BM25 + Heuristic + Confidence + Bayesian
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: four-layer cascade: heuristic, confidence, Bayesian, BM25
- judge_notes: Candidate derived from ranking-pipeline module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 7. KM-SEARCH-002

- corpus_id: `km_methodology`
- query: 中文查询为什么需要 jieba 分词，KM 是在哪些函数里处理 CJK token 的？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `hard`
- required_modules: `search/chinese-segmentation`
- required_module_titles: search/chinese-segmentation :: Chinese Word Segmentation: Jieba Integration for CJK Search
- nice_to_have_modules: `search/ranking-pipeline`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: _stem(), _field_stems(), record_search_event()
- judge_notes: Candidate derived from chinese-segmentation module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 8. SE-API-001

- corpus_id: `software_engineering`
- query: REST API 文档至少应该包含哪些认证、参数、响应和错误信息？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `easy`
- required_modules: `api/api-documentation-essentials`
- required_module_titles: api/api-documentation-essentials :: API Documentation Standards
- nice_to_have_modules: `api/restful-api-principles`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: documentation standards for authentication, parameters, responses, errors
- judge_notes: Candidate derived from api-documentation-essentials module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 9. SE-API-002

- corpus_id: `software_engineering`
- query: API 限流应该使用什么算法，并如何返回 X-RateLimit 相关 header？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `api/api-rate-limiting`
- required_module_titles: api/api-rate-limiting :: Rate Limiting Implementation
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: rate limiting implementation and X-RateLimit headers
- judge_notes: Candidate derived from api-rate-limiting module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 10. SE-API-003

- corpus_id: `software_engineering`
- query: HTTP status code 在 API 中如何区分客户端错误和服务端错误？
- task_type / scope_type / difficulty: `factual` / `in_scope` / `easy`
- required_modules: `api/http-status-codes`
- required_module_titles: api/http-status-codes :: HTTP Status Code Usage
- nice_to_have_modules: `api/restful-api-principles`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: HTTP status code usage
- judge_notes: Candidate derived from http-status-codes module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 11. SE-AUTH-001

- corpus_id: `software_engineering`
- query: OAuth 授权码流程中用户同意、授权码返回和 token exchange 分别由哪些模块说明？
- task_type / scope_type / difficulty: `synthesis` / `in_scope` / `hard`
- required_modules: `auth/user-authorization-consent; auth/authorization-code-receipt; auth/token-exchange-endpoint`
- required_module_titles: auth/user-authorization-consent :: User Authorization Consent Flow; auth/authorization-code-receipt :: Authorization Code Return Handling; auth/token-exchange-endpoint :: Token Exchange for Access Token
- nice_to_have_modules: `auth/authorization-code-flow`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: consent flow; authorization code receipt; token exchange endpoint
- judge_notes: Candidate requires multiple auth modules; author must verify all required modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 12. SE-AUTH-002

- corpus_id: `software_engineering`
- query: access token 应该如何放入 API 请求，哪些做法需要避免？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `auth/access-token-presentation`
- required_module_titles: auth/access-token-presentation :: API Access Token Usage
- nice_to_have_modules: `auth/token-exchange-endpoint`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: API access token usage
- judge_notes: Candidate derived from access-token-presentation module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 13. SE-DB-001

- corpus_id: `software_engineering`
- query: 数据库连接池应该如何设置大小、生命周期和常见陷阱？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `database/connection-pooling`
- required_module_titles: database/connection-pooling :: Database Connection Pooling
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: connection pooling sizing, lifecycle, pitfalls
- judge_notes: Candidate derived from connection-pooling module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 14. SE-DB-002

- corpus_id: `software_engineering`
- query: 数据库迁移和事务管理分别应该查哪些模块？
- task_type / scope_type / difficulty: `synthesis` / `in_scope` / `medium`
- required_modules: `database/database-migrations; database/transaction-management`
- required_module_titles: database/database-migrations :: Database Migrations; database/transaction-management :: Transaction Management
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: database migrations; transaction management
- judge_notes: Candidate requires two database modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 15. SE-DEP-001

- corpus_id: `software_engineering`
- query: 蓝绿部署和 CI/CD pipeline 在发布流程中分别解决什么问题？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `deployment/blue-green-deployment; deployment/ci-cd-pipeline`
- required_module_titles: deployment/blue-green-deployment :: Blue-Green Deployment; deployment/ci-cd-pipeline :: CI/CD Pipeline
- nice_to_have_modules: `deployment/monitoring-and-logging`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: blue-green deployment; CI/CD pipeline
- judge_notes: Candidate requires deployment modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 16. SE-BOUND-001

- corpus_id: `software_engineering`
- query: GraphQL API schema federation 的最佳实践是什么？
- task_type / scope_type / difficulty: `boundary` / `out_of_scope` / `medium`
- required_modules: ``
- required_module_titles: 
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `True`
- expected_boundary: The software_engineering corpus does not include GraphQL federation modules; the system should not answer as if reviewed knowledge exists.
- gold_evidence_spans: 
- judge_notes: Candidate out-of-scope query; author should confirm corpus coverage.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 17. HSE-001

- corpus_id: `safety_hse`
- query: 受限空间作业前的气体检测阈值和复测频率是什么？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `safety/confined-space-gas-control; safety/confined-space-gas-monitoring`
- required_module_titles: safety/confined-space-gas-control :: 受限空间作业气体控制标准; safety/confined-space-gas-monitoring :: 受限空间作业气体检测与监护要求
- nice_to_have_modules: `safety/confined-space-management-audit`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 先通风、再检测、后作业; 2小时复测; oxygen/flammable/H2S/CO thresholds
- judge_notes: Candidate derived from confined-space gas modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 18. HSE-002

- corpus_id: `safety_hse`
- query: 受限空间专项治理为什么要重新辨识并复核审批流程？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `safety/confined-space-governance; safety/confined-space-management-audit`
- required_module_titles: safety/confined-space-governance :: 受限空间专项治理; safety/confined-space-management-audit :: 受限空间重新辨识与审批流程复核
- nice_to_have_modules: `safety/confined-space-gas-control`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 二次辨识; 审批流程复核; 防止中毒窒息事故
- judge_notes: Candidate derived from confined-space governance modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 19. HSE-003

- corpus_id: `safety_hse`
- query: 事故调查中的“四不放过”和 5-Why 根因分析应如何执行？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `easy`
- required_modules: `safety/accident-investigation-4-no-pass`
- required_module_titles: safety/accident-investigation-4-no-pass :: 事故管理“四不放过”及根本原因分析
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 四不放过; 5-Why; 7个工作日内完成调查报告
- judge_notes: Candidate derived from accident-investigation module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 20. HSE-004

- corpus_id: `safety_hse`
- query: 动火作业如何分级审批，现场应配置哪些消防措施？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `safety/hot-work-grading-approval`
- required_module_titles: safety/hot-work-grading-approval :: 动火作业分级审批与防护
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 动火作业分级审批; 消防措施
- judge_notes: Candidate derived from hot-work module; author should verify exact module id and coverage.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 21. HSE-005

- corpus_id: `safety_hse`
- query: 高处作业防坠落控制应重点检查哪些安全措施？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `safety/height-work-safety-control`
- required_module_titles: safety/height-work-safety-control :: 高处作业安全防护与脚手架验收
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 高处作业; 防坠落; 安全控制
- judge_notes: Candidate derived from height-work-safety-control module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 22. HSE-006

- corpus_id: `safety_hse`
- query: 承包商安全绩效如何排名，末位约谈适用于什么情况？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `safety/contractor-safety-performance-ranking; safety/contractor-safety-ranking`
- required_module_titles: safety/contractor-safety-performance-ranking :: 承包商安全绩效排名与末位约谈; safety/contractor-safety-ranking :: 承包商安全绩效评价
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 承包商安全绩效排名; 末位约谈
- judge_notes: Candidate derived from contractor safety ranking modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 23. HSE-007

- corpus_id: `safety_hse`
- query: 施工区域应急物资如何配置，并如何做定期检查？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `safety/emergency-supplies-configuration; safety/emergency-supply-configuration`
- required_module_titles: safety/emergency-supplies-configuration :: 施工区域应急物资标准配置; safety/emergency-supply-configuration :: 应急物资配置与定期检查
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 应急物资标准配置; 定期检查
- judge_notes: Candidate derived from emergency supplies modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 24. HSE-008

- corpus_id: `safety_hse`
- query: 应急响应如何分级，上报时效有什么要求？
- task_type / scope_type / difficulty: `factual` / `in_scope` / `medium`
- required_modules: `safety/emergency-response-grading`
- required_module_titles: safety/emergency-response-grading :: 应急响应分级与上报时效
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 应急响应分级; 上报时效
- judge_notes: Candidate derived from emergency-response-grading module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 25. HSE-009

- corpus_id: `safety_hse`
- query: 防暑降温方案在高温天气下应包含哪些控制措施？
- task_type / scope_type / difficulty: `procedure` / `in_scope` / `medium`
- required_modules: `safety/heat-stress-prevention-protocol`
- required_module_titles: safety/heat-stress-prevention-protocol :: 暑期高温作业防暑降温应对机制
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: heat stress prevention protocol; 高温控制措施
- judge_notes: Candidate derived from heat-stress-prevention-protocol module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 26. HSE-010

- corpus_id: `safety_hse`
- query: 交工技术文件中为什么必须归档压力试验、NDT 和热处理等安全记录？
- task_type / scope_type / difficulty: `decision` / `in_scope` / `medium`
- required_modules: `safety/completion-safety-documents`
- required_module_titles: safety/completion-safety-documents :: 交工技术文件与安全记录归档
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: 交工文件清单; 安全相关记录; 可追溯
- judge_notes: Candidate derived from completion-safety-documents module.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 27. HSE-011

- corpus_id: `safety_hse`
- query: 受限空间里的 IoT 实时监测系统是否在当前知识库中有审核模块？
- task_type / scope_type / difficulty: `boundary` / `partial_scope` / `hard`
- required_modules: `safety/confined-space-gas-control`
- required_module_titles: safety/confined-space-gas-control :: 受限空间作业气体控制标准
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `True`
- expected_boundary: The corpus covers confined-space gas control, but IoT real-time monitoring should only be answered if a reviewed module exists.
- gold_evidence_spans: 受限空间气体控制 covered; IoT monitoring may be outside reviewed modules
- judge_notes: Candidate partial-scope boundary query; author must verify whether IoT-specific module exists.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 28. HSE-012

- corpus_id: `safety_hse`
- query: HAZOP 分析与 JSA 作业安全分析的区别是什么？
- task_type / scope_type / difficulty: `boundary` / `near_scope` / `hard`
- required_modules: ``
- required_module_titles: 
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `True`
- expected_boundary: Only answer from reviewed modules if explicit HAZOP/JSA modules exist; otherwise state coverage is insufficient.
- gold_evidence_spans: 
- judge_notes: Candidate near-scope query. Requires author coverage check before use.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 29. MIX-001

- corpus_id: `software_engineering`
- query: OAuth 登录失败和 redirect_uri 配置错误应该查哪个模块？
- task_type / scope_type / difficulty: `troubleshooting` / `in_scope` / `medium`
- required_modules: `auth/authorization-code-flow; auth/authorization-code-receipt`
- required_module_titles: auth/authorization-code-flow :: Authorization Code Flow Implementation; auth/authorization-code-receipt :: Authorization Code Return Handling
- nice_to_have_modules: `auth/token-exchange-endpoint`
- should_refuse_or_boundary_note: `False`
- expected_boundary: 
- gold_evidence_spans: authorization code flow; redirect/receipt handling
- judge_notes: Candidate troubleshooting query derived from OAuth modules.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 

### 30. MIX-002

- corpus_id: `km_methodology`
- query: 如果用户问 KM 的向量检索能力，应该加载哪个模块并如何说明边界？
- task_type / scope_type / difficulty: `boundary` / `partial_scope` / `hard`
- required_modules: `architecture/design-boundaries; search/ranking-pipeline`
- required_module_titles: architecture/design-boundaries :: Design Boundaries: What KM Will Never Introduce; search/ranking-pipeline :: Search Ranking Pipeline: BM25 + Heuristic + Confidence + Bayesian
- nice_to_have_modules: ``
- should_refuse_or_boundary_note: `True`
- expected_boundary: KM search uses heuristic/BM25-style ranking and has explicit anti-goals around vector databases; avoid claiming vector retrieval capability if not present.
- gold_evidence_spans: no vector databases; ranking pipeline uses heuristic/confidence/Bayesian/BM25
- judge_notes: Candidate boundary query combining design-boundaries and ranking-pipeline.
- author_decision: 
- author_corrected_required_modules: 
- author_boundary_revision: 
- author_notes: 
