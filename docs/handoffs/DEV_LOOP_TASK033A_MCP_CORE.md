# 任务单 033A：MCP 网关基础（客户端档案、身份、结果信封）

- 编写：2026-11-23，Claude Code。由 `scripts/dev_loop/` 执行（编码方 DeepSeek，审查方 Claude）。
- 总体设计以 [`DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md`](DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md) 为准（先完整阅读其 §0、§2、§4、§6）；**本任务单只做其中的基础三件**，与原 Prompt 冲突时以本任务单为准。
- 后续：033B 做 `server.py`、CLI 与端到端测试；033C 做文档归档。**本任务不要写 `server.py`，不要改 CLI，不要改任何文档。**

## 0. 已确认的事实（不必重新核实）

- 环境里已安装 MCP 官方 Python SDK **`mcp==2.3.0`**（v2 版本线）。写代码前先读已安装包的源码确认 API：`D:/anacada/envs/commercial-agent/Lib/site-packages/mcp/`（至少看 `types` / `mcp_types` 里的 `Tool`、`CallToolResult`、`TextContent`）。**不要按 v1 的写法写**；不要运行 `pip install`。
- 执行器：`ToolExecutor(registry, budget, trace_log=...)`，预算在构造时注入；`await executor.execute(tool_name, payload, context=..., agent_config=...)` 返回 `ToolExecution`。**一个 MCP 会话 = 一个 `Budget` = 一个 `ToolExecutor`。**
- 可信上下文：用现成的 `TrustedContext.from_principal(principal_record, trace_id=...)` 和 `.to_agent_context(run_id=...)`（用法见 `backend/app/evaluation/baselines.py` 的 `_context`）；主体记录来自 `FixtureRepository.load().principal(principal_id)`。
- `AgentConfig` 的必填字段（`capabilities`、`model_provider`、`model_name`、`prompt_path` 等）对网关没有意义，参照 `baselines.py` 的 `_config` 填固定占位值（`model_provider: "offline"`、`model_name: "none"`），并在代码注释里写明原因；`allowed_tools` 取自档案。
- 已注册工具：`lease.lookup`、`billing.statement.read`、`billing.arrears.calculate`、`property.work_orders.read`、`document.search`，全部只读。保留键集合是 `app.runtime.types.RESERVED_PAYLOAD_KEYS`。

## 1. 只新增 / 修改这些文件

| 文件 | 内容 |
|---|---|
| `backend/pyproject.toml` | `dependencies` 增加 `"mcp==2.3.0"`（加一行注释：Task 033 MCP 网关，v2 版本线）。不改其它依赖 |
| `backend/app/mcp_gateway/__init__.py` | 包说明（一段 docstring），不做导入副作用 |
| `backend/app/mcp_gateway/profiles.py` | 客户端档案 |
| `backend/app/mcp_gateway/identity.py` | 会话身份 |
| `backend/app/mcp_gateway/results.py` | `ToolExecution` → 结果信封 / `CallToolResult` |
| `backend/app/config/mcp_clients/local_dev.yaml` | 档案：开放全部 5 个只读工具，`max_tool_calls_per_session: 20` |
| `backend/app/config/mcp_clients/flowise.yaml` | 档案：内容照原 Prompt §4.5 |
| `backend/tests/test_mcp_gateway.py` | 本任务的单元测试（033B 会在同一文件追加端到端测试） |

其余文件一字不改。

## 2. 要求

### 2.1 `profiles.py`

- pydantic 模型 `ClientProfile`（`extra="forbid"`, `frozen=True`）：`name`、`enabled`、`principal_id`、`allowed_tools`（非空、不重复）、`budget.max_tool_calls_per_session`（正整数）。
- `load_profile(name, *, registry, config_dir=None) -> ClientProfile`：档案文件不存在、`enabled: false`、列出未注册的工具、`name` 与文件名不一致 → 抛出明确错误（用项目现有的 `AgentError`/`ErrorCode` 或专门的配置异常，错误信息要写出是哪个档案、哪一项）。
- `to_agent_config(profile) -> AgentConfig`：只做转换，不放宽白名单。
- **只读约束**：本版本只允许上面 5 个只读工具；若档案列出其它已注册工具也要拒绝（防止以后注册写工具时被顺手暴露）。

### 2.2 `identity.py`

- `SessionIdentity`（会话 ID、客户端名、主体 ID、来源）和 `resolve_context(session) -> AgentContext`。
- 本版本只有开发主体：主体来自档案的 `principal_id`，环境变量 `DEMO_PRINCIPAL_ID` 非空时覆盖它；来源字段如实记录（`profile` / `env:DEMO_PRINCIPAL_ID`）。
- `run_id` 记成 MCP 会话 ID（例如 `mcp_<client>_<随机>`），`trace_id` 每次调用唯一；在 docstring 里写清下一版 Streamable HTTP + OAuth 时要替换的是哪一步。**不要写假的令牌校验。**
- 提供 `DEV_MODE_WARNING` 常量，内容为“开发模式：固定主体，不可用于生产”（033B 启动时打印到 stderr）。

### 2.3 `results.py`

- 信封字段与原 Prompt §4.3 一致：`call_id`、`status`（`ok | denied | error | timeout | budget_exhausted`）、`data`、`evidence`、`error`（`code`、`message`）。
- `ToolExecution` 的状态 / 错误码到 `status` 的映射写成一张表，**未知情况一律落到 `error`**；只有执行器判定成功才是 `ok`。
- 生成 `CallToolResult`：`structuredContent` 放信封，`content` 放一条同内容的 JSON 文本，失败时 `isError=True`。
- **金额必须是字符串**：序列化走 pydantic 的 JSON 模式或自写 `Decimal → str`，任何路径都不能经过 `float`。
- 证据原样带出（文档、版本、页码、条款号等，以 `ToolExecution` 里实际有的字段为准）。
- `envelope_output_schema(output_model) -> dict`：信封的 JSON Schema，`data` 部分引用 `output_model.model_json_schema()`，金额字段在 schema 里是 `string`。失败信封（`data` 为空）也必须符合这个 schema。

## 3. 测试（`test_mcp_gateway.py`，本任务只写单元测试）

至少覆盖：

1. 档案：正常加载；文件不存在、`enabled: false`、未注册工具、非只读工具、多余字段、名称不一致 → 各自报错（用临时目录写坏档案，不改仓库里的档案）。
2. `to_agent_config` 的 `allowed_tools` 与档案一致。
3. 身份：默认取档案主体；设置 `DEMO_PRINCIPAL_ID` 后被覆盖且来源如实；`AgentContext` 的项目范围来自主体记录，不来自任何调用参数。
4. 结果：成功执行 → `ok`、`isError` 为假；拒绝 / 超时 / 预算耗尽 / 其它错误 → 对应 `status`、`isError` 为真、带执行器错误码；**构造一个未知状态 → 落到 `error`**。
5. 金额：用真实执行器调用 `billing.statement.read`（星汇项目合同），`structuredContent` 里的金额是字符串且精确到分；同时断言 JSON 文本里也没有浮点写法。
6. 失败信封与成功信封都能通过 `envelope_output_schema` 的校验（用 `jsonschema` 校验，它是 `mcp` 的依赖，已安装）。

## 4. 验收标准

- 只改第 1 节列出的文件。
- 全量回归通过（调度脚本会运行）；新测试没有 `skip`、没有恒真断言。
- 代码里没有 `tool.invoke(` 的调用；没有从调用参数读取身份。
- 新文件 UTF-8、LF。
- 结束时的总结里写明：你读了 `mcp` 2.3.0 的哪些源码文件确认 API，`CallToolResult` 的字段名实际是什么。
