# Task 038R 返修确认复查报告（LangChain 独立复查）

- **复查日期**：2026-11-25（Asia/Shanghai）
- **复查者**：deepseek-flash（由 `scripts/dev_loop/dev_review.ps1` 调用，非实施者）
- **依据**：`docs/handoffs/REVIEW_TASK038_REPAIR_PROMPT.md`、`DEV_LOOP_TASK038R_LANGCHAIN_REVIEW_FIXES.md`、上一轮 [独立复查报告](2026-11-25_task038_langchain_independent_review.md)、038 归档 §10
- **代码基线**：`HEAD = be4dd17`；被复查提交 `525413c`；差异 `git diff 9db6687 525413c`。开始时与结束时 `git status --porcelain` 均为空
- **环境**：Windows 11；项目 Python 3.11（`D:/anacada/envs/commercial-agent/python.exe`）；`COMMERCIAL_PG_TEST_URL` 已设置，未设置 `COMMERCIAL_DB_URL`
- **方式**：只读复查 + 仓库外实验目录（`C:/Users/lgwlo/AppData/Local/Temp/dev_review/20261125-201616`）。未修改、新建或删除仓库文件；未提交/推送/切分支/stash；未 `pip install`；未运行 docker
- **付费接口**：未调用。所有模型验证均用脚本/假客户端或 `httpx.MockTransport`；未使用 `--planner-provider deepseek` / `--model-provider deepseek`

## 1. 结论

**本轮返修通过（改判：上一轮“有条件通过”的两个条件已满足），无 P1、无 P2；仍有若干不阻断的 P3 残留。**

逐条关闭情况：

| 编号 | 关闭情况 | 依据摘要 |
|---|---|---|
| P2-2 SDK 重试无测试 | **关闭** | 新测试经生产构造路径建客户端并用 MockTransport 计物理请求；把 `max_retries` 改为 2 后测试失败（3 次请求 ≠ 账本 1） |
| P2-3 客户端切换模式无测试 | **关闭** | 新测试对 5 个字段断言 422 且服务端模式不变；变异后出现 201/503/模式被改写，测试失败 |
| P3-1 串行锁无测试 | **关闭** | 假执行器测并发峰值与顺序；去掉 `tool_lock` 后峰值 2、测试失败 |
| P3-2 检索先筛选后 top-k | **关闭** | 测试语料满足“全库前 8 名全在范围外”；回退旧实现后范围内结果为空、测试失败 |
| P3-3 超时不可重试 | **关闭** | 首次超时第二次成功 → 成功且账本 2；预算 1 次 → 不重试、`BUDGET_EXHAUSTED`；独立探针确认 Single 行为一致 |
| P3-8 综合节点绕过注入客户端 | **关闭** | 综合客户端优先用注入的 `planner_client`；变异回退后测试因“构造真实客户端”断言失败 |
| P3-9 综合节点死依赖 | **关闭（安全，有类型残留）** | 删除执行器；实测模型返回 tool_call 时得到 `model_error`，未触碰执行器；`executor=None # type: ignore` 属脆弱写法 |
| P2-1 运营总览写死状态 | **关闭（有文案残留）** | 在线状态、日期、每个指标卡、审批/回执按钮均已加模拟标注，并新增页面级声明；仍有“协同中/已完成/已审批”等词未逐处标注，见 P3-12 |
| P3-10 开发日志措辞 | **关闭** | 仅 Task 038 条目一行由“均独立验证”改为“均为实施者本地验证”，未改其它条目 |
| P3-4/5/6/7/11 | **维持“接受为已知差异”** | 038 归档 §10 的理由基本成立；P3-7 的“本地回归兜底”没有新增 CI/启动检查，属最弱的一条接受理由 |

**本报告不构成最终验收通过。** 真实 DeepSeek、浏览器/JS、正式评分审计等仍未验证。

## 2. 独立验证结果

| 项目 | 自报 | 我的实测 | 结论 |
|---|---|---|---|
| 全量回归（设置 PG URL） | 731 OK，skipped=1 | `Ran 731 tests in 45.212s ... OK (skipped=1)`，0 failure/error | 一致 |
| 全量回归（未设 PG URL） | —（上一轮 723） | `Ran 731 tests in 38.005s ... OK (skipped=45)` | 一致，新增 8 项 |
| 契约自检 | 70 | `全部通过：70 项检查` | 一致 |
| `app.cli check` | exit 0 | 输出完整 JSON，退出码 0 | 一致 |
| 新增测试 | 通过 | `test_task038r_langchain` 5 项、`TestClientCannotSelectModelMode` 2 项、`TestScopeFilteringBeforeTopK` 1 项全部 OK | 一致 |
| 6 项变异 | 全部被抓 | 我逐一重做，6 项全部被对应测试杀死 | 一致 |

### 2.1 变异复跑（仓库外副本）

| # | 变异 | 运行范围 | 结果 |
|---|---|---|---|
| M1 | `build_chat_client` 的 `max_retries=0` → `2` | `TestSdkRetryIsDisabled` | **杀死**：error/timeout 子用例均为 `3 != 1` |
| M2 | `RunRequest` 增加 `model_provider` 并在 `submit_run` 写回服务配置 | `TestClientCannotSelectModelMode` | **杀死**：6 个失败；第一字段请求变 503，deepseek→offline 请求变 201，服务模式被改写 |
| M3 | 删除 `awrap_tool_call` 的 `tool_lock` | `TestToolCallsAreSerialized` | **杀死**：`peak 2 != 1` |
| M4 | `KnowledgeService.search` 回退为“先取 `top_k*4` 再过滤” | `TestScopeFilteringBeforeTopK` | **杀死**：`scoped` 返回 `[]` |
| M5 | `LLMToolAgent.retryable` 回退为仅 `MODEL_ERROR` | `TestModelTimeoutRetrySemantics` | **杀死**：2 个失败（首次超时不重试；预算 1 次时报 `TIMEOUT` 而非 `BUDGET_EXHAUSTED`） |
| M6 | 综合节点去掉 `planner_client=planner_client` | `TestSynthesisUsesInjectedClient` | **杀死**：真实构造桩被调用，`AssertionError: 不应构造任何真实模型客户端` |

### 2.2 额外独立实验

- **SingleToolAgent 超时重试一致性**：用仓库代码构造 `SingleToolAgent`（`max_retries=1`，假客户端第一次抛 `ErrorCode.TIMEOUT`、第二次返回文本）：`attempt=2`、物理 `calls=2`、账本 `used_model_calls=2`，最终因无工具事实报 `insufficient_evidence`（预期），说明重试与领域 Agent 一致。`single.yaml` 默认 `max_retries: 0`，默认配置下不会因此多调用。
- **重试与截止时间**：截止时间已过时 `deadline_exceeded`、`attempt=0`、物理调用 0；执行中到期时 `deadline_exceeded`、`attempt=2`，但第二次尝试在 `awrap_model_call` 的 deadline 检查处停止，**物理模型调用仍为 1 次**，没有越过截止时间发出请求。
- **P3-9 的 tool_call 场景**：直接调用 `ReportSynthesizer`（`executor=None`），假客户端返回带 `tool_calls` 的回合：结果为 `{'status': 'model_error'}`，无异常、无执行器访问；原因是 `tool_loop.py:217-218` 在 `turn.tool_calls and not self.model.specs` 时先抛 `_AgentStopped(MODEL_ERROR)`，且 `request.tool is None` + `agent_config is None` 的分支也会直接返回错误 ToolMessage，不触碰执行器。
- **旧提交 `5d0b18b`**：两个测试都把 `drop_readonly_role(self.engine, role_name)` 放进外层 `finally`；`drop_readonly_role` 在角色不存在时静默返回（`roles.py:166-177`）。我在设置 PG URL 的环境下跑完全集，结束后查询 `pg_roles` 中 `ro_%` 为空，确认断言失败路径也会清理。
- **PG 实验卫生**：测试库查询结果 `roles: []`、`alembic_version: []`、`public` 表仅 `alembic_version`，即已在 base；我没有创建额外角色或数据，也因此无需 `downgrade base`。

## 3. 逐条确认

### P2-2 `TestSdkRetryIsDisabled`（关闭）

- `backend/tests/test_task038r_langchain.py:115-126` 用 `build_chat_client(_config())` 的真实构造路径生成 `ChatOpenAI`，再把它底层的 `root_async_client._client` 替换为 `httpx.MockTransport`；`:104-112` 统计每次物理请求。
- `:144-168` 对正常、500、读超时三种模式分别断言：恰好 1 次物理请求，且 `budget.snapshot().used_model_calls == len(counter.requests)`。
- 我重做 `max_retries=2`：error/timeout 子用例得到 `3 != 1`，测试失败；证明不是恒真断言，也确实会观察到 SDK 的隐式重试。

### P2-3 `TestClientCannotSelectModelMode`（关闭）

- `backend/tests/test_api.py:161-195`：`model_provider`、`engine`、`model_name`、`max_model_calls`、`planner_provider` 五个字段均断言 422；`/api/meta` 与 `service.model_provider` 保持 `offline`；`/api/runs` 计数为 0。
- 第二个用例把服务端设为 `deepseek`，客户端传 `offline` 仍为 422 且服务端不变。
- 我重做“给 `RunRequest` 加字段并写回服务配置”：出现 503（缺 Key）、201（模式被改写）等失败，测试准确捕捉。

### P3-1 工具串行锁（关闭）

- `test_task038r_langchain.py:179-261` 用 `_SlowExecutor` 在 `execute` 中记录 `active/peak` 并 `await asyncio.sleep(0.05)`；断言 `peak == 1`，事件序列严格为 `start a → end a → start b → end b`。
- 去掉 `tool_lock` 后实测 `peak == 2`，测试失败。

### P3-2 检索先筛选后 top-k（关闭）

- `backend/tests/test_rag.py:803-855` 在临时目录生成两份 PDF：范围外文档 10 个 chunk、范围内文档 1 个命中。
- 测试先做前提校验：`service.search(query, top_k=8)` 的前 8 名**全部**来自 `doc_outside`；然后按 `prj_xinghui` 搜索，断言结果非空且只含 `doc_inside`。
- 我回退为旧“先取 `top_k*4` 再过滤”，`scoped` 返回 `[]`，测试失败。该语料确实能区分两种实现。

### P3-3 超时重试（关闭）

- `llm_agent.py:172` 与 `single/agent.py:184` 均改为 `retryable=error_code in {MODEL_ERROR, TIMEOUT}`，错误码仍报 `TIMEOUT`。
- `test_task038r_langchain.py:309-326`：第一次超时、第二次成功 → `ok`、`client.calls=2`、账本 2、`attempt=2`；预算 `max_model_calls=1` → `client.calls=1`、账本 1、`BUDGET_EXHAUSTED`。
- 独立探针确认 `SingleToolAgent` 同样是 `attempt=2`、物理调用 2、账本 2。
- 重试受同一个 `Budget` 约束（每次 `reserve_model_call`）；截止时间检查仍由未被修改的 `BaseAgent.handle`/`tool_loop.awrap_model_call` 执行，实测不会在截止后发出物理请求。

### P3-8 综合节点使用注入客户端（关闭）

- `investigation_demo.py:432-438` 现在把 `planner_client=planner_client` 传给 `_planner_client`；`_planner_client` 在 `planner_client is not None` 时直接返回（`:122-123`）。
- `test_task038r_langchain.py:334-381` 在不设 Key 的情况下注入假综合客户端，并把 `build_model_client_for_config` 替换为抛 `AssertionError`；断言构造器未被调用、`synthesizer.client is synthesis`、综合节点确实消费了该假客户端的 1 个回合。
- `grep` 确认 `investigation_demo.py` 中其余真实构造路径只有生产用的 `_deepseek_clients`（`:207`）和未注入时的 `_planner_client` 回退（`:133`）；当前 Web 只在 `model_provider=deepseek` 且无注入时走真实构造，符合预期。

### P3-9 死依赖与 `executor=None`（关闭，安全）

- `synthesis.py:82-83` 删除 `executor` 参数，`investigation_demo.py` 不再创建 `ToolExecutor`；`grep` 未发现其它 `synthesizer.executor` 引用。
- 实测模型返回 tool_call 时结果为 `model_error`，不会调用执行器；工具节点不可能在 `tools=()` 时被触发。
- `executor=None  # type: ignore[arg-type]` 目前安全，但类型契约被绕过：若未来有人用非空工具复用该循环，`awrap_tool_call` 的 `self.executor.execute` 会触发 `AttributeError`。更明确的做法是让 `run_tool_loop` 接受 `ToolExecutor | None` 并在有工具时断言非空（本轮 `tool_loop.py` 禁止修改，当前写法可接受）。

### P2-1 运营总览标注（关闭，有残留文案）

- 已落实：`index.html:29` 改为“演示：6 个 Agent / 模拟状态”，`:41` 日期加“（模拟数据）”，`:50` 页面说明“本页指标与任务均为模拟数据；真实争议调查请进入左侧…”，`:69` “模拟在线”，`:95` “模拟待审批”，侧栏入口改为“争议调查（真实工作台）”。
- `app.js`：每个指标标题追加“（模拟数据）”，`agentState` 改为“模拟在线”，审批按钮“模拟批准并派单/模拟驳回”，回执“演示执行回执”，通知与 toast 均改为模拟措辞。
- `grep` 确认 `static/ops/` 仍无任何 `/api/`、`fetch`、XHR、EventSource、WebSocket，任务仍只存 localStorage。
- 残留（P3 级，不阻断关闭）：`app.js:50-52` 的“协同中/已完成/已驳回”、`:301` 的“执行中/已完成”、`:167` 的“疏导方案已审批”、`:170` 的“巡检完成”，以及指标卡趋势文案“2 项待审批/需运营介入”未逐处加“模拟”。页面顶部与侧栏已有明确演示声明，因此不再构成上一轮 P2 的“无标注误导”；建议后续统一加前缀。
- `static/mall/mall-hologram.js:57` 已有“模拟数据”徽标，且无 API 调用；其标题“商场实时态势”与“实时”字眼相邻处有徽标，建议改为“模拟态势”但不需要按 P2 处理。

### P3-10 开发日志措辞（关闭）

- `git diff 9db6687 525413c -- docs/development_logs/development_log.md` 只有 Task 038 条目的一行变化：“均独立验证” → “均为实施者本地验证”，其它条目未动。

### P3-4/5/6/7/11（维持接受）

- **P3-4**：“有效 + 非法 tool_call 整体失败”的理由（宁可显式失败，不在已输出非法调用的回合执行部分工具）成立，且已在归档写明后续可补混合调用用例。
- **P3-5**：未暴露别名仍报 `tool_not_found`，但拒绝、审计、不执行均存在；区分 `tool_not_allowed` 属审计精度改进，理由成立。
- **P3-6**：provider 原始异常可能含凭据而不进报告，理由成立；代价是排障信息变少，属于可接受权衡。
- **P3-7**：只锁 `langchain` 高层版本，core/graph 仍为范围；归档写“本地全量回归兜底”，但没有 CI/启动期检查，这是五条接受理由中最弱的一条，本轮没有新增缓解。
- **P3-11**：项目代码只读 `ToolMessage.content`，不读 `status`（`langchain_client.py:129`、`tool_loop.py` 相关分支），因此“无功能影响”成立。

## 4. 新问题与残留

### P1

无。

### P2

无。返修未改变生产路径的预算、权限、可信上下文或审批语义；未发现新的付费调用缝或回归。

### P3（不阻断本轮关闭）

1. **`SingleToolAgent` 的超时重试没有专属回归测试**：本轮只测了 `LLMToolAgent`。我独立探针确认当前 Single 行为一致，但若有人只回退 `single/agent.py:184`，现有 731 项测试不会失败。建议补一个 Single 的超时重试用例，或把 `_ProbeAgent` 参数化覆盖两种 Agent。
2. **`executor=None # type: ignore` 的契约脆弱性**：当前综合节点安全（实测 tool_call → `model_error`），但类型上把 `ToolExecutor` 传成了 `None`；未来复用需改为 Optional 或空实现。
3. **P2-2 测试依赖 SDK 私有属性**：`chat_model.root_async_client._client` 属 `ChatOpenAI`/openai SDK 内部结构，升级 `langchain-openai`/`openai` 小版本可能让测试假失败，这与 P3-7 的版本风险相关。
4. **超时重试的 deadline 路径没有新回归测试**：我独立探针确认不会在截止后发出物理请求，但现有新测试只覆盖了预算，不覆盖 deadline。
5. **运营总览/3D 商场仍有未逐处标注的状态词**：见 P2-1 残留；不影响“页面已有明显演示声明”的结论。
6. **P3-7 仍无 CI 或启动期兼容检查**：接受理由成立但缓解最弱，建议在最终验收前至少增加版本组合记录。

## 5. 通过条件

- 本轮没有阻断性通过条件；上一轮 §7 的第 1 项（四个测试缺口）与第 2 项（运营总览标注/措辞）已满足。
- 建议的后续工作（不要求本轮再做）：
  1. 给 `SingleToolAgent` 补超时重试用例；
  2. 将综合节点的 `executor=None` 改成显式 Optional/空实现；
  3. 运营总览地图与任务状态词统一加“模拟”前缀，mall 标题由“实时态势”改为“模拟态势”；
  4. 为 deadline + 重试补一条回归断言；
  5. 记录 core/graph/openai 的组合版本，或在启动期做兼容检查。

## 6. 本轮限制与实验卫生

- **未调用真实 DeepSeek**，未验证真实付费链路；所有模型路径均为脚本客户端或 `httpx.MockTransport`。
- **未执行浏览器/JS harness**：本机无 node，`ui-model-cases.js` 未运行；网页结论来自静态审读与 `grep`，不是浏览器渲染验证。
- **变异实验在仓库外副本执行**：`max_retries`、`RunRequest`、`tool_lock`、RAG 旧实现、`retryable`、综合客户端注入六项均逐一复跑；仓库实现未被修改。
- **PG 实验卫生**：运行了带 `COMMERCIAL_PG_TEST_URL` 的完整套件；结束时 `pg_roles` 中 `ro_%` 为空、`alembic_version` 无行、`public` 仅 `alembic_version` 表，未留下角色或业务数据。我没有额外创建角色，因此无需主动清理；未执行 `downgrade base`，因为库已在 base。
- **仓库状态**：复查开始与结束时 `git status --porcelain` 均为空；未新增/删除/修改仓库文件。
- **未重做整轮 036–038 复查**：沿用上一轮对权限、预算、检索、审批、XSS 等的结论；本轮只确认返修是否关闭问题及是否引入新回归。
- **未声称最终验收通过**：本报告只是返修确认复查意见；最终验收还需真实模型、浏览器和正式评分审计等独立验证。
