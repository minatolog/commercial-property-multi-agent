# 任务单 035C：PostgreSQL 实机——12 / 14 表清点、证据与文档归档

- 编写：2026-11-23，Claude Code。由 `scripts/dev_loop/` 执行。
- 前置：035A、035B 已完成并提交。**先阅读 035A / 035B 的任务单与全部改动、`backend/app/db/`、`backend/migrations/`、`docs/architecture/database_design.md`，以及 [Task 033 归档](../prompts/04_agents/2026-11-23_033_mcp_gateway.md) 的章节格式。**
- 本任务**不改任何代码和测试**。环境说明同 035A §0（`COMMERCIAL_PG_TEST_URL` 已设置；不运行 docker / pip；不写连接串）。

## 1. 只新增 / 修改这些文件

| 文件 | 内容 |
|---|---|
| `docs/reviews/task035_evidence/pg_unittest.txt` | 只运行 PG 套件的实际输出：`python -m unittest tests.test_postgres_layer -v` |
| `docs/reviews/task035_evidence/unittest.txt`、`smoke.txt` | 全量回归与契约自检的实际输出 |
| `docs/reviews/task035_evidence/schema_pg.txt` | 用 SQLAlchemy `inspect` 从测试库导出的实际表、列类型、约束清单（写一个只读的小脚本放在 `docs/reviews/task035_evidence/dump_schema.py`，输出原样保存；**输出里不能出现连接串**） |
| `docs/architecture/database_design.md` | 新增一节“实现对照（Task 035）”：12 张已实现表 vs 设计的 14 张表逐表对照（已实现 / 未实现 / 精简差异，例如 `lease_units`、`agent_runs`、`leases.signing_date`、`referenced_document_ids`），以及哪些约束已在 PG 实机验证、哪些仍未实现（RLS 等）。只改这一节和文首“实现边界”说明，其余设计内容不动 |
| `docs/prompts/02_database/2026-11-23_035_postgresql_verification.md` | 任务归档（格式参照 033 归档）：目标与范围、四个实机问题的现象与修复、约束清单、只读角色、CLI、测试点逐条结果、已知差异、遗留问题、对应 Git Commit Hash |
| `backend/README.md` | 新增“PostgreSQL”一节：如何用 Docker 起一个本地测试库、设置 `COMMERCIAL_PG_TEST_URL` 跑 PG 测试、创建只读角色、`--backend postgresql` 的用法与 `COMMERCIAL_DB_URL` |
| `docs/README.md` | 任务表登记 Task 035 |
| `docs/development_logs/development_log.md` | 最上方新增一条 |
| `docs/issues/issue_log.md` | 最上方新增一条：四个实机问题（seed 外键顺序、只读闸门只对单个事务有效、时区、单价精度）的现象、根因、解决、预防 |
| `docs/architecture/CURRENT_BASELINE.md` | 更新日期行、“PostgreSQL”行（原为“尚无实机验收”）、“最新回归证据”行 |
| `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | 更新首行、工作包 3 的状态、“下一步” |

不要改其它文件，也不要改这些文件里与 Task 035 无关的历史条目。

## 2. 内容要求

- **数字一律来自实际运行**：测试数、PG 测试数（实际执行，不是 skip）、契约数写证据文件里的数字。
- PG 版本写容器里实际查到的版本（用测试库连接执行 `select version()`）。
- **状态措辞**：Task 035 写“已实施并自检，待独立复查；未推送”；工作包 3 写“PG 实机验证已完成第一版（待独立复查）”，**不要写“已验收”**。RLS、多实例并发、生产部署明确写为未做。
- 归档里如实写明本任务的四个实机问题是 Claude Code 实机探测发现的（不是编码方发现的），以及 SQLite 为什么测不出来。
- 不调用任何付费模型接口。

## 3. 验收标准

- 只改第 1 节列出的文件；没有改任何代码和测试。
- 证据文件是真实输出；`schema_pg.txt` 与迁移里声明的约束一致。
- 文档里的数字与证据文件一致；各文档对 Task 035 的状态说法一致。
- 新文件 UTF-8、LF；任何文件里都没有连接串或密码。
