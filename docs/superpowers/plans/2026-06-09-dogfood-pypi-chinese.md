# Dogfood KB + PyPI Publish + Chinese Segmentation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make KM pip-installable with Chinese search support, and validate end-to-end with a dogfood knowledge base of the project itself.

**Architecture:** Three independent workstreams. Task 1 (dogfood KB) is manual/one-shot — extract KM's own design docs into a knowledge base and use it. Task 2 (PyPI) is packaging — fix metadata, build wheel, publish. Task 3 (Chinese segmentation) is a code change — modify `_stem()` to handle Chinese via jieba while keeping English snowballstemmer.

**Tech Stack:** Poetry (build), twine (upload), jieba (Chinese tokenization), existing KM CLI (dogfood extraction)

---

## File Structure

```
Modified:
  pyproject.toml                     ← fix author, version, add jieba dep
  src/knowledge_manager/storage.py   ← _stem() → tokenize + stem per language
  tests/test_storage.py              ← Chinese search tests

Created:
  kb/                                ← dogfood knowledge base (git-tracked)
  kb/index.json                      ← index of KM's own knowledge
  kb/architecture/                   ← architecture decisions as modules
  kb/patterns/                       ← code patterns as modules
  kb/blueprint/                      ← blueprint phases as modules
```

---

### Task 1: Dogfood KB — Extract KM's own knowledge

**Files:**
- Create: `kb/` directory with modules, index, git repo
- No code changes

This is a manual extraction task. Use `km add` to extract knowledge modules from the project's existing documentation, then review and approve them. The goal is to produce a working KB that Claude Code can use when working on KM itself.

- [ ] **Step 1: Initialize the dogfood KB**

```bash
cd D:\tyh\knowledge-manager
km init kb
```

- [ ] **Step 2: Configure LLM provider for extraction**

The existing `config.json` in `kb/` was created by `km init`. Verify it has a working LLM provider:

```bash
km --kb-path kb config list
```

If the API key is empty, set it:

```bash
km --kb-path kb config set llm_providers.deepseek.api_key "<your-key>"
```

- [ ] **Step 3: Extract architecture decisions as modules**

```bash
km --kb-path kb add docs/superpowers/specs/2026-06-08-knowledge-manager-blueprint.md -c architecture
```

Review the extracted modules:

```bash
km --kb-path kb review
```

For each module: review content, approve (`a`), reject (`r`), or skip (`s`).

- [ ] **Step 4: Extract code patterns from the source**

Key files to extract — run one at a time to keep extraction focused:

```bash
km --kb-path kb add docs/superpowers/specs/2026-06-08-knowledge-manager-blueprint.md -c blueprint --max 5
```

Review again:

```bash
km --kb-path kb review
```

- [ ] **Step 5: Verify the dogfood KB works**

```bash
km --kb-path kb stats
km --kb-path kb search "search ranking"
km --kb-path kb health
km --kb-path kb graph
```

- [ ] **Step 6: Connect KM to its own KB**

Generate MCP config so Claude Code uses this KB when working on KM:

```bash
km --kb-path kb connect claude-code
```

- [ ] **Step 7: Initialize git and commit**

```bash
cd kb
git init
git add -A
git commit -m "init: dogfood KB for knowledge-manager project"
```

---

### Task 2: PyPI Publishing

**Files:**
- Modify: `pyproject.toml` (metadata fixes)

Make KM installable via `pip install knowledge-manager`.

- [ ] **Step 1: Fix pyproject.toml metadata**

Current `pyproject.toml` has placeholder author. Update the `[tool.poetry]` section:

```toml
[tool.poetry]
name = "knowledge-manager"
version = "0.5.0"
description = "Git-native structured knowledge modules for LLM agent workflows via MCP."
authors = ["Tang Yanhao <your.email@example.com>"]
readme = "README.md"
license = "MIT"
keywords = ["knowledge-management", "mcp", "llm", "agent", "git-native"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Documentation",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
repository = "https://github.com/<user>/knowledge-manager"
packages = [{include = "knowledge_manager", from = "src"}]
```

(Replace `<user>` and `<your.email@example.com>` with real values.)

- [ ] **Step 2: Update version to 0.5.0**

The version string is already in the edit above. Verify:

```bash
cd D:\tyh\knowledge-manager
grep 'version' pyproject.toml | head -1
```

Expected: `version = "0.5.0"`

- [ ] **Step 3: Add jieba dependency**

Add `jieba` to `[tool.poetry.dependencies]`:

```toml
jieba = "^0.42.1"
```

- [ ] **Step 4: Verify package builds**

```bash
cd D:\tyh\knowledge-manager
pip install poetry  # if not already installed
poetry build
```

Expected: creates `dist/knowledge_manager-0.5.0-py3-none-any.whl` and `dist/knowledge_manager-0.5.0.tar.gz`

- [ ] **Step 5: Verify the wheel is installable**

```bash
pip install dist/knowledge_manager-0.5.0-py3-none-any.whl --force-reinstall
km --help
```

Expected: `km --help` shows the CLI with all commands including `connect`, `health`, `install`, `marketplace`, etc.

- [ ] **Step 6: Verify `km` entry point works from any directory**

```bash
cd /tmp
km --version
```

Expected: prints version number.

- [ ] **Step 7: Publish to PyPI**

If you have a PyPI account and API token:

```bash
poetry config pypi-token.pypi <your-token>
poetry publish
```

If using TestPyPI first for validation:

```bash
poetry config repositories.testpypi https://test.pypi.org/legacy/
poetry publish -r testpypi
```

- [ ] **Step 8: Verify pip install from PyPI**

```bash
pip install knowledge-manager
km --version
```

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml
git commit -m "chore: prepare v0.5.0 for PyPI publish — fix metadata, add jieba"
```

---

### Task 3: Chinese Word Segmentation

**Files:**
- Modify: `src/knowledge_manager/storage.py` (lines 11, 18, 64-65 — stem/tokenize)
- Modify: `tests/test_storage.py` (new Chinese search tests)
- Modify: `pyproject.toml` (jieba dep — done in Task 2 Step 3)

**Background:** `_stem()` currently calls `snowballstemmer.stemWord()` which is English-only. Chinese text has no spaces between words, so `\w+` regex captures entire sentences as single tokens. This breaks word-boundary matching, stem matching, and BM25 for Chinese content.

**Approach:** Replace `_stem()` with a language-aware tokenizer. For Chinese text (detected by presence of CJK characters), use `jieba.cut()` to segment into words, then apply no stemming (Chinese doesn't need stemming — words are already atomic). For non-Chinese text, keep existing snowballstemmer behavior. The `_WORD_RE` regex and downstream code that calls `_stem()` need no changes because `_stem()` still returns a string — it just now handles CJK internally.

- [ ] **Step 1: Install jieba and verify it works**

```bash
cd D:\tyh\knowledge-manager
pip install jieba
python -c "import jieba; print('|'.join(jieba.cut('知识管理系统搜索优化')))"
```

Expected output: `知识|管理|系统|搜索|优化`

- [ ] **Step 2: Write the failing Chinese search test**

Add to `tests/test_storage.py`:

```python
def test_search_modules_chinese_tokenization(kb_path):
    """Search should find Chinese modules by word after jieba segmentation."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="zh-search",
        category="general",
        title="知识管理系统架构决策",
        summary="关于知识管理系统的核心架构决策记录",
        content=ModuleContent(
            overview="我们选择 Git 作为存储层，JSON 文件作为数据格式，MCP 协议作为传输层",
            details="详细的架构决策包括不使用向量数据库、不使用 SQL 数据库、不使用消息队列等设计边界",
        ),
        metadata=ModuleMetadata(tags=["架构", "决策", "知识管理"]),
    )
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    # These Chinese words should match after jieba segmentation
    results = search_modules("架构决策", kb_path)
    assert len(results) == 1
    assert results[0].module.id == "zh-search"

    results2 = search_modules("向量数据库", kb_path)
    assert len(results2) == 1

    results3 = search_modules("消息队列", kb_path)
    assert len(results3) == 1
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd D:\tyh\knowledge-manager
pytest tests/test_storage.py::test_search_modules_chinese_tokenization -v
```

Expected: FAIL — no results returned because `消息队列` is tokenized as one long token without jieba.

- [ ] **Step 4: Modify `_stem()` to handle Chinese text**

In `src/knowledge_manager/storage.py`, replace the existing `_stem()` function (line 64-65):

Old:
```python
def _stem(word: str) -> str:
    return cast(str, _EN_STEMMER.stemWord(word.lower()))
```

New:
```python
import re as _re

_CJK_RE = _re.compile(r"[一-鿿㐀-䶿豈-﫿]")

def _stem(word: str) -> str:
    """Stem/tokenize a word. Chinese text is segmented with jieba; English uses snowball."""
    if _CJK_RE.search(word):
        try:
            import jieba
            return " ".join(jieba.cut(word))
        except ImportError:
            return word.lower()
    return cast(str, _EN_STEMMER.stemWord(word.lower()))
```

And update the `_field_stems` helper (line 91-92) to also segment Chinese text:

Old:
```python
def _field_stems(text: str) -> set[str]:
    return {_stem(word) for word in _WORD_RE.findall(text)}
```

New:
```python
def _field_stems(text: str) -> set[str]:
    stems: set[str] = set()
    for word in _WORD_RE.findall(text):
        stemmed = _stem(word)
        # _stem may return space-separated tokens for Chinese text
        stems.update(stemmed.split())
    return stems
```

And update the query tokenization in `record_search_event` (line 680) to also segment Chinese queries:

Old:
```python
    query_stems = [_stem(w) for w in _WORD_RE.findall(query.lower())]
```

New:
```python
    query_stems = []
    for w in _WORD_RE.findall(query.lower()):
        stemmed = _stem(w)
        query_stems.extend(stemmed.split())
```

- [ ] **Step 5: Verify the test passes**

```bash
pytest tests/test_storage.py::test_search_modules_chinese_tokenization -v
```

Expected: PASS

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
pytest tests/ -q
```

Expected: 342+ passed (all existing tests + 1 new Chinese test).

- [ ] **Step 7: Add integration test for mixed Chinese-English search**

Add to `tests/test_storage.py`:

```python
def test_search_modules_mixed_chinese_english(kb_path):
    """Search should work with mixed Chinese and English content."""
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
    from knowledge_manager.storage import save_module, rebuild_index, search_modules

    kb_path.mkdir(parents=True, exist_ok=True)
    mod = Module(
        id="mixed-lang",
        category="general",
        title="JWT 认证最佳实践",
        summary="JWT token 在微服务架构中的使用方法",
        content=ModuleContent(
            overview="JWT (JSON Web Token) 是一种无状态的认证机制，广泛应用于微服务架构",
            details="RS256 签名算法，24小时过期，支持 token refresh 流程",
        ),
        metadata=ModuleMetadata(tags=["auth", "认证", "JWT"]),
    )
    save_module(mod, kb_path)
    rebuild_index(kb_path)

    # English term in Chinese context
    assert len(search_modules("JWT 认证", kb_path)) == 1
    # Pure Chinese
    assert len(search_modules("微服务架构", kb_path)) == 1
    # Pure English
    assert len(search_modules("RS256", kb_path)) == 1
    # Tag search (Chinese tag)
    assert len(search_modules("认证", kb_path)) == 1
```

- [ ] **Step 8: Run full suite again**

```bash
pytest tests/ -q
```

Expected: 343+ passed.

- [ ] **Step 9: Commit**

```bash
git add src/knowledge_manager/storage.py tests/test_storage.py pyproject.toml
git commit -m "feat: add Chinese word segmentation via jieba

_stem() now detects CJK characters and delegates to jieba.cut()
for Chinese text, while keeping snowballstemmer for English.
_field_stems() splits jieba output into individual tokens.
Query tokenization in record_search_event also segmented."
```

---

## Execution Order

Tasks are independent and can run in parallel:

```
Task 1 (Dogfood KB) ──→ no dependencies, manual/one-shot
Task 2 (PyPI)        ──→ no dependencies, packaging only  
Task 3 (Chinese seg) ──→ depends on jieba dep added in Task 2 Step 3
```

Recommended order: **Task 2 Step 1-3 first** (add jieba dep to pyproject.toml), then run **Task 1** and **Task 3** in parallel, finish **Task 2** (build/publish) last.
