# 2026-11-23_035_postgresql_verification

## 1. 基本信息

- **日期**：2026-11-23（Asia/Shanghai）。
- **任务编号**：035（分 A / B / C 三段实施）。
- **模块**：02_database（只读数据层的 PostgreSQL 实机验证、P0 约束与只读角色）。
- **执行者**：编码方 DeepSeek（由 `scripts/dev_loop/` 驱动；任务单写明“编码方 DeepSeek，审查方 Claude”）。035A、035B 由编码方实施并提交；035C（证据与文档归档）由同一编码方在本轮完成。任务单由 Claude Code 编写；**四个实机问题由 Claude Code 用真实 PostgreSQL 探测发现，不是编码方发现的**（见 §5）。
- **Git Commit**：035A `af03655`，035B `f901ac5`，035C `5586ef3`（归档写作时未提交，之后提交）；独立复查返修见 §12。均未推送。
- **当前状态**：**已实施并自检，待独立复查；未推送。** 自检不等于最终验收。
- **环境**：Docker 容器 `cpma-pg-dev`（`postgres:16`），只绑定 `127.0.0.1:55432`；测试库实际版本 **PostgreSQL 16.16**（`select version()`，见 `schema_pg.txt` 第 3 行）；驱动 `psycopg==3.3.8`。连接串只放在环境变量 `COMMERCIAL_PG_TEST_URL`，未写入任何文件。
- **付费接口**：未调用（本任务不涉及任何模型调用）。
- **任务依据**：[035A 任务单](../../handoffs/DEV_LOOP_TASK035A_PG_CORRECTNESS.md)、[035B 任务单](../../handoffs/DEV_LOOP_TASK035B_PG_CONSTRAINTS_ROLE.md)、[035C 任务单](../../handoffs/DEV_LOOP_TASK035C_PG_DOCS.md)。

## 2. 任务目标与范围

路线图 P0 工作包 3“PostgreSQL 实机与数据边界验收”此前只在 SQLite 上验证。Task 035 拆成三段：

- **035A**：修四个 PG 实机问题（seed 外键顺序、只读闸门只对单事务有效、时区、单价精度），建立 PG 测试套件。
- **035B**：补 P0 约束（39 条 CHECK + 1 条租期 `EXCLUDE`）、只读数据库角色、CLI `--backend postgresql`。
- **035C**：用实际输出归档 12 / 14 表清点、PG 证据与文档；**不改任何代码和测试**。

本段范围明确不包含：RLS、多实例并发、生产部署、补齐 14 表设计。测试只在设置了 `COMMERCIAL_PG_TEST_URL` 时运行；未设置时整套 PG 测试跳过（默认回归不依赖 PG）。

## 3. 原始用户 Prompt

本轮由 `scripts/dev_loop/` 调度执行；调度脚本发给编码方的指令（由模板 `scripts/dev_loop/coder_prompt.md` 填充，非用户原话）逐字如下：

```text
你是本仓库的实施者（编码方）。另一个独立模型会审查你的改动，审查不通过会把问题清单交回给你。

## 本轮任务

- 任务单：`docs/handoffs/DEV_LOOP_TASK035C_PG_DOCS.md`（先完整阅读，以任务单为准）
- 本轮轮次：第 1 轮
- 这是第一轮，没有审查意见。

## 规则

1. 只做任务单要求的事；不要顺手重构、不要改无关文件、不要改评测题和评分规则。
2. **不提交、不推送、不切分支、不 stash。** 改动留在工作区，由用户最终决定是否提交。
3. 不碰 `data/`、`tools/flowise/`、`.gitignore` 里的 Flowise 三行。
4. 不调用付费模型接口（任何命令都不要带 `--planner-provider deepseek` / `--model-provider deepseek`）。
5. Python 用 `D:/anacada/envs/commercial-agent/python.exe`（Git Bash 里的 `python` 是占位程序）。调度脚本会在每轮结束后自动运行测试并把结果交给审查方；你自己想先验证时，在仓库根目录运行：
   `D:/anacada/envs/commercial-agent/python.exe -X utf8 -m unittest discover -s backend/tests -t backend -p "test_*.py"`
   （任务单另有测试命令时以任务单为准。）
6. 新写的文本文件用 LF 换行。
7. **每次 Bash 调用只执行一个简单命令**：不要用 `&&`、`;`、`|` 组合，不要 `cd`，不要 `git -C`，路径一律相对仓库根目录写，否则命令会被权限系统拒绝。命令被拒就是没执行，不要在总结里声称做过。
8. 如果审查意见中某条你认为不成立，不要硬改；在最后的总结里写明理由，交给审查方裁决。

## 结束时输出

用中文简要列出：改了哪些文件、每条审查意见如何处理（已修复 / 不同意及理由）、测试结果。
```

本归档结构参照 [Task 033 归档](../04_agents/2026-11-23_033_mcp_gateway.md)，并按 035C 任务单补充“12 / 14 表清点”与“测试点逐条结果”。

## 4. 实际改动

### 4.1 035A（Commit `af03655`）：正确性修复与 PG 测试套件

- `backend/app/db/seed.py`：按父 → 子顺序插入，每组 `flush()`。
- `backend/app/db/session.py`：PG 只读改为 Session `after_begin` 逐事务声明；`create_engine_for` 用连接启动参数固定数据集时区。
- `backend/app/db/models.py`：新增 `UnitPrice`（PG `NUMERIC(14,4)`，SQLite TEXT），用于 `unit_price` 与 `quantity`；`Money` 保持 2 位。
- `backend/migrations/versions/0002_unit_price_precision.py`：显式 `op.alter_column` 改 4 位，`downgrade` 改回；SQLite 无 DDL。
- `backend/app/db/bootstrap.py`：抽出 `build_repository_for_engine`，供 PG 复用 seed + 只读装配。
- `backend/tests/test_postgres_layer.py`（新增）与 `test_database_layer.py`（仅追加 SQLite 侧断言）。

### 4.2 035B（Commit `f901ac5`）：P0 约束、只读角色与 CLI

- `backend/migrations/versions/0003_p0_constraints.py`：39 条 CHECK + PG 专属 `EXCLUDE USING gist`；SQLite 用 `CAST(... AS REAL)` 比较 TEXT 金额，不建租期排他约束。
- `backend/app/db/roles.py`（新增）：`create_readonly_role` / `drop_readonly_role`。
- `backend/app/db/bootstrap.py`：新增 `build_postgres_repository`。
- `backend/app/cli.py`：`--backend postgresql`，连接串只从 `COMMERCIAL_DB_URL` 读取。
- `backend/tests/test_postgres_layer.py`、`test_database_layer.py`：只追加测试。

### 4.3 035C（Commit `5586ef3`）：证据与文档

- 新增 `docs/reviews/task035_evidence/dump_schema.py`（只读导出脚本）与 `schema_pg.txt`、`pg_unittest.txt`、`unittest.txt`、`smoke.txt`。
- 新增本归档；更新 `docs/architecture/database_design.md`、`backend/README.md`、`docs/README.md`、开发日志、问题日志、`CURRENT_BASELINE.md`、路线图。
- **未改任何代码、测试、评测题或评分规则。**

## 5. 四个实机问题：现象、根因与修复

以下四个问题由 **Claude Code 用真实 PostgreSQL 16.16 探测发现**，编码方在 035A 中修复。SQLite 测试未发现它们的原因逐条写明。

### 5.1 seed 外键顺序

- **现象**：`seed_from_fixture` 在 PG 上失败，`buildings` 插入违反 `buildings_project_id_fkey`；迁移本身正常，12 张表都能建出来。
- **根因**：模型没有定义 `relationship`，SQLAlchemy 仅凭外键无法推导多表 INSERT 顺序；而 SQLite 默认不检查外键。
- **修复**：`seed.py` 按父 → 子顺序逐表 `session.add` 后 `flush()`。
- **SQLite 为什么没测出**：SQLite 默认 `PRAGMA foreign_keys=OFF`，错误的插入顺序不会报错，数据照样落下。

### 5.2 只读闸门只对单个事务有效

- **现象**：只读会话在 `rollback()` 之后，同一个 Session 的新事务里 `UPDATE` 成功。
- **根因**：PG 的 `SET TRANSACTION READ ONLY` 是**事务级**声明，事务结束即失效；SQLite 的 `PRAGMA query_only` 是**连接级**，一直有效。
- **修复**：在 Session 的 `after_begin` 事件上为**每个新事务**执行 `SET TRANSACTION READ ONLY`（跳过 SAVEPOINT）。没有选连接级 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`，因为连接归还池后该设置仍保留，可能把后续复用的写连接（如 seed）也变成只读，故障方向不可控。
- **SQLite 为什么没测出**：两种方言的只读语义本来就不同；SQLite 的连接级 PRAGMA 让“事务结束后失效”这一 PG 特有行为无法暴露。

### 5.3 时区展示偏差

- **现象**：fixture 工单 `reported_at = 2026-07-12T13:20:00+08:00`，PG 读回 `2026-07-12T05:20:00+00:00`——同一时刻，但直接展示会差 8 小时。
- **根因**：列是 `DateTime(timezone=True)`，PG 按连接会话时区（默认 UTC）返回。
- **修复**：`create_engine_for` 为 PG 连接加启动参数 `-c timezone=Asia/Shanghai`，时区常量只定义一次（`session.DATASET_TIMEZONE`）。没有用 `SET TIME ZONE`，因为连接池复用连接时会重置会话状态（实测恢复为 `Etc/UTC`），只有启动参数在每次建立连接时都生效。
- **SQLite 为什么没测出**：SQLite 没有 `timestamptz`，时间以文本存储并原样读回，不做时区换算。

### 5.4 单价精度

> **复查更正**：本节的修复只覆盖**存储层 / ORM**。业务只读仓库（`DatabaseRepository`）读出单价与数量时仍量化到 2 位并用它计算应收租金，独立复查判为 P1-1，返修见 §12。

- **现象**：fixture 单价 `132.3000` 被保存成 `132.30`，最后两位静默丢失。
- **根因**：`lease_charge_rules.unit_price`、`invoice_items.unit_price`、`invoice_items.quantity` 复用了 2 位小数的 `Money`（Python 侧 `quantize(0.01)`，PG 侧 `NUMERIC(14,2)`）。
- **修复**：新增 `UnitPrice`（PG `NUMERIC(14,4)`，SQLite TEXT 存 4 位），迁移 `0002` 用显式 `op.alter_column` 扩列；金额列仍为 2 位。
- **SQLite 为什么没测出**：这不是 PG 特有缺陷——SQLite 路径同样会在 Python 侧截断；但原有 SQLite 等价性测试只比较了金额、核销、工单等选定字段，**从未断言 4 位小数单价**，所以两种方言都没暴露。035A 在 SQLite 侧追加了精度断言，在 PG 侧新增了 4 位单价比较。

## 6. 约束清单与 PG 实机证据

### 6.1 证据文件

| 文件 | 内容 |
|---|---|
| [`schema_pg.txt`](../../reviews/task035_evidence/schema_pg.txt) | 用 SQLAlchemy `inspect` 从测试库导出的 12 张表、列类型、主键 / 唯一 / CHECK / 外键、EXCLUDE 约束与服务端版本；不含连接串 |
| [`dump_schema.py`](../../reviews/task035_evidence/dump_schema.py) | 生成上述输出的只读脚本（只做 SELECT 与系统目录查询） |
| [`pg_unittest.txt`](../../reviews/task035_evidence/pg_unittest.txt) | 只运行 PG 套件的实际输出：`Ran 36 tests ... OK` |
| [`unittest.txt`](../../reviews/task035_evidence/unittest.txt) | 全量回归实际输出：`Ran 700 tests ... OK (skipped=1)` |
| [`smoke.txt`](../../reviews/task035_evidence/smoke.txt) | 契约自检实际输出：`全部通过：70 项检查` |

实际 schema 汇总：**12 张业务表** + `alembic_version`，**39 条 CHECK、1 条 EXCLUDE**；`unit_price` / `quantity` 为 `NUMERIC(14,4)`，金额为 `NUMERIC(14,2)`，时间列为 `TIMESTAMP WITH TIME ZONE`。

### 6.2 约束清单（按类别）

| 类别 | 条数 | 约束名 |
|---|---|---|
| 状态 / 类别枚举 | 17 | `ck_projects_status_p0`、`ck_units_physical_status_p0`、`ck_tenants_status_p0`、`ck_leases_status_p0`、`ck_leases_billing_cycle_p0`、`ck_charge_rules_charge_type_p0`、`ck_charge_rules_calculation_method_p0`、`ck_charge_rules_period_unit_p0`、`ck_invoices_status_p0`、`ck_invoice_items_charge_type_p0`、`ck_payments_status_p0`、`ck_payments_method_p0`、`ck_work_orders_category_p0`、`ck_work_orders_priority_p0`、`ck_work_orders_status_p0`、`ck_documents_doc_type_p0`、`ck_documents_status_p0` |
| 金额 / 面积 / 数量 | 10 | `ck_units_area_positive_p0`、`ck_units_chargeable_area_positive_p0`、`ck_leases_deposit_non_negative_p0`、`ck_charge_rules_amount_non_negative_p0`、`ck_charge_rules_unit_price_non_negative_p0`、`ck_invoice_items_amount_adjustment_p0`、`ck_invoice_items_quantity_nonzero_p0`、`ck_invoice_items_unit_price_non_negative_p0`、`ck_payments_amount_positive_p0`、`ck_payment_allocations_amount_positive_p0` |
| 日期区间 / 账期 | 7 | `ck_leases_date_range_p0`、`ck_leases_payment_terms_days_p0`、`ck_charge_rules_effective_range_p0`、`ck_invoices_period_range_p0`、`ck_invoices_due_after_issue_p0`、`ck_work_orders_resolved_after_reported_p0`、`ck_work_orders_resolved_status_time_p0` |
| 币种 / 规则一致性 / 版本 | 5 | `ck_leases_currency_format_p0`、`ck_invoices_currency_format_p0`、`ck_payments_currency_format_p0`、`ck_charge_rules_calc_consistency_p0`、`ck_documents_version_positive_p0` |
| **CHECK 小计** | **39** | 全部在 PG 上实际创建并由 `test_constraint_names_are_installed` 与 `test_invalid_rows_are_rejected` 验证 |
| 租期不冲突（PG 专属） | 1 | `ex_leases_unit_active_period_p0`：`EXCLUDE USING gist (unit_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status = 'active')`，需 `btree_gist` |

取值依据：fixture 中实际出现的值 + 设计文档 §9 状态机与 §6 各表定义；`invoice_items.amount` 仅 `charge_type='other_fee'` 允许负数（设计 §6.9 的减免 / 冲抵）。SQLite 分支用 `CAST(col AS REAL)` 比较 TEXT 金额；SQLite 上**不保证**租期不重叠。

## 7. 只读角色与 CLI

### 7.1 只读数据库角色（035B，`backend/app/db/roles.py`）

- `create_readonly_role(engine, role_name, password)`：创建 `LOGIN` 角色，只授予业务表 `SELECT`，并用 `ALTER DEFAULT PRIVILEGES` 覆盖之后由同一账号新建的表；**不授予 `alembic_version`**，也不授予任何写权限。
- `drop_readonly_role(engine, role_name)`：回收表 / 序列 / schema / 数据库连接权限后删除角色。
- 角色属性：`NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS`；测试实际查询 `pg_roles` 断言无提权属性。
- 安全：角色名只允许 `[a-z_][a-z0-9_]*` 且不超过 63 字节；密码用随机 dollar-quote 标签转义后交给 `exec_driver_sql`；`CREATE ROLE` 失败抛 `RoleCreationError`（`from None`），消息不含 SQL 或密码。
- 测试实际验证：只读角色能读出与 fixture 等价的数据；`INSERT` / `UPDATE` / `DELETE` / `CREATE TABLE`，以及 `SET TRANSACTION READ WRITE` 后再写，全部被数据库拒绝；含 `:` / 引号 / `%` 等特殊字符的密码也能登录。

### 7.2 CLI `--backend postgresql`（035B）

- `investigate --backend postgresql` 的连接串**只**从环境变量 `COMMERCIAL_DB_URL` 读取，不接受命令行明文；未设置 → 退出码 2 并提示。
- engine 必须经 `app.db.session.create_engine_for` 创建（035A 的时区修复在该函数的连接启动参数里）；CLI 测试断言工单时间带 `+08:00`。
- 使用只读仓库：会话级只读闸门仍然生效；连接的是**已迁移、已有数据**的库，CLI 不建表、不 seed。
- 报告元数据记录 `backend=postgresql`，不记录连接串；测试断言 stdout / stderr / 报告里都没有连接串或密码。
- `--backend postgresql` 与 `--variant` 同时使用会被明确拒绝（退出码 2）。
- **注意**：`backend/migrations/env.py` 会**优先**读取 `COMMERCIAL_DB_URL`；测试只在子进程环境或 `mock.patch.dict` 的局部范围设置它，避免 `test_database_layer` 的 SQLite 迁移测试误连 PG。

## 8. 测试点逐条结果

运行环境：设置了 `COMMERCIAL_PG_TEST_URL` 的 PG 16.16 测试库。PG 套件命令（仓库根目录，等价于在 `backend/` 下运行 `python -m unittest tests.test_postgres_layer -v`）：

```bash
D:/anacada/envs/commercial-agent/python.exe -X utf8 -m unittest discover -s backend/tests -t backend -p "test_postgres_layer.py" -v
```

**实际结果：`Ran 36 tests in 6.517s` → `OK`（36 个实际执行，0 跳过）。** 原始输出见 [`pg_unittest.txt`](../../reviews/task035_evidence/pg_unittest.txt)。

| 任务单要求 | 测试 | 结果 |
|---|---|---|
| 035A-1 迁移：12 表 + `alembic_version`；降级清空；列类型精度 | `TestMigrationsPostgres`（4 个） | 通过 |
| 035A-2 seed 行数与 fixture 一致 | `TestSeedPostgres.test_seed_row_counts_match_fixture` | 通过 |
| 035A-3 选定字段等价；时间 ISO 字符串含 `+08:00`；单价 4 位 | `TestEquivalenceWithFixturePostgres`（7 个） | 通过 |
| 035A-4 只读：首事务、`rollback()` 后、`commit()` 后均拒绝写入，且仍可读 | `TestReadOnlyPostgres`（3 个） | 通过 |
| 035A-5 项目隔离：越权项目拒绝、未知租约不存在 | `TestRepositoryIsolationPostgres`（3 个） | 通过 |
| 035A-6 金额为 `Decimal` 而非 `float` | `test_amounts_are_decimal_not_float` | 通过 |
| 035A-7 端到端：PG 只读仓库跑调查，关键数字与 fixture 一致 | `TestToolsBoundToPostgres.test_investigation_uses_postgres_repository` | 通过 |
| 035B-1 每类约束的违规写入被拒绝；fixture 全量 seed 成功 | `TestP0ConstraintsPostgres`（4 个） | 通过 |
| 035B-2 租期重叠被 `EXCLUDE` 拒绝；不重叠 / 非生效状态允许 | `TestLeaseExclusionPostgres`（3 个） | 通过 |
| 035B-3 只读角色：可读、写全部被拒、可建可删、无提权属性 | `TestReadonlyRolePostgres`（5 个） | 通过 |
| 035B-4 CLI：与 fixture 关键数字一致、`backend=postgresql`、未设 URL 退出码 2、无连接串泄露 | `TestCliPostgres`（4 个） | 通过 |
| 035B-5 `0003` 降级删约束后，`0002` / `0001` 仍能继续降级 | `TestConstraintsMigrationDowngradePostgres` | 通过 |

全量回归（同一 PG 环境，仓库根目录）：

```bash
D:/anacada/envs/commercial-agent/python.exe -X utf8 -m unittest discover -s backend/tests -t backend -p "test_*.py"
```

**实际结果：`Ran 700 tests in 52.788s` → `OK (skipped=1)`**；PG 测试真正执行（见上），唯一的 skip 是既有的与 PG 无关用例。契约自检 `python backend/tests/smoke_agent_contracts.py` → **70 项全部通过**。

## 9. 已知差异与归档说明

### 9.1 12 / 14 表清点

完整逐表对照见 [`database_design.md` §17](../../architecture/database_design.md#17-实现对照task-035)。摘要：

- **已实现 12 张**：`projects`、`buildings`、`units`、`tenants`、`leases`、`lease_charge_rules`、`invoices`、`invoice_items`、`payments`、`payment_allocations`、`work_orders`、`documents`。
- **未实现 2 张**：`lease_units`（空间关系直接放在 `leases.unit_id`，租期冲突改用 `leases` 上的 EXCLUDE）、`agent_runs`（Agent 审计仍只在进程内 Trace）。
- **共同精简**：无 `uuid` / `created_at` / `updated_at` / `deleted_at`、无部分唯一索引、无复合项目外键、无生成列与触发器。
- **fixture 有、数据库不存**：`leases.signing_date`、`leases.referenced_document_ids`（DB 仓库改用 `documents.lease_id` 并硬编码缺失文档清单）、`approval_drafts`（数据库待审批草案）。
- **草案差异**：fixture 里 A-301 有 `rent_reduction_draft`（v1 `756.00`、v2 `700.00`，`expires_at` 带 `+08:00`）。12 张表没有存草案的表，因此 `--backend fixture` 的报告有 `proposed_draft`，`--backend sqlite` / `postgresql` 都没有（两者一致）。这是精简设计差异，不是 PG 问题。

### 9.2 迁移 `0001` / `0002` 的实际行为

`0001` 用 `Base.metadata.create_all` 建表，而 035A 已把模型单价改成 `UnitPrice`（`NUMERIC(14,4)`）。因此**新建的库在 `0001` 之后就已经是 4 位**，`0002` 的 `upgrade` 在全新库上是**空操作**；`0002` 的价值在于把 035A 之前已建成的 2 位库改成 4 位。`0002` 的 `downgrade` 会把列改回 2 位，再 `upgrade` 又扩回 4 位——`test_0002_downgrade_narrows_then_upgrade_widens` 实际验证了这一点。

### 9.3 约束实现位置

- 39 条 CHECK 与 EXCLUDE 全部写在迁移 `0003`；模型没有重复声明同名约束（ORM 不参与约束定义，以迁移为准）。
- `btree_gist` 在 `0003` upgrade 时 `CREATE EXTENSION IF NOT EXISTS`；downgrade **不删除**扩展，因为它可能被其它对象或运维共用。
- SQLite 用 `CAST(... AS REAL)` 修正 TEXT 金额比较；租期不冲突只在 PG 上存在。

## 10. 遗留问题

| # | 问题 | 影响 / 建议 |
|---|---|---|
| 1 | **CLI 的 PG 仓库注入依赖临时替换 `bootstrap.build_sqlite_repository`**（`cli.py::_postgres_repository_seam`） | 035B 不允许改 `investigation_demo.py`，所以只能在装配期临时替换工厂。可用，但依赖延迟导入这一实现细节、且不是线程安全的；建议后续让 `build_investigation_bundle` 直接接受仓库参数 |
| 2 | **RLS 未启用** | 权限只在应用层与只读角色层，数据库没有行级策略；`project_id` 已就位，可作为后续工作 |
| 3 | `payment_allocations` 唯一约束是全量 `(payment_id, invoice_id)` | 设计为 `WHERE reversed_at IS NULL` 的部分索引；当前冲销后不能对同一账单重新核销同一笔收款 |
| 4 | 没有同类计费规则区间不重叠的 `EXCLUDE` | 设计 §6.7 的 `ex_charge_rules_no_overlap` 未实现 |
| 5 | 软删除、部分唯一索引、复合项目外键、生成列 / 触发器未实现 | 见设计 §17.1 / §17.2 |
| 6 | `referenced_document_ids` 不落库 | DB 仓库用 `REFERENCED_BUT_MISSING_BY_LEASE` 常量补 A-301 的缺失文档事实；新增类似数据需要改代码 |
| 7 | 多实例并发、生产部署、连接池故障切换未验证 | Task 035 只在单个本地容器上验证 |
| 8 | 既有的 PG 专属架构未覆盖 | 未验证其它 PG 版本、备份恢复、扩展安装权限受限的场景 |
| 9 | 状态 | 独立复查**不通过**（P1-1 单价读路径），已返修并自检，待复查确认（§12）；未推送 |

## 11. 对应 Git Commit Hash

- **035A**：`af03655`（`fix(db): Task 035A PostgreSQL 实机——seed 外键顺序、会话级只读、时区、单价精度`）。
- **035B**：`f901ac5`（`feat(db): Task 035B PostgreSQL P0 约束、只读数据库角色与 CLI --backend postgresql`）。
- **035C**：`5586ef3`。
- 以上均**未推送**。

## 12. 独立复查与返修（2026-11-23）

DeepSeek [独立复查](../../reviews/2026-11-23_task035_independent_review.md)（首次由 `scripts/dev_loop/dev_review.ps1` 自动执行，用户无需转交）结论：**不通过**。阻断项 P1-1；另有 P2 一项、P3 若干。Claude Code 直接返修，未新增付费调用以外的操作：

| 编号 | 问题 | 返修 |
|---|---|---|
| P1-1 | `DatabaseRepository` 读出 `unit_price` / `quantity` 时用 `_money` 量化到 2 位，并用 2 位值算 `expected_rent` / `rent_variance`；真实 4 位费率 `126.3456` 会算错差额 | 新增 `_unit()`（4 位）用于单价 / 数量的输出与应收计算；金额只在最终结果上量化到分。**根因在任务单**：035A / 035B 任务单把 `repository.py` 列为“不改”，复核者（Claude Code）也只验证了存储层 |
| P2-1 | 精度测试只读 ORM，fixture 单价末两位是 0，截断后补 0 无法区分；复查者的变异 M2b（写入量化回 2 位）存活 | SQLite 与 PG 各新增仓库级测试：把 A-301 2026 租金规则与明细改成 `126.3456` / `120.1234`，断言 `statement` / `lease_facts` 与 fixture 路径一致，`expected_rent = 15177.06`（截成 2 位会是 15177.16） |
| P3-1 | EXCLUDE 无首尾边界测试；`[]` → `[)` 变异存活 | 新增：首尾同日拒绝、次日允许、草案改为 active 时拒绝 |
| P3-2 | CLI 无连接失败 / 未迁移 / 无权限测试 | `main` 拦截 `SQLAlchemyError`，只报异常类型、退出码 2、无 traceback；新增三种失败的测试，断言不泄露连接串 / 密码 |
| P3-3a | `raise ... from None` 仍在 `__context__` 留着含密码的原异常 | 在 `except` 块之外抛出，`__cause__` / `__context__` 均为空；测试补 `__context__` 断言 |
| P3-3b | DDL 含密码，`echo=True` / `log_statement` / `pg_stat_activity` 可见 | `create_readonly_role` 拒绝 `echo=True` 的 engine；docstring 与 README 写明其余暴露面（PG 不能参数化 DDL） |
| P3-3c | `roles.py` docstring 说用 `quote_literal()`，实际是 dollar-quote | 已更正 |
| P3 收尾 | `drop_readonly_role` 可能无限等锁；seam 失效会静默回退 SQLite；SQLite 迁移测试受 `COMMERCIAL_DB_URL` 影响 | 删除角色加 `lock_timeout = 5s`；CLI 断言 bundle 用的是注入的 PG 仓库；`TestMigrations` 在 `setUp` 里移除该变量 |
| P3-6 / 文档 | 精度、闭区间语义措辞过宽；035C 提交状态陈旧；部署前提未写 | 本归档、`database_design.md`、`backend/README.md`、问题日志已更正（`ALTER DEFAULT PRIVILEGES` 的同一账号前提、`btree_gist` 保留、`0003` 校验存量行、`fixed_amount` 租金未支持） |

**验证**：707 tests OK（PG 环境 skipped=1；默认 skipped=43）、PG 套件 42 个全部执行（035C 时 36 个）、70 项契约、`check` exit 0；证据 `docs/reviews/task035_evidence/repair_unittest.txt`、`repair_pg_unittest.txt`。变异验证：读路径回到 2 位 → 2 失败；写入量化回 2 位（复查 M2b）→ 4 失败（PG 与 SQLite 两个测试模块合计；只跑 PG 模块为 2 项）；EXCLUDE 开区间（M4b）→ 1 失败；角色异常回到 `except` 内 `from None` → 1 失败；CLI 不拦数据库错误（M6b）→ 2 错误。存储类型改回 `NUMERIC(14,2)`（复查 M2）仍存活：迁移后的库会被 `0002` 再改回 4 位，对已迁移库不是真回归。

返修为自检，需复查确认后才能关闭；不等于最终验收。

### 12.1 返修确认复查（2026-11-23）

DeepSeek [返修确认复查](../../reviews/2026-11-23_task035_repair_review.md)（`dev_review`，157 轮、约 12 分钟）：**有条件通过**。P1-1、P2-1、P3-1、P3-2、P3-3a、P3-3c、P3 收尾**关闭**；P3-3b **部分关闭**；P3-6 基本关闭。新发现一项**既有 P2**与若干 P3 残留，已处理：

| 编号 | 问题 | 处理 |
|---|---|---|
| 既有 P2 | `DatabaseRepository.arrears()` 只返回总额，缺 `invoices` / `payments` / `allocations`；`billing.arrears.calculate` 遍历 `arrears["invoices"]`，在数据库后端抛 `KeyError`（`9fb3935` 之前就存在；以前只比较仓库方法的部分字段，从没在数据库仓库上调用过工具） | 补齐三项，与 `FixtureRepository.arrears()` 同契约。新增 `TestArrearsToolOnDatabase`（SQLite）、`TestArrearsToolOnPostgres`：在数据库仓库上真正调用 `billing.arrears.calculate` / `billing.statement.read` / `lease.lookup`，输出与 fixture 一致；撤回修复时两个测试都报错 |
| P3-3b 残留 | `echo=False` 但 `sqlalchemy.engine` logger 为 INFO/DEBUG 时，含密码的 DDL 仍会进日志 | `create_readonly_role` 在这种情况下同样拒绝；补测试 |
| docstring | `RoleCreationError` 仍写 `from None` | 已改为“在 except 之外抛出、无 `__cause__` / `__context__`” |
| 文档 | 开发日志 035C 状态；M2b 失败数；SQLite 方言限制未写 | 已更正；SQLite 限制写进 `backend/README.md` §7（见下） |
| 已知限制 | `fixed_amount` 租金规则未实现 | 复查判为可接受的已知限制，保持 README 说明 |

**SQLite 方言限制**（只影响离线 / 演示用的 SQLite 后端，PG 不受影响）：`DateTime(timezone=True)` 不保存 UTC 偏移，读回不带偏移的本地时间（fixture 为 `+08:00`）；金额以 TEXT 存储，约束里用 `CAST(... AS REAL)` 比较，非数字文本会被当作 0；币种约束用 `length` + `upper`，不能拒绝非 ASCII 字母；不保证租期不重叠。

验证见开发日志对应条目与 `docs/reviews/task035_evidence/repair2_unittest.txt`。条件满足后 Task 035 返修确认完成，**不等于最终验收**。

