# 任务单 035A：PostgreSQL 实机——数据层正确性修复与 PG 测试套件

- 编写：2026-11-23，Claude Code。由 `scripts/dev_loop/` 执行（编码方 DeepSeek，审查方 Claude）。
- 背景：路线图 P0 工作包 3“PostgreSQL 实机与数据边界验收”。数据层（`backend/app/db/`、`backend/migrations/`）此前只在 SQLite 上验证过。Task 035 拆为 035A（本任务：正确性修复 + PG 测试套件）、035B（约束、只读角色、CLI 接 PG）、035C（12/14 表清点与文档归档）。
- **本任务只改第 1 节列出的文件。**

## 0. 已确认的事实（Claude Code 用真实 PostgreSQL 16.16 探测得到，不必重新核实）

- 环境：Docker 容器 `cpma-pg-dev`（`postgres:16`）正在运行，只绑定 `127.0.0.1:55432`。连接串已放在环境变量 **`COMMERCIAL_PG_TEST_URL`**（形如 `postgresql+psycopg://postgres:...@127.0.0.1:55432/cpma`）；驱动 `psycopg==3.3.8` 已安装。**不要运行 `docker` 或 `pip install`**；不要把连接串或密码写进任何文件。
- `alembic upgrade head` / `downgrade base` 在 PG 上能跑通，12 张业务表都建出来了；PG 上目前**没有任何 CHECK 约束**（035B 处理）。
- **问题 1（阻断）**：`app/db/seed.py::seed_from_fixture` 在 PG 上失败——`buildings` 插入违反 `buildings_project_id_fkey`。原因：模型没有定义 `relationship`，SQLAlchemy 无法按外键排插入顺序；SQLite 默认不检查外键，所以一直没暴露。
- **问题 2（安全边界）**：`app/db/session.py::_enforce_read_only` 在 PG 上执行 `SET TRANSACTION READ ONLY`，它**只对当前事务有效**。实测：只读会话 `rollback()` 之后，同一个 Session 的新事务里 `UPDATE` 成功。SQLite 的 `PRAGMA query_only` 是连接级的，所以 SQLite 测试测不出来。
- **问题 3（展示错误）**：时间列是 `DateTime(timezone=True)`。PG 返回 UTC：fixture 工单 `reported_at = 2026-07-12T13:20:00+08:00`，PG 读回 `2026-07-12T05:20:00+00:00`（同一时刻，但展示给用户会差 8 小时）。
- **问题 4（精度）**：`unit_price`（`lease_charge_rules`、`invoice_items`）和 `quantity` 用的是 `Money`（2 位小数并 `quantize(0.01)`），fixture 单价是 4 位（如 `132.3000`）。两种方言都会被截成 `132.30`。
- 读写差异：数据库模型不保存 `leases.signing_date`、`referenced_document_ids` 等少数 fixture 字段——这是 12 表精简设计的已知差异，**本任务不补**，035C 清点时登记。
- 现有 SQLite 等价性测试在 `backend/tests/test_database_layer.py`，比较的是**选定字段**（金额、核销、工单等），可作为 PG 测试的参照。

## 1. 只新增 / 修改这些文件

| 文件 | 内容 |
|---|---|
| `backend/app/db/seed.py` | 修问题 1：按父 → 子顺序落库（例如每张表 `flush()` 一次，或按 `Base.metadata.sorted_tables` 顺序插入）；SQLite 行为不变 |
| `backend/app/db/session.py` | 修问题 2、3（见 §2） |
| `backend/app/db/models.py` | 修问题 4：新增 4 位小数的单价 / 数量类型（例如 `UnitPrice`，PG 为 `NUMERIC(14,4)`，SQLite 为 TEXT），用于 `unit_price` 与 `quantity`；`Money` 保持 2 位不变 |
| `backend/migrations/versions/0002_unit_price_precision.py` | 新迁移：用**显式 `op.alter_column`**（不能再用 `create_all`）把上述列改为 4 位；`downgrade` 改回；SQLite 上用 `batch_alter_table` 或确认 TEXT 无需改 |
| `backend/app/db/bootstrap.py` | 只在需要复用“建库 + seed + 只读仓库”逻辑时做最小改动（例如抽出一个接受 engine 的函数供 PG 测试用）；`build_sqlite_repository` 行为不变 |
| `backend/tests/test_postgres_layer.py` | 新增 PG 测试套件（见 §3） |
| `backend/tests/test_database_layer.py` | 只允许**追加**与问题 1–4 相关的 SQLite 侧断言（例如单价 4 位），不删改原有用例 |

其余文件一字不改（包括 `repository.py` 的查询逻辑、工具层、评测）。

## 2. 要求

### 2.1 只读闸门（问题 2）

- PG 上的只读必须对**会话的整个生命周期**有效，而不只是第一个事务：例如在 Session 的 `after_begin` 事件里每个事务都执行 `SET TRANSACTION READ ONLY`，或者对只读连接执行 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`。选一种并在注释里写清理由；`enforce_read_only` 的公开签名不变。
- SQLite 行为不变（`PRAGMA query_only = ON`）。
- 测试必须覆盖：只读会话在 `rollback()` 之后、`commit()` 之后的新事务里写入仍被拒绝；被拒后会话仍可继续读。

### 2.2 时区（问题 3）

- 数据库读出的时间要与 fixture 等价：同一时刻、**同一 UTC 偏移（+08:00）**。做法二选一并写明理由：PG 连接上 `SET TIME ZONE 'Asia/Shanghai'`（对只读连接和 seed 连接都生效），或在读取时统一转换为数据集时区。不要把时区写死在多个地方——放一个常量。
- SQLite 行为不变。

### 2.3 单价精度（问题 4）

- 4 位小数单价在两种方言上都原样保存和读回（`132.3000` → `Decimal("132.3000")`）；金额（`amount` 等）仍是 2 位。
- 迁移 `0002` 在 PG 上实际改列类型；`alembic upgrade head` 与 `downgrade base` 在两种方言上都能跑通。

## 3. PG 测试套件（`test_postgres_layer.py`）

- **只在设置了 `COMMERCIAL_PG_TEST_URL` 时运行**，未设置时整个模块 `skipTest` 并写明原因（默认回归不依赖 PG）。每个测试类自己建 / 清库（`downgrade base` → `upgrade head` → seed），不依赖执行顺序，不留残余。
- 至少覆盖：
  1. 迁移：`upgrade head` 建出 12 张业务表 + `alembic_version`；`downgrade base` 后业务表全部删除；`unit_price` / `quantity` 列在 PG 上是 `NUMERIC(14,4)`，金额列是 `NUMERIC(14,2)`。
  2. seed：各表行数与 fixture 一致（同 `test_database_layer.TestSeedAndSchema`）。
  3. 等价性：与 `test_database_layer.TestEquivalenceWithFixture` 相同的选定字段在 PG 上与 fixture 一致；**额外比较工单 `reported_at` / `resolved_at`、付款 `paid_at` 的 ISO 字符串完全相同**（含 `+08:00`）；单价 4 位与 fixture 字符串一致。
  4. 只读：首个事务写入被拒；`rollback()` 后、`commit()` 后的新事务写入仍被拒；被拒后仍能读。
  5. 项目隔离：越权项目 → `project_scope_denied`；未知租约 → `record_not_found`。
  6. 金额类型：仓库返回的金额是 `Decimal`，不是 `float`。
  7. 端到端：用 PG 上的只读仓库装配工具注册表，跑一次与 `test_database_layer.TestToolsBoundToDatabase` 相同的调查，关键数字（欠费、差额）与 fixture 路径一致。

## 4. 验收标准

- 只改第 1 节列出的文件；`test_database_layer.py` 原有用例原样保留并通过。
- 全量回归通过（调度脚本会在设置了 `COMMERCIAL_PG_TEST_URL` 的环境下运行，所以 PG 测试**会真正执行**）；新测试没有恒真断言；除“未设置 URL”外不得 `skip`。
- 不在任何文件里写入连接串、密码；新文件 UTF-8、LF。
- 总结里写明：只读闸门、时区各选了哪种做法及理由；`0002` 在两种方言上的实际行为；PG 测试实际运行了多少个（不是 skip）。
