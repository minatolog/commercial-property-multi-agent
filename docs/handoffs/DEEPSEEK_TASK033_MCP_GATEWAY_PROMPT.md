# 给 DeepSeek 的实施 Prompt：Task 033 MCP 工具网关（stdio 第一版）

> 系列任务：031（后端正确性）→ 032（业务流程工作台）→ **033（本任务）**。
> **前置条件：Task 031 已通过独立复查**（尤其是 Z2：失败的工具调用不能算成功，否则网关会把这个错误暴露给外部调用方）。032 是否完成不影响本任务。

请在当前 `D:\commercial-property-multi-agent` 仓库直接完成本任务：实现、自检、归档，然后汇报。**不提交、不推送、不部署。**

## 0. 目标

把现有的受控工具层以 MCP（Model Context Protocol）服务的形式开放，让 Flowise、阿里云百炼或其他 MCP 客户端可以**安全地**调用合同、账单、工单和文档检索工具。

**核心原则：MCP 只是一层很薄的协议外壳，`ToolExecutor.execute()` 仍然是唯一的调用入口。** 网关代码任何地方都不允许直接调用 `tool.invoke()`。白名单、权限、参数校验、保留键拦截、预算、超时重试、输出校验与项目范围检查，全部沿用执行器现有逻辑，执行器本身尽量不改。

## 1. 先核对仓库

完整阅读：`backend/app/tools/base.py`、`registry.py`、`executor.py`、`fixture_tools.py`、`knowledge_tools.py`；`backend/app/agents/base/contracts.py`（`AgentContext`）；`backend/app/runtime/types.py`（`ToolExecution`、`RESERVED_PAYLOAD_KEYS`）、`budget.py`；`backend/app/config/schema.py`；`backend/app/cli.py`。

运行 `git status`，保留无关的未提交改动和 `tools/flowise/`。

## 2. 依赖

- 使用 MCP 官方 Python SDK（PyPI 包名 `mcp`）。**锁定一个具体版本**，写进 `pyproject.toml`，并在归档中记录版本号。
- 这个 SDK 的 v1 和 v2 两条版本线 API 不同（v1 用装饰器注册处理器，v2 在 `Server(...)` 构造函数里传 `on_list_tools` / `on_call_tool`）。**以你实际安装的版本的官方文档为准**，不要混用两套写法。
- 工具是从注册表动态生成的，所以使用 SDK 的 low-level `Server`，不用 `@mcp.tool()` 这类装饰器。

## 3. 结构

```
backend/app/mcp_gateway/
    __init__.py
    server.py      # 构建 Server；list_tools / call_tool 处理器
    identity.py    # 会话 → AgentContext（本版本只有开发主体）
    profiles.py    # 客户端档案 → AgentConfig
    results.py     # ToolExecution → CallToolResult
backend/app/config/mcp_clients/
    local_dev.yaml
    flowise.yaml
backend/tests/test_mcp_gateway.py
```

CLI 新增子命令：`python -m app.cli mcp-serve --transport stdio --client local_dev`。

## 4. 设计要求

### 4.1 tools/list

- 只列出当前客户端档案允许的工具。
- `name`、`description` 取自注册表；`inputSchema` 来自 `input_model.model_json_schema()`。
- `outputSchema` 描述统一的结果信封（见 4.3），其中 `data` 部分来自 `output_model.model_json_schema()`。
- **工具名别名**：部分客户端不接受带点号的工具名。同时提供下划线别名（`billing.statement.read` → `billing_statement_read`），网关内部映射回原名，Trace 中记录原名。别名之间不能冲突，冲突时启动失败。

### 4.2 tools/call

```text
参数里出现身份字段（principal_id、permissions、project_ids 等保留键）→ 直接返回错误，不执行
→ AgentContext 只能从会话身份得到（本版本是开发主体），绝不从参数读取
→ 按客户端选择档案，转成 AgentConfig
→ executor.execute(原工具名, 参数, context=..., agent_config=...)
→ results.py 转成 MCP 结果
```

- 每个 MCP 会话一个独立的 `Budget`，额度来自客户端档案。
- 每次调用的 `run_id` 记录为“mcp 会话 ID”，便于在 Trace 中区分来源；在 Trace 或元数据里标记 `entrypoint=mcp` 和 `client=<档案名>`。

### 4.3 结果信封

```json
{
  "call_id": "...",
  "status": "ok | denied | error | timeout | budget_exhausted",
  "data": { ... },
  "evidence": [ ... ],
  "error": { "code": "...", "message": "..." }
}
```

- 同时放入 `structuredContent` 和一条 JSON 文本 `content`。
- 失败时设置 `isError: true`，并带上执行器的错误码。**任何失败都不能以成功的形式返回。**
- **金额必须保持为字符串**（例如 `"18036.00"`），`outputSchema` 中声明为 string；序列化时不得经过 float。补测试确认。
- 证据要原样带出（文档、版本、页码、条款号），外部调用方可以引用。

### 4.4 身份（本版本范围）

- 只实现 **stdio + 开发主体**：主体来自客户端档案或 `DEMO_PRINCIPAL_ID`，启动时向 stderr 打印“开发模式：固定主体，不可用于生产”。
- 在 `identity.py` 里预留清晰的接口（例如 `resolve_context(session) -> AgentContext`），给下一版 Streamable HTTP + OAuth 令牌校验使用。**本任务不实现 HTTP 传输和 OAuth**，也不要写一个假的令牌校验。

### 4.5 客户端档案

```yaml
# config/mcp_clients/flowise.yaml
name: flowise
enabled: true
principal_id: principal_ops_xinghui   # 仅开发模式使用
allowed_tools:
  - lease.lookup
  - billing.statement.read
  - property.work_orders.read
  - document.search
budget:
  max_tool_calls_per_session: 20
```

- 档案不存在、被禁用，或列出了未注册的工具 → 启动失败，并给出明确的错误信息。
- 档案的 schema 用 pydantic 定义，`extra="forbid"`。
- 本版本**只开放只读工具**。不暴露审批、调账、派单等任何写操作。

## 5. 测试（`test_mcp_gateway.py`）

用 SDK 自带的内存或 stdio 客户端做端到端测试，至少覆盖：

1. `tools/list` 只返回档案允许的工具，schema 与 `input_model` 一致，别名正确。
2. `tools/call` 一定经过执行器：替换某个工具的 `invoke` 并断言网关没有绕过执行器直接调用它（例如断言执行器的 Trace 有记录）。
3. 参数中带 `principal_id` 或 `permissions` → 错误，工具没有执行。
4. 不在档案中的工具 → `isError` + `TOOL_NOT_ALLOWED`。
5. 超出会话预算 → `BUDGET_EXHAUSTED`。
6. 跨项目数据 → 范围拒绝。
7. 工具执行失败 → `isError: true`，`status` 不是 ok。
8. 金额在 `structuredContent` 中是字符串，精确到分。
9. 用别名和原名调用的结果相同。
10. 档案配置错误时启动失败。

另外，用 MCP 官方 Inspector 或 SDK 客户端手动连接一次，把操作步骤和输出写进归档。

## 6. 边界

- 不改工具的业务逻辑，不改审批、评测、前端。
- 不接入 Flowise（只需在文档中写清楚 Flowise 如何以 stdio 方式连接，用 `flowise` 档案）。
- 执行器如果确实需要改动（例如增加 `entrypoint` 元数据），改动要最小化，并跑全量回归。

## 7. 归档与汇报

- 在 `docs/README.md` 登记 Task 033，建任务存档，更新开发日志、问题日志、`CURRENT_BASELINE.md`、路线图；在 `backend/README.md` 增加“MCP 网关”一节（启动命令、客户端档案、安全边界、下一版计划）。
- 运行全量回归和契约自检，记录实际数字。
- 汇报：每个测试点的结果、所用 SDK 版本、你认为下一版做 HTTP + OAuth 时最大的风险。**不要声称已通过最终验收。**

## 8. 如果启用了智能体团队协作

本任务规模小、文件集中，**建议由一名成员独立完成**，另一名成员只负责写测试和做最后的 Inspector 手动连接验证，不要多人同时改 `mcp_gateway/` 下的文件。
