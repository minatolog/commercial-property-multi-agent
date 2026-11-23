# Task 033（MCP 工具网关，stdio 第一版）独立复查

- **复查日期**：2026-11-23（Asia/Shanghai）。
- **复查者**：DeepSeek（独立复查模型；实施者、dev_loop 编码方与 dev_loop 审查方均不是本复查者）。本轮**只读**：不修改源码、测试、配置、评测题；不提交、不推送、不切分支、不 stash；实验在仓库外副本/临时目录完成。**未调用任何付费模型接口，未执行 `pip install`。**
- **复查依据**：[复查 Prompt](../handoffs/REVIEW_TASK033_PROMPT.md)、[原 Task 033 Prompt](../handoffs/DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md)、[033A 任务单](../handoffs/DEV_LOOP_TASK033A_MCP_CORE.md)、[033B 任务单](../handoffs/DEV_LOOP_TASK033B_MCP_SERVER.md)、[033C 任务单](../handoffs/DEV_LOOP_TASK033C_MCP_DOCS.md)、[Task 033 归档](../prompts/04_agents/2026-11-23_033_mcp_gateway.md)、实际代码/测试/证据。
- **代码基线**：`HEAD = 6588b5653c5f3b53cec6fed2f2a4776ff30a4950`（`57a0921` 033C 之后只多本复查 Prompt 的提交）。`git status --porcelain -uall` 只有允许排除的 `?? .claude/launch.json`；工作区干净。`git diff 483560a 57a0921 -- . ':(exclude)scripts/dev_loop'` 为 **21 个文件、3038 行新增、8 行删除**，与 Prompt 所述一致；`e4bc85e` 只改 `scripts/dev_loop`，不在范围。**`git diff 483560a 57a0921 -- backend/app/tools backend/app/runtime` 为空，执行器/`runtime` 未改，已确认。**
- **环境**：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18）；`backend/` 下运行，`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；已安装 `mcp==2.3.0` / `mcp-types==2.3.0`（`importlib.metadata` 确认），`mcp_types.version` 最新协议版本为 `2026-07-28`，SDK 客户端实际协商为 `2025-11-25`（见证据）。
- **方式**：不采信自报数字。独立复跑全量回归、`test_mcp_gateway.py`、契约自检、`check`、`stdio_probe.py`；用 SDK 内存客户端构造保留键/嵌套/大小写/身份/预算/跨项目/金额/证据/未知工具反例；在仓库外副本做 9 项变异测试；阅读已安装 SDK 源码确认 v2 API 与 schema 校验行为；逐项核对归档/README/文档数字与状态。

## 结论

**有条件通过。**

核心原则经独立验证成立：网关只经 `ToolExecutor.execute()` 调用工具；身份只从会话构造；保留键在执行器前拦截；失败以 `isError: true` 返回；金额保持十进制字符串；`tools/list` 与 `mcp-serve` 行为符合任务单；651 tests / 41 MCP tests / 70 契约 / `check` exit 0 与自报一致；stdio 证据可复现。**未发现 P1**。

发现 **2 项 P2**：① `document.search` 对跨项目 `lease_id`/`document_ids` 返回 `status=ok`、0 结果，而不是任务单要求的范围拒绝/isError（没有数据泄漏，但语义与测试点不符；跨项目测试只覆盖了 `billing.statement.read`）；② 未知工具名没有测试守护——我在仓库外把“未知名回退到 `lease.lookup`”的变异后，41 个测试全部通过。另有若干 P3（开发模式 `DEMO_PRINCIPAL_ID` 边界与文档、会话缓存/拒绝审计、启动期主体校验、测试覆盖边界、代码归档 commit 状态陈旧）。条件见 §4。

## 1. 独立验证结果

| 验证项 | 我实际运行/看到的结果 | 与自报对比 |
|---|---|---|
| 全量回归 | `-X utf8 -m unittest discover -s tests -p 'test_*.py'` → **Ran 651 tests in 42.510s，OK (skipped=1)** | 自报 651，**一致** |
| `test_mcp_gateway.py` | `-X utf8 -m unittest tests.test_mcp_gateway` → **Ran 41 tests in 1.701s，OK**；文件内 41 个 `def test_` | 自报 41，**一致** |
| 契约自检 | `python tests/smoke_agent_contracts.py` → **全部通过：70 项检查** | 自报 70，**一致** |
| `python -m app.cli check` | exit 0；planner 等既有检查不变 | 自报 exit 0，**一致** |
| `stdio_probe.py` | 在仓库根按脚本说明运行；输出 **302 行**；与 `stdio_probe.txt` 归一化 `call_id`/时间后 **0 行差异** | 自报“只有随机 call_id 不同”，**一致** |
| 执行器唯一入口 | `git diff 483560a 57a0921 -- backend/app/tools backend/app/runtime` 为空；`grep 'tool.invoke('` 在 `app/mcp_gateway` 无命中；所有调用只经过 `ToolExecutor.execute()` | 一致 |
| SDK API | 安装版本 `mcp==2.3.0`；代码使用 `Server(name/version/lifespan/on_list_tools/on_call_tool)`、`ServerRequestContext.lifespan_context`、`stdio_server`；未发现 v1 装饰器写法 | 一致 |
| `tools/list` | 本地档案 5 个工具、`flowise` 4 个；别名无点号；`inputSchema` 与 `input_model.model_json_schema()` 相等；`outputSchema` 与 `envelope_output_schema()` 相等；描述含原名 | 一致 |
| 保留键（顶层） | 9 个保留键逐个作为 `lease_lookup` 参数：全部 `isError=true/status=denied/code=permission_denied`；**Trace 数 0**，工具未执行 | 一致；覆盖比现有测试更全 |
| 保留键（大小写/嵌套） | `Principal_ID`/`PROJECT_IDS`/`Permissions`、嵌套 `filters.project_ids`/`metadata.principal_id`：全部 `is_error=true/status=error/code=invalid_tool_arguments`；由 `input_model` 的 `extra="forbid"` 挡住，未执行工具 | 行为安全；现有测试未覆盖这些输入（P3） |
| 未知工具 | `does_not_exist`、`billing.statement.write`、`Billing_Statement_Read`：全部 `isError=true/status=denied/code=tool_not_found`，无数据 | 当前行为正确；**测试没有覆盖未知名**，变异可绕过测试（P2-2） |
| 未预期异常 | `TestMcpGatewayUnexpectedError` 独立审读：补丁使执行器抛异常 → 客户端只收到 `status=error` 信封，堆栈只写 stderr；未泄漏 `gateway-secret-detail` | 一致 |
| 预算（同一连接） | 临时档案额度 1：保留键拒绝 → denied（不消耗）；第一次 `lease.lookup` → ok；第二次 → `budget_exhausted`；之后保留键 → denied；`used_tool_calls=1`、Trace 仅 2 条（执行成功 + 预算失败） | 与测试一致；被网关预拦截的调用不消耗额度，我判断合理；但无 Trace/审计记录（P3） |
| 跨项目（其他工具） | 星汇主体查 `lease_jl_b101_2025`：`lease.lookup`、`billing.statement.read`、`billing.arrears.calculate`、`property.work_orders.read` 均 `denied/project_scope_denied`；`unit_code=B-101` 也 denied | 与现有测试部分一致 |
| **跨项目（document.search）** | `document.search` 带 `lease_id=lease_jl_b101_2025` → **`isError=false`、`status=ok`、`data.result_count=0`、evidence=[]**；带本租约 + 锦澜 `document_ids` 同样 ok/0 | **不符合任务单“跨项目数据 → 范围拒绝/isError”**（P2-1；无数据泄漏） |
| 金额 | 5 个工具真实调用：`lease.lookup` 的 `deposit_amount="40000.00"`、账单 `52596.00/34560.00/18036.00/756.00`、欠费三项均为 **str**；递归扫描无金额 float。`document.search` 只有 `score` 是 float（检索分数，不是金额） | 一致；现有测试只覆盖账单（P3 覆盖边界） |
| 证据 | 真实 `document.search` 调用返回 1 条结果：`page=26`、`clause_id=附件B`、`document_id/version/project/lease/excerpt` 均在 `data`，`evidence.fields` 原样含页码、条款号、摘录、文档版本；`structuredContent` 与 JSON 文本相同 | 证据原样带出；现有测试未测这条真实路径（P3） |
| 失败信封与 SDK | 低层 SDK **不按工具 inputSchema/outputSchema 校验**：缺参 `{}` 未被 SDK 拒绝，而是到达执行器返回 `invalid_tool_arguments` 信封；`data=null` 的失败信封被 SDK 客户端正常接收。`get_tool_input_schema` 只用于 HTTP 头部 `Mcp-Param-*` 校验，不用于 stdio | 代码审读 + 实测；测试测的是网关/执行器逻辑，不是 SDK 的 schema 拒绝 |
| stdout | 档案不存在、非法 transport 均 exit 2 且 **stdout 为空**、stderr 有明确错误；正常启动只 stderr 打开发模式提示；stdio probe 的 stdout 只承载协议；未预期异常不把堆栈返回客户端 | 一致 |
| stdio 子进程 | `TestMcpGatewayStdio` 用真实子进程 + SDK 客户端；运行后无残留 `mcp-serve` 进程（检查 `Win32_Process`）；SDK `stdio_client` 源码含 close stdin/terminate/kill 树；测试结束正常 | 一致 |
| 变异测试（仓库外副本） | 见 §3；9 项中 8 项被现有测试抓到；“未知工具名回退到 `lease.lookup`”**未被抓到** | 与“全部被抓到”的自报**不同**，发现 P2-2 |

## 2. 逐项对照 §4

### 2.1 执行器是唯一入口

- `app/mcp_gateway/` 中无 `tool.invoke(`、无直接 fixture/仓库读写、无自写权限判断；`server.py` 只做档案/别名/身份/协议转换，最终调用 `ToolExecutor.execute()`。
- `profiles.py` 的白名单、`identity.py` 的上下文、`results.py` 的信封都不替代执行器的权限/预算/范围检查；网关新增检查（保留键预拦截、只读档案、别名冲突）只会更严。
- `git diff 483560a 57a0921 -- backend/app/tools backend/app/runtime` 为空，执行器与 `runtime/types.py` 真的没改。**通过。**

### 2.2 身份与参数

- 身份只从 `SessionIdentity` 构造：`create_session()` 从档案或 `DEMO_PRINCIPAL_ID` 取主体，`resolve_context()` 从 **fixture 主体记录**取 `project_ids`/`permissions`，不读取 `tools/call` 参数（`identity.py:66-116`；`server.py:337-342`）。顶层保留键 9 个全部 denied，未执行；嵌套/大小写变体被 `input_model` 的 `extra="forbid"` 挡住（我的实测），没有找到绕过。
- 语义差异：网关保留键返回 `permission_denied`/`denied`，执行器对同类输入返回 `invalid_tool_arguments`。任务单 `033B §2.2` 明确要求网关用 `denied`，且 README 写了 `permission_denied`；**合理，文档已说明**。
- **`DEMO_PRINCIPAL_ID` 边界**：它确实可以在启动时把主体换成任意 fixture 主体；我用 `principal_finance_jinlan` 启动后，`billing.statement.read` **能读锦澜账单**，星汇租约被拒。它不是 `tools/call` 参数路径，stdout/stderr 也没有认证；警告存在（stderr、README、归档）。我把它列为 P3（如果“能配置服务进程环境的一方”被视为不可信外部方，则升级为 P1；当前 stdio 开发模式明确不是这样）。

### 2.3 协议与结果

- v2 API 用法正确（`Server(on_list_tools=..., on_call_tool=..., lifespan=...)`、`ServerRequestContext.lifespan_context`），无 v1 装饰器；`CallToolResult` 使用 `content` / `structured_content` / `is_error`。
- **SDK 自身不校验工具的 `inputSchema` / `outputSchema`**：`mcp/server/lowlevel/server.py` 只注册处理器；`ServerRunner` 校验 JSON-RPC 参数与结果类型，不按 per-tool schema 校验；`get_tool_input_schema` 只在 HTTP `Mcp-Param-*` 头部路径使用。我的缺参调用返回网关错误信封而不是 JSON-RPC error，确认了这一点。`outputSchema` 是给外部客户端的声明，失败信封 `data=null` 符合我们自己 `jsonschema` 测试；测试没有被 SDK 的拒绝“代做”。
- 结果状态映射：只有 `ToolExecution.ok` 且无 error 才是 `ok`；未知状态/错误码落 `error`；`isError` 与 `status != ok` 一致；`structuredContent` 与 JSON 文本同源（我的 5 个工具真实调用均 `content_same=true`）。
- 金额：所有金额字段为字符串，递归扫描无 float；`outputSchema` 中 `Decimal` 被 `_StringDecimalSchema` 强制声明为 `string`；唯一 float 是 `document.search.score`，不是金额。
- 证据：真实 `document.search` 带出页码/条款/摘录/文档版本；执行器补齐 `source_tool/run_id/project_id/collected_at` 等。
- stdout：CLI 启动错误/正常启动/协议路径均只 stderr 提示，stdout 未见协议外内容；未预期异常不返回堆栈。

### 2.4 档案、预算与会话

- 档案错误：文件不存在、禁用、未注册工具、非只读工具、多余字段、名称不一致、空/重复白名单、非正预算均在启动期失败；我的 CLI `--client no_such_client` exit 2、stdout 空、stderr 指明档案。
- 只读约束：`READ_ONLY_TOOLS` 唯一常量（`profiles.py:42-50`），同时校验“已注册”和“只读”，未来写工具即使注册也会被档案拒绝；代码里没有第二套只读判断。
- 预算按连接：`GatewayServer._lifespan` 每个连接 `Budget`；同一连接额度正确，跨连接重新计算（测试通过）；被网关预拦截的保留键/未知工具不消耗额度（我判断合理：没有执行工具），但它们也没有 Trace/审计（P3）。
- `GatewayServer._sessions` 只追加、不清理（`server.py:218,271`）：stdio 下一般一进程一连接，影响小；HTTP 版本同进程多连接/会话恢复时会累积（P3）。
- 别名：原名与下划线别名映射；构建期检查别名冲突；原名/别名结果除 `call_id` 等易变字段外等价（测试通过）。

### 2.5 测试有效性

- 41 个测试无 `skip`、无空断言；`TestMcpGatewayUnexpectedError` 是复核者补的，我单独审读并通过：异常→error 信封、堆栈只在 stderr、客户端文本不含秘密。
- 我在仓库外副本（`D:\review033_copy`，复制 fixture）逐项变异，结果见 §3：8/9 被现有测试抓到；**未知工具名回退到 `lease.lookup` 存活**。这说明测试对“未知工具必须报错”这一条没有守护；当前实现本身是对的（我直接调用返回 `tool_not_found/denied`），但未来改动可能静默路由到允许工具。
- 现有测试未覆盖：`document.search` 真实调用/证据、嵌套/大小写保留键、未知工具名、CLI 错误路径 stdout、未知主体启动、`_sessions` 清理；部分是 P3 覆盖缺口。

### 2.6 文档与证据

- **数字一致**：`stdio_probe.txt` 我独立重跑后除随机 `call_id` 外 0 行差异；`unittest.txt` 651/42.536s；`smoke.txt` 70；归档/README/基线/路线图/开发日志均写 651、41、70（`docs/README` 033 行、`CURRENT_BASELINE` 最新证据行、`backend/README`、`PROJECT_DEVELOPMENT_ROADMAP` §17）。
- **状态措辞**：033 写“已实施并自检，待独立复查；未推送”，未写“已通过/已验收”，符合要求。
- **文档不一致（P3）**：归档 §1/§10 仍写 033C `Pending`、本轮“未提交”，但实际 033C 已提交 `57a0921`（当前 HEAD 只多本 Prompt 提交）；开发日志 033 条、问题日志 033 条也写“未提交/推送”。另外 `backend/README:184` 说“身份只由档案（开发模式）决定”，同一节 `:160` 又说主体来自档案或 `DEMO_PRINCIPAL_ID`，与代码和我的实测矛盾。
- **Flowise 说明**：命令、`cwd=backend`、`--client flowise`、只读白名单、预算、stdout/stderr 说明可操作；未在 Flowise 实连，归档已声明。
- **下一版最大风险**：归档 §9.2 的“身份与传输会话生命周期错配”具体、成立（会话恢复/重连复用旧主体与预算）；我补充 `_sessions` 增长、预拦截拒绝无审计/无速率限制，HTTP 版需要一起处理（P3）。

## 3. 变异测试（仓库外副本）

在 `D:\review033_copy\backend` 复制 fixture 后，逐项用原文件恢复再变异，运行 `python -m unittest tests.test_mcp_gateway`：

| 变异 | 结果 |
|---|---|
| 关闭 `_dispatch` 的保留键检查 | **抓到**（reserved 测试得到 `error` 而非 `denied`） |
| 未知执行状态改为 `ok` | **抓到**（未知状态断言失败） |
| `tools/list` 改为列出所有注册工具 | **抓到**（列表/白名单断言失败） |
| 所有连接共享一个 Budget | **抓到**（会话预算重置断言失败） |
| `structuredContent` 与文本不同源 | **抓到**（content vs structured 断言失败） |
| 忽略 `DEMO_PRINCIPAL_ID` | **抓到**（身份来源测试失败） |
| 跳过非只读工具校验 | **抓到**（测试专用写工具未被拒绝） |
| 未预期异常不再包成 error 信封 | **抓到**（客户端收到协议错误/堆栈） |
| **未知工具名回退到 `lease.lookup`** | **未被抓到**：41 个测试全部通过；当前正常实现则返回 `tool_not_found`。这是 P2-2 的直接证据 |

## 4. 问题清单

### P1

无。身份参数不能进入 `AgentContext`；保留键/嵌套/大小写输入没有绕过；失败不会以成功返回；跨项目数据没有泄漏（`document.search` 返回空）；金额不经过 float。

### P2

**P2-1 `document.search` 对跨项目目标返回 `ok` 0，而不是范围拒绝；跨项目测试只覆盖账单。**

- 位置：`backend/app/tools/knowledge_tools.py:92-135`（`_resolve_allowed` 用调用方给的 `lease_id`/`document_ids` 解析文档集合，但没有校验该租约是否属于 `context.project_ids`）；`backend/app/mcp_gateway/server.py:315-350` 只做保留键/别名/身份，不做目标范围检查。
- 复现（SDK 内存客户端，`local_dev` 星汇主体）：
  - `document_search {"query":"免租期","lease_id":"lease_jl_b101_2025"}` → `isError=false`、`status=ok`、`data.result_count=0`、`evidence=[]`；
  - `document_search {"query":"免租期","lease_id":"lease_xh_a301_2025","document_ids":["doc_jl_b101_contract"]}` → 同样 `ok/0`。
  - 同主体的 `lease.lookup`/`billing.*`/`property.work_orders` 对锦澜租约均为 `denied/project_scope_denied`。
- 影响：没有数据泄漏（服务层按 `context.project_ids` 过滤），但 `[DEV_LOOP_TASK033B_MCP_SERVER.md](../handoffs/DEV_LOOP_TASK033B_MCP_SERVER.md) §3 第 6 点`要求“跨项目数据 → 范围拒绝，isError”；外部调用方也无法区分“目标越权”和“没有匹配文档”。现有 `tests/test_mcp_gateway.py:856-872` 只测 `billing.statement.read`。
- 建议：在 `DocumentSearchTool._resolve_allowed` 中解析 `lease_id` 的项目并与 `context.project_ids` 比较，越权抛 `ProjectScopeDeniedError`；或网关对声明的目标做范围预检（但不要把业务判断搬进网关），并补 `document.search` 跨项目测试。

**P2-2 未知工具名没有测试守护；变异“未知名回退到 `lease.lookup`”后 41 个测试全部通过。**

- 位置：`backend/app/mcp_gateway/server.py:334-335` 当前正确地 `_call_names.get(requested_name, requested_name)` 交给执行器；但 `tests/test_mcp_gateway.py` 只测了“已注册但不在档案”的 `billing.arrears.calculate`（`:788-810`），没有测任意未知名（`does_not_exist`）。
- 我的独立反例：正常代码对一个未知名返回 `isError=true/status=denied/code=tool_not_found`（安全）；在仓库外副本把 `_dispatch` 改成未知名回退 `lease.lookup` 后，**41 个测试全部通过**，即测试没有守护“未知名绝不能执行允许工具”。
- 建议：补一条 `call_tool("does_not_exist", {...})` 断言 `isError` + `TOOL_NOT_FOUND`/`TOOL_NOT_ALLOWED`，并断言 Trace/执行器未被调用；这也覆盖 033B 任务单 §2.2 的未知工具要求。

### P3

1. **`DEMO_PRINCIPAL_ID` 是开发模式边界，文档/提示不够精确**：`identity.py:78-84` 可用环境变量把主体换成任意 fixture 主体（我用 `principal_finance_jinlan` 成功读取锦澜账单，星汇租约被拒）；它不是 `tools/call` 参数路径，而是启动环境，stdout/stderr 无认证。stderr 只打印“固定主体，不可用于生产”，不打印实际主体/来源；`backend/README:160` 说来自档案或 env，`:184` 又说“身份只由档案决定”，自相矛盾。建议提示中打印 `principal_id` 与 `source`，并明确移除生产 HTTP 的 env 兜底（归档 §9.2 已有方向）。
2. **`_sessions` 只增不清理**：`server.py:218,271` 每个连接 append，stdio 单连接影响小；HTTP 版本同进程多连接/恢复会累积；归档 §9.2 未把这一点列入。建议在 lifespan 结束移除，并评估内存上限。
3. **被网关预拦截的拒絕没有 Trace/审计**：保留键/未知工具在执行器前直接 `_failure`，我的预算测试里 denied 前后 Trace 仍为 0；这不消耗预算可接受，但外部网关的安全事件无记录、也没有速率限制。建议至少记录拒绝计数/日志（不写业务 Trace 也可以）。
4. **档案主体在启动期不校验**：临时档案 `principal_id=nonexistent` 时 `load_gateway` 构建成功，首次调用才返回 `record_not_found`；`DEMO_PRINCIPAL_ID` 同理。建议启动期检查主体存在，避免“服务起来了但所有调用失败”。
5. **测试覆盖边界**：只测 3 个保留键（`tests/test_mcp_gateway.py:752-785`），未测大小写/嵌套；未测 `document.search` 真实调用/证据；未测 CLI 错误路径 stdout；未测 `_sessions` 清理/未知主体启动。我的独立测试表明这些行为目前安全/可用，属于 P3 覆盖缺口。
6. **文档状态陈旧**：归档 `:9,221` 仍写 033C `Pending`/“未提交”；`docs/development_logs/development_log.md:15`、`docs/issues/issue_log.md:9` 也写“未提交”；实际 033C 已提交 `57a0921`。问题日志还写“本轮未发现产品代码或测试问题”，与 P2-1/P2-2 不符。数字（651/41/70）与状态“待独立复查”本身正确。

## 5. 通过条件与建议

1. 修复 P2-1：让跨项目 `document.search` 返回范围拒绝/isError（或在任务/归档中明确说明“空结果”是可接受语义，但任务单要求 isError，当前应按要求实现），并补测试。
2. 修复 P2-2 的测试缺口：补未知工具名断言；建议同时补嵌套/大小写保留键、`document.search` 证据、CLI stdout 错误路径的测试。
3. P3：在启动提示打印主体/source；清理 `_sessions`；记录预拦截拒绝；启动期校验主体；统一归档/开发日志/问题日志的 033C 提交状态与 README 的 env 描述。
4. 完成后再跑 651 tests / 70 契约 / `check`，并重跑 `stdio_probe.py` 对比证据。
5. **不要把本轮当作最终验收**：HTTP + OAuth/TLS、Flowise 实连、正式真实评测与人工量表仍未完成；本报告只覆盖 stdio 第一版的独立复查。

## 6. 本轮限制

- 未调用付费模型接口；网关不涉及模型。
- 未在 Flowise 或 MCP Inspector 中实际连接；只使用官方 SDK stdio 客户端和内存客户端。
- 未实现/验证 Streamable HTTP、OAuth、TLS、并发会话恢复；相关风险仅作代码/归档审读。
- 变异测试在仓库外副本（复制 backend 与 fixture）完成，未改工作区；测试结果依赖当前 Windows/Python 环境。
- 未修改任何源码/测试/配置；只新增本报告。
