# GitHub CI 与公开提交实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `knowledge-manager` 建立可复现的 Ubuntu GitHub 测试门禁，并整理公开提交所需的文档、忽略规则和发布审查证据。

**Architecture:** GitHub Actions 使用 Poetry 2.4.1 和仓库 `poetry.lock` 安装完整开发依赖。全量 pytest 是阻断 job；Black 和 Mypy 放在允许失败的质量 job 中单独报告。Windows 结果只写入项目限制，不参与 GitHub 阻断。

**Tech Stack:** GitHub Actions, Ubuntu, Python 3.12, Poetry 2.4.1, pytest, Black, Mypy, Markdown.

---

### Task 1: Add the Ubuntu blocking CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow**

Create a workflow with `push` and `pull_request` triggers, `ubuntu-latest`, Python 3.12, Poetry 2.4.1, `poetry install --no-interaction`, and blocking `poetry run pytest -q --junitxml=test-results/junit.xml`. Upload the JUnit artifact with `if: always()`.

Add a separate `quality` job with `continue-on-error: true` that runs `poetry run black --check src tests scripts` and `poetry run mypy src`.

- [ ] **Step 2: Validate locally**

```powershell
python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8')); print('workflow yaml ok')"
git diff --check
```

Expected: YAML parses and the diff check exits 0.

- [ ] **Step 3: Commit**

```powershell
git add .github/workflows/ci.yml
git commit -m "ci: add Ubuntu locked dependency test gate"
```

### Task 2: Make README suitable for public use

**Files:**
- Modify: `README.md`
- Review: `.env.production.example`, `examples/sample_knowledge_base/README.md`, `docs/runbooks/production-release-checklist.md`

- [ ] **Step 1: Document CI status**

State that Ubuntu GitHub Actions runs the locked full test suite as a blocking gate and Windows validation is `audit-only-windows` because of the current local sandbox limitation.

- [ ] **Step 2: Document installation and verification**

Add these commands:

```bash
poetry install
poetry run pytest -q
poetry run black --check src tests scripts
poetry run mypy src
```

State that Black and Mypy currently report known historical debt and are non-blocking CI checks.

- [ ] **Step 3: Document architecture boundaries**

Document `extract -> staging -> review -> publish -> serve`, the CLI/MCP/HTTP surfaces, Git-native JSON storage, intended small-to-medium scale, and that GraphRAG, Neo4j, vector databases, Celery, LangGraph, and microservices are outside the current architecture.

- [ ] **Step 4: Validate and commit**

```powershell
git diff --check
rg -n "poetry install|poetry run pytest|audit-only-windows|GraphRAG|Neo4j" README.md
git add README.md
git commit -m "docs: prepare README for public release"
```

### Task 3: Run the release hygiene audit

**Files:**
- Review: `.gitignore`, tracked files, `README.md`, `.env.production.example`, `poetry.lock`

- [ ] **Step 1: Confirm tracked scope**

```powershell
git status --short
git ls-files | rg "(^|/)(developer-kit|test-results|tmp|task1-manual-checks|\.pytest|\.mypy)"
```

Expected: local artifact directories are absent from tracked files.

- [ ] **Step 2: Scan tracked text for credentials**

```powershell
git grep -n -I -E "sk-[A-Za-z0-9]{20,}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}" -- . ":!poetry.lock"
```

Expected: no real credential match.

- [ ] **Step 3: Check dependency metadata**

```powershell
poetry check
poetry lock --check
```

Record any Poetry-version limitation instead of substituting an unverified command.

- [ ] **Step 4: Commit only required hygiene changes**

Do not add local knowledge bases, test results, nested repositories, caches, or temporary bundles.

### Task 4: Final pre-push review

**Files:**
- Review: commits since `origin/feat/knowledge-manager-phase2`
- Review: the design and assessment reports

- [ ] **Step 1: Run available local checks**

```powershell
python -m pytest -q tests/test_materialized_views.py tests/test_recommendation_index.py tests/test_storage.py
git diff --check
git status --short --branch
```

- [ ] **Step 2: Review the commit set**

```powershell
git log --oneline origin/feat/knowledge-manager-phase2..HEAD
git diff --stat origin/feat/knowledge-manager-phase2..HEAD
```

Confirm the diff contains only the fixes, tests, docs, CI, and ignore rules required for release.

- [ ] **Step 3: Record delivery state**

Record modified, verified, blocked, and not-executed items separately. Push and GitHub pull-request creation remain pending explicit user authorization.

