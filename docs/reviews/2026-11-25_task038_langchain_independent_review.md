# Task 036 / 037 / 038（LangChain 标准化重构与新页面）独立复查报告

- **复查日期**：2026-11-25（Asia/Shanghai）
- **复查者**：deepseek-flash（由 `scripts/dev_loop/dev_review.ps1` 调用，非实施者）
- **依据**：`docs/handoffs/REVIEW_TASK038_PROMPT.md`；ADR-007；Task 037 方案；Task 038 实施记录；`docs/architecture/langchain_integration.md`；Task 036 架构复查
- **代码基线**：`HEAD = 28c3a0b`（`50ad2c2` 之后仅多本复查 Prompt）；开始与结束时 `git status --porcelain` 均为空。被复查改动为 `git diff 77410ca d81e33d`
- **环境**：Windows 11；项目 Python 3.11.18（`D:/anacada/envs/commercial-agent/python.exe`）；`PYTHONUTF8` 以 `-X utf8` 等价启用；`COMMERCIAL_PG_TEST_URL` 已设置；未设置 `COMMERCIAL_DB_URL`；langchain 1.4.9 / langchain-core 1.7.6 / langchain-openai 1.7.4 / langgraph 1.2.20
- **方式**：只读复查 + 仓库外实验目录（`C:/Users/lgwlo/AppData/Local/Temp/dev_review/20261125-164409`）。未修改、新增或删除仓库文件；未提交/推送/切分支/stash；未 `pip install`；未运行 docker。实验副本位于实验目录，`old_backend` 由 `77410ca` 的 29 个差异文件回填生成
- **付费接口**：未调用。缺 Key 场景在进程内临时移除 `DEEPSEEK_API_KEY` 构造客户端，未发网络请求；所有“真实模型”验证均用脚本模型或 `ChatOpenAI` + `httpx.MockTransport`

> **实验卫生说明（如实记录）**：我运行了带 `COMMERCIAL_PG_TEST_URL` 的完整 PG 套件。调度方观察到测试库留下了 6 个 `ro_log_*` 临时角色并已清理。我结束时的查询（`rolname like 'ro\_%'`）没有显示残留，因此没有主动清理；这次检查不足/时机不符，**不能据此声称测试库已由我清理干净**。该库业务表当时已回到 base（仅 `alembic_version` 表、无版本行）。

## 1. 结论

**有条件通过**。

未发现 P1：生产路径确实由 `create_agent` 调度；工具仍只经 `ToolExecutor.execute()`；模型参数中的 `project_ids`/`principal_id` 被拒；预算账本与物理模型请求在生产配置下一致（含超时和取消）；综合节点不能引入新金额；旧 checkpoint 可被新版完成两级审批；新 checkpoint 未混入 LangChain 私有状态。

但这些核心不变量中有四项**没有测试兜底**，我在副本里把它们变异后全套 723 项仍通过：关闭 SDK 重试、工具串行锁、客户端禁止切换模型模式、检索“先筛选后 top-k”。另有运营总览把写死状态呈现为实时状态（虽有“演示环境/模拟数据”标注）这一 P2。因此有条件通过，条件见 §5；**本报告不构成最终验收**。

## 2. 独立验证结果（与 §3 对比）

| 项目 | 自报 | 我的实测 | 结论 |
|---|---|---|---|
| 全量回归（默认，无 PG URL） | 723 OK（skipped=45） | `Ran 723 tests ... OK (skipped=45)`，0 failure / 0 error | 一致 |
| 全量回归（设置 PG URL） | 723 OK（skipped=1） | `Ran 723 tests ... OK (skipped=1)`，0 failure / 0 error | 一致；见 §7 角色残留 |
| 契约自检 | 70 | `全部通过：70 项检查` | 一致 |
| `python -m app.cli check` | exit 0 | 输出完整 JSON，exit 0 | 一致 |
| `investigate --model-provider scripted` | exit 0 | exit 0；`used_model_calls=6`、`used_tool_calls=4`、三领域 success | 一致 |
| `pip check` | exit 0 | `No broken requirements found.` | 一致 |
| 离线 heldout A/B/C | 20 / 21 / 24（30 计分），96 条目一致 | 新跑 A 20/30、B 21/30、C 24/30；与 `20261121T093757_*` 逐行比较 **96 行 0 差异**（passed / applicable / correctness / 逐 assertion 通过映射全部相同） | 一致 |
| 浏览器渲染用例 | 通过 | **未复跑**：本机无 node，无浏览器 harness 执行入口 | 未验证 |
| 模拟 HTTP 3 次请求、45 tokens | 自报 | 未复现同一脚本；独立用 MockTransport 验证 2 次请求/30 tokens 与“物理请求=账本”不变量（见 §3.2） | 机制一致，具体数字未复现 |
| 旧 checkpoint 两级审批 | 通过 | 用 `77410ca` 原版生成待审批 checkpoint，新版两级审批 `approved`、`approved_draft_only`、`executed_side_effects=[]`、金额 `700.00` | 一致 |
| 新 checkpoint 是否混入 LangChain 私有状态 | 未直接自报 | 模型模式 + 审批 checkpoint DB 中 `langchain` / `BaseChatModel` / `AIMessage` / `create_agent` / `ToolMessage` / `messages` 命中均为 0 | 通过 |

## 3. 逐项对照 §4

### 3.1 迁移是否真实、是否只有一条循环

- **只有一条循环**：`run_tool_loop` 已是唯一实现，内部调用 `create_agent`（`backend/app/runtime/tool_loop.py:303`）；旧自研循环已被整体替换。调用方清点为 `LLMToolAgent`、`SingleToolAgent`、`ReportSynthesizer` 与测试；CLI、评测、Web 最终都经这些入口。未发现第二条生产循环。
- **StructuredTool 不绕过执行器**：`_Governance.tool()` 的 `invoke` 只调用 `executor.execute(...)`（`tool_loop.py:264-275`）；未见直接 `tool.invoke(`、直接读仓库或自行判定权限。`awrap_tool_call` 的拒绝分支也只调用执行器（空白名单）做审计。
- **可信上下文**：`principal_id` / `project_ids` / `permissions` 等保留键在 `ToolExecutor` 第一步被 `INVALID_TOOL_ARGUMENTS` 拒绝。实测模型分别塞 `project_ids`、`principal_id`：均 `invalid_tool_arguments`，未执行、trace 记为 error。
- **目标租约**：`lease_id` 确实出现在部分工具的模型可见 schema 中，但由 `TaskScope`/`scope_arguments_hook` 在调用边界注入或拒绝（`backend/app/agents/base/scope.py:116-157`），工具层再用可信租约解析文档集。不是“只靠模型自觉”，但也**不是完全不出现在 schema**；这是防御式设计，与 ADR 的“目标从可信上下文注入”不冲突。模型传错租约时在 `prepare_arguments` 被拒，未执行。

### 3.2 预算与模型调用记账（重点）

独立实验（MockTransport 计数）结果：

| 场景 | 物理 HTTP 请求 | 账本 model calls | 结果 |
|---|---|---|---|
| 工具一轮 + 最终回答，`max_retries=0` | 2 | 2 | `final_answer`，tokens 30 |
| 一轮两个 tool_call + 最终回答 | 2 | 2 | `final_answer`，execs=2 |
| 服务端 500，`max_retries=0` | 1 | 1 | `model_error` |
| 服务端 500，`max_retries=2`（仅用于证明风险） | 3 | 1 | `model_error` |
| 模拟超时，`max_retries=0` | 1 | 1 | `model_timeout` |
| 模拟超时，`max_retries=2` | 3 | 1 | `model_timeout` |

生产路径 `build_chat_client` 显式 `max_retries=0`（`backend/app/llm/langchain_client.py:102`），且 inner `ChatOpenAI` 实测 `max_retries=0`；因此一次 `handler` 只对应一次物理请求，账本不低记。上表第 4/6 行证明若该设置被改回默认，账本会**低记**物理请求。

其余记账路径：

- **预留失败**：`reserve_model_call` 抛错时在 `try/finally` 之前返回 `BUDGET_EXHAUSTED`，不会调用 `settle`。
- **超时/异常/取消**：`finally` 中 `settle` 总会执行；用 `BaseAgent` 的 `wait_for` 取消慢模型实测：结果 `timeout`，物理 1、账本 1。
- **deadline**：已过期时 0 次物理、0 记账；在调用中超时则 1 次物理、1 次记账，停止原因 `deadline_exceeded`。
- **token**：每次模型回合计 `turn.usage.total_tokens`；预留失败时 `record_unbudgeted_tokens` 如实入账。并发共享预算实测：`max_model_calls=1` 时两 Agent 只有一个物理调用，二者均 `budget_exhausted`，账本 1=物理 1。
- **token 上限不是硬上限**：两并发首次响应、上限 15 时实测总计 30（exceeded=15）。这是既有设计（响应前无法知道 token）在并发下的放大；旧循环同样如此，非本次引入，但应在文档中明确“最多可被并发首次响应超出”。
- **工具串行**：一轮两个 tool_call，两个工具各 sleep 0.2s，实测事件严格串行（peak concurrency=1），共享同一 Budget。
- **停止原因**：`MAX_ROUNDS`、`BUDGET_EXHAUSTED`、`DEADLINE_EXCEEDED`、`MODEL_TIMEOUT`、`MODEL_ERROR` 均实测可达，语义与旧循环基本一致；新增 `MODEL_TIMEOUT`（见 P3-3）。
- **“有目标但零成功事实”**：既有 `minimum_evidence_reason` 与 `check_capability_output` 未改弱，全套测试通过；独立脚本中模型只给文本不取数仍判 `insufficient_evidence`。
- **未宣布工具的拒绝审计**：模型调用 `drop__database`：`tool_executions` 记录 `tool_not_found`、trace `denied`、模型收到错误 ToolMessage、无执行；模型调用已注册但不在本次 specs 的暴露别名（如 `lease__lookup`）同样记录 `tool_not_found` 且不执行。审计存在，但错误码为 `tool_not_found` 而非 `tool_not_allowed`（P3-5）。

### 3.3 检索

- **先过滤后 top-k**：`backend/app/rag/service.py:157-181` 先按项目/文档/租约/状态构造候选集，再 `BM25Index.search(..., candidate_ids=...)`；分数仍用全索引 `total_docs` / `df` / `avg_length`。
- **与旧实现逐条对比**：用 fixture 的全部 67 个 chunk 文本 + 32 道 heldout 问题，共 792 个 query×scope 组合，旧 `77410ca` 与新版结果 **0 行差异**：chunk 顺序、score、page、clause、document_version 全部相同。当前 fixture 语料小，旧实现“先取 top_k*4 再过滤”从未截掉范围内条目，所以等价；新版对更大语料是严格改进。
- **范围与元数据**：`ContractRetriever` 输出 `Document(id=chunk_id)`，metadata 带 `page`（PDF 业务页码原值）、`clause_id`、`document_version`、`document_status`、`project_id`、`lease_id`、`score`。实测 A-301 检索返回 `p13/5.3` 等原页码。
- **Task 033/035 语义**：跨项目租约 `lease_jl_b101_2025`、跨项目文档 `doc_jl_b101_contract`（该合同缺 PDF、仅存在于 `catalog_metas`）均返回 `ProjectScopeDeniedError` / `project_scope_denied`；未知租约仍按原逻辑返回 0 条、不猜测。`catalog_metas` 路径仍生效。
- **空授权**：`TrustedContext` 本身禁止空 `project_ids`；服务层空集合返回空结果由既有测试覆盖。

### 3.4 证据综合节点

用 `ReportSynthesizer` + Fake client 独立跑了 12 个反例：

| 输入 | 结果 |
|---|---|
| 合法选择 | `completed`，facts/conflicts/gaps 为原报告对象（`is` 同一对象），next_steps 来自静态 `_ACTIONS` |
| 越界索引 `[9]` | `invalid_output` |
| facts 里塞对象/伪造金额 `{"statement":"金额 99999.00"}` | `invalid_output` |
| 未知动作码 `delete_everything` | `invalid_output` |
| 非 JSON 自由文本 | `invalid_output` |
| 额外键 `amount` | `invalid_output`（`extra=forbid`） |
| 50 个索引（超 max_length） | `invalid_output` |
| 有 facts 却一个不选 | `invalid_output` |
| 无 facts 无 conflicts | `insufficient_evidence`，**0 次模型调用** |
| 模型调用失败 | `model_error`，账本记 1 次 |

- 不能新增金额：输出只返回报告原对象索引；动作来自 `_ACTIONS` 常量；严格 JSON + `extra=forbid` + 索引范围 + 动作白名单共同限制。
- 同一 Budget：`run_tool_loop` 使用传入的共享 budget；实测记账 1 次。
- 失败不静默：`investigation.py:962-967` 把 `{"status": ...}` 写入 `report["synthesis"]`；UI 对 `invalid_output` / `budget_exhausted` / `model_error` / `model_timeout` 等均有明确文案（`report.js:96-121`）。
- 审批不受影响：API 测试与重启实验均确认审批两级流程照旧，`executed_side_effects=[]`。

### 3.5 网页

- **模型模式只由服务端决定**：`RunRequest` 为 `extra="forbid"`（`api/app.py:75`），客户端传 `model_provider` 实测 422 `invalid_request`；`/api/meta` 返回服务端 `model_provider`。
- **缺 Key**：进程内移除 Key、以 `model_provider=deepseek` 启动服务后 POST，返回 503 `missing_api_key`；响应体不含 Key 或环境变量名。未泄露。
- **实际引擎与用量**：报告写入 `execution.engine/provider/agent_framework`、`budget`、`agent_analyses`（含 served_models 与 usage）；工作台在 `engine === "llm"` 时展示“模型请求 N 次 · 已记账 N tokens”，缺失时显示“实际应答模型未报告”“未提供”。实测 web 模型模式 `used_model_calls=7`（6 次 Agent + 1 次综合），与脚本客户端调用数一致。
- **新页面的真实性**：`grep` 确认 `static/ops/` 与 `static/mall/` **没有任何 `/api/`、fetch、XHR、EventSource、WebSocket**。ops 的指标、6 个 Agent、“协同网络运行正常”、任务/审批/回执全部写死或 localStorage。页面有顶部“演示环境”徽标、侧栏“演示值班员”、3D 组件“模拟数据”标注；但数据区本身没有“模拟数据”，且“待审批/已批准/派单/已接单/执行回执”措辞与真实审批相同。**判 P2**（非“完全无标注”，故不判 P1）。首页仍通过侧栏“争议调查”链接和 3D 商铺“新建商铺调查”清晰到达 `/workbench`。
- **XSS**：两个新脚本的动态内容基本都用 `textContent`/`el`/`escape()`；ops 中唯一用户输入（表单标题）在所有渲染路径均转义；`store` 参数经静态 Map 白名单，不写 DOM；mall 的商铺/Agent 文案为静态。未发现可注入点。`/?run=...` 的原样查询串只进入 API 请求（`encodeURIComponent`）与静态 Map，不进入 HTML。
- **旧链接与开放重定向**：`/?run=abc&tab=evidence&tech=open`、`/?store=A-302` 均 307 到 `/workbench?...` 且参数完整；`/?run=//evil.com` 仍重定向到同源 `/workbench?run=//evil.com`，前缀固定，无开放重定向。`/`、`/workbench`、静态资源均 `Cache-Control: no-cache`。

### 3.6 恢复与兼容

- **旧 checkpoint 跨版本恢复**：已复现。旧代码生成待审批 checkpoint（request `apr_...`，draft_version=2），新代码两级审批成功，`approved_draft_only`、`executed_side_effects=[]`、金额 700.00。
- **新 checkpoint 私有状态**：模型模式（脚本客户端 + deepseek 装配）审批暂停后，checkpoint SQLite 的 `checkpoints`/`writes` 原始字节中无 `langchain` / `BaseChatModel` / `AIMessage` / `create_agent` / `ToolMessage` / `messages` 命中；报告中 `synthesis`、`budget`、`execution` 均为 JSON 可序列化内容。
- **重启恢复**：同一 deepseek 模式的暂停运行，由新的 `WorkflowService(model_provider="offline")` 恢复两级审批成功，`execution`/`synthesis`/`budget` 原样保留。
- **依赖**：`langchain==1.4.9` 为精确锁定；`langchain-core`/`langchain-openai`/`langgraph` 为范围（`pyproject.toml:12-19`）。`pip check` 通过，但无 CI、无版本兼容性测试兜底（P3-6）。

### 3.7 测试有效性

- 对比 `77410ca`，**没有删除或放宽既有断言**：`test_llm_tool_loop.py`、`test_token_budget_gate.py`、`test_rag.py` 等未修改且全部通过；`test_api.py` 仅新增模型模式测试并适配首页/静态资源断言；`ui-model-cases.js` 只新增 1 个用例。
- 新增测试质量：`test_model_analysis_uses_actual_tools_and_shared_accounting` 断言 `used_model_calls == len(model.calls)+len(synthesis.calls)`，是有意义的“物理调用=账本”检查；`test_invalid_synthesis_indices` 与 `test_model_timeout_is_visible_and_accounted` 也直接覆盖失败路径。
- 但 §4 变异显示 4 个核心不变量没有测试兜底（见 §4）。

### 3.8 文档

- ADR-007、`langchain_integration.md`、`CURRENT_BASELINE.md`、路线图、README 均如实区分“接口标准化”与“检索质量提升”，明确 BM25 未替换、向量/混合未引入；明确“模拟 HTTP/脚本模型”与“实际 DeepSeek 待实测”；明确 `formal_20261123` 是迁移前旧循环结果、评分审计与人工量表未完成。未发现把本地验证写成已验收。
- `development_log.md` 中“均独立验证”一语指实施者自测，容易被读成“独立复查”；属措辞问题（P3-10）。
- Task 036 已登记的运营总览模拟风险仍在，038 未关闭，只新增了问题记录；文档披露与页面实际一致（页面确有徽标，但状态措辞仍有误导性）。

## 4. 问题分级

### P1

无。未发现预算可绕过/少记（生产配置）、工具绕过执行器、可信上下文可被模型参数覆盖、综合节点可引入未核验金额，或页面完全无标注却把写死数据当实时状态。

### P2

**P2-1 运营总览把写死的运营状态呈现为当前事实（有标注，但仍可能误导）**
- 位置：`backend/app/api/static/ops/index.html:29`（“6 个 Agent 在线 / 协同网络运行正常”+ live-dot）、`:41`（写死“11 月 24 日，周二”）、`static/ops/app.js:88-107`（静态指标）、`:366-378`（本地审批/派单）、`:427`（本地新建任务）。
- 实测：`grep` 确认无任何 `/api/` 调用；任务只存 localStorage；按钮文案“待审批/已批准/派单/已接单/执行回执”与真实审批一致。
- 缓解：顶部“演示环境”、侧栏“演示值班员”、3D 组件“模拟数据”；Task 036/issue_log 已有记录。仍建议在指标与在线状态旁逐处标“模拟数据”，并把“批准并派单/已接单”改为“模拟批准/演示回执”。

**P2-2 “关闭 SDK 重试、物理请求=账本”没有回归测试兜底**
- 位置：`backend/app/llm/langchain_client.py:102`。
- 复现：副本把 `max_retries=0` 改为 `2`，全套 723 项仍通过（仅 2 项与副本环境有关的既有失败）；用 MockTransport 计数则 500/超时场景变为 **3 次物理请求、账本 1 次**。当前生产代码正确，但任何回归都不会被 723 项测试发现。

**P2-3 Web 客户端不能切换模型模式没有回归测试兜底**
- 位置：`backend/app/api/app.py:68-81`（`RunRequest.extra="forbid"`）。
- 复现：副本给 `RunRequest` 增加 `model_provider` 字段并在 `submit_run` 里写 `svc.model_provider`，全套 723 项仍通过；用 TestClient 发 `model_provider=deepseek` 时服务被切成 deepseek 并返回 503（未变异时该请求为 422）。当前代码安全，但安全边界无测试保护。

### P3

**P3-1 工具串行锁没有测试**
- `tool_loop.py:256-257` 的 `tool_lock` 被移除后全套 723 项仍通过；独立实验显示一轮两个 tool_call 的 peak concurrency 从 1 变为 2。工具目前只读，影响限于 trace/evidence 顺序与未来写工具，但这是刻意保留的旧语义，应有测试。

**P3-2 检索“先筛选后 top-k”无法被现有 fixture 区分**
- `service.py:157-181` 回退为旧“先取 top_k*4 再过滤”后全套 723 项仍通过；我的 792 个 query×scope 对比也是 0 差异。改动本身正确，但缺少能证明它优于旧实现的语料（> 4*top_k 且高分段含范围外 chunk）。

**P3-3 模型超时的重试语义发生变化且未记录**
- `tool_loop.py:191-194` 新增 `MODEL_TIMEOUT`；`llm_agent.py:60-65` / `single/agent.py` 将其映射为 `ErrorCode.TIMEOUT`，而 `retryable=error_code is ErrorCode.MODEL_ERROR` 使其**不可重试**。旧实现把超时收敛为 `MODEL_ERROR`（可重试），因此一次瞬时超时现在会直接失败子任务。`test_api.test_model_timeout_is_visible_and_accounted` 只验证可见性和记账，未验证重试次数。应在文档明确或恢复旧语义。

**P3-4 同一回合“有效+非法”工具调用现在整体失败**
- `tool_loop.py:214-216` 只要存在 `invalid_tool_calls` 或重复 call_id 就 `MODEL_ERROR`，即使同时有有效调用；旧循环会执行有效调用、忽略非法项。更严格本身可接受，但属未记录的行为变化，且无测试。

**P3-5 未宣布工具的拒绝错误码不够精确**
- `tool_loop.py:245-255` 用执行器 + 空白名单审计。模型调用已注册但未暴露的别名（如 `lease__lookup`）得到 `tool_not_found`，审计的 `tool_name` 也是 provider 别名而非内部名；应尽量区分 `tool_not_allowed`（已注册但未授权/未暴露）与 `tool_not_found`（完全未知）。

**P3-6 模型失败诊断信息变少**
- `tool_loop.py:191-198` 的 `_AgentStopped` 消息只保留“模型调用失败: <code>”，旧循环会带上 `exc.message`；provider 的原始错误细节未进入 warnings。`test_api.test_model_timeout...` 只检查 code。

**P3-7 依赖只锁 langchain 高层版本**
- `backend/pyproject.toml:12-19`：`langchain==1.4.9`，但 core/openai/langgraph 为 `>=1,<2`；仓库无 CI，`pip check` 只检查声明范围。升级 `langchain-core`/`langgraph` 小版本后 middleware 签名或 checkpointer 行为可能变化，当前只有本地回归能发现。建议至少增加启动期兼容检查或在文档写明组合版本。

**P3-8 Synthesizer 绕过注入的 planner_client**
- `investigation_demo.py:426-436`：即使调用方注入了 `planner_client`，综合客户端仍走 `_planner_client(..., planner_client_factory=...)` → `build_model_client_for_config`。当前 Web 未注入、测试用 patch 覆盖，因此未触发；但“注入假模型却仍可能构造真实客户端”是潜在的付费调用缝。

**P3-9 综合节点创建了未使用的 ToolExecutor**
- `investigation_demo.py:434-435` 与 `ReportSynthesizer` 的 `executor` 从不使用；属死依赖，建议删除或明确保留原因。

**P3-10 文档措辞**
- `docs/development_logs/development_log.md` 把实施者自测写成“均独立验证”，易与独立复查混淆；建议改为“实施者本地验证”。

**P3-11 新 checkpoint 的 ToolMessage 状态不一致（低）**
- `_Governance.tool().invoke` 对执行器失败返回字符串，LangChain 会包成 `status="success"` 的 ToolMessage（内容里是 error JSON）；`parse_error` 分支则显式 `status="error"`。项目自身不读该 status，故无功能影响，但审计/调试时容易误读。

## 5. 变异测试表

副本位于实验目录；每个变异重新复制 pristine 后打补丁。基线（未变异副本）在这套环境下有 2 项与实验目录有关的既有失败：`test_gitignore_excludes_runtime_state`（副本不在 git 仓库内）和 `test_postgres_layer...test_create_role_refuses_when_sql_logging_enabled`（副本环境），与变异无关，下文“全套通过”均指**除这 2 项外**通过。

| # | 变异 | 运行范围 | 结果 | 说明 |
|---|---|---|---|---|
| M1 | `awrap_model_call` 的 `finally` 不调用 `settle` | `test_token_budget_gate` + `test_llm_tool_loop` + `TestWebModelMode`（46 项） | **被杀**：5 failures | 账本 model calls 变 0，Q1 门禁、API 记账、超时记账均失败 |
| M2 | `build_chat_client` 的 `max_retries=0` → `2` | 全套 723 项 | **存活**（仅 2 项环境失败） | 独立 MockTransport：500/超时从 1 次物理请求变 3 次，账本仍 1 → P2-2 |
| M3 | 去掉 `awrap_tool_call` 的 `tool_lock` | 全套 723 项 | **存活**（仅 2 项环境失败） | 独立实验 peak concurrency 1→2 → P3-1 |
| M4 | StructuredTool 直接 `registry.get(...).invoke(...)`，绕过执行器 | `test_llm_tool_loop` + `test_task_scope` + `test_single_agent_scope` + `test_token_budget_gate` + `test_task031_z2_evidence`（97 项） | **被杀**：29 failures + 2 errors | 权限、范围注入、预算、证据、失败审计全线失败 |
| M5 | 删除 `ReportSynthesizer._select` 的索引范围检查 | `TestWebModelMode`（4 项） | **被杀**：1 error | 越界索引导致运行失败，预期 `invalid_output` 的测试失败 |
| M6 | `KnowledgeService.search` 回退为旧“先 top-k 再过滤” | 全套 723 项 | **存活**（仅 2 项环境失败） | 独立 792 组合对比 0 差异 → P3-2 |
| M7 | `RunRequest` 增加 `model_provider` 并由客户端写入 `svc.model_provider` | 全套 723 项 | **存活**（仅 2 项环境失败） | 独立 TestClient：客户端传 deepseek 后服务切模式并 503（未变异为 422） → P2-3 |
| M8 | 删除未宣布工具的空白名单审计调用 | `test_llm_tool_loop` + `test_llm_agents` + `test_task031_z2_evidence` + `test_api`（123 项） | **被杀**：1 failure | `test_llm_domain_agent_judges_only_its_capability` 依赖失败审计计数 |

## 6. 独立实验补充结果

- **物理请求计数**：见 §3.2 表；生产 `max_retries=0` 时 2 请求/2 记账、500 时 1/1、超时 1/1。
- **工具串行**：一轮两个 tool_call，事件序列 `start a → end a → start b → end b`，peak=1；工具预算 2。
- **共享模型预算**：`max_model_calls=1`、两并发 Agent → 两者 `budget_exhausted`，物理完成 1、账本 1。
- **token 并发**：`max_total_tokens=15`、两并发首次响应 → 账本 30、exceeded 15；设计上允许并发首响应超额，建议文档写明。
- **取消/超时记账**：`BaseAgent.wait_for` 取消慢模型 → `timeout`、物理 1、账本 1。
- **deadline**：已过期 0/0；调用中过期 1/1，`deadline_exceeded`。
- **保留键**：`project_ids`、`principal_id` 均 `invalid_tool_arguments`，未执行。
- **未宣布工具**：`drop__database` → `tool_not_found` + trace denied + 无执行；已注册别名 `lease__lookup` 同样被拒。
- **参数 Schema 非法**：`document.search` 缺 `query`、`query=123`、`top_k=99` 都由执行器记录 `invalid_tool_arguments`，审计未丢；可信 scope 注入 `lease_id` 后正常执行。
- **RAG**：A-301 正常检索返回 page/clause/version/status；跨项目租约与缺 PDF 的 Jinlan 文档均 `project_scope_denied`；未知租约 0 条。
- **Web 模型模式**：脚本客户端 + deepseek 装配 → `execution.engine=llm`、`agent_framework=langchain`、`used_model_calls=7`、三领域 `agent_analyses`、`synthesis=completed`；checkpoint 无 LangChain 私有标记；两级审批后 `synthesis`/`budget` 不变、`executed_side_effects=[]`。
- **跨版本恢复**：旧 checkpoint 由新版两级审批成功；deepseek 暂停运行由新 offline 服务恢复成功。

## 7. 通过条件与返修建议

1. **补齐四个 P2/P3 测试缺口**（不改实现即可）：
   - Mock HTTP transport 计数：强制 500/超时，断言 `max_retries=0` 时物理请求=账本；若有人改回 SDK 重试，测试必须失败。
   - 一轮多 tool_call 的串行断言（起止时间不重叠、共享预算）。
   - 客户端不能传 `model_provider`/模型模式的 422 断言，以及服务端模式固定。
   - 构造一个“高分段含范围外 chunk 且候选数 > 4*top_k”的检索用例，证明先筛选后 top-k 与旧实现不同且新实现正确。
2. **运营总览逐处标注模拟并改措辞**：指标区、在线状态、日期戳旁标“模拟数据/示例”；“批准并派单/已接单/执行回执”改为“模拟批准/演示回执”，避免与 `/workbench` 真实审批混淆。保留显眼的“争议调查”入口。
3. **记录或恢复超时语义**：说明 `MODEL_TIMEOUT` 不可重试的选择；若希望与旧行为一致，应在 `LLMToolAgent`/`SingleToolAgent` 对 TIMEOUT 允许重试并补测试。
4. **记录“有效+非法 tool_call 整体失败”** 的新行为，并补混合调用用例。
5. **提升审计精度**：未暴露但已注册的别名尽量报 `tool_not_allowed`，保留内部名；模型失败 warnings 保留 provider 原始 message/details。
6. **依赖策略**：为 `langchain-core`/`langgraph` 增加组合版本约束或启动期兼容检查；至少让 CI/回归固定运行。
7. **Synthesizer 使用注入的 planner client**（若提供），避免测试缝绕过；删除未使用的 ToolExecutor 依赖。
8. 修正 `development_log.md` 的“独立验证”措辞。

以上不要求本轮立即修改；但第 1 项与第 2 项建议在最终验收前完成。

## 8. 本轮限制

- **未调用真实 DeepSeek**，也未用真实网页服务验证；Web 模型链路只用脚本客户端和 MockTransport。
- **未执行浏览器/JS harness**：本机无 node，`ui-model-cases.js`/`ui-model-harness.html` 未运行；“浏览器渲染通过”只能由实施者自报，我未独立确认。
- **未审计正式评测评分**：`formal_20261123` 为迁移前旧循环结果，文档已如此标注；评分器、跨主体安全题与人工量表不在本轮复查范围。
- **PG**：全量 PG 套件通过（skipped=1），但实验留下 6 个 `ro_log_*` 临时角色，已由调度方清理；我结束时的查询未见残留，故未主动清理，不能声称测试库由我清理干净。业务表当时在 base。
- **变异实验**在实验目录副本执行；副本不在 git 仓库内导致 `test_gitignore...` 失败，PG SQL logging 用例在副本环境也失败，这两项是基线噪音，不归因于变异。
- **未复现**自报的“3 次 HTTP 请求、45 tokens”具体脚本；只独立验证了“物理请求=账本”的机制与 2 次/30 tokens、3 次/1 账本的反例。
- **未做**真实 PostgreSQL 之外的数据库、docker、`pip install`、网络抓包；`data/` 文件 mtime 未变，仓库 `git status` 为空。
- 受时间限制，未对 3D 渲染、响应式布局和全部 `innerHTML` 调用做逐像素/逐浏览器验证；XSS 结论来自静态审读与数据流检查，不是运行时攻击测试。

**本报告为独立复查意见，不构成最终验收通过。**
