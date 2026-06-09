# M12 Spec — 多模态知识

> Phase 7 M12 | 2026-06-09 | 硬依赖: M11 (通过插件钩子扩展)

## 概述

扩展 `km add` 支持图片、代码仓库、会议记录等非纯文本知识源。LLM Vision + 代码分析 + 会议理解。

## 三种输入模式

### 图片理解
```bash
km add architecture.png -c architecture
  → LLM Vision 分析图片
  → 提取: 组件识别、数据流向、技术栈标注
  → 生成模块: "微服务架构图 (2026 Q1)"
```

### 代码仓库理解
```bash
km add --repo ../backend -c backend
  → 扫描目录结构
  → 读取 README/ARCHITECTURE/config/入口文件
  → LLM 分析代码结构和依赖
  → 生成多模块: overview, api-structure, database-schema, auth-mechanism
  → related_modules 自动反映代码依赖
```

### 会议记录理解
```bash
km add meeting-2026-06-09.txt -c decisions
  → 识别架构决策 → decision-record 类型
  → 识别行动项 → draft 模块
  → 识别风险 → 更新相关模块 caveats
```

## 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/knowledge_manager/extractor.py` | 修改 (支持 vision/code/meeting 模式) |
| `src/knowledge_manager/cli.py` | 修改 (add 命令增强) |
