# backend/ — Task 007 Runtime 与受控只读工具

离线、确定性的最小 Agent Runtime。**不联网、不调用模型、不连数据库**；
数据来自 `../docs/evaluation/fixtures/agent_first_v1.json`（合成数据，只读）。

## 环境

- Python 3.11+
- 已安装依赖：`pydantic` v2、`PyYAML` v6（本仓库 Conda 环境已具备）
- 本任务**未安装**任何新依赖；`pytest` 只在 `pyproject.toml` 的 `dev` 可选依赖中声明，
  当前环境没有 pytest，因此测试以标准库 `unittest` 执行（测试类同时可被 pytest 收集）。

## 常用命令（在 `backend/` 目录下）

```bash
python -m app.cli --help
python -m app.cli tools
python -m app.cli check
python -m app.cli demo
python -m app.cli demo --variant v_oct_rent_corrected
python -m app.cli demo --budget-tool-calls 1
```

回归测试：

```bash
python tests/smoke_agent_contracts.py          # 既有 57 项骨架自检
python -m unittest discover -s tests -v        # 新增 Runtime / Tool 测试
```

## 模块职责

| 路径 | 职责 |
|---|---|
| `app/agents/base/` | 既有 Agent 契约（`AgentRequest/Context/Result`）、Registry、BaseAgent |
| `app/agents/factory.py` | 配置 → 实例的静态白名单；K2 配置/实现一致性校验 |
| `app/config/` | Agent YAML 与 Schema（拒绝密钥字段） |
| `app/fixtures/repository.py` | fixture 只读仓库：项目范围、`Decimal` 金额、变体 overlay |
| `app/runtime/types.py` | `TrustedContext`、`Evidence`、Trace、`RuntimeResult` |
| `app/runtime/budget.py` | 共享预算：原子预留 / 结算 / 释放（按 `call_id` 幂等） |
| `app/runtime/agent_runtime.py` | Runtime 边界：拒绝 payload 授能给、解析 Agent、汇总结果 |
| `app/tools/registry.py` | 工具静态白名单（拒绝重名、拒绝非 `BaseTool`） |
| `app/tools/executor.py` | 统一执行器：白名单、权限、参数/结果校验、超时、有限重试、预算、Trace |
| `app/tools/fixture_tools.py` | Lease / Billing / Property 只读工具 |
| `app/demo.py` | Fake Agent（ScriptedToolAgent）与端到端接线，**不调用模型** |
| `app/cli.py` | 命令行入口 |

## 安全边界

- 权限与项目范围只来自 `TrustedContext`（CLI 从 fixture 可信主体构造），
  payload 出现 `permissions` / `project_ids` / `principal_id` 等保留键直接拒绝；
- 工具无法伪造证据来源：`Evidence` 的 `source_tool` 与 `tool_call_id` 由执行器写入；
- 不提供任意 SQL / Python / Shell / 文件系统 / 网络工具；
- Trace 只记录参数摘要（SHA-256 前缀），不记录原始参数，避免泄露密钥。

## 尚未实现（Task 008+）

真实模型调用、LangChain/LangGraph、多 Agent 图、RAG/PDF、数据库、审批与持久 checkpoint、
FastAPI 与前端。
