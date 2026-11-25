# 2026-11-24_038_langchain_standardization

## 1. 基本信息

- **日期**：2026-11-24
- **任务编号**：038
- **模块**：04_agents
- **Git Commit**：`Pending`，起点 `main` / `77410ca`。保留已有未提交页面及 Task 036/037 文档。
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

`Pending`。本轮按源码和文档验证交付，未执行 Git 提交。基线 `77410ca`，保留已有工作区修改。

## 9. 后续待办事项

- [ ] 验证工作台调用实际 DeepSeek 服务。网页默认 `offline`，配置 `COMMERCIAL_WEB_MODEL_PROVIDER=deepseek` 后由运行该配置的服务接入已有 Key。
- [ ] 完成旧真实评测的评分审计、人工量表与独立环境复现。
