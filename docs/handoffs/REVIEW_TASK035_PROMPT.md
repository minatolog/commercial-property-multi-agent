# 复查 Prompt：Task 035（PostgreSQL 实机验证）独立复查

- 编写：2026-11-23（Asia/Shanghai），Claude Code（任务拆分、实机探测、dev_loop 调度与复核者）。
- 给：与实施者不同的模型（由 `scripts/dev_loop/dev_review.ps1` 调用）。
- 性质：**只读复查**。仓库内不改任何文件；实验在调度脚本给的仓库外实验目录里做。

> 实施方式：035A / 035B / 035C 三张任务单由 dev_loop 执行（编码方 DeepSeek，审查方 Claude）；035A、035C 第 1 轮通过，035B 第 2 轮通过。四个 PG 实机问题是 Claude Code 先用探针发现、写进任务单的；复核时 Claude Code 还**自己补了测试**（见 §4.6）。编码方、dev_loop 审查方、复核者都不是独立复查者；下面的“疑点”只是起点。

---

## 0. 硬性约束

1. 不调用付费模型接口；不 `pip install`；**不运行 `docker`**。
2. 仓库内不改任何文件；不提交、不推送、不切分支、不 stash；不碰 `data/`。
3. **PostgreSQL 测试库**：环境变量 `COMMERCIAL_PG_TEST_URL` 已设置（本机 Docker 容器 `cpma-pg-dev`，PostgreSQL 16.16，只绑定本机）。你可以在这个库上做任何实验（迁移、seed、建临时角色、违规写入），但**结束时必须清理**：临时角色全部删除，库回到 `alembic downgrade base` 状态。**报告里不要写出连接串或密码**。
4. 不要设置 `COMMERCIAL_DB_URL` 到全局环境：`backend/migrations/env.py` 会优先读取它，覆盖测试里的 URL。需要时只在子进程环境里设置。
5. 做变异测试时，把 `backend/` 和 `docs/evaluation/fixtures/` 按原有相对结构一起复制到实验目录（fixture 路径相对于仓库根），在副本里改。
6. 环境：`D:/anacada/envs/commercial-agent/python.exe`；在 `backend/` 下运行，设置 `PYTHONUTF8=1`。

## 1. 复查对象

- 都已提交：`282c35a`（三张任务单）、`af03655`（035A）、`88ddcdf`（035B 任务单补充）、`f901ac5`（035B）、`5586ef3`（035C）。
- 差异：`git diff 34a51a2 5586ef3`（`34a51a2` 之前是 Task 033 与 dev_loop 工具，不在范围）。
- 开始前确认 `git rev-parse HEAD` 为 `5586ef3` 或其后只多了本 Prompt 的提交，`git status --porcelain` 除 `.claude/` 外为空。

## 2. 必读材料

| 用途 | 文件 |
|---|---|
| 任务单（含实机探测结论） | [`DEV_LOOP_TASK035A_PG_CORRECTNESS.md`](DEV_LOOP_TASK035A_PG_CORRECTNESS.md)、[`DEV_LOOP_TASK035B_PG_CONSTRAINTS_ROLE.md`](DEV_LOOP_TASK035B_PG_CONSTRAINTS_ROLE.md)、[`DEV_LOOP_TASK035C_PG_DOCS.md`](DEV_LOOP_TASK035C_PG_DOCS.md) |
| 实施记录 | [`prompts/02_database/2026-11-23_035_postgresql_verification.md`](../prompts/02_database/2026-11-23_035_postgresql_verification.md) |
| 代码 | `backend/app/db/`（`session.py`、`seed.py`、`models.py`、`bootstrap.py`、`roles.py`）、`backend/migrations/versions/0002_*.py`、`0003_*.py`、`backend/app/cli.py` 的 `--backend postgresql` |
| 测试 | `backend/tests/test_postgres_layer.py`、`backend/tests/test_database_layer.py` 的新增部分 |
| 设计对照 | `docs/architecture/database_design.md`（新增“实现对照（Task 035）”一节） |
| 证据 | `docs/reviews/task035_evidence/` |

## 3. 自报数字（全部独立复跑）

| 项 | 自报 |
|---|---|
| 全量回归（设置 `COMMERCIAL_PG_TEST_URL`） | 700 OK（skipped=1） |
| 全量回归（不设置） | 700 OK（skipped=37；其中 36 个是 PG 测试） |
| `tests.test_postgres_layer` | 36 个，全部实际执行 |
| 契约 / `check` | 70 / exit 0 |
| `dump_schema.py`（库迁移到 head 后运行） | 与 `schema_pg.txt` 一致；39 条 CHECK + 1 条 EXCLUDE |

## 4. 复查清单

### 4.1 四个实机问题是否真的修好

1. **seed 外键顺序**：用原始 `seed_from_fixture` 在 PG 上落库是否成功；`flush` 的位置能否覆盖所有父 → 子依赖。
2. **只读闸门**（`session.py` 的 `after_begin`）：除了 `rollback()` / `commit()` 之后的新事务，再试：`session.begin_nested()`（SAVEPOINT）里写入、`session.connection()` 拿到连接后直接写、`session.execute(text("SET TRANSACTION READ WRITE"))` 之后再写、连接池复用后的新 Session。找一找有没有绕过 Session 直接用 engine 连接的业务路径（`DatabaseRepository` 及其调用方）。
3. **时区**：修复在 `create_engine_for` 的连接启动参数里。清点**所有**创建 PG engine 的地方（迁移 `env.py`、`roles.py`、CLI、测试），有没有绕过 `create_engine_for` 的；绕过的话读出的时间是否仍是 UTC，是否影响业务输出。
4. **单价精度**：`UnitPrice` 在两种方言上是否原样保存 4 位；金额列仍是 2 位。`0001` 用 `create_all` 建表，所以新库在 `0001` 之后已是 4 位、`0002` 实际是空操作——判断这是否会在“从旧库升级”的场景出错（旧库是 2 位时 `0002` 是否正确改列）。

### 4.2 P0 约束（迁移 `0003`）

1. 每条约束的取值是否有依据（fixture、代码、设计文档），有没有会拒绝合法业务流转的值，或漏掉 fixture 里实际出现的值。
2. SQLite 分支用 `CAST(col AS REAL)` 比较 TEXT 金额：判断精度与边界（例如 `0.00`、极小正数）是否可靠。
3. `EXCLUDE USING gist`：只约束 `status = 'active'`、闭区间 `[]`。实测：两个生效租约首尾同一天是否被拒（是否符合业务语义）；`end_date` 为空时的行为；草案租约与生效租约重叠是否允许。
4. `downgrade` 是否删净全部约束；`btree_gist` 扩展不删除是否合理。

### 4.3 只读数据库角色（`roles.py`）

1. 授权范围：只有业务表 `SELECT`？序列、函数、`alembic_version`、其它 schema 呢？`ALTER DEFAULT PRIVILEGES` 只对**执行它的角色**之后建的表生效——判断这是否与“迁移账号建表”的实际部署方式一致。
2. PG 16 的 `public` schema 默认权限下，只读角色能否 `CREATE TABLE`、`CREATE TEMP TABLE`、调用有副作用的函数（例如 `pg_advisory_lock`、`set_config`）？哪些算问题、哪些可接受。
3. 角色名校验与密码处理（dollar-quote、`exec_driver_sql`、`RoleCreationError` 不带 SQL / 不留异常链）是否有绕过；密码是否会出现在任何日志、异常、`pg_stat_activity` 之外的地方。
4. `drop_readonly_role` 是否回收干净（角色拥有对象、默认权限残留时能否删除）。

### 4.4 CLI `--backend postgresql`

1. 连接串只从 `COMMERCIAL_DB_URL` 读取；任何错误路径（连不上、库未迁移、权限不足）都不把连接串 / 密码写进 stdout、stderr、报告。
2. 用**只读角色**连接跑一次 `investigate`，结果与 `--backend sqlite` 一致（Claude Code 复核时实测一致）；与 `--backend fixture` 的差异是否只有“待审批减免草案”（12 表没有草案表）。
3. `_postgres_repository_seam` 临时替换 `bootstrap.build_sqlite_repository`：判断风险（并发、异常时是否恢复、`investigation_demo` 改动后静默失效），以及有没有因此把 PG 运行误标成 sqlite 的地方。

### 4.5 测试有效性

1. 36 个 PG 测试有没有空断言、恒真断言、只在 SQLite 路径上断言的情况；每个测试类是否自己建 / 清库、不依赖执行顺序、不留残余（跑完检查 `pg_roles` 与表）。
2. 在仓库外副本里**独立设计并执行至少 5 项变异**（不要只重做复核者做过的），例如：`after_begin` 跳过第二个事务、`UnitPrice` 改回 2 位、删掉一条 CHECK、EXCLUDE 改成开区间、只读角色多授 `INSERT`、CLI 把连接串写进报告元数据。每项写结果。
3. 复核者补的两个测试（`test_readonly_role_has_no_elevated_attributes`、`test_role_creation_failure_never_leaks_password` 里的 `__cause__` / traceback 断言）请单独审一遍。

### 4.6 文档与证据

1. 库迁移到 head 后自己运行 `dump_schema.py`，与 `schema_pg.txt` 对比（注意 Windows 下 stdout 可能是 CRLF）；运行后把库回退到 base。
2. `database_design.md` 的“实现对照”是否准确：12 表 vs 14 表、精简差异、已验证 / 未验证约束、RLS 等是否如实。
3. 各文档对 Task 035 的状态是否一致（“已实施并自检，待独立复查；未推送”），工作包 3 有没有被写成“已验收”。
4. 任何文件里有没有真实连接串、密码。

## 5. 输出

你的最终回复就是报告正文（由调度脚本保存到 `docs/reviews/2026-11-23_task035_independent_review.md`），参照 [`2026-11-23_task033_independent_review.md`](../reviews/2026-11-23_task033_independent_review.md) 的格式：

1. 头部：复查日期、复查者（模型名）、依据、代码基线（HEAD 与 `git status` 核对）、环境（PG 版本，不写连接串）、复查方式、是否调用付费接口。
2. **结论**：`通过` / `有条件通过` / `不通过`，一句话理由。只读边界可被绕过写入、项目隔离失效、金额精度丢失、连接串或密码泄露，都是`不通过`。
3. 独立验证结果表（与 §3 自报数字对比）。
4. 逐项对照 §4 与你自己发现的问题，分级：**P1** 安全边界突破 / 数据错误；**P2** 与任务单不符、测试没覆盖所声称的行为；**P3** 文档、可维护性、边界说明。每条给复现步骤或 `文件:行号`。
5. 变异测试表。
6. 通过条件与返修建议（不要动手修改）；本轮限制。不要声称最终验收通过。
