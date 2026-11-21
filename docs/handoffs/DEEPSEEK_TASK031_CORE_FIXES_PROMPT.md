# 给 DeepSeek 的实施 Prompt：Task 031 核心正确性收尾（Z1–Z3、CLI、模型配置、配置真实性、路由兜底）

> 系列任务：031（本任务，后端正确性）→ 032（业务流程工作台前端）→ 033（MCP 工具网关）。
> **三个任务分开执行，每个任务完成后停下来等待独立复查，不要一次做完三个。** 本任务完成前不得开始 032/033。

请在当前 `D:\commercial-property-multi-agent` 仓库直接完成本任务：实现、自检、按项目文档规范归档，然后汇报。本任务已获用户授权实施；**不提交、不推送、不打 Tag、不部署**，不调用付费真实模型（除非用户在对话中另行明确授权）。

## 0. 为什么做这个任务

外部复查（2026-11-21）结论：Runtime / LangGraph / RAG / 审批 / 评测骨架不需要重做，但有几类问题会让“真实模型下多 Agent 是否优于单 Agent”的正式对照失真，必须先清掉：

1. Z1–Z3 仍未修（见 `docs/reviews/2026-11-07_q1_q3_acceptance_review.md`）。
2. CLI 存在名不副实或无效的参数。
3. 所有领域 Agent 实际共用 `single.yaml` 创建的模型客户端，领域 YAML 中的模型配置不生效。
4. 配置声明了未实现的能力（`compliance.yaml` 写着 chroma 向量库与 bge 嵌入，代码只有 BM25）。
5. `RuleBasedPlanner` 关键词未命中时**静默**落到 billing。

## 1. 先核对仓库（必须）

完整阅读并以实际代码为准：

- `docs/architecture/CURRENT_BASELINE.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`、`docs/README.md`
- `docs/reviews/2026-11-07_q1_q3_acceptance_review.md`（Z1–Z3 原始反例）
- `backend/app/cli.py`、`backend/app/single_demo.py`、`backend/app/agents/single/agent.py`
- `backend/app/agents/base/scope.py`、`llm_agent.py`、`conclusions.py`、`evidence.py`
- `backend/app/llm/factory.py`、`langchain_client.py`、`backend/app/agents/factory.py`
- `backend/app/config/schema.py`、`loader.py`、`backend/app/config/agents/*.yaml`
- `backend/app/orchestration/investigation.py`（`RuleBasedPlanner`）
- 相关测试：`test_single_agent_scope.py`、`test_evidence_and_answer.py`、`test_fund_conclusions.py`、`test_llm_agents.py`、`test_graph_workflow.py`、`test_runtime.py`

运行 `git status`。复查时工作区有未提交的 `.gitignore` 修改和未跟踪的 `tools/flowise/`：**保留，不改、不删、不提交**。`tools/flowise/` 是独立试用的 Flowise 实例，本任务不接入、不引用。

## 2. 工作项

### 2.1 Z1：`ask` 必须携带可信目标

- `ask` 增加 `--lease`（与 `investigate` 同名同语义）及必要的 `--unit`；目标通过现有 TaskScope 机制注入可信上下文，模型不能更换或省略。
- 有业务目标的问题不能再被当成 explain 处理。
- 补回归：Z1 原始反例通过；目标被模型改写时拒绝；省略时按注入值执行。

### 2.2 Z2：失败的工具调用不能算作取证

- 失败、被拒绝、超预算、超时的调用不得进入 accepted 证据，也不能满足“已取证”的完成条件。
- 有目标的请求如果零事实，结果必须失败或降级，不能成功。
- **合法的零结果**（工具成功执行、查询结果为空，例如没有未关闭工单）必须保留为成功事实，不能和失败混为一谈。
- 补回归，覆盖上述三种情况。

### 2.3 Z3：默认输出必须展示可信资金结论

- `ask` 和 `investigate` 的默认摘要都要展示结构化资金结论（应收 / 已收 / 未收及其核验状态），与模型原话分栏，并标明来源。
- 模型叙述与可信字段不一致时，显示差异提示（复用现有 `narrative_discrepancies`），不能只展示模型原话。

### 2.4 CLI 清理

1. **模型来源参数统一**：两个命令都用 `--model-provider {offline,scripted,deepseek}`。`ask` 的旧参数 `--provider fake|deepseek` 保留为**已弃用别名**（`fake` 映射到 `scripted`），使用时向 stderr 打印弃用提示。两个命令的预算参数对齐（`investigate` 补 `--budget-model-calls`）。
2. **`approve --dry-run` 名不副实**：现在它会真实写入审批台账，只是不恢复图，可能导致台账与 checkpoint 不一致。改为**只做校验、不写入任何数据**。如果确实需要“只记录不恢复”的能力，另起明确的名字（如 `--record-only`），并在帮助文本写清会写台账。补测试：dry-run 前后台账逐字节不变。
3. **`approve --thread-id` 是无效参数**（定义了但从未使用）：删除，或真正接通并测试，二选一，在归档里说明选择理由。
4. **退出码分开**并写进 `--help` 和 `backend/README.md`：`0` 成功，`1` 业务结果失败（如 Z2 的零事实），`2` 用法或配置错误，`3` 审批错误。现有测试和脚本如有依赖，同步更新。
5. **身份来源可见**：`--principal` 暂时保留（演示和评测依赖它），但默认值改为读取与 API 相同的 `DEMO_PRINCIPAL_ID` 环境变量；显式传入 `--principal` 时向 stderr 打印“开发模式：命令行自报身份，不可用于生产”，并在 Trace 或报告元数据中记录 `identity_source=cli_flag`。**不要**在本任务里实现 SSO/OAuth。

### 2.5 每个 Agent 的模型配置真正生效

- 模型客户端按各 Agent 自己的 YAML 创建（provider、model_name、temperature、max_tokens、api_key_env、timeout）。参数相同的可以共享缓存实例，缓存键必须包含全部影响行为的参数。
- 报告和评测输出中按 Agent 列出**实际使用的** provider / model / 参数，不能只写一个全局模型。
- 配置无效（未知 provider、缺少 api_key_env、参数越界）时启动即失败，不静默回退。
- 离线测试证明：修改某个领域 YAML 的 model_name 只影响该 Agent。
- **核对模型名是否过时**：现有 YAML 使用 `deepseek-chat`。DeepSeek API 在 2026-09 发布了 V4.1-Flash（模型名 `deepseek-flash`），并下线或重路由了部分旧型号。请以 DeepSeek 官方 API 文档为准，核对 `deepseek-chat` 目前实际路由到哪个模型；如需更换，只改配置并在归档中写明依据和日期，**不要为此调用付费接口做测试**。报告中记录的模型名必须是实际调用的那个。

### 2.6 配置不能声明未实现的能力

- `config/schema.py` 校验 `retrieval_settings`：只接受当前实际实现的检索方式（目前是 BM25）。声明 `vector_store: chroma`、`embedding_model` 等未实现项时，`app.cli check` 报错。
- 修正 `compliance.yaml` 等现有 YAML，使其只描述真实能力。未来计划写进文档，不写进运行配置。
- Compliance Agent 保持禁用，不实现业务逻辑。

### 2.7 路由兜底：未命中不能静默落到 billing

- `RuleBasedPlanner` 未命中任何领域时，返回明确的 `needs_clarification` 结果（或等价路由），说明“无法判断问题属于合同、账单还是物业”，并列出可选领域。**禁止**默认走 billing。
- 新建 `docs/architecture/planner_vocabulary.md`，把关键词表整理成“领域 → 同义词”，可以适度补充真实口语说法（如“冷气 / 不制冷 / 空调不凉”“物业费 / 管理费”）。**每一个新增词都要说明来源依据，不得为了让某道评测题通过而加词。**
- 路由理由（命中了哪些词）写入报告，方便排查。

## 3. 评测与边界（重要）

- **不得修改** `docs/evaluation/cases/` 下任何题目、评分规则文件或已有报告。
- 改动前后各跑一次离线评测：`python -m app.cli evaluate --split heldout`。新报告另存为新版本，在归档中逐题列出结果变化及原因。如果路由兜底导致某些题从通过变为失败，**如实报告，不要为了维持分数去调规则**。
- 不新增业务写操作，不改变审批语义（两级串行、只产出草案、副作用为空）。
- 不改前端（属于 Task 032），也不做 MCP（属于 Task 033）。

## 4. 验收

1. 全量回归：`python -m unittest discover -s tests -p "test_*.py"`，以及 `python tests/smoke_agent_contracts.py`。记录**实际**输出数字，不照抄 409/57。
2. Z1、Z2、Z3 各自的原始反例逐条复跑并贴出输出。
3. CLI：每个改动点至少一条测试；`--help` 文本与行为一致。
4. `python -m app.cli check` 对错误配置报错，对修正后的配置通过。
5. 用 `--model-provider scripted` 跑通 ask 和 investigate；不调用付费模型。

## 5. 归档（按项目现有规范）

- 在 `docs/README.md` 登记 Task 031；新建 `docs/prompts/06_testing/`（或合适分类）下的任务存档，包含：原始 Prompt 全文、实施内容、验证命令与真实输出、遗留问题。
- 更新 `docs/development_logs/development_log.md`、`docs/issues/issue_log.md`（每个问题写根因、修法、如何防止复发）。
- 同步更新 `CURRENT_BASELINE.md`、路线图和根目录 README 的相关状态行。**正文和状态表必须一致**，不能只在顶部叠加新结论。

## 6. 汇报格式

完成后用中文汇报：每个工作项的“做了什么 / 证据（测试名或命令输出）/ 仍未解决的”；评测前后对比表；你认为最需要复查的 3 个地方。**不要声称已通过最终验收**，最终验收由独立复查决定。

## 7. 如果启用了智能体团队协作

- `backend/app/cli.py` 同时涉及 2.1、2.3、2.4，**只能由一名成员修改**，其他成员把需要的改动交给他合并。
- 适合并行的拆分：①Z2（证据与完成条件）；②2.5 模型配置 + 2.6 配置校验；③2.7 路由兜底与词表文档；④负责人：CLI（2.1、2.3、2.4）及全部归档文档。
- 评测前后对比必须在所有改动合并之后由负责人统一运行，不能用各成员分别跑的结果拼表。
