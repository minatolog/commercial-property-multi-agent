# Task 035 返修确认复查（DeepSeek，经 dev_review）

- **复查日期**：2026-11-23（Asia/Shanghai）。
- **复查者**：DeepSeek（独立复查会话，模型标识 `deepseek-flash`；未参与 035A/035B/035C 与返修）。
- **复查依据**：[复查 Prompt](../handoffs/REVIEW_TASK035_REPAIR_PROMPT.md)、[上一轮复查](2026-11-23_task035_independent_review.md)、返修提交 `127e503`、[035 归档 §12](../prompts/02_database/2026-11-23_035_postgresql_verification.md)、实际代码 / 测试 / 证据。
- **代码基线**：`HEAD = 5ab4b45`（`127e503` 之后只多本复查 Prompt 的提交）；`git status --porcelain` 只有 `?? .claude/`；`git diff --stat 9fb3935 127e503` 为 15 个文件，与 Prompt 所述一致。
- **环境**：本机 PostgreSQL **16.16**；Python 3.11.18、SQLAlchemy 2.1.8、psycopg 3.3.8、Alembic 1.20.1。连接串只从 `COMMERCIAL_PG_TEST_URL` 读取，本报告不写连接串或密码。
- **方式**：不采信自报数字。独立复跑两种环境的全量回归、PG 套件、契约、`check`；在 SQLite 与 PG 上用**末位非零**的 4 位值重做 P1-1；在仓库外副本做 8 项变异；在真实 PG 上验证角色异常链、echo 绕过、删角色锁超时、CLI 失败路径；复跑离线 heldout 并逐题对比；核对文档与证据。
- **付费接口**：**未调用**（没有 `--planner-provider deepseek` / `--model-provider deepseek`）；未运行 `docker`；未 `pip install`；仓库内未改任何文件。

## 结论

**有条件通过（返修本身通过；不等于最终验收）。**

| 条件 | 结论 |
|---|---|
| P1-1 单价 / 数量读路径 2 位 | **关闭**。SQLite 与 PG 的仓库输出、`expected_rent` / `rent_variance`、`lease.lookup` / `billing.statement.read` 工具输出均为 4 位；上一轮的 `126.3456` 反例现给出正确结果 |
| P2-1 精度测试测不出截断 | **关闭**。新增的仓库级测试（PG 与 SQLite）在 M2b（写入量化回 2 位）和“读路径回到 2 位”两种变异下都失败；期望值 `15177.06` 可独立复算 |
| P3-1 EXCLUDE 无首尾边界测试 | **关闭**。M4b（`[]`→`[)`）被同首日用例抓到 |
| P3-2 CLI 无失败路径测试 | **关闭**。URL 泄漏与“不拦数据库错误”两种变异均被抓到；非数据库异常仍原样抛出；尝试“0002”后确认它本身不是失败路径 |
| P3-3a `__context__` 残留 | **关闭**。真实触发失败后 `__cause__` / `__context__` 均为 `None`，消息与 traceback 均无密码 / SQL |
| P3-3b DDL 密码暴露面 | **部分关闭**。`echo=True` 被拒绝且不留角色；但 `echo=False` + `sqlalchemy.engine` logger 调到 INFO 仍会把含密码的 `CREATE ROLE` 完整打印出来，文档未提这条 |
| P3-3c docstring 与实现不符 | **关闭**（模块 docstring 已改为 dollar-quote）；`RoleCreationError` 类 docstring 仍写 `raise ... from None`，属残留 |
| P3 收尾（锁超时 / seam / 迁移测试隔离） | **关闭**。三项均实测有效 |
| P3-6 / 文档 | **基本关闭**。精度、闭区间、035C 提交状态、部署前提已更正；仍有 1 处旧日志与若干文档残留（见 §3） |

**新发现**：一项**既有 P2**（`DatabaseRepository.arrears()` 与 `billing.arrears.calculate` 的契约不符，上一轮未覆盖，`9fb3935` 即存在，不是本次返修引入）；以及若干 P3 文档 / 暴露面残留。

**条件**（满足后可视为 Task 035 返修确认完成，仍不等于最终验收）：
1. 把“DB 仓库 `arrears()` 缺 `invoices/payments/allocations`，导致 `billing.arrears.calculate` 在数据库后端抛 `KeyError`”立项修复，或在文档中明确该工具暂不支持 DB 后端并加回归测试；
2. 关闭 §3 列出的 P3 残留（Python 日志暴露面、`RoleCreationError` docstring、开发日志 035C 状态、M2b 失败数、SQLite 方言限制）。

## 1. 独立复跑的数字

| 项 | 返修自报 | 我实际运行 / 看到 |
|---|---|---|
| 全量回归（设置 PG URL） | 707 OK（skipped=1） | `python -X utf8 -m unittest discover -s backend/tests -t backend -p "test_*.py"` → **Ran 707 tests in 41.085s，OK (skipped=1)** |
| 全量回归（不设置 PG URL） | 707 OK（skipped=43） | 子进程移除变量后运行 → **Ran 707 tests in 34.825s，OK (skipped=43)** |
| PG 套件 | 42，全部执行 | `... -p "test_postgres_layer.py"` → **Ran 42 tests in 6.787s，OK**，0 skip |
| 契约 / `check` | 70 / exit 0 | `backend/tests/smoke_agent_contracts.py` → **全部通过：70 项检查**；`cli.main(["check"])` → **EXIT 0** |
| 证据文件 | `repair_unittest.txt` 707、`repair_pg_unittest.txt` 42 | 两文件分别以 `Ran 707 ... OK (skipped=1)`、`Ran 42 ... OK` 结尾，与实测一致；未见连接串 / 密码 |

数字差异：707−700=+7，正好是新增的 1 个 SQLite 仓库测试 + 1 个 PG 仓库测试 + 3 个 EXCLUDE 边界测试 + 1 个 CLI 失败测试 + 1 个 echo 测试；默认 skipped 43−37=+6，对应 PG 套件 36→42。

## 2. 逐条确认

### P1-1：单价 / 数量读路径（**关闭**）

**做了什么**：在 SQLite 与 PG 上分别用修改过的 fixture 复现上一轮反例（`unit_price=126.3456`、`quantity=120.0000`、三条租金明细 `amount=15161.47`），以及返修测试的反例（`120.1234 × 126.3456`）；调用 `DatabaseRepository.lease_facts` / `statement` / `arrears`，再调用 `lease.lookup`、`billing.statement.read`。PG 上还直接查了列类型和原始值。

**看到**：
- SQLite 与 PG 的上一轮反例：规则 `unit_price="126.3456"`，三条租金明细 `quantity="120.0000"` / `unit_price="126.3456"`，`expected_rent="15161.47"`、`rent_variance="0.00"`、`rent_variance_total="0.00"`；fixture 路径相同。上一轮的 `15162.00 / -0.53` 未再出现。
- 返修测试反例：`120.1234 × 126.3456 = 15177.06304704 → 15177.06`，三条明细均 `expected_rent="15177.06"`，`rent_variance` 分别 `-57.06 / -57.06 / 698.94`，`rent_variance_total="584.82"`，与 fixture 路径逐项一致；PG 原始值 `quantity=120.1234`、`unit_price=126.3456`，列类型为 `numeric(14,4)`。
- 工具层：`lease.lookup` 的规则单价 `"126.3456"`；`billing.statement.read` 的明细 `quantity="120.1234"` / `unit_price="126.3456"`、`expected_rent="15177.06"`；金额仍 2 位。
- 默认 fixture：2026 / 2027 租金规则读回 `"126.0000"` / `"132.3000"`，明细 `"120.0000"` / `"132.3000"`，与 fixture 一致；`rent_variance_total="756.00"`。
- `repository.py` 中单价 / 数量已无 `_money`（`_unit()` 位于 `repository.py:52-60`，用于 `:256`、`:403`、`:432-433`）；`_money` 仍用于 `amount`、`deposit_amount`、`area_sqm` / `chargeable_area_sqm`，与 `NUMERIC(14,2)` 的面积 / 金额设计一致，不是单价或数量。

**结论**：关闭。

### P2-1：精度测试有效性（**关闭**）

**做了什么**：把 `backend/` 与 `docs/evaluation/fixtures/` 复制到仓库外副本，在副本上做变异，运行 `TestTask035ADataLayerFixesOnSqlite`、`TestFourDecimalReadPath`、`TestEquivalenceWithFixturePostgres`、`TestFourDecimalReadPathPostgres`。

**看到**：
- **M2b（`UnitPrice.process_bind_param` 量化回 0.01）**：**2 failures**，即 `TestFourDecimalReadPath` 与 `TestFourDecimalReadPathPostgres`；旧的两个只读 ORM 测试仍通过，因为 `process_result_value` 会再补回 4 位，`132.3000` 这类末位为 0 的值无法区分。归档 §12 写“M2b → 4 失败”，与实测不符（应为 2），但“新增测试能抓到 M2b”这一结论成立。
- **读路径回到 2 位（`_unit()` 的 `quantize` 改回 0.01）**：**恰好 2 failures**，即两个新增仓库级测试；fixture 末位为 0 的旧等价性测试仍通过，说明这 2 个测试确实是新增守护。
- 期望值独立性：`120.1234 × 126.3456 = 15177.06304704`，量化到分是 `15177.06`；若先量化到 2 位则是 `120.12 × 126.35 = 15177.16`。测试里的 `Decimal("15177.06")` 是硬编码锚点，不依赖被测实现；同时另有与 `FixtureRepository` 的逐项比较。

**结论**：关闭（测试有效）；仅修正自报的失败数量。

### P3-1：EXCLUDE 首尾边界（**关闭**）

**做了什么**：在副本把 `0003` 的 `daterange(..., '[]')` 改为 `'[)'`，运行 `TestLeaseExclusionPostgres`。

**看到**：**6 tests，1 failure**，失败的是 `test_same_day_handover_is_rejected`；新增的“次日允许”“草案改 active 被拒”在变异下仍通过。说明 `[]` 的选择已被测试守护。

**结论**：关闭。

### P3-2：CLI 失败路径（**关闭**）

**做了什么**：在副本分别做两种变异：(a) 把 `COMMERCIAL_DB_URL` 拼进错误消息；(b) 让 `main` 不再拦截 `SQLAlchemyError`（`if True: raise`）。运行 `test_database_failures_exit_2_without_leaking_connection_info`。另在原代码上：用错误密码、`0002` 库、非数据库异常分别探测。

**看到**：
- 变异 (a)：**2 个子用例失败**（“库未迁移”“无表权限”），断言 URL 出现在输出中，测试确实能发现连接串泄漏。
- 变异 (b)：**2 个子用例 error**（traceback、exit 1），测试确实要求 `SQLAlchemyError` 被收敛。
- “认证失败”子用例走的是**既有**装配期 `except (SQLAlchemyError, OSError)`（`cli.py:935-942`，转成 `UsageError`），不是新的 `main` 分支；因此新分支实际由“库未迁移 / 无权限”两类子用例覆盖。三类都得到 exit 2、无 traceback、无 URL / 密码。
- 尝试 Prompt 举例的“库存在但 `alembic_version` 停在 `0002`”：迁移到 `0002` 并 seed 后运行 `investigate --backend postgresql` → **exit 0**，因为业务表在 `0001` 已建、查询可正常完成。该情形不是失败路径，无需新分支处理。
- 非数据库异常：monkeypatch `run_investigation` 抛 `RuntimeError` → 原样抛出 `RuntimeError: probe-non-db`，没有被新分支吞掉。

**结论**：关闭。

### P3-3a：`RoleCreationError` 的异常链（**关闭**）

**做了什么**：迁移到 head，建一个无 `CREATEROLE` 的临时登录角色，用它调用 `create_readonly_role` 触发 `CREATE ROLE` 权限失败；检查异常对象与完整 traceback，随后删除临时角色。

**看到**：`RoleCreationError`；`__cause__ is None`、`__context__ is None`、`__suppress_context__ is False`；消息与 `traceback.format_exception` 都不含密码、不含 `CREATE ROLE`；数据库无残留角色。新测试补的 `assertIsNone(__context__)` 也在变异“把 raise 放回 except 内 + from None”下失败（1 failure）。

**结论**：关闭。

### P3-3b / 3c：DDL 密码暴露面与 docstring（**部分关闭 / 关闭**）

**做了什么**：手工验证 `echo=True` 的 engine 被拒绝；再用 `echo=False` 的 engine，把 `logging.getLogger("sqlalchemy.engine")` 调到 INFO 并挂 handler，调用 `create_readonly_role`，检查捕获日志。

**看到**：
- `echo=True` → `ValueError`，且 `pg_roles` 无任何 `ro_echo_*` 角色。
- **绕过真实存在**：`engine.echo` 为 False 时，Python 日志仍完整打印了 `CREATE ROLE ... LOGIN PASSWORD $ro_...$<密码>$ro_...$ ...`（44 行日志中同时出现 `CREATE ROLE` 与密码）。`roles.py` 与 README 只写了 `echo=True`、`pg_stat_activity`、服务器 `log_statement`，没有写“应用把 `sqlalchemy.engine` logger 调到 INFO/DEBUG”这条；`engine.echo` 之外还有 `Connection` 等入口（函数类型标注为 `Engine`，未强制检查）。属于部分关闭的 P3。
- docstring：模块级已改为“随机标签 dollar-quote”，与 `_password_literal` 实现一致；但 `RoleCreationError` 类 docstring（`roles.py:44-50`）仍写“以 `raise ... from None` 抛出”，与“在 `except` 外抛出”不符。

**结论**：echo 拒绝与模块 docstring 关闭；日志绕过与类 docstring 记为 P3 残留。

### P3 收尾（**关闭**）

- **删除角色锁超时**：保留一个角色会话并在未提交事务里 `CREATE TEMP TABLE`，调用 `drop_readonly_role` → **5.01s 后 `OperationalError: canceling statement due to lock timeout`**，不再无限等待；无争用时删除仍正常。附注：若临时表已提交，`DROP ROLE` 会立即报依赖错误（既有行为），不会等锁。
- **seam 断言**：用 mock 让装配返回“另一个 repository”，`_investigation_assembly` 抛出 `RuntimeError`（“没有使用注入的 PG 仓库”）；返回同一对象时正常进入。断言确实能发现“bundle 没用注入的仓库”。
- **`TestMigrations` 隔离**：把 `COMMERCIAL_DB_URL` 设为 PG 测试库后运行该类 → 迁移日志为 `SQLiteImpl`，**1 test OK**，没有再被指向 PG。

### P3-6 / 文档（**基本关闭，有残留**）

- `database_design.md §17.1` 已写“存储精度 035A 修正；业务读路径在 035 复查返修后同为 4 位”，与实测一致；`§17.3` 的闭区间措辞已改为“首尾同日视为重叠（已有测试）；仓库没有租约区间查询，闭区间是业务选择”，准确。
- 归档 §5.4 加了“只覆盖存储层”的复查更正；§12 记录返修与验证，状态写“待复查确认”；README / `CURRENT_BASELINE` / 路线图 / 问题日志均为“已返修，待复查确认 / 待确认”，**没有写成“已通过 / 已验收”**。
- README §6.3 / §6.4 补齐了 `ALTER DEFAULT PRIVILEGES` 同一账号前提、`btree_gist` 保留、`0003` 校验存量行、`fixed_amount` 未支持；`0003` 的 `downgrade` 确实保留 `btree_gist`（我最后看到扩展为 `btree_gist` + `plpgsql`）。
- 残留：`docs/development_logs/development_log.md:22`（原始 035 条目）仍写“035C 未提交、未推送”，与归档 `:9` 的 `5586ef3` 不一致；归档 §12 的 M2b 失败数（4）与实际（2）不符；上一轮建议的 SQLite 方言限制（`CAST('abc')=0`、非 ASCII 币种、混用时间偏移）仍未见文档登记；问题日志的新条目只列了 P1-1 / P2-1 / P3-3a，未列 P3-1 / P3-2 / P3-3b 等（完整性不足，不算错误）。

## 3. 新发现

### P2（既有，不是本次返修引入）：DB 仓库 `arrears()` 与工具契约不符

`backend/app/db/repository.py:297-306` 的 `DatabaseRepository.arrears()` 只返回 `lease / 各总额 / outstanding_invoice_ids / rent_variance_total`，没有 `invoices`、`payments`、`allocations`；而 `backend/app/tools/fixture_tools.py:508` 的 `BillingArrearsTool.invoke()` 直接遍历 `arrears["invoices"]`，`FixtureRepository.arrears()`（`fixtures/repository.py:306-317`）则包含这些键。

我在 SQLite 4 位 fixture 上直接调用 `BillingArrearsTool`：**`KeyError: 'invoices'`**；PG 仓库共用同一方法。经 `ToolExecutor` 时会被转成 `INTERNAL_ERROR`（`executor.py:264-269`），因此声明为 `billing.arrears_check` 的能力在数据库后端会失败。该问题在 `9fb3935` 已存在（返修未触碰 `arrears()`），上一轮复查只比较了仓库方法、没有真正调用 arrears 工具，所以未发现。

**影响**：当前 CLI `investigate` 只调用 `billing.statement`，MCP / demo 使用 fixture 仓库，因此是**潜在**缺陷，不阻断本次返修；但“数据库仓库与 fixture 仓库同契约”的说法对 arrears 不成立，应在 Task 035 最终验收前登记并处理，或明确“DB 后端暂不支持 arrears 工具”并加测试。

### P3 残留

1. `echo=True` 之外，应用级 `sqlalchemy.engine` logger 调到 INFO/DEBUG 仍会打印含密码的 DDL；文档需登记该暴露面（或创建角色时临时压低 logger 级别）。
2. `RoleCreationError` 类 docstring 仍写 `from None`。
3. `development_log.md:22` 的“035C 未提交”未同步。
4. 归档 §12 的 M2b“4 失败”应为 2 失败。
5. SQLite 方言限制（`CAST('abc')=0`、非 ASCII 币种、混用时间偏移）未按上一轮建议文档化。
6. `fixed_amount` 租金仍未实现：`_unit(rule.unit_price)` 对 `None` 会抛 `decimal.InvalidOperation`，目前只在 README 说明“未支持”。可接受为已知限制，但不是修复。

## 4. 变异与实验记录

| # | 变异 / 实验 | 结果 |
|---|---|---|
| M2b | `UnitPrice.process_bind_param` 量化回 0.01 | 2 failures（两个新增仓库测试）；旧 ORM 测试因读取时再量化而存活 |
| M-read | `_unit()` 量化回 0.01 | 2 failures（两个新增仓库测试） |
| M4b | EXCLUDE `daterange(..., '[]')` → `'[)'` | 1 failure（首尾同日） |
| M-role | `raise RoleCreationError(...) from None` 放回 `except` 内 | 1 failure（`__context__` 断言） |
| M6b-a | CLI 错误消息拼入 `COMMERCIAL_DB_URL` | 2 个子用例失败（URL 泄漏） |
| M6b-b | `main` 不再拦截 `SQLAlchemyError` | 2 个子用例 error（traceback / exit 1） |
| — | `echo=False` + `sqlalchemy.engine` logger INFO | 完整 `CREATE ROLE`（含密码）被打印 |
| — | 角色有未提交 TEMP TABLE 时删除角色 | 5.01s 后 lock timeout，正常抛错 |
| — | seam 返回不同 repository | `RuntimeError`，断言生效 |
| — | `COMMERCIAL_DB_URL` 指向 PG 时跑 `TestMigrations` | SQLite 迁移，1 test OK |
| — | CLI 指向 `0002` 库 | exit 0，不是失败路径 |

## 5. 回归与副作用

- **全量回归、PG 套件、契约、`check`**：见 §1，全部与自报一致。
- **离线 heldout**：`evaluate --split heldout --out <实验目录>` 产生 32 行 A/B/C 报告；与 `docs/evaluation/reports/20261121T093757_*` 逐题比较（忽略 `latency_ms` / `duration_ms` / `bindings.code_commit` 等运行元数据），A / B / C **各 32 题逐行完全一致，0 个差异**；A 20/30、B 21/30、C 24/30 不变。
- **三条数据路径的调查结果**：`investigate --backend sqlite` 与 `--backend postgresql` 的 JSON 除 `thread_id` 与各工具 `duration_ms` 外完全相同；与 `--backend fixture` 相比，除同类运行差异外只剩 `approval_status`（`unavailable` vs `not_required`）及已排除的 `proposed_draft`（DB 无草案表，既有已知差异），关键金额、结论、冲突、缺失信息一致。
- **连接串 / 密码扫描**：改动的文档与证据文件中只有 README 的 `<本地测试密码>` / `<强密码>` 占位符；新证据文件无 URL / 密码 / `PASSWORD`。
- **工作区与测试库清理**：最终 `git status --porcelain` 仍只有 `?? .claude/`；`data/` 未见本轮写入；PG 测试库 `public` 只剩 `alembic_version`（无版本行）、无 `ro_*` 角色、无其它会话，保留 `btree_gist` / `plpgsql`（与文档一致）。

## 6. 未处理的上一轮建议

| 建议 | 状态 | 是否可接受 |
|---|---|---|
| `fixed_amount` 租金 | 只写进 README；代码仍会抛 `InvalidOperation` | 可接受为本轮范围外，但仍是潜在缺陷，需后续任务 |
| seam 只加断言、未重构 | 已加身份断言并验证有效；全局打补丁仍在 | 可接受；长期建议让 `build_investigation_bundle` 直接接收 repository |
| SQLite 方言限制文档化 | 未登记 `CAST('abc')=0` / 非 ASCII 币种 / 混用偏移 | P3 残留，建议补 |
| 035C 提交状态 | 归档已改，开发日志旧条目未改 | P3 残留 |
| 删除角色时角色拥有持久对象 / 第三方 membership | 未处理；未提交 TEMP TABLE 的情形现在会立即报依赖错误 | 可接受（文档已要求先断开会话） |

## 7. 通过条件

1. **P2（既有）**：修复 `DatabaseRepository.arrears()` 补齐 `invoices/payments/allocations`，或明确 `billing.arrears.calculate` 暂不支持数据库后端并加“应失败”的回归测试；在 Task 035 最终验收前完成。
2. **P3 残留**：登记 Python 日志暴露面；更正 `RoleCreationError` docstring、`development_log.md:22`、归档 M2b 失败数；补充 SQLite 方言限制说明。

满足以上条件后，本轮返修可作为 Task 035 的确认结论；**仍不等于最终验收**（真实模型 heldout、RLS、多实例并发、生产部署均未做）。

## 8. 本轮限制

- 只在单个本机 PostgreSQL 16.16 上验证；未验证其它 PG 版本、RLS、多实例并发、连接池故障切换、备份恢复、生产部署。
- 未调用任何付费模型接口；未跑真实模型 / Supervisor 规划路径；`--with-approval` 的 PG 组合未单独验证。
- 变异实验在仓库外副本（`backend/` + `docs/evaluation/fixtures/`）进行；副本缺 `docs/evaluation/documents`，复制环境里一个无关 RAG 测试会失败，未计入变异结论；目标测试类均在副本上单独运行。
- P2（arrears）是通过直接调用工具 + 阅读 `ToolExecutor` 确认的，没有通过完整 Agent 运行复现；当前产品路径未触达该能力，因此定为潜在缺陷。
- 日志泄露实验依赖本机 SQLAlchemy / psycopg 的日志行为；结论是“文档与守卫没有覆盖这条常见途径”，不是“所有版本都必然如此”。
- 本轮是返修确认复查，不是最终验收；报告中的所有结论均来自本轮实际运行，未采信实施者自报数字。
