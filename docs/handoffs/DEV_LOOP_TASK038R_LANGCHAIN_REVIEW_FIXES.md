# 任务单 038R：LangChain 重构独立复查返修（测试兜底 + 小修）

- 编写：2026-11-25，Claude Code。由 `scripts/dev_loop/` 执行（编码方 DeepSeek，审查方 Claude）。
- 依据：[独立复查报告](../reviews/2026-11-25_task038_langchain_independent_review.md)（有条件通过，无 P1；P2 三项、P3 十一项）。先完整阅读报告 §3–§5，以及 [ADR-007](../decisions/ADR-007-langchain-standard-components.md)、[038 归档](../prompts/04_agents/2026-11-24_038_langchain_standardization.md)。
- 约束：**不调用付费模型接口**（用脚本模型或 `ChatOpenAI` + `httpx.MockTransport`）；不 `pip install`；不运行 docker；不改评测题、评分规则与 `docs/evaluation/reports/` 下的任何结果；不改 `.gitignore`。PG 测试库通过环境变量 `COMMERCIAL_PG_TEST_URL` 已可用，不要把连接串写进任何文件。

## 1. 只改这些文件

| 文件 | 内容 |
|---|---|
| `backend/tests/test_llm_tool_loop.py`（或新建 `backend/tests/test_task038r_langchain.py`，二选一，写在总结里） | §2.1–§2.4 的新测试 |
| `backend/tests/test_api.py` | §2.2 的新测试（只追加） |
| `backend/tests/test_rag.py` | §2.4 的新测试（只追加） |
| `backend/app/agents/base/llm_agent.py`、`backend/app/agents/single/agent.py` | §3.1 |
| `backend/app/investigation_demo.py`、`backend/app/orchestration/synthesis.py` | §3.2、§3.3 |
| `backend/app/api/static/ops/index.html`、`backend/app/api/static/ops/app.js` | §3.4（只改文案与标注，不改布局和交互逻辑） |
| `docs/prompts/04_agents/2026-11-24_038_langchain_standardization.md` | 新增 §10 “独立复查与返修”（见 §4） |
| `docs/development_logs/development_log.md` | 只把 Task 038 条目里“均独立验证”之类的措辞改为“实施者本地验证”（复查 P3-10），不改其它条目 |

其余文件一字不改（尤其 `backend/app/runtime/tool_loop.py`、`backend/app/llm/langchain_client.py`、`backend/app/rag/` 的实现——本任务只给它们补测试）。

## 2. 补测试（复查者的变异在当前测试下全部存活，必须让它们失败）

每个新测试都要在总结里写明：**把哪一行改成什么样（对应复查报告的哪个变异），这个测试会失败**。在仓库外临时副本里实际做一遍，写出结果。

### 2.1 SDK 重试关闭，物理请求 = 账本（复查 P2-2）

用 `backend/app/llm/langchain_client.py` 的真实构造路径建 `ChatOpenAI` 客户端，把它的 HTTP 传输换成 `httpx.MockTransport`（或等效的可计数假传输），分别模拟 500、超时、正常返回：断言每次 `handler` 调用的**物理 HTTP 请求数 = 1**，且预算账本里模型调用数与物理请求数相等。变异：把 `max_retries=0` 改成 `2`，测试必须失败。

### 2.2 Web 客户端不能切换模型模式（复查 P2-3）

`POST /api/runs` 带 `model_provider` / `engine` / `model_name` 等字段时必须 422，服务端模式不变（仍是服务端配置的值）。变异：给 `RunRequest` 加 `model_provider` 字段并在提交时写回服务配置，测试必须失败。

### 2.3 工具串行锁（复查 P3-1）

一轮模型返回两个 tool_call，用会 `await asyncio.sleep` 的假工具记录并发峰值：断言峰值 = 1、执行顺序与 tool_call 顺序一致。变异：去掉 `tool_lock`，测试必须失败。

### 2.4 检索“先筛选后 top-k”（复查 P3-2）

在测试里构造一份小语料（不改 fixture 文件）：同一查询下，**全库得分最高的若干 chunk 都在授权范围外**，范围内的命中排在 `top_k*4` 之后。断言授权范围内仍能返回结果、且不含范围外 chunk。变异：回退到“先取 `top_k*4` 再过滤”，测试必须失败。

## 3. 小修

### 3.1 模型超时恢复为可重试（复查 P3-3）

旧循环把模型超时收敛为可重试的 `MODEL_ERROR`；新实现映射为 `ErrorCode.TIMEOUT` 且不可重试，一次瞬时超时就会直接失败子任务。改为：错误码仍报 `TIMEOUT`（可见性不变），但 `retryable` 与 `MODEL_ERROR` 一致。重试仍受同一个 `Budget` 约束，每次重试都计入模型调用。补测试：第一次超时、第二次成功 → 子任务成功、账本记 2 次模型调用；预算只够 1 次时 → 不重试、明确失败。

### 3.2 综合节点必须使用注入的模型客户端（复查 P3-8）

`investigation_demo.py` 里，调用方注入了 `planner_client`（或测试 / 评测注入的假客户端）时，`ReportSynthesizer` 必须用它，**不能再自己构造真实客户端**（这是潜在的付费调用缝）。补测试：注入假客户端 + 不设 Key 时，综合节点使用的就是这个假客户端，且没有构造任何真实客户端。

### 3.3 删除综合节点里未使用的 ToolExecutor（复查 P3-9）

`ReportSynthesizer` 的 `executor` 参数与 `investigation_demo.py` 里为它新建的 `ToolExecutor` 删除；相关测试同步。

### 3.4 运营总览逐处标注模拟数据（复查 P2-1）

`static/ops/` 没有调用任何 API，在线状态、指标、日期、审批 / 派单回执都是写死或本地模拟的。要求：
- “6 个 Agent 在线 / 协同网络运行正常”改为明确的演示表述（例如“演示：6 个 Agent”“模拟状态”），去掉会被理解为实时的措辞；
- 每个指标卡、写死的日期旁加“模拟数据”标注；
- “批准并派单 / 已接单 / 执行回执”等按钮与状态改为“模拟批准 / 演示回执”之类，不能与真实审批（`/workbench`）混淆；
- 保留到真实争议调查工作台（`/workbench`）的显眼入口。
不改布局、样式结构和交互逻辑；不引入新依赖。

## 4. 归档

在 038 归档新增 §10：复查结论链接、每条 P2 / P3 的处理（已修 / 已补测试 / 接受为已知差异及理由）。以下几项**本任务不改代码**，在 §10 中写明接受理由或后续建议：P3-4（同一回合有效 + 非法工具调用整体失败）、P3-5（未暴露工具的错误码粒度）、P3-6（模型失败诊断信息变少；注意不要把可能含 Key 的原始异常写进报告）、P3-7（只锁 langchain 高层版本）、P3-11（ToolMessage status）。

## 5. 验收标准

- 只改 §1 列出的文件；不删改已有测试用例，只追加。
- 全量回归通过（调度脚本在设置了 `COMMERCIAL_PG_TEST_URL` 的环境下运行）；`python tests/smoke_agent_contracts.py` 70 项、`python -m app.cli check` exit 0。
- §2 每个测试都附“对应变异会失败”的实测说明；没有恒真断言、没有 skip。
- 不调用任何付费接口；不写入连接串、Key、密码。
