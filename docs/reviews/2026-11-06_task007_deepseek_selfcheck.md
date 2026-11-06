# Task 007 DeepSeek 自检报告

- **日期**：2026-11-06
- **任务**：007（正式 Prompt 2）Runtime 与受控工具执行，含 R1 返修（F1 / F2）
- **自检结论**：**DeepSeek 自检通过**（发现并修复 1 项 R1 遗漏缺陷；本报告**不代表** Codex 已验收——项目已取消 Codex 逐任务复核流程）
- **仓库状态**：分支 `main`，HEAD `fe95ba5af0bf079b3f903cd6149062ad9c868f7a`，`git status` 干净，与 `origin/main` 同步
- **运行环境**：`D:\anacada\envs\commercial-agent\python.exe`，Python 3.11.18
- **验证边界**：全部离线。未调用模型、未连接数据库、未访问网络。`DEEPSEEK_API_KEY` 当前**未设置**

---

## 1. 自检范围与方法

不复用既有报告结论，直接读源码 + 独立脚本复现 + 运行既有测试。三项重点（对应接手要求）：

| # | 要求验证的行为 | 方法 |
|---|---|---|
| A | 同项目不同租约的付款不会影响当前租约账单 | 独立脚本在 fixture 内存副本注入 A-302 账单/付款/核销，比对 A-301 Statement |
| B | 同一 Runtime 连续运行与并发运行时，结果 Trace 按 run 隔离 | 独立脚本：同一 bundle 连续两次 `run_demo`；另一 bundle `asyncio.gather` 并发两次 |
| C | 现有测试与 CLI 示例仍可用 | 直接运行 57 项 smoke、unittest、四个 CLI 子命令与一个变体命令 |

---

## 2. 发现的问题与修复

### 2.1 R1 的 F1 修复不完整（本次自检发现）

**现象**：`FixtureRepository.statement()` 的 `paid_total` 仍按**整笔付款金额**累计。

```python
# R1 修复后（仍有缺陷）
paid_total = _quantize(sum((money(p["amount"]) for p in valid_payments), _ZERO))
```

`valid_payments` 已正确收敛为"核销到本租约账单的付款"，但同一笔付款若**拆分核销到不同租约**的账单（同项目内），整笔金额都会被算进本租约已收。

**独立复现**：在 fixture 副本中新增一笔 `500.00` 确认付款，其中 `200.00` 核销到 A-301 的 `inv_2026_10`，`300.00` 核销到 A-302 的测试账单。查询 A-301：

| 指标 | 修复前（错误） | 修复后（正确） |
|---|---|---|
| `paid_total` | `35060.00`（= 34560 + 整笔 500） | `34760.00`（= 34560 + 本租约核销 200） |
| `outstanding_total` | `17536.00`（少算 300） | `17836.00` |

**修复**：已收额与未收额改为按**核销到本租约的金额**计算：

```python
paid_total = _quantize(sum((money(alloc["amount"]) for alloc in allocations), _ZERO))
outstanding_total = _quantize(sum((view["outstanding"] for view in invoice_views), _ZERO))
```

**回归测试**：新增 `TestStatementLeaseIsolation::test_payment_split_across_leases_counts_only_own_allocation`，同时断言 A-301（34760.00 / 17836.00）与 A-302（300.00 / 0.00）。

> 该缺陷与 F1 同源（跨租约金额污染），只是入口更隐蔽。仅按 `invoice_ids` 过滤 allocations 不够，聚合口径也必须跟着改。

### 2.2 F2 验证结果：实现正确，无需修改

`AgentRuntime.run()` 每次生成新 `run_id`，`ToolTrace.run_id` 由执行器从 `AgentContext.run_id` 写入，结果按 `run_id` 过滤，共享 `TraceLog` 保持 append-only 不清空。三项设计要点均成立：

| 设计要点 | 验证 |
|---|---|
| 结果只含本次 Trace | 连续两次运行各 3 条，`call_id` 集合不相交 |
| 不清空共享日志 | 共享日志保留 6 条 = 两次结果并集 |
| 并发不丢数据 | `gather` 两次并发各 3 条、互不交叉、日志恰 6 条且无重复 `call_id` |

---

## 3. 验证命令与真实结果

工作目录 `backend/`，PowerShell，`$env:PYTHONIOENCODING='utf-8'`。

| # | 命令 | 退出码 | 真实结果 |
|---|---|---|---|
| 1 | `python tests/smoke_agent_contracts.py` | 0 | `全部通过：57 项检查` |
| 2 | `python -m unittest discover -s tests` | 0 | `Ran 52 tests in 1.285s` / `OK`（R1 的 51 + 本次新增 1） |
| 3 | `python -m app.cli --help` | 0 | 列出 `tools` / `check` / `demo` |
| 4 | `python -m app.cli tools` | 0 | 4 个只读工具，含权限/超时/重试上限 |
| 5 | `python -m app.cli check` | 0 | 3 Agent / 4 能力 / 4 工具；如实列出未实现的 `lease.term_extract`、`compliance.checklist.read` |
| 6 | `python -m app.cli demo` | 0 | `status=success`，未收 `18036.00` |
| 7 | `python -m app.cli demo --variant v_oct_rent_corrected` | 0 | `status=success`，未收 `17280.00` |
| 8 | `python -m app.cli demo --budget-tool-calls 1` | 2 | `budget_exhausted`、`status=failed`、`tool_trace_count=2`（失败可见且 Trace 不虚增） |
| 9 | 独立脚本 A（租约隔离，13 项断言） | 0 | `PASS=13 FAIL=0`（修复后） |
| 10 | 独立脚本 B（Trace 隔离，12 项断言） | 0 | `PASS=12 FAIL=0` |

修复前脚本 A 为 `PASS=11 FAIL=2`，两处失败即 §2.1 的 `paid_total` / `outstanding_total`。

---

## 4. 未覆盖项与剩余风险

| # | 项 | 说明 |
|---|---|---|
| 1 | 真实模型 / Tool Calling | 未接入（Task 008 范围）；`ScriptedToolAgent` 是 Fake Agent |
| 2 | LangGraph / 多 Agent 并行图 | 未实现（Task 009） |
| 3 | 数据库 | 未接入（Task 010）；金额均来自 fixture |
| 4 | RAG / PDF | 未实现（Task 011） |
| 5 | 审批 / checkpoint | 未实现（Task 012） |
| 6 | pytest | 环境未安装；测试用 `unittest` 编写，可被 pytest 原生收集 |
| 7 | `git diff --check` | 仍报 `docs/architecture/database_design.md:1661: new blank line at EOF`（Task 005 遗留；本任务禁区，未处理） |
| 8 | 单次运行内多 Agent 复用同一 `run_id` | Task 009 引入图后需复核：子任务是否共享 run_id、是否需要 `subtask_id` 维度（已记入 Task 009 待办） |

---

## 5. 变更文件

| 文件 | 变更 |
|---|---|
| `backend/app/fixtures/repository.py` | `paid_total` 改为按本租约核销金额累计；`outstanding_total` 改为按账单逐项未收求合 |
| `backend/tests/test_runtime.py` | 新增跨租约拆分付款回归测试（1 项） |

未修改：`database_design.md`、三个 Agent YAML、其他历史 Prompt 原文；未安装依赖、未调用模型、未建库。
