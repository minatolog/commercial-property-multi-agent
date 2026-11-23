# 复查 Prompt：Task 035 返修确认（只看返修改动）

- 编写：2026-11-23（Asia/Shanghai），Claude Code（返修者）。
- 给：与返修者不同的模型（由 `scripts/dev_loop/dev_review.ps1` 调用）。
- 性质：**只读复查**，只确认 [上一轮复查](../reviews/2026-11-23_task035_independent_review.md) 提出的问题是否真的关闭、返修有没有引入新问题。不重做整轮复查。
- 上一轮结论：**不通过**（P1-1 单价读路径）；P2 一项、P3 若干。

## 0. 硬性约束（与上一轮相同）

1. 不调用付费模型接口；不 `pip install`；不运行 `docker`。
2. 仓库内不改任何文件；不提交、不推送、不切分支、不 stash；不碰 `data/`。
3. PG 测试库：`COMMERCIAL_PG_TEST_URL` 已设置。可以做任何实验，但结束时删除临时角色、把库回退到 `alembic downgrade base`；报告里不写连接串或密码。
4. 不要把 `COMMERCIAL_DB_URL` 设到全局环境（`migrations/env.py` 会优先读取它）。
5. 变异实验：把 `backend/` 与 `docs/evaluation/fixtures/` 按原相对结构复制到实验目录再改。
6. Python：`D:/anacada/envs/commercial-agent/python.exe`，在 `backend/` 下运行，设置 `PYTHONUTF8=1`。

## 1. 返修范围

- 返修提交：`127e503`（复查报告本身是 `9fb3935`）。差异：`git diff 9fb3935 127e503`。
- 代码只改了 `backend/app/db/repository.py`、`backend/app/db/roles.py`、`backend/app/cli.py`；其余是测试、证据与文档。
- 返修记录：[035 归档 §12](../prompts/02_database/2026-11-23_035_postgresql_verification.md)。
- 开始前确认 `git rev-parse HEAD` 是 `127e503` 或其后只多了本 Prompt 的提交，`git status --porcelain` 除 `.claude/` 外为空。

## 2. 返修自报数字（独立复跑）

| 项 | 上一轮实测 | 返修后自报 |
|---|---|---|
| 全量回归（设置 PG URL） | 700 OK（skipped=1） | **707** OK（skipped=1） |
| 全量回归（不设置） | 700 OK（skipped=37） | **707** OK（skipped=43） |
| `tests.test_postgres_layer` | 36 | **42**，全部执行 |
| 契约 / `check` | 70 / exit 0 | 70 / exit 0 |

## 3. 逐条确认（每条写：做了什么、看到了什么、关闭 / 部分关闭 / 未关闭）

| 编号 | 上一轮问题 | 返修位置 | 请这样验证 |
|---|---|---|---|
| P1-1 | 仓库读路径把单价 / 数量量化到 2 位并参与应收计算 | `repository.py` 的 `_unit()`、`_rule_dict` / `_item_dict` / `statement` | 重做你上一轮的 `126.3456` 复现，在 SQLite 与 PG 上对比 fixture 路径；再看工具层输出（`lease.lookup`、`billing.statement.read`、`billing.arrears.calculate`）里的单价、数量、差额；检查 `repository.py` 里还有没有其它对单价 / 数量用 `_money` 的地方 |
| P2-1 | 精度测试只读 ORM、fixture 末位为 0 | `test_database_layer.TestFourDecimalReadPath`、`test_postgres_layer.TestFourDecimalReadPathPostgres` | 在副本里重做 M2b（写入量化回 2 位）与“读路径回到 2 位”，确认失败；判断测试的期望值 `15177.06` 是否独立于被测代码算出 |
| P3-1 | EXCLUDE 无首尾边界测试 | `TestLeaseExclusionPostgres` 新增三个用例 | 重做 M4b（`[]` → `[)`） |
| P3-2 | CLI 无失败路径测试 | `cli.py::main` 新增的 `SQLAlchemyError` 分支；`test_database_failures_exit_2_without_leaking_connection_info` | 重做 M6b；另外试一个测试没覆盖的失败（例如库存在但 `alembic_version` 停在 `0002`）；确认非数据库异常仍原样抛出、没有被这个分支吞掉 |
| P3-3a | `__context__` 留着原异常 | `roles.py::create_readonly_role` | 用你上一轮的方法触发失败，检查 `__cause__`、`__context__`、完整 traceback |
| P3-3b / 3c | DDL 密码暴露面；docstring 与实现不符 | `roles.py` docstring、`echo` 检查、`backend/README.md` §6.3 | 判断文档是否足够；`echo` 检查能否被绕过（例如 `engine.echo` 之外的日志途径） |
| P3 收尾 | 删除角色等锁、seam 静默失效、迁移测试受 `COMMERCIAL_DB_URL` 影响 | `drop_readonly_role` 的 `lock_timeout`；`cli.py` 的 bundle 断言；`TestMigrations.setUp` | 各自验证一次；特别是 seam 断言能否真的发现“bundle 没用注入的仓库” |
| P3-6 / 文档 | 精度、闭区间措辞过宽；035C 提交状态；部署前提 | 归档 §5.4 / §12、`database_design.md` §17、`backend/README.md`、问题日志 | 核对措辞是否准确、各文档状态是否一致（“已返修，待复查确认”），没有写成“已通过 / 已验收” |

未处理的上一轮建议请明确列出并判断是否可接受（例如 `fixed_amount` 租金只写了文档、seam 只加了断言没有重构）。

## 4. 回归与副作用

1. 复跑全量回归（两种环境）、PG 套件、契约、`check`，记录实际数字。
2. 读路径改成 4 位后，fixture / SQLite / PG 三条路径的调查结果是否仍一致（例如 `investigate --backend sqlite` 与 `--backend postgresql`）；离线 heldout 是否受影响（可用 `evaluate --split heldout --out <实验目录>` 与 `docs/evaluation/reports/20261121T093757_*` 逐题对比，忽略延迟、`planning`、cost）。
3. 新改的文件里有没有真实连接串、密码。

## 5. 报告

你的最终回复就是报告正文（由调度脚本保存到 `docs/reviews/2026-11-23_task035_repair_review.md`）：

- 开头写结论：每个条件关闭 / 部分关闭 / 未关闭；是否发现新问题（P1 / P2 / P3）；整体是否改判为“通过”或“有条件通过”。
- 写明本轮限制。不要声称最终验收通过。
