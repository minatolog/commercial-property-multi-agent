# backend/ — Agent Runtime、受控只读工具与单 Agent 基线

离线优先的 Agent 工程骨架：**默认不联网、不调模型、不连数据库**。
数据来自 `../docs/evaluation/fixtures/agent_first_v1.json`（合成数据，只读）。

## 环境

- Python 3.11+
- 已安装依赖：`pydantic` v2、`PyYAML` v6、`langchain-core` v1、`langchain-openai` v1
- `pytest` 仅在 `pyproject.toml` 的 `dev` 可选依赖中声明；测试以标准库 `unittest` 编写并执行
  （`Test*` / `test_*` 命名可被 pytest 原生收集）

## 常用命令（在 `backend/` 目录下）

```bash
python -m app.cli --help
python -m app.cli tools
python -m app.cli check
python -m app.cli demo                                  # Fake Agent，无模型
python -m app.cli demo --variant v_oct_rent_corrected
python -m app.cli demo --budget-tool-calls 1            # 预算耗尽 -> 退出码 2
python -m app.cli ask "A-301 现在还有多少钱没交？"        # 单 Agent + Tools，默认 fake
python -m app.cli ask "..." --provider deepseek         # 真实调用，需 DEEPSEEK_API_KEY
```

回归测试：

```bash
python tests/smoke_agent_contracts.py          # 骨架契约自检（57 项）
python -m unittest discover -s tests -v        # Runtime / Tool / 模型适配 测试
```

## 模块职责

| 路径 | 职责 |
|---|---|
| `app/agents/base/` | Agent 契约（`AgentRequest/Context/Result`）、Registry、BaseAgent |
| `app/agents/factory.py` | 配置 → 实例的静态白名单；K2 配置/实现一致性校验 |
| `app/agents/single/` | 单 Agent + Tools 基线（`single.investigate`） |
| `app/config/` | Agent YAML 与 Schema（拒绝密钥字段） |
| `app/fixtures/repository.py` | fixture 只读仓库：项目范围、`Decimal` 金额、变体 overlay |
| `app/llm/adapter.py` | 厂商参数裁剪与密钥来源（环境变量） |
| `app/llm/model_client.py` | 与厂商无关的消息/工具/响应类型；`FakeChatModelClient` |
| `app/llm/langchain_client.py` | LangChain ↔ DeepSeek（OpenAI 兼容）适配器 |
| `app/runtime/types.py` | `TrustedContext`、`Evidence`、Trace、`RuntimeResult` |
| `app/runtime/budget.py` | 共享预算：原子预留 / 结算 / 释放（按 `call_id` 幂等） |
| `app/runtime/tool_loop.py` | 有限轮次工具调用循环（轮次/预算/deadline 上限） |
| `app/runtime/agent_runtime.py` | Runtime 边界：拒绝 payload 授能给、解析 Agent、汇总结果 |
| `app/tools/registry.py` | 工具静态白名单（拒绝重名、拒绝非 `BaseTool`） |
| `app/tools/executor.py` | 统一执行器：白名单、权限、参数/结果校验、超时、有限重试、预算、Trace |
| `app/tools/fixture_tools.py` | Lease / Billing / Property 只读工具 |
| `app/demo.py` | Fake Agent（`ScriptedToolAgent`）端到端接线，**不调用模型** |
| `app/single_demo.py` | 单 Agent + Tools 装配（fake / deepseek 可切换） |
| `app/cli.py` | 命令行入口 |

## 安全边界

- 权限与项目范围只来自 `TrustedContext`；payload 出现 `permissions` / `project_ids` / `principal_id` 等保留键直接拒绝
- 工具无法伪造证据来源：`Evidence` 的 `source_tool` 与 `tool_call_id` 由执行器写入
- 不提供任意 SQL / Python / Shell / 文件系统 / 网络工具
- Trace 只记录参数摘要（SHA-256 前缀），不记录原始参数，避免泄露密钥
- API Key 只从环境变量读取；缺失时明确报错，不静默降级

## 尚未实现（Task 009+）

LangGraph 多 Agent 图、PostgreSQL 数据层、RAG/PDF、审批与持久 checkpoint、FastAPI 与前端。