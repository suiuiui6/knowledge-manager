# Knowledge Manager 项目来源语料 v1

本包是从当前项目现有文件自动提取的单项目案例语料。用途是为知识组织、检索与上下文加载的后续实验提供可追溯输入。它不是独立真实团队研究，不证明部署效果或检索优势。

## 文件结构

- sources/：10份原文件的字节级快照，包含6份Markdown文档和4份Python源码。
- modules/：183个知识模块；文档按代码围栏之外的真实标题分段，Python按顶层函数和类分段。
- manifest.json：原始项目路径、快照路径、SHA-256、模块与证据单元映射及边界。
- evidence-units.json：每个模块的字符区间、行号和源标题。
- build-verification.json：183个来源区间、快照哈希、关联可解析性和原文件未变校验。
- schema-verification.json：实际项目Module模型对183个模块的结构校验。

## 生成方法与作者角色

构建脚本由AI辅助编写，实际构建是Python标准库执行的确定性抽取，不调用生成模型、第三方API或外部服务。details字段逐字保留源区间；overview、summary和caveats是明确的组织/来源说明，不新增事实摘要。
模块均标为draft，没有声称人类审核完成。related_modules仅表示同源相邻分段，不表示人工判断的语义关联。metadata.source采用本地来源ID；精确文件路径与哈希位于manifest，不虚构Confluence/Notion来源。

## 可复现命令

在项目根目录执行：

```powershell
python paper-assets/scripts/rebuild_source_grounded_corpus.py --verify-only
```

首次构建使用同一脚本不加--verify-only。构建默认拒绝覆盖已存在版本；要重建应使用新的版本目录，例如--output paper-assets/corpora/km-project-sources-v2。冻结后的离线校验也可通过脚本verify函数仅检查包内快照。公开时需保留构建脚本、所用源快照和Python版本。

## 实验用途和限制

原始来源快照可供chunk检索路线使用；模块包可供模块路线使用。两种格式来自同一项目，不能把文档与源码分别包装成两个独立团队数据集。
各路线须使用共同的证据单元和预算规则；人工黄金标注未完成，不能把由模块反推的查询标为人工标注。任何程序生成查询需标为自动/银标签，并单独报告。
当前只验证提取与结构，不含检索性能、任务正确率、token收益或显著性结果。下游主系统组必须调用实际Knowledge Manager链路；已有模块BM25脚本只适合对照。
源码模块可能很长，具有不同粒度与依赖；粒度、截断、来源文档上下文和预算处理应在实验协议中明确。
文档中的命令与部署判断是研究材料文本，不表示其已在本次任务中执行或验证。

## 可用性与许可状态

全部文件当前仅保存在本项目本地，没有公开存储库、DOI或数据集访问号。使用本地材料进行本次处理已获用户授权；公开再分发的权利未审核，不从README许可字样推断所有文件均可公开。
原有knowledge_base与knowledge-manager/kb均未覆盖；旧的来源不明模块不自动并入正式实验语料。
