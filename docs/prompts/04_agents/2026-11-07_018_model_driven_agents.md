# 2026-11-07 - 018 - 模型驱动的领域 Agent 与 B/C 真实运行入口

- **日期**：2026-11-07
- **任务编号**：018
- **模块**：04_agents
- **关联任务**：017（复查报告第 3 节第 4 条）

---

## 1. 任务目标和背景

[Task 017 复查报告](../../reviews/2026-11-07_release_candidate_recheck.md)第 3 节第 4 条指出：

> 真实集成仍未完成……真实模型注入、B/C 运行入口可在无密钥时先用 Fake/适配器测试开发；实际调用验证才依赖凭据。不要把尚未实现的装配统称为"只缺 API Key"。

上一轮（Task 017）修复了 R1–R7，但**没有**实现这件事：调查工作流里领域 Agent 仍是确定性工具代理，评测 B 是规则多工具循环、C 是规则 Planner。因此"缺 `DEEPSEEK_API_KEY`"之外还欠一块可离线完成的工作。

本任务补上这块：让 Agent 真正可以由模型驱动，并让 B/C 有真实运行入口；无密钥时用脚本化模型验证装配，有密钥时同一入口直连 DeepSeek。

## 2. 原始任务 Prompt（逐字保存）

来源分两部分，按实际发生顺序记录：

**（a）用户在当前会话中的长期指令（原文节选，来自 Task 017 报告交付后的继续要求）**

> 真实模型注入、B/C 运行入口可在无密钥时先用 Fake/适配器测试开发；实际调用验证才依赖凭据。不要把尚未实现的装配统称为"只缺 API Key"。

**（b）系统在 Task 017 交付后给出的续作要求（原文）**

> You have not yet marked the task as complete using the task_complete tool. If you were planning, stop planning and start implementing. You aren't done until you have fully completed the task.
>
> IMPORTANT: Do NOT call task_complete if:
> - You have open questions or ambiguities - make good decisions and keep working
> - You encountered an error - try to resolve it or find an alternative approach
> - There are remaining steps - complete them first

**（c）本任务的自定范围**（依据 (a)(b) 与项目现有架构约束推导，非用户逐字要求）：

1. 领域 Agent 支持"模型决定调哪个工具"的引擎，且事实仍来自工具输出；
2. 调查工作流可按引擎装配（`deterministic` / `llm`）；
3. 评测 B/C 有真实模型入口，`--model-provider {offline,scripted,deepseek}`；
4. 无密钥时用脚本化模型验证装配，不缺密钥的验证不得假装完成；
5. 保持既有离线结果可复现（不改变 `scoring-v2` 与历史报告口径）。

## 3. AI 实际执行的主要步骤

1. 核对现状：`SingleToolAgent`（B）已有 `run_tool_loop` + 注入 `model_client`；缺的是**领域 Agent** 与**基线装配**。
2. 新增 `app/agents/base/facts.py`：把"工具输出 → 可评分事实"下沉为共享契约（Agent 与评测共用同一口径）。
3. 新增 `app/agents/base/llm_agent.py`：`LLMToolAgent`，模型选工具、事实取自工具、预算/权限/错误码复用既有链路；并把工具输出映射成与确定性 Agent **相同**的领域视图（否则图与报告的冲突/缺失检测会静默失效）。
4. 新增 `lease` / `billing` / `property` 三个 LLM 实现（各自类属性，满足 K2 配置一致性校验）。
5. `factory.py`：新增 `AGENT_LLM_IMPLEMENTATIONS` 与 `engine`，两个都是代码内静态白名单；`compliance` 无 LLM 实现时明确跳过（`strict` 下报错）。
6. `investigation_demo.build_investigation_bundle(engine=, model_client=)`，并把引擎/模型写入 bundle 供审计。
7. 新增 `app/llm/scripted.py`：脚本化模型（按"已调过哪些工具"决策，无状态，适配并发子任务）。
8. 新增 `app/llm/factory.py`：`offline` / `scripted` / `deepseek` 三态；`deepseek` 缺密钥直接抛 `MissingApiKeyError`。
9. `baselines.py`：B 注入模型时走 `SingleToolAgent`；C 注入模型时用 `engine="llm"`；A 拒绝模型（否则基线含义被改变）。`partial` 不再被当成 `internal_error`。
10. `cli.py`：`investigate --model-provider`、`evaluate --model-provider`；`evaluate` 传模型时自动排除 A。
11. 修复并发预算记账缺陷（见第 7 节）。
12. 新增 `tests/test_llm_agents.py`（23 项）。

## 4. 新增和修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/agents/base/facts.py` | 新增：`facts_from_tool_output` / `facts_of_executions` / `outputs_of_executions` |
| `backend/app/agents/base/llm_agent.py` | 新增：`LLMToolAgent` + 领域视图映射 |
| `backend/app/agents/lease/llm_agent.py` | 新增 |
| `backend/app/agents/billing/llm_agent.py` | 新增 |
| `backend/app/agents/property/llm_agent.py` | 新增 |
| `backend/app/agents/factory.py` | `engine` 参数 + `AGENT_LLM_IMPLEMENTATIONS` + `implementations_for()` |
| `backend/app/agents/single/agent.py` | 输出增加 `facts` / `tool_facts` / `tool_outputs` |
| `backend/app/investigation_demo.py` | `engine` / `model_client`，bundle 记录引擎与模型 |
| `backend/app/llm/scripted.py` | 新增：`ScriptedToolModel` |
| `backend/app/llm/factory.py` | 新增：provider → 客户端 |
| `backend/app/evaluation/baselines.py` | B/C 模型路径、A 拒绝模型、`partial` 处理 |
| `backend/app/evaluation/runner.py` | `evaluate(model_client=...)` |
| `backend/app/cli.py` | `--model-provider`（investigate / evaluate） |
| `backend/app/runtime/tool_loop.py` | 模型预算 `call_id` 纳入 `subtask_id`（修复并发少记） |
| `backend/tests/test_llm_agents.py` | 新增 23 项 |

## 5. 执行结果和验证方式

```powershell
cd D:\commercial-property-multi-agent\backend
D:\anacada\envs\commercial-agent\python.exe -m unittest discover -s tests -p "test_*.py"
# Ran 284 tests ... OK

D:\anacada\envs\commercial-agent\python.exe tests\smoke_agent_contracts.py
# 全部通过：57 项检查

D:\anacada\envs\commercial-agent\python.exe -m app.cli investigate --model-provider scripted
# EXIT=0；3 个子任务 success；4 条 trace
# budget: used_model_calls=6（3 子任务 × 2 轮）、used_tool_calls=4
# verdict=conflicting；冲突 756.00；缺失附件 B；completeness=partial

D:\anacada\envs\commercial-agent\python.exe -m app.cli investigate --model-provider deepseek
# EXIT=2；[error] MissingApiKeyError: 环境变量 DEEPSEEK_API_KEY 未设置

D:\anacada\envs\commercial-agent\python.exe -m app.cli evaluate --baseline B_single_agent --model-provider deepseek
# EXIT=2；同上（明确失败，不静默降级）

D:\anacada\envs\commercial-agent\python.exe -m app.cli evaluate --split heldout --baseline C_multi_agent --quiet
# 仍走离线口径，结果与历史报告一致
```

关键断言（`tests/test_llm_agents.py`）：

- 同一题在 `deterministic` 与 `llm` 引擎下得到**相同判定**：`conflicting` + `partial` + 冲突 756.00 + 缺失附件 B；
- `facts` 与工具输出逐字段一致（`invoiced_total=52596.00` 等），模型文本不影响事实；
- 模型写了白名单外的工具时**不会**被执行；
- 空最终回答 → `MODEL_ERROR`；
- 并发子任务的模型调用**逐次**记账（3 子任务 × 2 轮 = 6 次），预算上限真实生效；
- `engine="llm"` 未注入模型、未知引擎均立即失败。

## 6. 执行结果：真实服务的边界（必须如实阅读）

| 项 | 状态 |
|---|---|
| 模型驱动装配（代码 + 离线验证） | **已完成**，`scripted` 路径可跑通整条调查与 B/C |
| 真实 DeepSeek 工具闭环 | **未执行**：本机 `DEEPSEEK_API_KEY` 未设置（已检查）。入口已就绪，缺 key 时明确报错 |
| 真实模型下的 B/C 质量对照 | **未执行**：需要密钥 + 多次重复测量；不得用 `scripted` 结果代替 |
| PostgreSQL、人工量表、部署 | 仍未完成（同 Task 017） |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| 脚本化模型在并发子任务下互相抢轮次 | 固定轮次队列被 3 个并发子 Agent 共享 | 改为按"对话里已调过哪些工具"决策（无状态），并在第一轮发出**批量**工具调用 |
| LLM 引擎下冲突检测失效（verdict 变成 `supported`） | 模型路径只输出 `facts`，而图读的是 `output["rent_variance_total"]` / `output["lease"]` | 增加 `_domain_view()`，把工具输出映射成与确定性 Agent 相同的领域视图 |
| 预算 `call_id` 并发去重：同轮只记一次 | 预算 `call_id = mc_{run_id}_{round}`，3 个并发子任务同轮共用一个 ID | `call_id` 纳入 `context.subtask_id`；此前 `model_calls` 恒为 0 掩盖了它，模型驱动后立即暴露（3 子任务 6 次调用被记成 2 次） |
| B 基线模型路径把 `partial` 记成 `internal_error` | 只用 `status is not SUCCESS` 判断失败 | 区分 `FAILED`（失败）与 `PARTIAL`（有事实但未走完总结轮），后者按事实评分 |

## 8. 对应 Git Commit Hash

- 上一轮基线：`6b0b119`
- 本轮：见 `docs/checkpoints/git_history.md`（提交后回填）

## 9. 后续待办事项

- [ ] 配置 `DEEPSEEK_API_KEY` 后，用 `--model-provider deepseek` 跑一次真实工具闭环并归档 trace
- [ ] 真实模型下按冻结配置重复 3 次测量 B/C，另立报告版本（不得与离线报告混比）
- [ ] PostgreSQL 实机验证
- [ ] 人工量表评分（H25/H26 + rubric 队列）
- [ ] 真实服务鉴权与部署验证
