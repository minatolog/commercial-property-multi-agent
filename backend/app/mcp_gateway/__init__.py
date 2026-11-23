"""MCP 工具网关（Task 033）。

网关是一层**很薄的协议外壳**：`ToolExecutor.execute()` 仍是唯一调用入口，
白名单、权限、参数校验、保留键拦截、预算、超时重试、输出校验与项目范围检查
全部沿用执行器现有逻辑。

本包包含：

- `profiles`：客户端档案（YAML）→ 强类型 `ClientProfile` → `AgentConfig`；
- `identity`：MCP 会话身份 → 可信 `AgentContext`（本版本仅开发主体）；
- `results`：`ToolExecution` → 统一结果信封 / MCP `CallToolResult`；
- `server`（Task 033B）：low-level `Server`、`tools/list` / `tools/call`
  处理器与 stdio 入口；一个连接一个 `Budget` / `ToolExecutor`。

本模块刻意不做任何导入副作用，导入本包不会读取配置、建档或启动服务。
"""
