# 2026-11-06_010_PostgreSQL 只读业务工具与数据访问边界

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：010（正式 Prompt 5）
- **模块**：02_database
- **状态**：**DeepSeek 自检通过（SQLite 验证）；PostgreSQL 未验证**
- **前置任务**：009（调查图）、005（数据库设计 v2）
- **Git Commit**：见 `docs/checkpoints/git_history.md`

## 2. 任务目标和背景

前九个任务的数据全部来自 JSON fixture。本任务把数据源换成真实关系数据库，并验证：

1. 业务工具**不需要修改**就能在新数据源上工作（说明数据访问边界正确）；
2. 只读权限由**连接层**保证，而不只是"代码里没写 UPDATE"；
3. 金额仍然是 `Decimal` 精确值；
4. 同一输入在 fixture 与数据库返回等价事实。

## 3. 原始用户 Prompt

````
Task 010：PostgreSQL 只读业务工具及其数据访问边界
...
- 确定并实施最小 Schema、SQLAlchemy、Alembic、只读 Repository/Service；
- 导入固定合成业务数据；保留旧 14 表设计；
- 验收：独立测试库可由迁移与种子数据重建；同一输入在 fixture 与 PostgreSQL
  返回等价结果；项目隔离、冲销排除和余额计算通过；业务工具无写入权限。
````

完整约束见路线图 `Prompt 5 / Task 010`。

## 4. AI 实际执行的主要步骤

1. 确认环境：**本机无 PostgreSQL**（`psql` / `pg_isready` / `postgres` 均不存在）。
2. 安装 `SQLAlchemy>=2.0`、`alembic>=1.13`。
3. 新增 `app/db/models.py`：12 张表的 P0 子集（不含 `lease_units` / `agent_runs`，因为当前工具不查询它们），并实现 `Money` 类型。
4. 新增 `app/db/session.py`：只读闸门（SQLite `PRAGMA query_only`，PostgreSQL `SET TRANSACTION READ ONLY`）。
5. 新增 `app/db/seed.py`：从 fixture 导入，不产生第二份事实源。
6. 新增 `app/db/repository.py`：与 `FixtureRepository` 同形的只读查询契约。
7. 新增 Alembic 脚手架（`alembic.ini` / `migrations/env.py` / `versions/0001`）。
8. `investigation` CLI 增加 `--backend fixture|sqlite`。
9. 新增 `tests/test_database_layer.py`（12 项）。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/db/{__init__,models,session,seed,repository,bootstrap}.py` | 新增 | 模型 / 只读闸门 / 种子 / 仓库 / 装配 |
| `backend/alembic.ini`、`backend/migrations/{env.py,script.py.mako,versions/0001_initial_schema.py}` | 新增 | 迁移 |
| `backend/tests/test_database_layer.py` | 新增 | 12 项 |
| `backend/app/investigation_demo.py`、`cli.py` | 修改 | `backend` 参数 |
| `backend/pyproject.toml` | 修改 | 声明 SQLAlchemy / Alembic |

**未改动**：`docs/architecture/database_design.md`（14 表长期设计保持不动）、三个业务工具实现（零修改即适配新数据源）。

## 6. 执行结果和验证方式

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python -m alembic upgrade head`（`COMMERCIAL_DB_URL` 指向临时 SQLite） | 0 | 12 张表创建成功 |
| 2 | `python -m alembic downgrade base` | 0 | 12 张表全部删除（可重建） |
| 3 | `python -m unittest tests.test_database_layer` | 0 | `Ran 12 tests ... OK` |
| 4 | `python -m unittest discover -s tests` | 0 | `Ran 106 tests ... OK` |
| 5 | `python -m app.cli investigate`（fixture） | 0 | `verdict=conflicting`、`amount=756.00` |
| 6 | `python -m app.cli investigate --backend sqlite` | 0 | 同上，**结果一致** |

等价性与安全性断言：

| 断言 | 结果 |
|---|---|
| 应收/已收/未收/租金差额与 fixture 一致 | ✅ `52596.00` / `34560.00` / `18036.00` / `756.00` |
| allocations / payments 集合一致 | ✅ |
| 租约事实与缺失文档一致 | ✅ 含 `doc_xh_a301_annex_b` |
| 工单（hvac）一致 | ✅ 3 条 |
| 只读闸门 | ✅ `PRAGMA query_only = 1`；写语句抛 `OperationalError` |
| 仓库写方法 | ✅ `add` / `delete` / `commit` 抛 `ReadOnlyViolation` |
| 跨项目访问 | ✅ `PROJECT_SCOPE_DENIED` |
| 图在数据库后端运行 | ✅ 3 条 Trace、结论一致 |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `alembic` 读取 `alembic.ini` 报 GBK 解码错误 | ini 中含中文注释，`configparser` 按 locale 解码 | 注释改为 ASCII |
| `alembic upgrade` 建库到默认路径而非测试路径 | `env.py` 无条件用环境变量覆盖程序设置的 URL | 改为"环境变量优先，其次保留调用方设置" |
| SQLite 无十进制类型，`Numeric` 退化为 REAL | SQLite 动态类型 | `Money` TypeDecorator：SQLite 用 TEXT + `Decimal` 转换，PostgreSQL 保持 `NUMERIC(14,2)` |
| fixture 的 `arrears` 没有 `rent_variance_total` | 两个仓库返回字段略有差异 | 数据库侧额外提供该字段（更完整），测试对公共字段做等价比较 |

## 8. 对应 Git Commit Hash

见 `docs/checkpoints/git_history.md`（本轮里程碑提交回填）。

## 9. 未验证项与限制（必须如实告知）

| # | 限制 | 影响 | 后续 |
|---|---|---|---|
| 1 | **PostgreSQL 未验证**（本机无服务） | 原生 `NUMERIC`、`EXCLUDE USING gist`、部分唯一索引、RLS 均未实测 | 需在具备 PostgreSQL 的环境执行 `alembic upgrade head` 与等价性测试 |
| 2 | 迁移 0001 用 `Base.metadata.create_all` | 与 14 表设计的排他约束不一致 | 后续迁移必须显式 `op.execute` 补 `EXCLUDE` / 部分索引 |
| 3 | 只实现 12 张表的 P0 子集 | `lease_units` / `agent_runs` 未落库 | 待多商铺或审计需求出现时补 |
| 4 | 每请求一个 Session 未实现 | 当前 CLI 复用单 Session（只读，无脏写风险） | API 层（Task 014）改为请求级 Session |
| 5 | `documents` 缺 `snippets`（RAG 语料） | 文档证据仍来自 fixture 片段 | Task 011 处理 |
| 6 | 服务端会话未实现 | 主体仍从 fixture 的 `principals` 读取 | Task 014 由服务端注入可信身份 |
