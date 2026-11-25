# 2026-11-24_038_langchain_standardization

## 1. 基本信息

- **日期**：2026-11-24
- **任务编号**：038
- **模块**：04_agents
- **Git Commit**：`d81e33d`（`langchain`，与 Task 036/037 及运营总览 / 3D 商场页面同一提交；起点 `main` / `77410ca`）。
- **关联决策**：[ADR-007](../../decisions/ADR-007-langchain-standard-components.md)

## 2. 任务目标和背景

采用标准 LangChain 领域 Agent、工具与检索接口，降低维护成本。保留 LangGraph 的跨领域流程和业务治理。将网页纳入同一装配入口并展示有据分析。

## 3. 原始用户 Prompt

```text
把本项目的架构修改为langchain 架构
```

## 4. AI 实际执行的主要步骤

1. 检查本机依赖、ADR、模型契约、工具循环、报告、审批与检索边界。通过依赖解析选择 LangChain 1.4.9 并在项目环境安装，原有 core、openai 和 LangGraph 版本可继续使用。
2. 将所有领域和 Single 共用的 `run_tool_loop` 实现切到 `create_agent`。将旧模型客户端接入标准模型接口，模型调用中间件结算共享账本，工具节点经 `StructuredTool` 执行。原循环可通过 Git 基线 `77410ca` 查阅。
3. 合同工具从标准 `BaseRetriever` 读取 `Document`，保留 BM25、证据 ID 与源定位。候选范围先过滤再截取 top-k，分数仍使用全索引统计。
4. 增加网页服务端模式和用量/回答投影。LangGraph 报告后增加证据综合节点，使用同一个 Budget，通过严格 JSON 选择已核验条目及适用的下一步。综合节点正常结束或报告明确失败后，图按既有审批规则继续。
5. 重跑既有回归，加上模型路径、缺密钥、超时、无效引用、浏览器展示和审批恢复验证。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/pyproject.toml`、`backend/app/runtime/tool_loop.py`、`backend/app/llm/langchain_client.py`、领域与 Single Agent | 修改 | 标准 Agent、治理中间件、模型适配与错误映射 |
| `backend/app/rag/retriever.py` | 新增 | 标准合同检索器 |
| `backend/app/rag/{bm25,service}.py`、`backend/app/tools/knowledge_tools.py` | 修改 | 保留来源与范围，先筛选候选再排序 |
| `backend/app/orchestration/synthesis.py` | 新增 | 证据综合 |
| `backend/app/investigation_demo.py`、`backend/app/orchestration/investigation.py`、`backend/app/api/{app,service}.py`、工作台报告和 `.env.example` | 修改 | 网页模型模式、状态与报告 |
| `backend/tests/test_api.py`、`backend/app/api/static/tests/ui-model-cases.js` | 修改 | API 行为和前端渲染回归 |
| [接手指南](../../architecture/langchain_integration.md) | 新增 | 架构图、装配边界、扩展方法 |
| ADR、设计、开发指南、当前基线、路线图、README、索引、日志、问题记录、检查点 | 修改 | 同步待验收状态与迁移证据 |

## 6. 执行结果和验证方式

- `python -m unittest discover -s tests -p 'test_*.py'`：723 项发现，678 项通过，45 项跳过（44 项 PostgreSQL 与 1 项既有跳过）。
- `python tests/smoke_agent_contracts.py` 通过 70 项，`python -m app.cli check`、`python -m app.cli investigate --model-provider scripted`、`python -m pip check` 退出 0。浏览器渲染用例通过。
- API 经标准模型循环实际取证并核算调用次数。以 `ChatOpenAI` 模拟 HTTP 运输完成 3 次请求，记账 45 tokens，报告响应模型与综合引用。
- 用 `77410ca` 原版源码生成待审批 checkpoint，再由新版完成两级审批，`executed_side_effects=[]`。新版模型报告也可在两级审批后保留完整账本和综合分析。
- 离线 heldout 报告写入临时目录。A 20/30、B 21/30、C 24/30，96 个条目的状态、通过结果和断言计数与 20261121T093757 基线一致。

## 7. 遇到的问题及解决方法

首轮全量发现未宣布工具的拒绝丢失失败审计。用限定为空的工具白名单通过受控执行器记录拒绝，阻止执行。配置错误与 Agent 执行错误属于不同类型，补足缺密钥及配置错误的 HTTP 503 映射。上述反例已回归。

工程取舍包括固定本次实测的 LangChain 版本，保留现有外部结果契约，领域内工具序列化，网页继续用规则规划。用于 RAG 的页码继承原 PDF 业务页码。综合分析以服务端原文生成结果，不允许模型新增金额或业务操作。

## 8. 对应 Git Commit Hash

`d81e33d`（归档写作时为 Pending，之后由用户提交）。基线 `77410ca`。

## 9. 后续待办事项

- [ ] 验证工作台调用实际 DeepSeek 服务。网页默认 `offline`，配置 `COMMERCIAL_WEB_MODEL_PROVIDER=deepseek` 后由运行该配置的服务接入已有 Key。
- [ ] 完成旧真实评测的评分审计、人工量表与独立环境复现。

## 10. 独立复查与返修（2026-11-25）

### 10.1 复查结论

独立复查由 `scripts/dev_loop/dev_review.ps1` 调用另一模型完成，报告见 [Task 036–038 独立复查报告](../../reviews/2026-11-25_task038_langchain_independent_review.md)：**有条件通过，无 P1**；四个核心不变量（关闭 SDK 重试、工具串行锁、客户端不能切换模型模式、检索先筛选后 top-k）缺少测试兜底，运营总览的状态措辞仍可能被误读。返修任务单见 `docs/handoffs/DEV_LOOP_TASK038R_LANGCHAIN_REVIEW_FIXES.md`。本轮未调用任何付费模型接口，测试均用脚本客户端与 `httpx.MockTransport`。

### 10.2 处理结果

| 复查项 | 处理 | 说明 |
|---|---|---|
| P2-1 运营总览把写死状态当实时 | 已修 | 在线状态改为“演示：6 个 Agent / 模拟状态”，日期与每个指标卡标注“模拟数据”，审批按钮与回执改为“模拟批准 / 演示执行回执”，保留侧栏到 `/workbench` 的真实工作台入口 |
| P2-2 关闭 SDK 重试无测试 | 已补测试 | `test_task038r_langchain.TestSdkRetryIsDisabled`：经生产构造路径建 `ChatOpenAI`，用 `MockTransport` 分别模拟正常、500、超时；断言每次 `complete()` 只有 1 次物理 HTTP 请求，且账本模型调用数等于物理请求数 |
| P2-3 客户端不能切换模型模式无测试 | 已补测试 | `test_api.TestClientCannotSelectModelMode`：`POST /api/runs` 带 `model_provider` / `engine` / `model_name` 等字段一律 422，服务端模式与 `/api/meta` 不变，且不创建运行 |
| P3-1 工具串行锁无测试 | 已补测试 | `test_task038r_langchain.TestToolCallsAreSerialized`：一轮两个 `tool_call`，假工具 `await asyncio.sleep` 并记录并发峰值与起止顺序；断言峰值 = 1、顺序与 `tool_call` 一致 |
| P3-2 检索先筛选后 top-k 无测试 | 已补测试 | `test_rag.TestScopeFilteringBeforeTopK`：测试内构造“全库最高分 8 个 chunk 都在授权范围外”的语料，断言范围内仍能返回、范围外不出现 |
| P3-3 模型超时不可重试 | 已修 + 已补测试 | `LLMToolAgent` / `SingleToolAgent` 仍以 `TIMEOUT` 报错（可见性不变），但 `retryable` 与 `MODEL_ERROR` 一致；重试受同一个 `Budget` 约束并逐次记账。`TestModelTimeoutRetrySemantics`：首次超时、第二次成功 → 成功且账本 2 次；预算只够 1 次 → 不重试、`BUDGET_EXHAUSTED` 明确失败 |
| P3-4 同一回合“有效 + 非法”tool_call 整体失败 | 接受为已知差异 | 宁可显式 `MODEL_ERROR`，不在模型已输出非法调用的回合继续执行部分工具；行为已在此记录，后续如需要可补“混合调用”用例与更细的停止原因 |
| P3-5 未宣布工具的错误码粒度 | 接受为已知差异 | 已注册但未暴露的别名当前同样报 `tool_not_found`，但拒绝与审计均存在、不执行工具；区分 `tool_not_allowed` 属审计精度改进，留待后续 |
| P3-6 模型失败诊断信息变少 | 接受为已知差异 | 报告与告警只保留错误码/停止原因；provider 原始异常可能包含凭据，不写入报告。需要排障时在受控日志中查看，不进入版本库或网页 |
| P3-7 只锁 langchain 高层版本 | 接受为已知差异 | 本轮维持 `langchain==1.4.9` 与既有 core/graph 范围；建议后续在 CI 或启动期增加组合版本检查，当前以本地全量回归兜底 |
| P3-8 Synthesizer 绕过注入的 planner_client | 已修 + 已补测试 | 综合客户端改为 `_planner_client(..., planner_client=planner_client, ...)`，注入优先；`TestSynthesisUsesInjectedClient` 在不设 Key、且把真实构造替换为抛错的情况下，证明综合节点使用的就是注入的假客户端 |
| P3-9 综合节点创建未使用的 ToolExecutor | 已修 | 删除 `ReportSynthesizer` 的 `executor` 参数与 `investigation_demo.py` 中为它新建的 `ToolExecutor`；综合循环不暴露工具，执行器不会被调用 |
| P3-10 开发日志“独立验证”措辞 | 已修 | `development_log.md` Task 038 条目改为“实施者本地验证”，不改其它条目 |
| P3-11 ToolMessage status 不一致 | 接受为已知差异 | 项目自身不读取该 status（执行器结果以内容 JSON 与审计为准），无功能影响；审计/调试时需注意，留待后续统一 |

### 10.3 新测试的变异验证

在仓库外临时副本中逐项打补丁后运行对应测试（基线副本均通过）：

| 变异 | 结果 |
|---|---|
| `build_chat_client` 的 `max_retries=0` → `2` | 被杀死：500/超时场景物理请求数变为 3，账本仍为 1 |
| 去掉 `awrap_tool_call` 的 `tool_lock` | 被杀死：并发峰值变为 2 |
| `RunRequest` 增加 `model_provider` 并由提交写回服务配置 | 被杀死：客户端字段从 422 变为 201，服务端模式被改写 |
| `KnowledgeService.search` 回退为“先取 `top_k*4` 再过滤” | 被杀死：范围内命中返回空列表 |
| `LLMToolAgent` 的 `retryable` 回退为仅 `MODEL_ERROR` | 被杀死：首次超时后不再重试，子任务失败 |
| 综合节点回退为不传注入的 `planner_client` | 被杀死：测试中真实客户端构造被调用 |

### 10.4 本地验证

- 全量回归：731 项发现，`OK (skipped=1)`（运行环境已设置 `COMMERCIAL_PG_TEST_URL`）。
- `python backend/tests/smoke_agent_contracts.py`：全部通过 70 项。
- `python -m app.cli check`：完整 JSON，退出码 0。
- 新增文件：`backend/tests/test_task038r_langchain.py`（§2.1、§2.3、§3.1、§3.2 的测试）；`test_api.py`、`test_rag.py` 只追加。
- 未修改 `backend/app/runtime/tool_loop.py`、`backend/app/llm/langchain_client.py`、`backend/app/rag/` 的实现，只补测试。
