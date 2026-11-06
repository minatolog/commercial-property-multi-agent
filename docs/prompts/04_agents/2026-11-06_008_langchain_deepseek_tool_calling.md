# 2026-11-06_008_LangChain、DeepSeek 模型适配与真实工具调用闭环

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：008（正式 Prompt 3）
- **模块**：04_agents
- **状态**：**DeepSeek 自检通过**（离线闭环已验证；真实 DeepSeek 调用受凭据限制，未验证）
- **需求基线**：[Agent-first V1.0](../../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)、[MVP scope](../../product/mvp_scope_v2.md)、[Runtime contracts](../../architecture/agent_runtime_contracts.md)
- **前置任务**：007（DeepSeek 自检通过）
- **Git Commit**：`Pending`

## 2. 任务目标和背景

Task 007 交付了离线 Runtime 与受控工具执行，但"Agent 会思考并选择工具"这件事仍由 `ScriptedToolAgent` 的固定脚本模拟。

本任务接入 **LangChain + DeepSeek**，并把"模型决定调用哪个工具 → 受控执行 → 结果回传 → 给出最终答案"变成真实闭环，同时实现**单 Agent + Tools 基线**的最小可用版本。它是 Task 009 多 Agent 图、Task 013 三基线评测的共同前置。

## 3. 原始用户 Prompt

````
你现在接手 commercial-property-multi-agent 项目的后续开发。项目所有者决定取消 Codex 逐任务审查环节，
由你负责实现、验证、记录和推进后续任务。

任务顺序以仓库路线图和 Prompt 归档为准，预计涉及：

- Task 008：LangChain、DeepSeek 模型适配和真实 Tool Calling 闭环
...

每个任务的执行要求：
1. 一次只推进一个任务，保持模块边界清晰、低耦合、Agent 可插拔、配置独立。
2. 按 docs/README.md 的编号规则分配下一个全局唯一 Prompt 编号，并将完整 Prompt 归档到正确目录。
3. 实现当前任务的最小完整垂直切片，不顺手扩张到无关功能。
4. 为关键行为补充自动化验证；运行本任务相关测试和适当的现有回归测试，记录真实命令与结果。
5. 每个任务结束后更新对应 Prompt 归档、开发日志、路线图、检查点等。
6. 只有真实实现和验证完成后，才可把任务标记为"DeepSeek 自检通过"。
7. API Key 等只从安全的环境变量或本地忽略文件读取。
8. 没有外部凭据时，完成可验证的接口、Fake/离线测试和配置说明；准确标出真实服务验证受凭据限制。
10. 不执行破坏性 Git 操作；不改写历史，不 force push。
````

> 原始 Prompt 为长文，此处保留与本任务直接相关的约束段落；完整原文见用户消息（2026-11-06）。任务范围以仓库路线图 `Prompt 3 / Task 008` 小节为准。

## 4. AI 实际执行的主要步骤

1. 读取 `PROJECT_DEVELOPMENT_ROADMAP.md`、Task 007 归档与自检报告，确认 Task 008 范围：LangChain + DeepSeek 适配、有限轮次工具循环、单 Agent + Tools 基线。
2. 检查环境：pip 可访问索引；`DEEPSEEK_API_KEY` **未设置**；无 PostgreSQL。
3. 安装 `langchain-core>=1.0`、`langchain-openai>=1.0`（DeepSeek 使用 OpenAI 兼容端点，不引入额外 SDK 封装）。
4. 新增厂商无关的模型客户端抽象 `app/llm/model_client.py`（消息、工具声明、响应、Fake 客户端、参数解析）。
5. 新增 `app/llm/langchain_client.py`：复用 `app/llm/adapter.py` 的参数裁剪与密钥来源，`max_retries=0` 关闭 LangChain 隐式重试，避免与上层重试相乘。
6. 新增 `app/runtime/tool_loop.py`：有限轮次循环，轮次/预算/deadline 三重上限，参数解析失败回传给模型而非抛异常。
7. 新增 `app/agents/single/`（Agent + Prompt）与 `config/agents/single.yaml`，注册进 `factory.AGENT_IMPLEMENTATIONS`。
8. 扩展 `AgentConfig`：新增 `max_tool_rounds`（1–8，默认 3）。
9. 新增 `app/single_demo.py` 装配层：`provider=fake|deepseek` 可切换，共享 `TraceLog` 与 `Budget`。
10. CLI 新增 `ask` 子命令（默认 `fake`，`--provider deepseek` 需密钥）。
11. 新增 `tests/test_llm_tool_loop.py`（24 项）；同步更新 smoke 自检的 Agent 数量断言。
12. 运行全部测试、CLI、敏感键/链接/diff 检查，记录真实结果。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/llm/model_client.py` | 新增 | `ChatMessage` / `ModelToolCall` / `ModelTurn` / `ToolSpec` / `ChatModelClient` / `FakeChatModelClient` / `ToolSpecBuilder` / `parse_tool_call` |
| `backend/app/llm/langchain_client.py` | 新增 | LangChain ↔ DeepSeek（OpenAI 兼容）客户端与 `build_chat_client` |
| `backend/app/runtime/tool_loop.py` | 新增 | 有限轮次工具调用循环与停止原因 |
| `backend/app/agents/single/agent.py`、`__init__.py`、`prompts/system.md` | 新增 | 单 Agent + Tools 基线 |
| `backend/app/single_demo.py` | 新增 | 单 Agent 装配（fake / deepseek） |
| `backend/app/config/agents/single.yaml` | 新增 | 独立配置（含 `max_tool_rounds`） |
| `backend/app/config/schema.py` | 修改 | 新增 `max_tool_rounds` |
| `backend/app/agents/factory.py` | 修改 | 注册 `single` |
| `backend/app/cli.py` | 修改 | 新增 `ask` 子命令与摘要输出 |
| `backend/pyproject.toml` | 修改 | 声明 LangChain 依赖 |
| `backend/README.md` | 修改 | 命令、模块职责、安全边界 |
| `backend/tests/test_llm_tool_loop.py` | 新增 | 24 项测试 |
| `backend/tests/smoke_agent_contracts.py` | 修改 | Agent 数量断言 3 → 4（检查项仍为 57） |

## 6. 执行结果和验证方式

工作目录 `backend/`，`$env:PYTHONIOENCODING='utf-8'`。

| # | 命令 | 退出码 | 真实结果 |
|---|---|---|---|
| 1 | `python tests/smoke_agent_contracts.py` | 0 | `全部通过：57 项检查` |
| 2 | `python -m unittest discover -s tests` | 0 | `Ran 76 tests ... OK`（Task 007 的 52 + 本任务 24） |
| 3 | `python -m app.cli ask "A-301 现在还有多少钱没交？"` | 0 | `status=success`、`stop_reason=final_answer`、`rounds=2`、`used_model_calls=2`、`used_tool_calls=1`、13 条证据、1 条工具 Trace |
| 4 | `python -m app.cli ask "..." --provider deepseek` | 2 | `[error] MissingApiKeyError: 环境变量 DEEPSEEK_API_KEY 未设置` |
| 5 | `python -m app.cli check` | 0 | 4 个 Agent、5 个能力、4 个工具；如实列出 2 个未实现的 allowed_tools |
| 6 | `python -m app.cli demo` | 0 | 未收 `18036.00`（回归未破坏） |

关键断言（`test_llm_tool_loop.py`）：

- 工具清单只下发"配置允许 + 调用方有权限 + 项目已实现"的交集；
- 工具结果以 `tool` 角色回传，含 `18036.00` 与 `tool_call_id`；
- 非法参数 JSON **不执行工具**，以 `invalid_tool_arguments` 回传；
- 越权租约返回 `PROJECT_SCOPE_DENIED`，`data` 为空；
- 最大轮次 3 强制生效并给出警告；
- 模型调用预算耗尽、模型异常均以显式停止原因退出；
- token 用量跨轮累加；
- 缺密钥/缺模型客户端/空问题/payload 注入权限均明确失败。

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `ask` 首次运行时 `tool_trace_count=0`，但确实调用了工具 | `SingleToolAgent` 自建 `ToolExecutor` 时用了新的 `TraceLog`，与 Runtime 的共享日志不是同一个对象 | Agent 新增 `trace_log` 注入参数，装配层传入同一实例；测试断言 `len(result.tool_traces)==1` 防回归 |
| `max_tool_rounds` 非法值测试未抛错 | 测试用 `model_copy(update=...)`，Pydantic 的 `model_copy` **不触发校验** | 改为 `AgentConfig.model_validate({...})` 断言 `ValidationError` |
| 模型预算耗尽测试得到 `final_answer` | 首轮就是纯文本回答，只需 1 次模型调用，预算 1 足够 | 修正用例：首轮要求工具调用，第二轮才需要模型 → 预算不足才可观测 |
| 新增 `single` 后 smoke 自检 3 项失败 | 历史断言把 Agent 集合写死为 3 个 | 更新为 4 个（含 `single`），检查项总数仍为 57，其余语义不变 |

## 8. 对应 Git Commit Hash

- **状态**：`Pending`
- **原因**：按约定由项目所有者在里程碑点确认提交；本任务暂不提交。

## 9. 后续待办事项

- [ ] **真实 DeepSeek 调用尚未验证**：需要 `DEEPSEEK_API_KEY` 与用户同意的调用预算；本轮只验证"缺密钥时明确失败"
- [ ] Task 009：LangGraph 多 Agent 图；需复核子任务 `run_id` / Trace 维度
- [ ] Task 013：三基线评测时，`single` 作为 Single Agent 基线复用本任务的循环
- [ ] 模型重试策略当前为"上层不重试、仅工具层重试"；接入真实 Provider 后需实测限流表现
