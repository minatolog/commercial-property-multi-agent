# 复查 Prompt：Task 036 / 037 / 038（LangChain 标准化重构与新页面）独立复查

- 编写：2026-11-25（Asia/Shanghai），Claude Code（复核者；不是本次实施者）。
- 给：与实施者不同的模型（由 `scripts/dev_loop/dev_review.ps1` 调用）。
- 性质：**只读复查**。仓库内不改任何文件；实验在调度脚本给的仓库外实验目录里做。

> 这是项目迄今改动面最大的核心重构：所有领域 Agent 与 Single 的“模型 → 工具 → 继续”循环从自研实现换成了 `langchain.agents.create_agent`。它直接影响每一次模型调用的预算记账、拒绝审计、错误映射与审批恢复。实施记录自述“通过本地验证”，**尚无独立复查**。下面的疑点只是起点。

---

## 0. 硬性约束

1. **不调用付费模型接口**（DeepSeek 等），不 `pip install`，不运行 `docker`。需要模型时只能用项目里的 scripted / 假模型，或 `ChatOpenAI` 配合模拟 HTTP 传输。
2. 仓库内不改任何文件；不提交、不推送、不切分支、不 stash；不碰 `data/`。
3. PG 测试库：`COMMERCIAL_PG_TEST_URL` 已设置（本机一次性测试库）。实验后把库回退到 `alembic downgrade base`、删除临时角色；报告里不写连接串或密码。不要把 `COMMERCIAL_DB_URL` 设成全局变量（`backend/migrations/env.py` 会优先读它）。
4. 变异实验：把 `backend/` 与 `docs/evaluation/fixtures/` 按原相对结构复制到实验目录再改。
5. Python：`D:/anacada/envs/commercial-agent/python.exe`，在 `backend/` 下运行，设置 `PYTHONUTF8=1`。LangChain / LangGraph 源码可在 `D:/anacada/envs/commercial-agent/Lib/site-packages/` 下直接读。

## 1. 复查对象

- 提交 `d81e33d`（“langchain”，用户提交，46 个文件，+3221 / −868），基线 `77410ca`：`git diff 77410ca d81e33d`。
- `50ad2c2` 只把 `.claude/` 移出仓库并回填归档里的提交哈希，**不在范围**。
- 开始前确认 `git rev-parse HEAD` 为 `50ad2c2` 或其后只多了本 Prompt 的提交，`git status --porcelain` 为空。

## 2. 必读材料

| 用途 | 文件 |
|---|---|
| 决策与方案 | `docs/decisions/ADR-007-langchain-standard-components.md`、`docs/prompts/04_agents/2026-11-24_037_langchain_standardization_plan.md` |
| 实施记录 | `docs/prompts/04_agents/2026-11-24_038_langchain_standardization.md` |
| 接手指南 | `docs/architecture/langchain_integration.md` |
| 迁移前审查 | `docs/reviews/2026-11-24_current_architecture_review.md` |
| 核心代码 | `backend/app/runtime/tool_loop.py`（`_ProjectChatModel`、`_Governance`、`run_tool_loop`）、`backend/app/llm/langchain_client.py`、`backend/app/rag/retriever.py`、`backend/app/rag/{bm25,service}.py`、`backend/app/tools/knowledge_tools.py`、`backend/app/orchestration/synthesis.py`、`backend/app/orchestration/investigation.py`、`backend/app/investigation_demo.py`、`backend/app/api/{app,service}.py` |
| 页面 | `backend/app/api/static/ops/`、`backend/app/api/static/mall/`、工作台 `static/index.html` 与 `js/` |
| 旧循环（对照） | `git show 77410ca:backend/app/runtime/tool_loop.py` |

## 3. 自报数字（全部独立复跑）

| 项 | 自报 |
|---|---|
| 全量回归（默认） | 723 OK（skipped=45） |
| 全量回归（设置 PG URL） | 723 OK（skipped=1）——复核者 2026-11-25 实测 |
| 契约 / `check` / `investigate --model-provider scripted` / `pip check` | 70 / exit 0 / exit 0 / exit 0 |
| 离线 heldout（`evaluate --split heldout --out <实验目录>`）对比 `20261121T093757_*` | A 20/30、B 21/30、C 24/30，96 个条目一致 |

## 4. 复查清单

### 4.1 迁移是否真实、是否只有一条循环

1. 生产路径是否**真的**走 `create_agent` 的模型 / 工具节点，而不是在标准 Agent 外壳里再嵌旧循环；旧 `run_tool_loop` 的自研循环是否已无调用方（清点所有调用方，包括 Single `ask`、评测基线、Web）。
2. `ToolExecutor.execute()` 是否仍是**唯一**业务执行入口：`StructuredTool` 的实现里有没有直接调用 `tool.invoke(`、直接读仓库、或自己判断权限。
3. 可信上下文（主体、项目范围、预算、目标租约）是否**只从运行上下文注入**，没有出现在模型可见的工具参数 schema 里；模型若在参数里塞 `project_ids` / `principal_id` 是否仍被拒绝。

### 4.2 预算与模型调用记账（重点）

1. **物理模型请求数 = 账本记录数**：在 `_Governance.awrap_model_call` 里，`reserve_model_call` → `handler` → `settle` 的顺序在超时、异常、取消（`CancelledError`）、预算耗尽时是否都正确；`settle` 是否会在 `reserve` 失败时也被调用并造成错误记账。
2. LangChain / `ChatOpenAI` / SDK **自身的重试**是否关闭：一次 `handler` 调用会不会触发多次物理 HTTP 请求而账本只记一次（可用模拟 HTTP 传输计数验证）。
3. 模型一次返回多个 tool_call 时，工具是否串行（`tool_lock`）、是否共享同一个 `Budget`；多个领域 Agent 并发时总预算是否仍不超限。
4. token 用量、服务端实际应答模型（`served_models`）是否仍逐 Agent 写入报告，与 `formal.py` / runner 的汇总字段兼容。
5. 停止原因（`MAX_ROUNDS`、`BUDGET_EXHAUSTED`、`DEADLINE_EXCEEDED`、`MODEL_TIMEOUT`、`MODEL_ERROR`）与旧循环语义是否一致；错误的 ToolMessage 是否被误计为成功事实；“有目标但零成功事实”是否仍不能判完成。
6. 038 §7 提到的“未宣布工具的拒绝丢失失败审计”修复：用限定为空的白名单经执行器记录拒绝——核实模型调用**不在白名单里**的工具名时，审计记录、错误码、是否执行都正确。

### 4.3 检索（`retriever.py`）

1. 授权范围过滤先于 top-k 截取；Task 033 的跨项目 `document.search` 范围拒绝、Task 035 的 `catalog_metas`（缺 PDF 文档的归属判断）是否仍生效（相关测试是否还在、是否被改弱）。
2. 038 说“候选先筛选再截取 top-k，分数仍用全索引统计”：与旧 BM25 结果逐条对比，判断排序是否真的等价；页码、条款号、版本、签署状态、引用 ID 是否原样带出。

### 4.4 证据综合节点（`synthesis.py`）

1. 只能从已核验条目中选择、不能新增金额或业务动作：用假模型返回越界索引、伪造金额、未知动作码、非 JSON、超长输出，确认都被拒绝并以明确失败结束，审批仍按台账规则继续。
2. 它使用同一个 `Budget`；离线模式（`offline`）是否完全不调用模型；失败时报告是否如实标注，而不是静默省略。

### 4.5 网页

1. 模型模式只由服务端配置（`COMMERCIAL_WEB_MODEL_PROVIDER`）决定，客户端不能切换；缺密钥 / 配置错误返回 503 且不泄露 Key；页面如实显示实际引擎与用量。
2. **新页面的真实性**：`static/ops/`（运营总览）与 `static/mall/`（3D 商场）没有调用任何 `/api/`，“6 个 Agent 在线”“协同网络运行正常”、协同任务数等均为写死的内容。判断它们是否会让使用者误以为是实时系统状态；页面上是否有“演示数据”之类的明确标注；首页 `/` 改为运营总览后，用户是否还能清楚地到达真实的争议调查工作台。
3. `innerHTML` 的使用（两个新脚本约 16 处）：有没有把来自 URL 参数、API 或用户输入的内容未转义写入 DOM（XSS）。`/?store=...` 跳转到 `/workbench` 的参数处理是否安全。
4. 旧链接（`?run=`、`?tab=`）重定向是否保留全部参数且不形成开放重定向。

### 4.6 恢复与兼容

1. 038 自述“用 `77410ca` 原版生成的待审批 checkpoint 由新版完成两级审批”——自己复现一次；新版 checkpoint 中是否混入 LangChain 私有状态，导致以后升级 LangChain 时恢复失败。
2. 依赖：`backend/pyproject.toml` 是否锁定了 `langchain==1.4.9`（还是范围）；与 `langchain-core 1.7.6`、`langgraph 1.2.20` 的兼容是否有测试兜底。

### 4.7 测试有效性

1. 新增 / 修改的测试（`test_api.py`、`ui-model-cases.js`，以及 `test_llm_tool_loop`、`test_token_budget_gate`、`test_rag` 等）有没有被改弱以适配新框架：对比 `77410ca` 版本，找被删除的断言、放宽的期望值、新增的 skip。
2. 在副本里**至少做 6 项变异**并写结果，例如：`settle` 不调用、重试次数改为 2、`tool_lock` 去掉、工具绕过执行器直接 `invoke`、`synthesis` 不校验金额、检索先 top-k 后过滤、Web 允许客户端指定模型模式。

### 4.8 文档

1. ADR-007、`langchain_integration.md`、`CURRENT_BASELINE.md`、路线图、README 是否如实：有没有把“接口标准化”写成“检索质量提升”，把“本地验证”写成“已验收”，把模拟传输写成真实 DeepSeek 验证。
2. 已知遗留（真实 DeepSeek 网页验证、正式评测评分审计）是否都登记。注意：`formal_20261123` 的结果是旧循环（`c6037fe`）跑的，文档不能把它当新架构的结果。

## 5. 输出

你的最终回复就是报告正文（由调度脚本保存到 `docs/reviews/2026-11-25_task038_langchain_independent_review.md`），参照 `docs/reviews/2026-11-23_task035_independent_review.md` 的格式：

1. 头部：复查日期、复查者（模型名）、依据、代码基线（HEAD 与 `git status` 核对）、环境、方式、是否调用付费接口。
2. **结论**：`通过` / `有条件通过` / `不通过`，一句话理由。预算可被绕过或少记、工具绕过执行器、可信上下文可被模型参数覆盖、综合节点能引入未核验金额、页面把写死的数据呈现为实时系统状态且无标注——都至少是 P1 / 不通过候选，按实际影响判定。
3. 独立验证结果表（与 §3 对比）。
4. 逐项对照 §4 与自己发现的问题，分级 **P1 / P2 / P3**，每条给复现步骤或 `文件:行号`。
5. 变异测试表。
6. 通过条件与返修建议（不要动手修改）；本轮限制。不要声称最终验收通过。
