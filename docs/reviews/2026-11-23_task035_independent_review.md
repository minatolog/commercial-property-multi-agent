# Task 035（PostgreSQL 实机验证）独立复查

- **复查日期**：2026-11-23（Asia/Shanghai）。
- **复查者**：DeepSeek（独立复查会话，模型标识 `deepseek-flash`；本会话未参与 035A/035B/035C 的实施）。
- **复查依据**：[复查 Prompt](../handoffs/REVIEW_TASK035_PROMPT.md)、[035A](../handoffs/DEV_LOOP_TASK035A_PG_CORRECTNESS.md) / [035B](../handoffs/DEV_LOOP_TASK035B_PG_CONSTRAINTS_ROLE.md) / [035C](../handoffs/DEV_LOOP_TASK035C_PG_DOCS.md) 任务单、[Task 035 归档](../prompts/02_database/2026-11-23_035_postgresql_verification.md)、实际代码 / 测试 / 证据。
- **代码基线**：`HEAD = d0061ca9aaeabf38320a8d1be0e671ba96f8dee1`（`5586ef3` 之后只多本复查 Prompt 的提交）；`git status --porcelain` 只有允许排除的 `?? .claude/`；`git diff --stat 34a51a2 5586ef3` 为 26 个文件、3927 行新增、61 行删除，与 Prompt 所述一致。
- **环境**：本机 Docker 容器 `cpma-pg-dev` 的 PostgreSQL **16.16**；连接串只从 `COMMERCIAL_PG_TEST_URL` 读取，本报告不写出。Python 3.11.18、SQLAlchemy 2.1.8、psycopg 3.3.8、Alembic 1.20.1。
- **方式**：不采信自报数字。独立复跑全量回归（设置 / 不设置 PG URL）、36 个 PG 测试、契约自检、`check`、`dump_schema.py`；在真实 PG 上逐项构造 seed、只读绕过、时区、精度、约束、角色、CLI 反例；在仓库外副本做 10 项变异测试；逐项核对文档、证据与状态措辞。
- **付费接口**：**未调用**（未使用 `--planner-provider deepseek` / `--model-provider deepseek`）；未运行 `docker`；未执行 `pip install`。

## 结论

**不通过。**

存储层、ORM、迁移的 4 位精度确实修好了，36 个 PG 测试、700 全量回归、70 项契约、schema 证据也与自报一致；但**业务只读仓库仍把 `unit_price` / `quantity` 经 `_money` 量化到 2 位，并用这两个 2 位值计算 `expected_rent` / `rent_variance`**（`backend/app/db/repository.py:245,392,421-422`）。我用真实 4 位单价 `126.3456` 复现：数据库仓库给出 `expected_rent=15162.00`、`rent_variance=-0.53`，正确应为 `15161.47` / `0.00`；fixture 仓库按 4 位计算是正确的。按复查 Prompt §5“金额精度丢失 → 不通过”，本项阻断。其余为 P2 / P3。

> 需要说明的是：`repository.py` 被 035A / 035B 任务单明确列为“不改”的文件，实施者没有越界；这是**任务单验收口径与测试设计的遗漏**。但按交付状态，工具层（`lease.lookup` / `billing.statement.read` / `billing.arrears.calculate`）看到的仍是 2 位单价/数量，真实 4 位费率会算错金额，因此仍判不通过，需追加一个小任务修读路径与测试。

## 1. 独立验证结果

| 验证项 | 我实际运行 / 看到的结果 | 与自报对比 |
|---|---|---|
| 全量回归（设置 `COMMERCIAL_PG_TEST_URL`） | `python -X utf8 -m unittest discover -s backend/tests -t backend -p "test_*.py"` → **Ran 700 tests in 48.570s，OK (skipped=1)** | 自报 700 / skipped=1，**一致** |
| 全量回归（不设置 PG URL） | 用 Python 脚本移除环境变量后运行 → **Ran 700 tests in 42.039s，OK (skipped=37)** | 自报 700 / skipped=37，**一致**；36 个 PG 测试确实被跳过 |
| PG 套件 | `-m unittest discover ... -p "test_postgres_layer.py"` → **Ran 36 tests in 6.206s，OK**，0 skip | 自报 36 实际执行，**一致** |
| 契约自检 | `backend/tests/smoke_agent_contracts.py` → **全部通过：70 项检查** | 自报 70，**一致** |
| `check` | `app.cli.main(["check"])` → **exit 0**，输出正常 JSON | 自报 exit 0，**一致** |
| `dump_schema.py` | 迁移到 head 后运行，输出与 `schema_pg.txt` 归一化 CRLF 后**完全相同（263 行，equal=True）**；39 CHECK + 1 EXCLUDE；运行后已 `downgrade base` | 自报一致，**确认** |
| seed（问题 1） | 全新 head 库上用原始 `seed_from_fixture` 落库成功；12 表行数 2/2/3/3/3/4/3/6/3/3/4/3 与 fixture 一致 | 确认 |
| 精度（问题 4，存储与 ORM） | PG：`unit_price`/`quantity` 为 `NUMERIC(14,4)`，金额为 `NUMERIC(14,2)`；ORM 读回 `132.3000` / `120.0000` / `15876.00`；直接插入 `1.2345` / `2.3456` 原样往返；`0002` 在“0001 遗留 2 位库”上确实扩回 4 位 | 存储/ORM 层**确认**；业务读路径**不成立**（见 P1-1） |
| 时区（问题 3） | `create_engine_for` 连接 `SHOW TIME ZONE = Asia/Shanghai`，`reported_at = 2026-07-12T13:20:00+08:00`、`paid_at = 2026-08-20T09:05:00+08:00`；连接池复用两次仍为 Asia/Shanghai；直接 `create_engine` 仍为 `Etc/UTC` / `+00:00` | 确认 |
| 只读闸门（问题 2） | 首事务、`rollback()` 后、`commit()` 后、`begin_nested()` SAVEPOINT、`session.connection()` 直接写、`SET SESSION CHARACTERISTICS ... READ WRITE` 后新事务写：**全部被 PG 拒绝**；被拒后仍可读 | 确认 |
| 租期 EXCLUDE | 生效租约重叠、首尾同一天（`start == existing.end_date`）、单日区间、把 active 改期到重叠区、draft→active：**均被拒绝**；次日开始、不同商铺（自身租期外）、draft / terminated 重叠：**允许**；`end_date NULL` 被 NOT NULL 拒绝 | 确认 |
| 只读角色 | 只授予 12 张业务表 `SELECT`（`information_schema.role_table_grants` 核对）；`alembic_version` 不可读；`INSERT/UPDATE/DELETE/TRUNCATE/CREATE TABLE/CREATE SCHEMA/SET ROLE` 均拒绝；`CREATE TEMP TABLE`、`pg_advisory_lock`、`set_config` 允许；`ALTER DEFAULT PRIVILEGES` 对同账号后建的表生效；删除后 `pg_roles`、`pg_default_acl` 均无残留 | 确认；边界见 P3 |
| CLI `--backend postgresql` | 用只读角色跑 `investigate`：`verdict`、`authoritative_amounts`、`findings`、`conflicts`、`missing_information`、`failures`、`agent_results`、`planner` 等 13 个键与 `--backend sqlite` **完全一致**；与 `--backend fixture` 的唯一差异是 `proposed_draft` 及其“未配置审批通道”警告；输出无连接串 / 密码 / 用户名 / host；`backend=postgresql`；PG 输出中无 `sqlite` 字样 | 与自报“只有草案差异”一致 |
| CLI 错误路径 | 未设置 / 非 postgresql URL / 连接拒绝 / 数据库不存在：**exit 2，stdout 为空，stderr 无连接串或密码**；`--variant` 与 PG 同用：exit 2；**库未迁移 / 无权限**：未捕获异常、traceback、exit 1（无连接串 / 密码，见 P3-2） | 泄漏检查确认；错误处理有缺口 |
| SQLite 0003 | 在 0002 已 seed 的 SQLite 库上升级 0003：6 条 invoice_items / 3 条 leases 数据保留，外键与唯一索引保留；降回 0002 数据仍保留 | 确认 |
| 最终清理 | PG `public` 只剩 `alembic_version`；无 `ro_*` 角色；无其它会话；扩展为 `btree_gist` + `plpgsql`（0003 故意不删，见 P3）；仓库 `git status` 只有 `.claude/` | 完成 |

## 2. 逐项对照 §4 与发现的问题

### 2.1 四个实机问题

**4.1.1 seed 外键顺序：通过。** `seed.py` 按父 → 子逐表 `flush()`，依赖覆盖 `projects → buildings → units → tenants → leases → lease_charge_rules → invoices → invoice_items → payments → payment_allocations → work_orders → documents`；我在全新 PG head 库上直接调用原始 `seed_from_fixture`，12 张表全部落库、行数与 fixture 一致。SQLite 侧也新增了 `PRAGMA foreign_keys = ON` 的回归（`test_database_layer.py:395-429`）。

**4.1.2 只读闸门：核心行为通过；显式 SET / 原生连接可绕过（P3，符合设计）。**
- 已实测：首事务、rollback 后、commit 后、SAVEPOINT（`begin_nested`）、`session.connection()` 直接 INSERT、`SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE` 后新事务写，均被 `SET TRANSACTION READ ONLY` 拒绝。
- `session.execute(text("SET TRANSACTION READ WRITE"))` 之后再写：**写入成功**（owner 账号）。`session.connection().exec_driver_sql("COMMIT")` 后直接 INSERT 也能绕过 Session 的 `after_begin`。这两条都是“故意绕过”，不是误写；只读角色下同样的 `SET TRANSACTION READ WRITE` + INSERT 被权限拒绝（已实测）。
- 业务路径未发现绕过：`DatabaseRepository` 只持有 `Session`（`repository.py:59-60`），工具层只经仓库；`bootstrap`、`roles.py`、迁移走 engine 的是装配 / 运维路径，不是业务查询。
- 结论：会话级只读按 035B §0 定位为“误写保护”，真正的权限边界是只读角色；这不构成 P1。但若运维把 `COMMERCIAL_DB_URL` 指向建表账号而非只读角色，CLI 就只有这一层可被显式 SET 绕过的保护。README §6.3 / §6.4 已要求用只读角色，建议在 CLI 启动时检查当前角色是否为只读（或至少打印角色属性）。

**4.1.3 时区：通过。** `create_engine_for` 的 `connect_args={"options": "-c timezone=Asia/Shanghai"}` 对 seed 与只读连接都生效，连接池复用两次仍为 Asia/Shanghai；直接 `create_engine` 读出 `05:20+00:00`。清点 PG engine 创建点：
- `migrations/env.py:44-48` 用 `engine_from_config`，但迁移不读取业务时间列，不影响业务输出；
- `roles.py` 不创建 engine，使用调用方 engine（测试 / README 均传 `create_engine_for`）；
- `docs/reviews/task035_evidence/dump_schema.py:89` 用原始 `create_engine`，只导出 schema；
- 测试的 PG 连接均用 `create_engine_for`；SQLite 用原始 engine 无时区问题。
- CLI 经 `build_postgres_repository` → `create_engine_for`，实测工单时间带 `+08:00`（P3：如果以后有人在别处直接 `create_engine` 连 PG 读业务时间，会退回 UTC；README 已提示）。

**4.1.4 单价精度：存储 / ORM 通过，业务读路径失败（P1-1、P2-1）。**
- PG 列类型、ORM 往返、`0002` 对旧 2 位库的扩列都实测正确。
- **但 `DatabaseRepository` 的读路径仍用 `_money()` 量化到 0.01**：
  - `repository.py:392`：`"unit_price": str(_money(rule.unit_price))`；
  - `repository.py:421-422`：`quantity` / `unit_price` 同样 `_money`；
  - `repository.py:245`：`expected = (_money(item.quantity) * _money(rule.unit_price)).quantize(0.01)`。
- 复现：
  1. PG head + seed → `repo.lease_facts(...)` 的 `rule_xh_a301_rent_2027.unit_price` 为 `"132.30"`；fixture 仓库为 `"132.3000"`。
  2. `repo.statement(...)` 的明细为 `("120.00", "126.00")`；fixture 仓库为 `("120.0000", "126.0000")`。
  3. 把 `rule_xh_a301_rent_2026.unit_price` 改为 `126.3456`、`itm_inv09_rent` 改为 `quantity=120.0000, unit_price=126.3456, amount=15161.47` → DB 仓库 `expected_rent=15162.00`、`rent_variance=-0.53`；正确应为 `15161.47` / `0.00`。fixture 仓库的 `money()` 不做 2 位量化（`fixtures/repository.py:49-54,257`），因此会算对。
  4. 工具层直接使用该输出：`fixture_tools.py:312` `LeaseRuleOut(unit_price=Decimal(rule["unit_price"]))`、`:401-402` 明细同样取仓库字符串；`lease.lookup` / `billing.statement.read` / `billing.arrears.calculate` 都会看到 2 位值。
- 这不是 fixture 当前数值能暴露的问题（fixture 的 4 位恰好以两个 0 结尾），但它是任务目标“4 位单价原样保存和读回”的一部分；实施者被任务单禁止改 `repository.py`，因此应作为**任务单遗漏**追加返修，而不是判实施者越界。

### 2.2 P0 约束（迁移 `0003`）

**4.2.1 取值依据：通过。** 我逐项对照 fixture、设计 §6 / §9 与代码：
- 枚举：`projects.status`、`units.physical_status`、`tenants.status`、`leases.status`、`billing_cycle`、`charge_type`、`calculation_method`、`period_unit`、`invoices.status`、`invoice_items.charge_type`、`payments.status`、`payment_method`、`work_orders.category/priority/status`、`documents.doc_type/document_status` 的取值均覆盖设计 / fixture 合法值，没有拒绝正常流转。fixture 实际值（`active`、`issued`、`confirmed/reversed`、`bank_transfer/cheque`、`closed/in_progress`、`hvac/electrical`、`normal/high`、`lease_contract/attachment`、`signed` 等）全部通过 seed。
- 金额 / 面积 / 数量：`units.area_sqm`、`chargeable_area_sqm`、`deposit_amount`、`charge_rules.amount/unit_price`、`invoice_items.amount/quantity/unit_price`、`payments.amount`、`allocations.amount` 的下限均与 fixture / 设计一致；`invoice_items.amount` 仅 `other_fee` 允许负数（设计 §6.9），实测 `other_fee` 负数可写入。
- 日期：`leases.end_date >= start_date`、`invoices.period_end >= period_start`、`due_date >= issue_date`、`effective_to >= effective_from`、`resolved_at IS NULL OR resolved_at >= reported_at`、`resolved/closed` 必须有 `resolved_at` 均符合设计；`>=` 比设计 `>` 更宽松（不会拒绝合法数据，P3 文档差异）。
- 遗留差异（P3）：设计 §6.7 的 `is_rent_free` 金额为 0 检查、§6.12 的“无商铺必须有 location_note”、§6.8/§6.10 的 void/reversed 原因检查等未实现；`documents.document_status` 的实现值（`signed/draft/draft_unsigned`）在设计里没有对应字段。这些已在 `database_design.md §17.2/§17.3` 部分登记，但 `is_rent_free` 等未逐条列出。
- 已有库升级风险（P3）：`ADD CHECK` 会校验存量数据；若真实库存在枚举外状态、零金额收款、存量重叠租约，`0003` 会失败。本次只在 fixture 数据上验证。

**4.2.2 SQLite `CAST(col AS REAL)`：常规值可靠；畸形 TEXT 有边界（P3）。** 我在 0002 已 seed 的 SQLite 库上升级 0003 后实测：
- `amount='0.00'` 对 `>= 0` 约束允许（正确，`invoice_items` 是“非负”）；`payments/allocations` 的 `> 0` 对 `0.00` 拒绝（测试覆盖）；`quantity='0.0000'` 拒绝；`amount='-0.001'` 拒绝。
- 边界：`CAST('abc' AS REAL) = 0`，因此 `invoice_items.amount='abc'` 在 `charge_type='rent'` 下会**通过** `>= 0` 检查（PG 的 NUMERIC 会先报非法输入）；`'0.001'`、`'1e3'` 也能通过 SQLite 检查（PG NUMERIC(14,2) 会把 0.001 round 成 0.00 并拒绝 `>0`）。`quantity='0.0000001'` 也能通过 SQLite 的 `<> 0`。这些只可能来自绕过 TypeDecorator 的原始 SQL；应用写入经 `Money` / `UnitPrice` 量化为合法十进制文本，因此不构成当前业务缺陷，但“SQLite 约束是严格校验器”的说法不成立。
- 币种 SQLite 用 `length + upper`：非 ASCII 三字符（如 `人民币`）会通过，PG 正则拒绝；时间列是带偏移文本，混用 `+00:00` / `+08:00` 时 `resolved_at >= reported_at` 的字典序比较不等价于绝对时刻比较（应用 seed 固定 +08:00）。均为测试方言边界，P3。

**4.2.3 EXCLUDE：核心语义通过；边界闭区间已实测。**
- `EXCLUDE USING gist (unit_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status = 'active')` 定义与 `schema_pg.txt:258` 一致。
- 实测：active 重叠拒绝；首尾同一天（`start == 2027-12-31`，existing `2025-01-01..2027-12-31`）**拒绝**；次日开始（2028-01-01）**允许**；draft / terminated 重叠允许；`end_date NULL` 被 NOT NULL 拒绝（不是 EXCLUDE）；把 active 租约改到重叠区、把 draft 改成 active 覆盖已占区间，均被拒绝。
- 结论：闭区间意味着“上一租约最后一天 = 下一租约第一天”视为重叠，语义上把 `end_date` 当含当日；这与“含首尾日”的业务解释一致，但与设计 §15.2 的 `[)` 半开区间不同。该选择已在迁移注释和 §17.3 说明，可接受；但**没有测试守护这个边界**（变异 M4b 证明改成 `[)` 后 36 个测试全部通过，P3-1）。
- P3：`leases.end_date` / `start_date` 只有 `>=` 检查，没有“同日零天租约”的业务规则；当前允许 `start == end`（我的单日测试被 EXCLUDE 拒绝是因为落在现有区间内，不是日期规则拒绝）。

**4.2.4 downgrade 与 btree_gist：通过。** 实测 `0003` downgrade 后 39 条 CHECK + 1 条 EXCLUDE 全部删除，`0002` / `0001` 仍可继续 `downgrade base`；重新 upgrade 后约束回来。`btree_gist` 不删除是合理的（可能被其它对象共用），但意味着 `downgrade base` 后测试库仍保留该扩展；报告的自报“库回到 base”应理解为“表/约束回到 base”，不是“完全无扩展残留”。P3。

### 2.3 只读数据库角色

**4.3.1 授权范围：通过，有运维注意事项。**
- `information_schema.role_table_grants` 实测只有 12 张业务表的 `SELECT`；无 INSERT/UPDATE/DELETE；`alembic_version` 不可读（P3：运维无法用只读角色查 schema 版本，不是安全问题）。
- 没有序列（表用字符串主键），未授予任何序列权限；函数默认 `EXECUTE` 给 PUBLIC，角色可调用函数；其它 schema 无 USAGE；只授予当前数据库 CONNECT 和 public schema USAGE。
- `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO role` 只对**执行该语句的角色**之后创建的表生效。测试中 owner 建 `zz_default_probe` 后角色可读；若生产用另一个迁移账号建表，则不会自动授权。README §6.3 写“含将来由同一账号新建的表”，措辞准确；建议部署时用迁移账号执行 `create_readonly_role`，或补 `ALTER DEFAULT PRIVILEGES FOR ROLE <migration_role>`。P3-8。

**4.3.2 PG 16 public schema 与函数副作用：可接受。**
- `CREATE TABLE` / `CREATE SCHEMA` / `CREATE DATABASE` / `SET ROLE postgres` 均拒绝；`CREATE TEMP TABLE` 允许（PG 默认给 PUBLIC `TEMP`），`pg_advisory_lock`、`set_config` 允许；`TRUNCATE` / `INSERT` / `UPDATE` / `DELETE` 拒绝。
- 判断：临时表是会话级、不落业务表；advisory lock / set_config 只能影响自己的会话（或与使用同一 advisory key 的进程协调），当前业务不使用 advisory lock；函数无 SECURITY DEFINER 安装。可接受。真正的行级隔离仍缺 RLS（文档已写未实现）。

**4.3.3 角色名 / 密码处理：主路径安全；两处残留（P3）。**
- 角色名只允许 `[a-z_][a-z0-9_]*` 且 ≤63 字节；`x; DROP ROLE y` 等全部拒绝；标识符再经方言 quote。
- 密码含 `:x`、`%`、`'`、`\` 时能建角色并登录（实测）；`CREATE ROLE` 失败抛 `RoleCreationError`，消息不含密码 / SQL，`__cause__ is None`、`__suppress_context__ == True`，渲染 traceback 不含密码 / `CREATE ROLE`。
- **P3-3a**：`raise ... from None` 只抑制显示，**没有清空 `__context__`**。我用只读角色触发失败，`e.__context__` 的 `str()` 仍是：
  `... [SQL: CREATE ROLE ro_new_... LOGIN PASSWORD $ro_...$P@ss:word%%quote'back\slash$ro_...$ ...]`。密码中的 `%` 被写成 `%%`，所以对原密码做子串检查会误判“未泄漏”，但密码本身仍在异常对象里。默认 traceback 不打印它（复核者补的测试断言正确）；但如果上层把 `__context__` 序列化 / 记录，就会泄漏。建议在 `except` 块外再抛，或显式 `error.__context__ = None`，并补 `__context__` 断言。
- **P3-3b**：密码在 `CREATE ROLE` DDL 里；`engine.echo=True`、`log_statement=all` 或执行期间的 `pg_stat_activity.query` 都会看到。PG 不能参数化 DDL，这是结构性限制；应文档化，或在函数里拒绝 `echo=True` 的 engine。
- **P3-3c**：`roles.py` 模块 docstring 第 18-19 行说“密码先由服务器 `quote_literal()` 转义”，但实现用的是随机 dollar-quote（`roles.py:48-64`）；文档与代码不一致。

**4.3.4 drop 清理：会话关闭后干净；有活会话时可能阻塞（P3-4）。**
- 无活会话时：`REVOKE ...` + `ALTER DEFAULT PRIVILEGES ... REVOKE` + `DROP ROLE` 执行后 `pg_roles` 无角色、`pg_default_acl` 无残留（实测）。
- 我保留一个只读角色会话并创建 TEMP TABLE，再调用 `drop_readonly_role`：`DROP ROLE` **无限等待**（脚本 180s 超时），直到我终止该会话后才成功。函数没有 `lock_timeout` / `statement_timeout`；运维脚本在池化连接未释放时可能挂住。建议加超时或在文档里要求先关闭所有该角色会话。
- 角色若拥有其它 schema 的持久对象或第三方授予的 membership，`DROP ROLE` 可能失败；当前函数只回收自己授予的权限，未处理这些情况。P3。

### 2.4 CLI `--backend postgresql`

**4.4.1 连接串来源与错误泄漏：基本通过；未迁移 / 无权限路径未捕获（P3-2）。**
- 连接串只从 `COMMERCIAL_DB_URL` 读取；命令行没有明文选项；未设置 → exit 2，stdout 空，提示环境变量；非 postgresql URL → exit 2；连接拒绝 / 数据库不存在 → exit 2，stderr 只有异常类型，无连接串 / 密码 / 用户名 / host。
- 实际子进程（`python -m app.cli investigate --backend postgresql`）指向未迁移库（`postgres` 库）或一个无任何授权的登录角色：**exit 1，77-81 行 Python traceback**。traceback 含 SQL 文本与 SQLAlchemy 提示，但**不含连接串 / 密码 / 用户名 / host**。任务 035B 只要求“不泄漏”，这一条满足；但从 CLI 的“2=用法或配置错误”契约看，库未迁移 / 权限不足应给出干净的错误与退出码 2，而不是 traceback。建议在 `run_investigation` 外层或 `main` 捕获 `SQLAlchemyError`，输出 `[error] ...` 并返回 2。
- 测试只覆盖“未设置 URL”，没有覆盖连接失败 / 权限失败的泄漏（变异 M6b 证明把 URL 写进错误消息后 36 个测试仍全过，P3-2）。

**4.4.2 PG vs sqlite vs fixture：通过。** 用只读角色跑 `investigate`，与 `--backend sqlite` 的 `verdict / authoritative_amounts / agent_results / findings / conflicts / missing_information / failures / route / revision / requires_human_review / planner / backend` 全部一致；与 fixture 只差 `proposed_draft` 及其“未配置审批通道”警告（12 表无草案表，符合 035C §1.1 登记）。输出无连接串 / 密码 / host；PG 输出无 `sqlite` 字样。**但注意**：这个比较不覆盖 `lease.lookup` 的规则单价（见 P1-1），所以“等价”只对选定字段成立。

**4.4.3 `_postgres_repository_seam`：当前可用；有结构性风险（P3-5）。**
- 我验证：seam 内 `bootstrap.build_sqlite_repository` 被替换；seam 体抛异常后 `finally` 恢复原工厂；`investigation_demo` 确实在 `:344-346` 延迟导入，没有模块级缓存；PG 报告没有把 `backend` 写成 sqlite。
- 风险：① 它改的是进程全局属性，**不是线程安全的**；两个并发 CLI 装配可能互相覆盖，后者失败路径可能让 `investigation_demo` 取到真正的内存 SQLite 仓库，最终报告仍写 `backend=postgresql`。当前 CLI 单线程，没有并发调用。② 如果以后 `investigation_demo` 改成模块级导入 / 缓存 / 直接接收仓库，seam 会**静默失效**，没有任何断言。建议至少加 `assert bundle.repository is repository`（或比较对象身份）并在文档中登记；长期让 `build_investigation_bundle` 直接接受仓库参数。

### 2.5 测试有效性

**4.5.1 36 个 PG 测试：整体有效；精度测试与边界测试有缺口。**
- 36 个测试全部实际执行，0 skip；每个测试类 `setUpClass` 自己 `downgrade base → upgrade head → seed`，`tearDownClass` 清库；我跑完后 `pg_roles` 无 `ro_*`、public 只剩 `alembic_version`，无残留。
- 未发现恒真断言；`test_invalid_rows_are_rejected` 的 39 个 case 与 39 条 CHECK 一一对应，且断言错误消息里出现期望约束名；`test_constraint_names_are_installed` 用集合差断言；`test_amounts_are_decimal_not_float` 遍历实际金额；`TestReadonlyRolePostgres` 的建 / 删角色有 finally。
- **P2-1（测试有效性）**：`test_unit_price_keeps_four_decimals`（`test_postgres_layer.py:320-343`）与 SQLite 的 `test_unit_price_and_quantity_keep_four_decimals`（`test_database_layer.py:430`）都直接读 ORM / 模型，不经过 `DatabaseRepository`；fixture 的 `132.3000` / `120.0000` 末两位是 0，因此“存储 2 位、显示补 0”和“真正 4 位”在断言上不可区分。我的变异 M2（`UnitPrice` 类型改回 `Numeric(14,2)`）和 M2b（`process_bind_param` 量化回 0.01）都**存活**（36/36 OK）。要覆盖声称的行为，应使用非零末位（如 `132.3456`）并断言 `lease_facts` / `statement` / 工具输出的字符串，而不是只断言 ORM 的 `str()`。
- **P3-1**：`TestLeaseExclusionPostgres` 没有“首尾同一天 / 次日”边界；变异 M4b（`[]` → `[)`）存活。
- **P3-2**：`TestCliPostgres` 没有连接失败 / 权限失败的泄漏测试；变异 M6b 存活。
- `TestCliPostgres.setUpClass` 先 `super().setUpClass()` 再建角色；若建角色失败，`tearDownClass` 不会执行，可能留下已迁移的库（当前无失败）。P3 测试健壮性。

**4.5.2 变异测试：见 §3。**

**4.5.3 复核者补的两个测试：**
- `test_readonly_role_has_no_elevated_attributes`（`test_postgres_layer.py:1141-1165`）：查询 `pg_roles` 的 super/createdb/createrole/bypassrls/inherit/canlogin/replication 七项，断言只允许登录；有效。它不覆盖“被授予特权预定义角色（如 `pg_read_all_data`）”或 `rolconnlimit`，但当前实现没有这些授予，P3。
- `test_role_creation_failure_never_leaks_password`（`:1096-1139`）：覆盖消息、`PASSWORD` / `CREATE ROLE` 子串、`__suppress_context__`、`__cause__ is None`、完整 traceback；默认渲染路径确实安全。**未覆盖 `__context__`**，而 `from None` 并不清空它（见 P3-3a），所以测试 docstring 的“异常消息/链不出现密码或 SQL”对“链”言过其实。

### 2.6 文档与证据

**4.6.1 schema 证据：通过。** 我在 head 库上运行 `dump_schema.py`，与 `schema_pg.txt` 归一化 CRLF 后完全一致（263 行），39 CHECK + 1 EXCLUDE；随后已回退 base。

**4.6.2 `database_design.md` §17：大体准确，有一处与 P1 相关的美化。**
- 12/14 表清点、缺失字段（`leases.signing_date` / `referenced_document_ids` / `approval_drafts`）、`lease_units` / `agent_runs` 未实现、RLS 未启用、部分唯一索引 / 复合外键 / 生成列未实现：与代码和我的检查一致。
- **P3-6**：§17.1 / §17.3 说“单价与数量 `NUMERIC(14,4)`（Task 035A 修正精度后）”，只对**表结构**成立；业务读路径仍 2 位（P1-1）。§17.3 说闭区间“与 fixture / 仓库含首尾日语义一致”，但仓库里没有租约区间查询，`_rent_rule` 的 `effective_to >= period_start` 只证明费用规则含首尾日，不能直接证明租约 EXCLUDE；措辞应更精确。
- §17.2 的 `leases` / `lease_charge_rules` “设计为 `>`、实现为 `>=`”、`payment_allocations` 全量唯一、`documents` 的 `document_status` 差异等均准确。

**4.6.3 状态一致性：大体一致；035C 提交状态陈旧（P3-6）。**
- `docs/README.md`、`CURRENT_BASELINE.md`、路线图、README 均写“已实施并自检，待独立复查；未推送”，工作包 3 写“PG 实机验证已完成第一版（待独立复查）”，没有写“已验收”。**一致。**
- 但 `docs/prompts/02_database/2026-11-23_035_postgresql_verification.md:9,77,228,234` 与 `docs/development_logs/development_log.md:15` 仍写“**035C 未提交**（改动留在工作区）”，而 035C 实际已提交为 `5586ef3`。这是交付时的事实错误，P3。
- `docs/issues/issue_log.md` PG-4 状态写“已修复并自检”，只对存储层成立；读路径仍有 2 位截断（P1-1），应改为“存储已修、读路径待修”或追加遗留项。

**4.6.4 连接串 / 密码：通过。** 全树 grep 发现的 `postgresql+psycopg://...` 只有 README 的 `<本地测试密码>` / `<强密码>` 占位符和任务单的 `postgres:...@` 省略号；证据文件无 URL / 密码 / `PASSWORD`；本报告也不写连接串。

## 3. 变异测试表

在仓库外副本 `backend/` + `docs/evaluation/fixtures/` 上修改后运行 `test_postgres_layer.py`；每次运行后恢复原文件，最终 baseline 重新跑 **36 tests OK**。

| # | 变异 | 结果 | 说明 |
|---|---|---|---|
| M1 | `after_begin` 只允许第一个事务只读（`session.info` 计数后跳过） | **被抓住**：2 failures（`test_transaction_after_rollback_still_rejects_write`、`..._after_commit_...`） | 问题 2 的回归有守护 |
| M2 | `UnitPrice.impl` / `load_dialect_impl` 改回 `Numeric(14,2)` | **存活**：36/36 OK | 0002 仍把列扩到 4 位；fixture 末两位为 0，测试不可区分（P2-1） |
| M2b | `UnitPrice.process_bind_param` 量化回 `Decimal("0.01")` | **存活**：36/36 OK | 同上；测试只断言 `str()` 格式，不验证非零末位（P2-1） |
| M3 | 从 `_CHECKS` 删除 `ck_payments_amount_positive_p0` | **被抓住**：3 failures（约束名集合、payments.amount 违规、downgrade 期望） | 约束清单与违规写入有守护 |
| M4a | EXCLUDE 去掉 `WHERE (status = 'active')` | **被抓住**：1 error（draft 重叠被拒） | 状态谓词有守护 |
| M4b | EXCLUDE 的 `daterange(..., '[]')` 改为 `'[)'` | **存活**：36/36 OK | 没有首尾同日 / 次日边界测试（P3-1） |
| M5 | 只读角色额外授予 `INSERT, UPDATE, DELETE` | **被抓住**：4 failures（INSERT / UPDATE / DELETE / 整体写入测试） | 权限边界有守护 |
| M6a | CLI 报告元数据加入 `COMMERCIAL_DB_URL` | **被抓住**：1 failure（`test_investigate_matches_fixture_and_reports_backend` 的泄漏断言） | 成功路径泄漏有守护 |
| M6b | CLI 连接失败消息加入 `url` | **存活**：36/36 OK | 没有连接失败 / 权限失败测试（P3-2） |
| M7 | `create_engine_for` 去掉 PG 时区 `connect_args` | **被抓住**：9 failures（时区、工单 / 收款时间、CLI offset、角色测试中的时区） | 时区修复有守护 |

补充直接实验（不属于变异表）：`fixed_amount` 租金规则（`calculation_method='fixed_amount', unit_price=NULL`，约束允许）会让 `statement` 抛 `decimal.InvalidOperation`（`repository.py:245` 对 `None` 调 `_money`）。这是既有逻辑与 fixture 不覆盖的组合，P3；建议要么在 repository 支持固定额租金，要么在文档中明确当前只支持 `per_sqm`。

## 4. 通过条件与返修建议

本轮**不修改任何文件**；以下返修建议供后续任务单使用。

**阻断项（必须关闭才能改判通过）**

1. **P1-1：把 4 位精度贯通到业务读路径。**
   - `DatabaseRepository._rule_dict` 的 `unit_price`、`_item_dict` 的 `quantity` / `unit_price` 改用 4 位量化（例如新增 `_unit_price()` / `_quantity()`，`Decimal.quantize(0.0001)`，输出 4 位字符串）；`amount` 仍 2 位。
   - `statement` 的 `expected = quantity * unit_price` 使用 4 位值，只在最终金额 / 差额上 `quantize(0.01)`。
   - 补仓库级测试：在 fixture 或直接更新的数据中使用**非零末位**的 4 位值（如 `132.3456` / `120.1234`），在 PG 与 SQLite 上断言 `lease_facts` / `statement` / `lease.lookup` 输出与 fixture 路径一致，且 `expected_rent` / `rent_variance` 正确。
   - 更新 `issue_log.md` PG-4、README §6 / 归档 §5.4、`database_design.md §17`，把“已修好”限定为存储 / ORM，并登记读路径返修完成后的证据。

**应关闭的测试缺口（P2 / 重要 P3）**

2. **P2-1**：把精度测试从 ORM / `str()` 提升到仓库 / 工具输出，并使用非零末位 4 位值；否则 M2 / M2b 这类回归仍然不可见。
3. **P3-1**：补 LEASE EXCLUDE 边界测试：首尾同日（应拒绝）、次日（应允许）、draft / terminated（应允许）、更新路径（active→重叠应拒绝），把 `[]` 的选择固化下来。
4. **P3-2**：补 CLI 连接失败 / 库未迁移 / 无权限的测试；建议在 `main` / 调查外层捕获 `SQLAlchemyError`，输出 `[error] ...` 并 exit 2，同时断言 stdout / stderr / 报告无连接串 / 密码。当前 traceback 不泄漏，但不可作为约定。
5. **P3-3a**：让 `RoleCreationError` 不保留含 SQL / 密码的 `__context__`（在 `except` 块外抛出，或显式清空），并把测试从 `__cause__` 扩展到 `__context__` / 日志输出；文档化 `log_statement` / `pg_stat_activity` / `echo=True` 的暴露面。

**建议的 P3 收尾**

6. `drop_readonly_role` 加 `lock_timeout` / `statement_timeout` 或在文档中要求先关闭角色会话；处理角色拥有对象 / 第三方 membership 的失败原因。
7. `_postgres_repository_seam` 加“注入的仓库就是 bundle.repository”的身份断言；长期让 `build_investigation_bundle` 直接接受 repository 参数，去掉全局打补丁。
8. 文档事务：修正 `roles.py` docstring 的 `quote_literal()` 说法（实际是 dollar-quote）；把 035C 的“未提交”改成 `5586ef3`（或写“归档时未提交，后提交为 5586ef3”）；说明 `btree_gist` 在 `downgrade base` 后仍保留；把 `ALTER DEFAULT PRIVILEGES` 的“同一账号”部署前提写进 README / 归档；把 SQLite `CAST('abc')=0`、非 ASCII 币种、混用时间偏移列为测试方言限制。
9. 防御性：SQLite 迁移测试在 `setUpClass` 临时移除 `COMMERCIAL_DB_URL`（或在测试内 patch），避免开发者按 README 导出 `COMMERCIAL_DB_URL` 后跑全量测试时，`migrations/env.py` 把 SQLite 迁移指向 PG（`migrations/env.py:22-27`；README 已警告，但测试层可以自保）。
10. 预存数据升级：在归档 / README 写明 `0003` 会校验存量行，含枚举外状态 / 零金额收款 / 重叠 active 租约的真实库需先清洗；`CREATE EXTENSION` 需要权限。
11. `fixed_amount` 租金规则当前会让 `statement` 抛 `decimal.InvalidOperation`（`repository.py:245`）；建议明确当前仅支持 `per_sqm` 租金，或补固定额分支与测试。

## 5. 本轮限制

- 只在单个本机 PostgreSQL 16.16 容器上验证；未验证其它 PG 版本、多实例并发、连接池故障切换、生产部署、备份恢复、RLS。RLS / 多实例 / 生产部署按任务单明确未做，不因本轮通过与否改变。
- 未测试真实模型驱动的 `--model-provider deepseek` / 规划模型路径；未调用任何付费接口。`--with-approval` 的 PG 组合未单独跑；只验证了 `investigate` 默认路径。
- 实验在仓库外副本 / 临时 SQLite 文件上做；仓库内未修改、未提交、未推送、未切分支、未 stash；`git status` 最终只有允许的 `.claude/`。PG 实验库最终回到 `alembic downgrade base`（`public` 只剩 `alembic_version`），无临时角色；`btree_gist` / `plpgsql` 扩展保留。
- P1-1 是用直接更新规则 / 明细后在仓库层复现的；fixture 当前值恰好不暴露错误，因此没有生产数据佐证。该结论不依赖自报数字。
- 本轮是独立复查，不是最终验收；即使后续关闭 P1 / P2，也需要返修后的复查确认。
