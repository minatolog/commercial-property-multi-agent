# 2026-11-06_014_FastAPI 与轻量演示页

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：014（正式 Prompt 9）
- **模块**：05_frontend
- **状态**：**DeepSeek 自检通过**（本地 uvicorn 实测；未做真实部署/HTTPS/多用户并发）
- **前置任务**：012（审批生命周期）、013（报告格式）
- **Git Commit**：见 §8

## 2. 任务目标和背景

此前只能靠读终端输出理解任务。本任务提供可现场演示的入口：提交问题 → 看报告/证据/缺失项 → 暂停在审批 → 人工批准 → 恢复。

硬约束（路线图 Prompt 9）：

- 身份由**服务端**注入，请求不能自报权限；
- 任务之间隔离；
- 展示层只是核心 `WorkflowRunner` 的适配层，**删掉它 CLI 与评测仍然可用**；
- 接口错误可追踪。

## 3. 原始用户 Prompt

本轮（2026-11-06）用户取消 Codex 逐任务审查，要求连续推进 Task 007 自检 → 015。与本任务相关的原文摘录：

````
- Task 014：FastAPI 演示/API 与运行状态、结果和 trace 展示

## 每个任务的执行要求

1. 一次只推进一个任务，保持模块边界清晰、低耦合、Agent 可插拔、配置独立。
4. 为关键行为补充自动化验证；运行本任务相关测试和适当的现有回归测试，记录真实命令与结果。
6. 只有真实实现和验证完成后，才可把任务标记为"DeepSeek 自检通过"。
8. 没有外部凭据时，完成可验证的接口、Fake/离线测试和配置说明。
````

范围以 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` 的 **Prompt 9 / Task 014** 为准
（建议 FastAPI + 同源 HTML/JS，避免完整 React 管理后台）。

## 4. AI 实际执行的主要步骤

1. 安装 `fastapi`（0.162.0）、`uvicorn`（0.54.0）、`httpx`（测试用）。
2. `app/api/service.py`：`WorkflowService`（提交 / 查询 / Trace / 审批）+ `RunIndex`（`data/api/runs.sqlite`，运行索引进 SQLite 以便跨进程看到同一条运行）。
3. `app/api/app.py`：FastAPI 应用 + 6 个接口 + 统一错误体 + `X-Trace-Id` 中间件。
4. `app/api/static/index.html`：同源单页，无构建步骤、无外部依赖（原生 JS）。
5. `app/api/__init__.py` 明确"删除本包不影响 CLI/评测"。
6. 新增 `backend/tests/test_api.py`（13 项），其中一条用子进程断言 `app.cli` / `app.evaluation` 不 import `app.api`。
7. 更新 `tests/test_runtime.py` 的依赖守卫（fastapi 成为允许的展示层依赖，同时把 chromadb/psycopg/torch 等仍列为禁止）。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/api/__init__.py`、`app.py`、`service.py`、`static/index.html` | 新增 | 适配层 + 演示页 |
| `backend/tests/test_api.py` | 新增 | 13 项 |
| `backend/pyproject.toml` | 修改 | 声明 `fastapi` / `uvicorn` |
| `backend/tests/test_runtime.py` | 修改 | 依赖守卫允许 fastapi，新增 3 类禁止依赖 |

## 6. 执行结果和验证方式

| # | 命令 / 方式 | 结果 |
|---|---|---|
| 1 | `python -m unittest tests.test_api` | `Ran 13 tests ... OK` |
| 2 | `python -m unittest discover -s tests -p "test_*.py"` | `Ran 192 tests ... OK`（原 179 + 13） |
| 3 | `python tests/smoke_agent_contracts.py` | 57 项通过 |
| 4 | `uvicorn app.api.app:app --port 8123` + `GET /api/meta` | 200，返回服务端可信主体与审批人白名单 |
| 5 | `GET /` | 200，返回演示页（10KB） |
| 6 | `POST /api/runs`（真实 HTTP） | 201，`status=awaiting_approval`、`approval_request_id=apr_…` |
| 7 | 两级审批经 HTTP（`TestClient`） | 阶段1 `pending_next_stage` → 阶段2 `approved` + `approved_draft`，`executed_side_effects=[]` |

关键行为（均有断言）：

| 行为 | 证据 |
|---|---|
| 请求不能自报身份 | 带 `principal_id`/`permissions`/`roles` 的请求一律 400 |
| 审批人白名单在服务端 | 非白名单 actor → 403 `permission_denied`；缺 `X-Actor-Id` → 400 |
| 任务隔离 | 两次提交的 `run_id`/`thread_id` 不同，Trace 按各自 run 返回 |
| 审批暂停可恢复 | 详情页可见 `approval_request`（两级 stage、草案 v2、金额 700.00） |
| 批准不产生副作用 | `approved_draft.status=approved_draft_only`、`executed_side_effects=[]` |
| 版本不匹配 | 用 v1 审批 v2 草案 → 409 `invalid_request` |
| 错误可追踪 | 404/400/403/409 响应均带 `X-Trace-Id`，且错误体 `trace_id` 与响应头一致 |
| 展示层可删除 | 子进程断言 `app.cli`/`app.evaluation` 未 import `app.api` |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `KeyError: 'created_at'`（提交后返回摘要） | `RunIndex.upsert` 返回的是补全后的记录，但代码用了未补全的 `record` | 用 `upsert()` 的返回值构造摘要 |
| 依赖守卫测试失败 | 原规则把 `fastapi` 列为"禁止引入" | 更新断言：fastapi 属展示层依赖，允许；同时把 chromadb/psycopg/torch/transformers 明确列为禁止 |
| 运行索引放内存会看不到"前一个进程"的运行 | CLI 与网页可能是两个进程 | 索引落 `data/api/runs.sqlite`，并注明它只是投影，权威状态仍是 checkpoint/审批台账 |

## 8. 对应 Git Commit Hash

- **状态**：见 `docs/checkpoints/git_history.md`（里程碑提交后回填）。

## 9. 后续待办事项

- [ ] 演示身份用的是服务端配置的固定主体（`DEMO_PRINCIPAL_ID`）；真实部署需换成会话/OIDC，并加上 CSRF 与鉴权中间件。
- [ ] `X-Actor-Id` 只是"在白名单内选人"，不是认证；上线前必须换成签名令牌。
- [ ] 无分页/无并发写入保护（`RunIndex` 是单机 SQLite），大并发下需换 PostgreSQL 并加任务队列。
- [ ] 页面没有做移动端适配与可访问性检查，仅作演示。
