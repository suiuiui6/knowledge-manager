# 2026-10-22 干净环境安装验证

本批仅修复依赖安装与锁文件一致性，不修改业务源码。安装链路验证通过；项目整体验收未通过。

## 修改与原因

- 为 Poetry 配置本机已验证可达的腾讯 PyPI 镜像；使用 HTTPS，保留正常证书和包哈希校验。
- 通过真实 `poetry lock` 重新生成锁文件。旧锁遗漏 `fastapi`、`jieba`、`pyyaml`，并锁定了不满足项目 `^0.32.0` 约束的 `uvicorn 0.48.0`。旧锁的 `poetry check --lock` 仍返回 0，因此该命令不能单独证明依赖图完整。
- 新锁包含 `fastapi 0.115.14`、`jieba 0.42.1`、`pyyaml 6.0.3`、`uvicorn 0.32.1`、`starlette 0.46.2`、`sse-starlette 3.0.3`，保留 `PyJWT 2.13.0` 和 `cryptography 48.0.0`。
- 直接运行时依赖和开发依赖均已逐项核对锁定版本满足声明约束。

## 快照与环境

- 源码提交：`4683d463c538bf186e9d643f9b0a13a7e33b0078`；本批依赖配置变更在该提交之后。
- `pyproject.toml` SHA256：`7a92b98c89e71f1c416e4a3845e453d4d335aedcf8a05b76fa5b78877e1af249`。
- `poetry.lock` SHA256：`bfcc8d0a63b9464ecc9171ea79c1365dcfb055934dcbb57257e619f891b75c1c`。
- Windows、CPython 3.14.3、Poetry 2.4.1；状态为 `audit-only-windows`。
- 新建专用 Poetry 虚拟环境，未继承全局 site-packages；从锁文件安装 53 个依赖并安装当前项目。
- 测试使用 `PYTHONUTF8=1`、`PYTHONPATH=src`，TEMP/TMP 和 pytest basetemp 使用独立工作目录。未加载替代 tmp_path fixture，未跳过失败测试。
- 只验证了本次 Windows/Python 3.14 环境；Python 3.10–3.12、Linux、CI 和生产部署未执行。

## 最终验证

| 验证 | 实际命令或入口 | 退出码 | 结果 |
|---|---|---:|---|
| 重新锁定 | `poetry lock -vv` | 0 | 生成完整依赖图 |
| 全新锁定安装 | `poetry install --no-interaction` | 0 | 53 个依赖及当前项目安装成功 |
| 锁元数据检查 | `poetry check --lock` | 0 | 有配置弃用警告 |
| 依赖一致性 | 隔离解释器 `-m pip check` | 0 | No broken requirements found |
| 运行时导入及 RS256 | `summary.json` 中的完整 Python 命令 | 0 | JWT、加密、HTTP、MCP 等关键导入及实际签名验签通过 |
| wheel 安装冒烟 | `python scripts/verify_install_smoke.py --work-dir <专用临时目录> --format json` | 0 | 8 项检查通过；离线安装并使用最终锁定环境导出的精确版本约束 |
| 完整测试 | 隔离解释器 `-m pytest -q --basetemp <全新目录> --junitxml <报告路径>` | 1 | 792 passed、13 failed、79369 warnings |
| 格式检查 | 隔离解释器 `-m black --check --workers 1 src tests scripts` | 1 | 84 个文件待格式化，31 个文件不变 |
| 类型检查 | 隔离解释器 `-m mypy src` | 1 | 57 个源码文件中，26 个文件共 100 个错误 |

Black 使用一个 worker；检查范围未缩减。所有最终报告来自锁定环境。早先非锁定 wheelhouse 环境的 786 passed/19 failed 仅为排查过程，不作为最终结果。

## 剩余问题与下一批顺序

1. 优先核查 HTTP 审核操作返回 422、租户范围报告和 MCP 租户过滤相关失败，确认是行为缺陷还是过期的测试契约。不能仅凭失败名称认定权限绕过。
2. 处理 ModuleCache 的类别键读写不一致，以及 Markdown 同步与非 Git 目录 changelog 测试失败。当前缓存写入键包含类别，而不带类别的读取键不同；修复需保留类别隔离。
3. 核查搜索结果序列化断言、后台视图与推荐 telemetry 复用测试失败，再处理格式与类型债务。

本批没有修复上述测试，也没有削弱断言或忽略类型错误。完整失败清单和堆栈见 JUnit/pytest 报告。

## 证据与交付

证据目录：`test-results/dependency-install-20261022/`，含安装日志、锁解析日志、精确版本约束、安装冒烟 JSON、完整 pytest 日志/JUnit、Black/Mypy 日志及 `summary.json`。其中 `summary.json` 记录了解释器绝对路径、实际运行时检查命令、哈希和退出码。安装冒烟脚本会清理其一次性 wheel/venv，JSON 中保留原运行路径。

- 已修改：`pyproject.toml`、`poetry.lock`，新增本记录和验证证据。
- 已验证：安装、运行时依赖一致性、RS256 签名验签和 wheel 冒烟通过；完整测试、格式、类型检查未通过。
- 已提交：本记录生成时尚未提交；用户于 2026-10-23 确认将依赖配置、锁文件与本记录作为独立本地提交保存，实际提交 ID 以 Git 历史为准。此前源码提交保留。
- 已部署：未执行。未运行新的生产性能矩阵、发布门禁、备份恢复或部署验证；本报告不代表生产就绪。
