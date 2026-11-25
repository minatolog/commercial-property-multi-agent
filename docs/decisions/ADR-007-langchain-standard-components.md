# ADR-007：采用 LangChain 标准 Agent 与检索接口

- 日期：2026-11-24；任务：037。
- 状态：**Task 037 记录用户方向与原迁移建议。Task 038 已实施标准循环、检索和网页装配，并通过本地验证。** 实际差异、证据与外部验证范围见 [实施记录](../prompts/04_agents/2026-11-24_038_langchain_standardization.md)。
- 依据：用户对大量自研控制逻辑难以复用、理解和修改的反馈；保留 Agent-first V1.0/ADR-005 的业务、安全及可插拔要求。
- 当前代码：main / 77410ca + 已有未提交页面和审查文档；不覆盖这些成果。

## 1. 目标与判断

将通用“模型→工具→结果→继续模型”循环交给 LangChain 标准 Agent；LangGraph 继续组织跨领域调查、补查、人工审批与持久恢复。用标准工具和检索接口降低新工程师需要学习的自定义概念数量。

已有 Registry、Agent 契约、Repository 和工具治理具备复用基础，不能笼统称原系统完全没有复用性；具体问题是通用循环、消息转换与自定义结果映射较多，标准生态接入点少。采用框架也不会自动获得权限正确性、领域可信结果或生产可维护性。

Task 037 检查时只有 `langchain-core 1.7.6`、`langchain-openai 1.7.4` 和 `langgraph 1.2.20`。Task 038 新增 `langchain 1.4.9`，沿用原三个核心依赖版本，并通过 `pip check`。

## 2. 目标职责分工

| 部分 | 迁移方向 | 保留边界 |
|---|---|---|
| 单领域 LLM 循环 | 用 `langchain.agents.create_agent` 替代生产路径中的自研 run_tool_loop；框架拥有唯一 Agent 循环 | 不在 create_agent 工具内再嵌套旧循环冒充完成迁移 |
| 工具接口 | 采用标准 Tool/BaseTool/StructuredTool；具体类型按兼容版本实测选择 | 所有业务工具仍通过 ToolExecutor.execute，不让包装器绕过权限、预算、目标范围和输出校验 |
| 模型调用 | 复用逐 Agent YAML 与客户端缓存，向标准 Agent 提供兼容 ChatModel | 保留服务端实际模型、用量、非法工具调用和错误的审计；关闭不透明 SDK 重试 |
| 运行扩展 | 用标准 middleware/hooks 承接适合框架生命周期的上下文/日志/模型预算接入 | 既有 Budget 是预算事实来源；并发与物理请求计数需测试证明，不能用每 Agent 独立计数替代共享预算 |
| RAG 输入输出 | 使用标准 Document 与 Retriever 接口；现有 KnowledgeService 以薄适配接入 | 项目/租约过滤先于召回、文档版本/页码/条款/引用 ID/来源校验保持原语义 |
| 检索算法 | 第一阶段继续 BM25，后续有评测依据再替换或增强 | 使用标准 Retriever 不等于已经有向量/混合检索，不能只改接口后宣称检索质量提升 |
| 多 Agent 编排 | 保留现有 LangGraph + Registry，以领域 Agent 子图或明确包装节点接入 | 一份跨领域流程，不新建与现有调查图竞争的 Supervisor/审批系统 |
| 业务治理 | 继续保留 Scope、Evidence、Decimal 计算、权限与审批台账 | 这些是领域规则，不是应当删除的重复框架实现 |
| Web / CLI / Evaluation | 共用标准 Agent 装配入口，网页显式选择并显示实际引擎 | Web 已通过模拟传输验证，实际 DeepSeek 待实测 |

不要求本轮把所有 PDF 加载器、分块器和算法改为某个默认实现：原页码/条款分块在评测中具有契约意义，替换前须证明引用等价。使用 LangChain 标准接口与可替换实现才是目标，不是依赖数量最大化。

## 3. 目标结构

```text
Web / CLI / Evaluation
          ↓ 共用装配
LangGraph 调查：规划 → 领域节点 → 核验 → 报告 → 审批
          ↓
LangChain create_agent（各领域内部标准模型/工具循环）
          ├─ 标准模型：独立 YAML / 用量 / 实际模型
          ├─ middleware：上下文 / 日志 / 模型调用治理适配
          └─ 标准 Tool → ToolExecutor（唯一业务执行边界）
                            ├─ Repository：fixture / SQLite / PG
                            └─ 标准 Retriever / Document → 现有知识服务

MCP Gateway ─────────────────→ 同一个 ToolExecutor
```

不要把身份、权限、预算和模型私有配置作为模型可填的 Tool 参数；从可信运行上下文注入。标准工具输出与 Evidence/ToolExecution 必须建立明确关联，不能靠模型文字重建可信事实。

## 4. 分四个可验收实施步骤

### 第一步：一个真实领域纵向试点

建议先迁移 Billing：增加最小兼容依赖、标准 Agent 工厂、工具桥接和可信上下文；用受控假模型执行完整标准循环。沿用现有 AgentRequest/AgentResult 对外契约，明确内部字段转换，不向 UI 泄漏 LangChain 私有 State。

验收：实际执行 create_agent 的模型/工具节点，不走旧 run_tool_loop；工具真实进入同一个执行器。标准 Agent 的回答、成功事实、失败审计、预算与 Trace 均可检查。提供与旧路径相同输入的离线对照；有目标零成功事实仍不能完成。

### 第二步：推广所有 LLM 入口并接入现有 Graph

迁移 Lease、Property、Single，复用同一标准工厂和桥接器；现有 LLM/hybrid 规划与审批流程保持职责不变。过渡期间保留 legacy 仅用于明确的对照/回滚，不长期维护两套默认运行路径。

验收：相同拒绝/超时/重试/补查/并发用例下，可信目标、项目隔离、合法零结果、失败取证、模型物理调用计数、token 超限记账与审批恢复不退化。框架若并行调用工具，所有调用共享同一预算对象。旧 checkpoint 兼容须实测；无法兼容则显式拒绝或定义新版本，不能静默覆盖旧状态。

### 第三步：检索接口标准化

将 KnowledgeService 结果映射为 Document，提供受可信范围约束的 Retriever；仍由 `document.search` 的受控入口访问。页码、文档版本、签署状态、原文与引用 ID 作为明确 metadata，定义页码从 0/1 起算的转换规则，禁止默默偏移。

验收：同 query、top_k、可信文档集，结果与现有 BM25 期望一致；跨项目/跨租约拒绝、草案/缺失合同语义、引用 L1/L2 校验通过。能独立替换检索后端而不修改领域 Agent；先不引入 Chroma/BGE/reranker 或数据库重建。

### 第四步：Web 真实模型接线、文档与旧循环收尾

API 与 CLI 使用共同装配；服务端配置选择模式和预算，不暴露 Key。网页展示实际引擎、服务端模型、调用次数、用量、领域回答及证据，离线与真实模式明确。最终综合分析是单独可测的报告步骤，不能由 UI 编造或省略证据校验。

验收：离线假模型端到端证明 Web 请求确实进入标准 Agent；缺 Key/超时/预算错误不冒充 AI 成功。真实付费验证仅在用户另行明确授权后进行。补新工程师文档：入口、标准对象、项目适配点、新增 Agent/Tool/Retriever 步骤；清点旧循环调用方，迁移完成前保留历史，完成后旧实现标 legacy/归档，不直接删除。

## 5. 迁移测试与范围控制

- Task 036 的 719 项测试（45 项跳过）是迁移前证据。迁移后结果见 [Task 038](../prompts/04_agents/2026-11-24_038_langchain_standardization.md)。
- 先复用、扩展有业务意义的契约和反例；不得为适配新框架而放宽安全/金额/审批断言。新实现导致离线轨迹变化须解释；真实文本不要求字面一致。
- 重点补物理模型请求=账本、并发/重试不超限、可信 Scope 注入、错误 ToolMessage 不计事实、多 Agent 补查、Graph 恢复与跨项目检索用例。
- 不改历史 scoring-v3.3 或 formal_20261123 原始结果。新引擎的实验独立标版本，评分审计与模型框架迁移分开。
- 不将 dev_loop 自动编码循环视为运行时 Agent 架构的一部分；本 ADR 不触发自动编码、安装、付费请求或 Git 操作。

## 6. 取舍与官方依据

收益：标准 Agent 生命周期、工具/消息接口和检索扩展点更容易被熟悉 LangChain 的工程师理解；减少自定义通用循环维护。

代价：新增高层依赖及版本兼容责任；结果/预算/错误/恢复适配仍需项目代码，不能因“用了框架”就宣称低耦合或安全已自动达成。最小跨项目核心应只知道标准组件与治理接口，不能硬编码合同/账单/物业领域。

本轮核对官方文档（2026-11-24）：

- [Agents / create_agent](https://docs.langchain.com/oss/python/langchain/agents)：标准模型工具循环与 prompt/tools/middleware 配置。
- [Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview)：日志、提示词、工具选择、重试/回退等生命周期扩展。
- [Tools](https://docs.langchain.com/oss/python/langchain/tools)：类型化工具与 ToolRuntime 可信运行上下文。
- [Retrieval](https://docs.langchain.com/oss/python/deepagents/retrieval)：可复用既有知识库和检索服务，不需要为采用框架重建知识底座。

以上支持迁移方向，不代表官网当前示例和本机已装版本天然兼容。具体依赖版本、函数签名、middleware 顺序及子图恢复语义由第一步验证后冻结。
