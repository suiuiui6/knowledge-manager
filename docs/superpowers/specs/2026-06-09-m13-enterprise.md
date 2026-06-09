# M13 Spec — 企业功能

> Phase 7 M13 | 2026-06-09 | 硬依赖: M11 (通过插件实现)

## 概述

企业级功能：SSO 单点登录、审计日志、RBAC 权限控制、合规报告。全部通过 M11 插件系统实现，核心不引入企业依赖。

## 功能列表

### SSO (OIDC/SAML)
- 通过插件钩子注入认证中间件
- 支持 OIDC (Google Workspace, Okta) 和 SAML (Azure AD)
- `km serve --ui --auth oidc --oidc-config config.json`

### 审计日志
- 记录: 谁、何时、做了什么操作 (create/edit/delete/approve/reject)
- 不可篡改: append-only JSONL + git commit
- `km audit log --since 2026-01-01 --user alice`

### RBAC
- 角色: admin (全部权限), editor (创建/编辑), reviewer (审核), viewer (只读)
- 权限: 读模块、写模块、审核、管理配置、管理用户
- 配置: `config.json` 中的 `rbac` 字段

### 合规报告
- 导出: 所有审核记录 + 模块状态 + 用户活动
- 格式: PDF (通过 pandoc/weasyprint) 或 JSON
- `km compliance report --period 2026Q1 --format pdf`

## 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/knowledge_manager/auth.py` | **新建** (SSO 中间件) |
| `src/knowledge_manager/audit.py` | **新建** (审计日志) |
| `src/knowledge_manager/rbac.py` | **新建** (RBAC) |
| `src/knowledge_manager/http_server.py` | 修改 (注入认证) |
| 插件包 | km-plugin-sso, km-plugin-audit, km-plugin-rbac |

## 设计原则

- 核心不引入企业依赖（不增加 SAML/OIDC 库到 pyproject.toml）
- 企业功能通过可选插件实现
- 文件系统 + Git 保持可审计性根基
- 不引入数据库作为依赖
