# 任务单 035B：PostgreSQL 实机——P0 约束、只读数据库角色、CLI 接 PG

- 编写：2026-11-23，Claude Code。由 `scripts/dev_loop/` 执行。
- 前置：035A 已完成并提交（seed 顺序、会话级只读、时区、单价精度已修；`backend/tests/test_postgres_layer.py` 已有 PG 测试套件）。**先完整阅读 035A 的改动与 [035A 任务单](DEV_LOOP_TASK035A_PG_CORRECTNESS.md) §0 的环境说明**（`COMMERCIAL_PG_TEST_URL`、不运行 docker / pip、不写连接串）。
- 设计依据：[`docs/architecture/database_design.md`](../architecture/database_design.md)（14 表长期设计；本任务只做其中 P0 必要约束，不补表）。

## 0. 背景

- PG 上目前没有任何 CHECK 约束；“同一商铺租期不得冲突”也没有数据库约束。
- 只读目前只靠会话级 `READ ONLY` 事务——这是“误写保护”，不是权限边界：连接用的是建表账号，任何人拿到这个连接都能 `SET TRANSACTION READ WRITE`。真正的边界是**只有 SELECT 权限的数据库角色**。
- CLI 的 `--backend` 只有 `fixture` / `sqlite`，PG 还没有接入任何业务入口。

## 1. 只新增 / 修改这些文件

| 文件 | 内容 |
|---|---|
| `backend/migrations/versions/0003_p0_constraints.py` | P0 约束（见 §2.1），`downgrade` 全部删除 |
| `backend/app/db/models.py` | 只在需要让 ORM 与迁移保持一致时，给对应列加同名约束声明；不改列类型 |
| `backend/app/db/roles.py` | 新增：创建 / 删除只读角色的函数（见 §2.2） |
| `backend/app/db/bootstrap.py` | 新增“按 URL 构建只读 PG 仓库”的函数，供 CLI 使用；SQLite 路径不变 |
| `backend/app/cli.py` | `--backend` 增加 `postgresql`（见 §2.3） |
| `backend/tests/test_postgres_layer.py` | **只追加**测试，不删改 035A 的用例 |
| `backend/tests/test_database_layer.py` | 只允许追加：约束在 SQLite 上的对应断言 |

其余文件一字不改。

## 2. 要求

### 2.1 P0 约束（迁移 `0003`）

先读 fixture（`backend/app/fixtures/` 下的数据文件），**fixture 里合法存在的数据不能被约束拒绝**（例如若有负数调整行，金额约束就要允许它，并在迁移注释里写明）。至少：

- 金额类（`deposit_amount`、`invoice_items.amount`、`payments.amount`、`payment_allocations.amount`、面积）：按 fixture 实际情况设下限；
- 日期区间：`leases.end_date >= start_date`；账单 `period_end >= period_start`；工单 `resolved_at` 为空或 `>= reported_at`；
- `payment_terms_days BETWEEN 0 AND 180`；币种为 3 位大写字母（PG 用正则，SQLite 用 `length` + `upper`，或只在 PG 上加并写明）；
- 状态 / 类别列：`CHECK (col IN (...))`，取值以 fixture 与现有代码里出现的值为准（不使用 PG 原生 ENUM，见设计文档 2.6）；
- **租期不冲突（PG 专属）**：同一商铺（`leases.unit_id`）在 `status` 为生效类的租约之间，`[start_date, end_date]` 不得重叠。用 `btree_gist` + `EXCLUDE USING gist`，通过 `op.execute` 手写，只在 PG 上执行；SQLite 上跳过并在注释里写明。

约束名统一前缀（例如 `ck_` / `ex_`），便于 `downgrade` 与排查。

### 2.2 只读数据库角色（`roles.py`）

- `create_readonly_role(engine, role_name, password)`：创建可登录角色，只授予业务表的 `SELECT`（含将来新表的 `ALTER DEFAULT PRIVILEGES`），**不授予** `alembic_version` 以外的任何写权限；`drop_readonly_role(...)` 回收并删除。角色名只允许 `[a-z_][a-z0-9_]*`，防止 SQL 注入；密码通过参数绑定或安全转义，不拼接进日志。
- 这是运维 / 测试用函数，不在业务路径里自动调用。

### 2.3 CLI 接 PG

- `--backend postgresql`：连接串**只**从环境变量 `COMMERCIAL_DB_URL` 读取，不接受命令行明文；未设置 → 退出码 2 并提示。连接用只读仓库（035A 的会话级只读仍然生效）。
- `ask` / `investigate` / `search` 等现有支持 `--backend` 的子命令都能用；报告元数据里如实记录 `backend=postgresql`（不要记录连接串）。
- **注意**：`backend/migrations/env.py` 会**优先**读取 `COMMERCIAL_DB_URL`，覆盖测试里设置的 URL。所以测试里设置 `COMMERCIAL_DB_URL` 只能用于子进程环境或 `mock.patch.dict(os.environ, ...)` 的局部范围，不得泄漏到其它测试（否则 `test_database_layer` 的 SQLite 迁移测试会去迁移 PG）。这一点在 035C 的文档里也要写明。

## 3. 测试（追加到 `test_postgres_layer.py`，只在设置了 `COMMERCIAL_PG_TEST_URL` 时运行）

1. 约束：对每类约束各构造一条违规写入（用建表账号的**可写**会话），断言被数据库拒绝；fixture 全量 seed 仍成功。
2. 租期不冲突：同一商铺插入与现有生效租约重叠的租约 → 被 `EXCLUDE` 拒绝；不重叠、或另一租约为非生效状态 → 允许。
3. 只读角色：用 `create_readonly_role` 建一个随机名 / 随机密码的临时角色，以它连接：能读出与 fixture 等价的数据；`INSERT` / `UPDATE` / `DELETE` / `CREATE TABLE` / `SET TRANSACTION READ WRITE` 后再写，全部被拒；测试结束删除角色。
4. CLI：设置 `COMMERCIAL_DB_URL`（指向测试库，最好用只读角色）跑一次 `investigate`，关键数字与 `--backend fixture` 一致，元数据为 `backend=postgresql`；未设置时退出码 2；stdout / 报告里没有连接串。
5. `0003` 的 `downgrade` 删除全部约束后，`0002`、`0001` 仍能继续 `downgrade base`。

## 4. 验收标准

- 只改第 1 节列出的文件；035A 的测试原样保留并通过。
- 全量回归通过（PG 测试真正执行）；新测试没有恒真断言。
- 不在任何文件里写入连接串、密码；新文件 UTF-8、LF。
- 总结里写明：每类约束的具体取值依据（引用 fixture 或代码位置）；哪些约束只在 PG 上存在。
