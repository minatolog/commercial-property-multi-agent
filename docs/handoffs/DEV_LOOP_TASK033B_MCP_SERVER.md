# 任务单 033B：MCP 网关服务、CLI 与端到端测试

- 编写：2026-11-23，Claude Code。由 `scripts/dev_loop/` 执行。
- 前置：033A 已完成并提交（`backend/app/mcp_gateway/` 下已有 `profiles.py`、`identity.py`、`results.py`，`tests/test_mcp_gateway.py` 已有单元测试）。**先完整阅读这三个文件和现有测试，复用它们，不要另写一套。**
- 总体设计见 [`DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md`](DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md) §4.1、§4.2、§5；与本任务单冲突时以本任务单为准。
- SDK 是已安装的 `mcp==2.3.0`（v2）。写之前读 `D:/anacada/envs/commercial-agent/Lib/site-packages/mcp/` 里 low-level `Server`、stdio 传输和**内存客户端 / 内存传输**的源码，按实际 API 写。不要运行 `pip install`。

## 1. 只新增 / 修改这些文件

| 文件 | 内容 |
|---|---|
| `backend/app/mcp_gateway/server.py` | 构建 low-level `Server`；`list_tools` / `call_tool` 处理器；stdio 运行入口 |
| `backend/app/mcp_gateway/__init__.py` | 如需导出入口可改；不做导入副作用 |
| `backend/app/cli.py` | 新增子命令 `mcp-serve --transport stdio --client <档案名>`（`--transport` 本版本只接受 `stdio`） |
| `backend/tests/test_mcp_gateway.py` | **只追加**端到端测试，不删改 033A 的测试 |
| `backend/app/tools/executor.py`、`backend/app/runtime/types.py` | **原则上不改**。只有确实无法在 Trace 中区分 MCP 来源时才做最小改动（例如可选的元数据字段，默认值保持旧行为），并在总结里写明理由 |

其余文件一字不改，包括 033A 的 `profiles.py` / `identity.py` / `results.py`（发现它们有缺陷时，在总结里写明，交给审查方裁决，不要顺手改）。

## 2. 要求

### 2.1 `tools/list`

- 只列档案允许的工具；`name` 用**下划线别名**（`billing.statement.read` → `billing_statement_read`），`description` 取自注册表并注明原名；`inputSchema` = `input_model.model_json_schema()`；`outputSchema` = 033A 的 `envelope_output_schema(output_model)`。
- 原名调用也要接受（部分客户端会用原名）；别名之间、别名与原名之间冲突 → 构建 `Server` 时失败。

### 2.2 `tools/call`

```text
参数里有 RESERVED_PAYLOAD_KEYS 中的任何键 → 直接返回 isError 信封（status=denied，错误码用执行器同类拒绝的码），不调用执行器
→ 别名映射回原名（未知工具名 → isError + TOOL_NOT_ALLOWED 或 TOOL_NOT_FOUND，与执行器一致）
→ context = identity.resolve_context(会话)    # 绝不从参数读取身份
→ await executor.execute(原名, 参数, context=..., agent_config=profiles.to_agent_config(档案))
→ results.py 转成 CallToolResult
```

- **一个会话一个 `Budget` / `ToolExecutor`**，额度来自档案；Trace 里能看出来源：`run_id` 是 MCP 会话 ID，且能区分 `entrypoint=mcp` 与 `client=<档案名>`（优先靠 `run_id` / `trace_id` 的命名做到，不改执行器）。
- 网关代码任何地方都不能调用 `tool.invoke(`。
- 处理器里的异常不能变成成功结果：未预期异常 → `status=error`、`isError=True`，并且不把 Python 堆栈原样返回给客户端（写到 stderr 日志）。

### 2.3 CLI

- `python -m app.cli mcp-serve --transport stdio --client local_dev`：启动时向 **stderr** 打印 `identity.DEV_MODE_WARNING`；stdout 只留给 MCP 协议（不要往 stdout 打印任何其它内容）。
- 档案错误 → 非零退出码，stderr 写明原因，不启动服务。

## 3. 端到端测试（追加到 `test_mcp_gateway.py`）

用 SDK 的内存客户端连接 `server.py` 构建的 `Server`（不起子进程）。原 Prompt §5 的 10 点全部覆盖：

1. `tools/list` 只返回档案允许的工具（分别用 `local_dev` 与 `flowise` 档案验证）；`inputSchema` 与 `input_model` 一致；别名正确。
2. 一定经过执行器：替换某个工具的 `invoke` 并断言执行器 Trace 有这次调用的记录（`run_id` 为会话 ID）。
3. 参数带 `principal_id`、`permissions`、`project_ids` → `isError`，工具没有执行（`invoke` 未被调用，Trace 里也没有该工具的执行记录）。
4. 不在档案中的工具（例如 `flowise` 档案调用 `billing.arrears.calculate`）→ `isError` + `TOOL_NOT_ALLOWED`。
5. 超出会话预算（临时档案把额度设为 1，调用两次）→ 第二次 `BUDGET_EXHAUSTED`；新会话额度重新计算。
6. 跨项目数据（星汇主体查锦澜的合同）→ 范围拒绝，`isError`。
7. 工具执行失败（让 `invoke` 抛错）→ `isError: true`，`status` 不是 `ok`。
8. 金额在 `structuredContent` 中是字符串，精确到分。
9. 别名和原名调用的结果相同（比较去掉 `call_id` 后的信封）。
10. 档案配置错误时 `Server` 构建失败 / CLI 非零退出。

另加 1 个 stdio 冒烟测试：用 SDK 的 stdio 客户端以子进程方式启动 `python -m app.cli mcp-serve --transport stdio --client local_dev`，完成初始化、`tools/list` 和一次 `lease.lookup` 调用；断言 stderr 有开发模式提示。子进程要在测试结束时关闭。

## 4. 验收标准

- 只改第 1 节列出的文件；033A 的测试原样保留并通过。
- 全量回归通过；新测试没有 `skip`、没有恒真断言。
- 代码里没有 `tool.invoke(` 的调用；没有从调用参数读取身份；stdout 没有协议之外的输出。
- 新文件 UTF-8、LF。
- 总结里写明：实际使用的 `Server` 构造方式与处理器签名；是否改了执行器（没改就写没改）。
