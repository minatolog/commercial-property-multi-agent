# 2026-11-21_031_core_correctness_fixes

## 1. 基本信息

- **日期**：2026-11-21（Asia/Shanghai）。
- **任务编号**：031（全局递增，接 030）。
- **模块**：06_testing（后端正确性收尾：Z1–Z3、CLI、模型配置、配置真实性、路由兜底；实现跨 `06_testing` / `04_agents` / `01_environment` 的边界）。
- **Git Commit**：`Pending`。起点 `main` / `e3b3594`；本轮未提交、未推送、未打 Tag、未部署。
- **起点工作区**：`main` / `e3b3594`，含未提交 `.gitignore` 修改与未跟踪 `tools/flowise/`；按 Prompt 要求**保留、未改、未删、未提交**。`docs/handoffs/DEEPSEEK_TASK031..033_*.md` 为用户提供的交接文件，保持未跟踪，不作为本轮产出。
- **协作方式**：本任务按 Prompt 第 7 节启用 Agent Teams：负责人（Lead）统一修改 `backend/app/cli.py`、`backend/app/single_demo.py`、`backend/app/orchestration/approval.py` 与全部归档文档；三名成员分别负责 ①Z2 取证口径、②2.5 模型配置 + 2.6 配置校验、③2.7 路由兜底与词表文档。改动合并后，评测前后对比由负责人统一运行。
- **关联任务**：[Task 025 独立复查](../../reviews/2026-11-07_q1_q3_acceptance_review.md)（Z1–Z3 原始反例）、任务 024（Q1–Q3 修复）、任务 030（最新独立复查）。Task 032/033 未启动。

## 2. 任务目标和背景

外部复查（2026-11-21）结论：Runtime / LangGraph / RAG / 审批 / 评测骨架不需要重做，但以下问题会让"真实模型下多 Agent 是否优于单 Agent"的正式对照失真，必须先清掉：

1. **Z1–Z3 仍未修复**：默认 `ask` 未装配可信目标（业务问题被当成 explain）；失败的工具调用被算作取证；默认 CLI 摘要不展示可信资金结论。
2. **CLI 名不副实**：`approve --dry-run` 会真实写审批台账；`approve --thread-id` 是无效参数；退出码不区分业务失败与用法错误；身份来源不可见。
3. **领域 YAML 的模型配置不生效**：所有领域 Agent 实际共用 `single.yaml` 创建的模型客户端。
4. **配置声明未实现能力**：`compliance.yaml` 声明 chroma 向量库与 bge 嵌入，代码只有 BM25。
5. **路由静默兜底**：`RuleBasedPlanner` 关键词未命中时静默落 billing。

本轮目标：按 Prompt 完成上述修复，离线自检，按项目规范归档；**不提交、不推送、不打 Tag、不部署、不调用付费模型**；不改前端（032）、不做 MCP（033）。

## 3. 原始用户 Prompt

> 逐字保存，不擅自改写、不提炼、不补全。原文同时存在于 `docs/handoffs/DEEPSEEK_TASK031_CORE_FIXES_PROMPT.md`。

```text
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
```

## 4. AI 实际执行的主要步骤

1. **仓库核对**：完整阅读 `docs/architecture/CURRENT_BASELINE.md`、路线图、`docs/README.md`、Task 025 复查报告，以及 Prompt 列出的 CLI、Single Agent、BaseAgent 契约、模型工厂、配置、Planner 与相关测试；记录 `git status`（原有 `.gitignore` 修改与 `tools/flowise/` 保留不动）。
2. **改动前基线**：在 `backend/` 运行全量回归（409 tests，OK，skipped=1）、契约自检（57 项）、`python -m app.cli check`（exit 0），并运行 `python -m app.cli evaluate --split heldout`，把 4 份报告与命令输出保存到 `docs/reviews/task031_evidence/before/`（A 20/30、B 21/30、C 23/30）。
3. **改动前反例取证**：用 `git worktree add --detach <临时目录> HEAD` 取出干净 HEAD 代码（只读临时工作树，用后 `git worktree remove` 清理），运行统一反例脚本 `docs/reviews/task031_evidence/counterexamples.py`，保存 Z1/Z2/Z3 的真实"改动前"输出。
4. **分工与并行实施**（Lead 统一集成）：
   - 负责人：Z1（`ask` 可信目标解析/注入与拒绝）、Z3（`ask`/`investigate` 默认摘要分栏展示可信资金结论）、2.4 全部 CLI 改动（含 `approve --dry-run` 改为纯校验、删除 `--thread-id`、退出码、身份来源）、`approval.py` 的只读预演、全部归档文档。
   - 成员 A（z2-evidence）：Z2——把"可算取证"的判定收敛到 `agents/base/evidence.py` 的 `partition_tool_executions` / `evidence_of_executions` / `minimum_evidence_reason`，Single 与 LLM 两条路径共用；失败/越界调用只做审计。
   - 成员 B（model-config）：2.5 每 Agent 模型配置（按 YAML 建客户端、缓存键含全部参数、非法配置启动期失败、按 Agent 报告实际模型）+ 2.6 检索配置真实性 + 官方文档核对模型名 + `deepseek-chat → deepseek-flash` 配置更新。
   - 成员 C（planner-fallback）：2.7 路由兜底（`needs_clarification` + `routing_reason`）、新建 `vocabulary.py` 与 `docs/architecture/planner_vocabulary.md`。
5. **跨范围协调**：`backend/app/cli.py` 只由负责人修改；成员需要 CLI/评测集成时先在完成消息中说明契约，负责人统一接线（如 `build_investigation_bundle(model_provider=..., scripted_calls=...)`、`evaluate(..., model_provider=...)`、`bundle.agent_models`）。
6. **合并与自检**：三名成员完成后，负责人逐文件复核 diff、清理临时脚本，再统一运行全量回归、契约、`check`、无效配置反例、CLI 证据采集、Z1–Z3 反例复跑。
7. **改动后评测**：在所有改动合并后，由负责人统一运行一次 `python -m app.cli evaluate --split heldout`（报告写入 `docs/evaluation/reports/` 新版本），并用脚本与改动前报告逐题比较（用例、fixture 校验和确认未变）。
8. **归档**：按项目规范新增本文件、证据目录、词表文档；同步 `docs/README.md`、`CURRENT_BASELINE.md`、路线图、根 README、`backend/README.md`、`agent_architecture.md`、`agent_development_guide.md`、`evaluation_plan.md`、开发日志、问题记录、Git 检查点。未提交、未推送。

## 5. 新增和修改的文件

### 5.1 实现（backend）

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/single_demo.py` | 修改 | Z1：`resolve_ask_target()` + `AskTarget` + `TargetResolutionError`；可信目标注入 `payload`；新增 `scripted` provider；`bundle.target` / `identity_source`；deepseek 改用每配置工厂 |
| `backend/app/cli.py` | 修改 | Z1 参数接线与退出码；Z3 默认摘要分栏；2.4 全部改动（统一 `--model-provider`、弃用 `--provider`、`investigate --budget-model-calls`、`approve --dry-run` 纯校验、删除 `approve --thread-id`、身份来源、`check` 输出模型/检索配置） |
| `backend/app/orchestration/approval.py` | 修改 | 新增 `ApprovalStore.preview_decision()`：在台账副本上执行真实 `decide()`，原台账零写入 |
| `backend/app/agents/base/evidence.py` | 修改 | Z2：`partition_tool_executions` / `evidence_of_executions` / `minimum_evidence_reason` / 失败审计投影 |
| `backend/app/agents/single/agent.py` | 修改 | Z2：accepted 只含成功且目标一致的执行；零事实有目标请求失败；证据只来自 accepted；失败审计输出 |
| `backend/app/agents/base/llm_agent.py` | 修改 | Z2：与 Single 共用取证口径；证据过滤；最低取证检查；契约校验不放松 |
| `backend/app/llm/factory.py` | 修改 | 2.5：`validate_model_config`、`build_model_client_for_config`、`ModelClientCache`、`describe_agent_model`；保留原 `build_model_client` 语义 |
| `backend/app/agents/factory.py` | 修改 | 2.5：`build_registry(..., model_client=..., model_clients=...)`，按 Agent 名注入；llm 引擎缺客户端显式失败 |
| `backend/app/investigation_demo.py` | 修改 | 2.5：`model_provider` / `scripted_calls` / `config_dir` / `client_factory`；`bundle.agent_models`；脚本化/真实模型按 YAML 装配 |
| `backend/app/evaluation/baselines.py` | 修改 | 2.5：`BaselineResult.models_by_agent`；B/C 模型路径按各自配置装配 |
| `backend/app/evaluation/runner.py` | 修改 | 2.5：`evaluate(..., model_provider=...)`；`summary["models_by_agent"]`、`bindings.models_by_agent`、markdown 小节 |
| `backend/app/config/schema.py` | 修改 | 2.6：`RetrievalSettings` 只保留 `enabled` / `top_k`；声明未实现检索字段即加载失败 |
| `backend/app/config/agents/*.yaml` | 修改 | 2.6 真实化检索配置；2.5 `model_name` 更新为 `deepseek-flash`（5 个文件） |
| `backend/app/orchestration/vocabulary.py` | 新增 | 2.7：唯一领域词表（`DOMAINS`/`DOMAIN_LABELS`/`DOMAIN_HINTS`/`matched_domains`），逐词来源见词表文档 |
| `backend/app/orchestration/investigation.py` | 修改 | 2.7：`PlanDetail`/`plan_detailed()`；未命中 → `needs_clarification` 分支；`routing_reason` 与 `clarification` 写入报告 |

### 5.2 测试（backend/tests）

| 文件 | 类型 | 说明 |
|---|---|---|
| `test_task031_z1_ask_target.py` | 新增 | Z1：原始反例、换目标拒绝、省略注入、无目标业务问题、目标冲突、纯说明 |
| `test_task031_z2_evidence.py` | 新增 | Z2：schema 错/超时/预算耗尽/范围拒绝/parse_error/纠正/合法零结果；Single 与 LLM 两条路径 |
| `test_task031_z3_default_output.py` | 新增 | Z3：ask/investigate 默认摘要分栏、verified/mismatch/unverified、差异提示 |
| `test_task031_cli.py` | 新增 | 2.4：`--model-provider` 统一与弃用别名、`--budget-model-calls`、dry-run 逐字节不变、删除 `--thread-id`、退出码、身份来源、`check` 输出 |
| `test_task031_model_config.py` | 新增 | 2.5/2.6：逐 Agent 客户端隔离、缓存键、非法配置启动失败、配置校验、逐 Agent 模型报告 |
| `test_task031_planner_fallback.py` | 新增 | 2.7：无法归类 → clarification 且零工具；路由理由；普通路由不变 |
| `test_llm_agents.py` | 修改 | 2.5 模型工厂/装配断言更新（脚本化注入语义、模型名） |
| `test_llm_tool_loop.py` | 修改 | 2.5 模型名断言（`deepseek-chat` → `deepseek-flash`，一行） |
| `test_evaluation.py` | 修改 | 2.5 `models_by_agent` 报告断言 |
| `test_graph_workflow.py` | 修改 | 2.7 未命中问题断言由"默认 billing"改为"clarification" |
| `test_task031_*.py` 之外的既有测试 | 未改 | `test_single_agent_scope.py` / `test_evidence_and_answer.py` / `test_runtime.py` 全部原样通过 |
| `smoke_agent_contracts.py` | 修改 | 2.6：未实现检索字段（vector/embedding/rerank/权重/min_score）逐个拒绝 + 加载器级拒绝 + 真实配置只留 `enabled`/`top_k`；2.5：逐 Agent 模型参数审计、未知 provider/缺 `api_key_env` 报错、模型名更新为 `deepseek-flash` |

### 5.3 文档与证据

| 文件 | 类型 | 说明 |
|---|---|---|
| `docs/architecture/planner_vocabulary.md` | 新增 | 2.7：领域 → 同义词逐词来源、兜底契约、`routing_reason`/`clarification` 口径、加词门禁 |
| `docs/reviews/task031_evidence/` | 新增 | 前后命令输出、报告、反例 JSON、对比脚本与结果（见第 6 节） |
| `docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md` | 新增 | 本归档 |
| `docs/README.md`、`docs/architecture/CURRENT_BASELINE.md`、`docs/architecture/agent_architecture.md`、`docs/architecture/agent_development_guide.md`、`docs/architecture/agent_runtime_contracts.md`、`docs/architecture/system_design.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`、`docs/product/mvp_scope_v2.md`、`docs/evaluation/evaluation_plan.md`、`docs/demo/demo_script.md`、`docs/development_logs/development_log.md`、`docs/issues/issue_log.md`、`docs/lessons_learned/knowledge_notes.md`、`docs/checkpoints/git_history.md`、`README.md`、`backend/README.md` | 修改 | 同步状态、命令、退出码、模型名、评测与未完成项；**正文与状态表一致** |
| `docs/evaluation/reports/20261121T085431_*` | 新增 | 改动后离线 heldout 评测报告（新版本，不覆盖历史） |

## 6. 执行结果和验证方式

解释器：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18）；命令均在 `backend/` 下执行；设置 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`。证据文件在 `docs/reviews/task031_evidence/`（`before/` 与 `after/`）。

### 6.1 全量回归与自检（改动后）

| 验证项 | 命令 | 实际输出 / 结论 |
|---|---|---|
| 全量回归 | `python -m unittest discover -s tests -p "test_*.py"` | `Ran 529 tests in 33.425s`，`OK (skipped=1)`；skip 为既有"本机已配置密钥跳过缺密钥用例" |
| 契约自检 | `python tests/smoke_agent_contracts.py` | `全部通过：70 项检查` |
| 配置自检 | `python -m app.cli check` | exit 0；输出含逐 Agent `models`（provider/model/temperature/max_tokens/timeout/api_key_env/api_key_env_present）与 `retrieval_settings`（只剩 `enabled`/`top_k`） |
| 无效配置必须报错 | 临时在 `compliance.yaml` 的 `retrieval_settings` 加 `vector_store: chroma` 后跑 `check` | exit 2，`AgentConfigError: ... retrieval_settings.vector_store: Extra inputs are not permitted`；随后按字节恢复原文件并校验 SHA-256 一致 |
| 脚本化 ask | `python -m app.cli ask "A-301 现在还有多少钱没交？"` | exit 0；`target.source=question_parse`、`trusted_conclusion.check_status=unverified`、`fund_conclusion` 为 52596.00 / 34560.00 / 18036.00 |
| 脚本化 investigate | `python -m app.cli investigate --model-provider scripted` | exit 0；`agent_models` 按 Agent 列出 scripted 客户端；`authoritative_amounts` 有可信金额；模型叙述单列（unverified） |
| 无付费模型调用 | — | 本轮未配置/未使用付费接口；deepseek 分支只用占位密钥做客户端构造，未发起请求 |

### 6.2 Z1：`ask` 必须携带可信目标（原始反例复跑）

同一脚本 `counterexamples.py` 分别在干净 HEAD（改动前，临时 worktree）与当前工作区（改动后）运行；完整 JSON 见 `docs/reviews/task031_evidence/{before,after}/counterexamples.json`。

**改动前**（真实输出）：`ask "A301现在还欠多少" --provider fake`，模型调用 B-101 后回答"应收 0、已收 0、未收 0，已经结清"

```json
{"exit": 0, "status": "success", "error_code": null,
 "answer_or_narrative": "A301 应收 0.00、已收 0.00、未收 0.00，已经结清。",
 "target_mode": null, "target_lease": null, "evidence_count": 0,
 "trusted_conclusion_source": null}
```

**改动后**（同一脚本）：

```json
{"exit": 1, "status": "failed", "error_code": "insufficient_evidence",
 "target_mode": "targeted", "target_lease": "lease_xh_a301_2025",
 "evidence_count": 0, "trusted_conclusion_source": "none",
 "failed_tool_calls": [{"tool": "billing.statement.read", "status": "rejected_arguments",
   "error_code": "invalid_tool_arguments",
   "message": "参数 lease_id='lease_jl_b101_2025' 超出本次任务范围（应为 'lease_xh_a301_2025'）；工具 billing.statement.read 的调用已被拒绝"}],
 "stderr_head": ["[deprecated] --provider 已弃用，请改用 --model-provider（fake→scripted，deepseek→deepseek）"]}
```

回归测试（`test_task031_z1_ask_target.py`，11 项）覆盖：原始反例 now failed；模型改写到同项目 A-302 → 拒绝且零证据；模型省略 `lease_id` → 按注入值执行（verified，fund_conclusion 正确）；`--lease`/`--unit` 显式目标生效；问题与 `--lease` 冲突 → 用法错误；问题含不可解析商铺编号 → 用法错误；有业务词但无目标 → exit 2（不再静默 explain）；纯说明问题无目标 → explain 成功。

### 6.3 Z2：失败调用不计取证（原始反例复跑）

**改动前**（定向构造：目标 A-301，模型调用 `billing.statement.read` 且带未知字段，随后说"已经核对，没有问题"）：

```json
{"status": "success", "error_code": null, "facts": {}, "evidence_count": 0,
 "tool_calls": [{"tool": "billing.statement.read", "status": "error", "attempts": 0}],
 "failed_tool_calls": null}
```

**改动后**：

```json
{"status": "failed", "error_code": "insufficient_evidence", "facts": null,
 "evidence_count": 0,
 "error_details_keys": ["failed_tool_calls", "rejected_outputs", "task_scope", "tool_calls", "warnings"]}
```

回归测试（`test_task031_z2_evidence.py`，17 项）覆盖：schema 参数错、工具超时、工具预算耗尽、跨项目范围拒绝、parse_error、全部失败、失败后合法纠正、失败与合法调用共存、越界输出证据过滤、纯说明不强制取数、合法零结果（零工单 / 条款零命中）仍成功；SingleToolAgent 与 LLMToolAgent 两条路径。

### 6.4 Z3：默认输出展示可信资金结论（原始反例复跑）

**改动前**：`ask` 默认摘要只有 `answer`（模型原话），`investigate` 默认摘要没有 `authoritative_amounts` / 模型叙述分栏：

```json
{"ask": {"has_trusted_conclusion": false, "raw_answer_field": "应收 52596.00、已收 34560.00、未收 18036.00。"},
 "investigate": {"has_authoritative_amounts": false, "model_narratives": null}}
```

**改动后**：

```json
{"ask": {"has_trusted_conclusion": true,
  "trusted_conclusion": {"source": "tool_facts", "check_status": "verified",
    "fund_conclusion": {"invoiced_total": "52596.00", "paid_total": "34560.00", "outstanding_total": "18036.00"},
    "rendered": "应收 52596.00、已收 34560.00、未收 18036.00（CNY）"},
  "model_narrative": {"answer": "应收 52596.00、已收 34560.00、未收 18036.00。", "fund_check_status": "verified"},
  "narrative_discrepancies": []},
 "investigate": {"has_authoritative_amounts": true,
  "authoritative_amounts": [{"agent": "billing", "capability": "billing.statement", "source": "tool_facts",
    "fund_conclusion": {"invoiced_total": "52596.00", "paid_total": "34560.00", "outstanding_total": "18036.00"},
    "check_status": "not_checkable", "check_note": "本子任务没有模型叙述，核对状态不适用"}],
  "model_narratives": []}}
```

回归测试（`test_task031_z3_default_output.py`，5 项）另覆盖：写反金额 → `check_status=mismatch` 且 `narrative_discrepancies` 出现 `kind=fund`；脚本化 investigate → `unverified` 单列；模型叙述与可信金额不一致 → 默认摘要可见。

### 6.5 2.4 CLI 清理（真实命令输出见 `after/cli_contract_evidence.json`）

| 改动点 | 实际结果 |
|---|---|
| 统一 `--model-provider {offline,scripted,deepseek}` | `ask` 默认 `scripted`；`investigate` 默认 `offline`；`--provider fake` 收到 stderr 弃用提示并映射 `scripted`；`--provider` 与 `--model-provider` 冲突 → exit 2；`ask --model-provider offline` → exit 2（ask 必须有模型） |
| `investigate` 补预算参数 | `--budget-model-calls`（默认 32）出现在 `--help`，并传入调查预算 |
| `approve --dry-run` 名不副实 | 改为只做校验：`dry_run=true`、`wrote_data=false`、`resumed_graph=false`；**台账与 checkpoint 全部文件逐字节不变**（SHA-256 对比），台账决定数仍为 0；随后的真实 `approve` 才写入决定（`pending_next_stage`）。台账不存在时 exit 3 且**不创建**台账 |
| `approve --thread-id` 无效参数 | 删除；argparse 拒绝该参数（SystemExit 2）；恢复所用 thread_id 一律取自台账请求 |
| 退出码分开 | `0` 成功 / `1` 业务结果失败（Z2 零事实、clarification）/ `2` 用法或配置错误 / `3` 审批错误；写入顶层 `--help` epilog、`approve --help` 与 `backend/README.md` |
| 身份来源可见 | `--principal` 默认读取 `DEMO_PRINCIPAL_ID`（与 API 相同，环境缺失时回退原默认主体）；显式传入时 stderr 输出"开发模式：命令行自报身份，不可用于生产"，报告元数据记录 `identity_source=cli_flag`；`approve` 的主体若无审批权限则回退默认审批人并提示 |

### 6.6 2.5 每个 Agent 的模型配置真正生效

- 实现：`build_investigation_bundle(model_provider=...)` 对每个 LLM Agent 用**自己的 YAML** 构造客户端（同参数共享缓存实例，缓存键 = provider/model_name/temperature/max_tokens/api_key_env/timeout_seconds）；`build_registry(model_clients=...)` 按 Agent 名注入；`bundle.agent_models` 与评测 `models_by_agent` 逐 Agent 记录实际 provider/model/参数/是否共享/配置来源。
- 离线隔离证据（`test_task031_model_config.py`，37 项）：临时配置目录只把 `billing.yaml` 的 `model_name` 改为 `billing-probe-model-X` 后，`client_factory` 收到的映射为 `billing:billing-probe-model-X`，`lease/property/single` 仍为 `deepseek-flash`；参数完全相同的 Agent 共享同一客户端实例、改任一参数即不再共享。
- 非法配置启动期失败：未知 provider、YAML 写 `scripted`、缺 `api_key_env`、temperature/max_tokens/timeout 越界 —— 均抛 `AgentConfigError`，不回退到其它 Agent 的客户端或离线实现。
- **模型名核对**（2026-11-21 查阅 DeepSeek 官方文档，未调用接口）：
  - <https://api-docs.deepseek.com/news/news260424>：`deepseek-chat` & `deepseek-reasoner` 于 **2026-07-24 15:59 UTC** 之后完全退役、不可访问（原文 "will be fully retired and inaccessible after Jul 24th, 2026, 15:59 (UTC Time)"）。
  - <https://api-docs.deepseek.com/quick_start/pricing>：当前模型名只有 `deepseek-flash`（MODEL VERSION `DeepSeek-V4.1-Flash-1017`）与 `deepseek-v4-pro`；`deepseek-v4-flash` 等旧名仍被接受但已改由 V4.1-Flash 承接。
  - 结论：5 个 Agent YAML 的 `model_name` 改为 `deepseek-flash`；历史报告/历史文档中的 `deepseek-chat` 保留原文（当时确实使用该模型名），不追改。
  - **（返修 R2 更正）** 官方公告已下线；本项目 11-06 实测以该名字仍可调用，实际应答模型当时未记录。历史报告中的 `model_name` 是**配置名**，不是服务端实际应答模型；返修后真实调用会额外记录 `served_models`（见第 10 节）。

### 6.7 2.6 配置不声明未实现能力

- `RetrievalSettings` 只保留 `enabled`、`top_k`；`vector_store`/`embedding_model`/`rerank_top_n`/`bm25_weight`/`vector_weight`/`min_score` 已从 Schema 移除（声明即 `extra="forbid"` 报错）。
- `compliance.yaml`/`lease.yaml` 等已删除上述字段；`compliance` 保持 `enabled: false`、业务逻辑未实现（`NOT_IMPLEMENTED`）。
- `check` 对非法配置 exit 2（见 6.1）；对修正后的配置 exit 0。
- 历史未实现 `allowed_tools`（`lease.term_extract`、`compliance.checklist.read`）按 Task 007 决策保留，由 `check.unimplemented_allowed_tools` 显式列出，不属静默声明；本任务未扩展该范围。

### 6.8 2.7 路由兜底不再静默落 billing

- **改动前**（真实图路径，问题"请帮我看看这个事情"）：`route=deterministic`，静默调用 1 次 `billing.statement.read`，`verdict=conflicting`，报告**没有** `routing_reason`。
- **改动后**：`verdict=needs_clarification`、`route=clarification`、零子任务、零工具调用、`approval_status=not_required`；`report["clarification"]` 说明"无法判断属于合同、账单还是物业"并列出三个可选领域；`report["routing_reason"]` 在普通运行中始终写入命中词（示例见 `after/cli_investigate_clarification.json` 与脚本化调查报告）。
- 词表：`backend/app/orchestration/vocabulary.py` 为唯一来源；Task 009 原词 100% 保留；新增 14 个词逐词来源见 [planner_vocabulary.md](../../architecture/planner_vocabulary.md)（"欠/没交"等来自既有 `_ARREARS_HINTS`，"物业费/管理费/冷气/不制冷/空调不凉"来自 Prompt 举例与 fixture 原文/口语；未针对评测题调词）。
- 回归测试（`test_task031_planner_fallback.py`，18 项）：无法归类 → clarification 零工具；有命中 → 原 route/subtask 不变；路由理由写入报告；补查/审批恢复不丢理由。

### 6.9 离线 heldout 评测前后对比（同一 fixture / 用例 / 评分，改动合并后统一重跑）

改动前：`docs/reviews/task031_evidence/before/reports/20261121T083756_*`；改动后：`docs/evaluation/reports/20261121T085431_*`。用例 SHA-256、fixture SHA-256、评分规则版本均未变化（`cf22fd46…`、`bcff5ce9…`、`scoring-v3.3`）。两份报告的 `code_commit` 都是 `e3b3594`，因为改动尚未提交；区分依据是生成时间与对应工作区状态，这是项目现有"报告绑定 commit"的已知局限，复查时需注意。

| 基线 | 通过（前 → 后） | 通过率 | 自动断言通过率 | 资金结论 verified/未验证/不可核对 | 路由命中（效率） |
|---|---|---|---|---|---|
| A_deterministic | 20/30 → 20/30 | 0.6667 → 0.6667 | 0.7267 → 0.7267 | 9/0/13 → 9/0/13 | 24/32 → 24/32 |
| B_single_agent | 21/30 → 21/30 | 0.7 → 0.7 | 0.7756 → 0.7756 | 11/0/11 → 11/0/11 | 0/32 → 0/32 |
| C_multi_agent | 23/30 → **24/30** | 0.7667 → **0.8** | 0.8489 → 0.8822 | 11/3/8 → 11/4/7 | 28/32 → 27/32 |

逐题变化（只有 C 基线有变化；A/B 完全不变）：

| 题号 | 变化 | 原因 | 是否改变通过 |
|---|---|---|---|
| H19 | route deterministic → fanout（工具 2→3） | 新增词"物业费"使该题同时命中 billing 与 lease；仍因证据缺失失败 | 否（路由只作效率指标） |
| H25 | route → clarification；工具 1→0 | 该题无任何领域词 → 回问、零工具 | 否（`scorable=false` 人工评定题） |
| H26 | 同上 | 同上 | 否（人工评定题） |
| H27 | failed → **passed**（0/1 → 1/1） | 该题 `expected_outcome=failed`（要求明确失败）；旧逻辑静默 billing 反而"答出内容"，新逻辑回问=明确失败 | **是（+1）** |

**没有出现"通过变失败"的题**；未为维持分数调整词表或用例。

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `ask` 的旧 `--provider fake` 与统一参数冲突 | 需要兼容旧脚本，又不能静默忽略歧义 | 保留为弃用别名（stderr 提示，fake→scripted），与 `--model-provider` 冲突时 exit 2 |
| `ask` 无目标但问题含业务词 | 直接放行会退回 Z1 的老问题（静默 explain） | 有业务领域词且无目标 → `TargetResolutionError`（exit 2，提示 `--lease/--unit`）；纯说明问题无业务词仍可 explain |
| `--unit` 既可能是商铺 ID 也可能是编号 | 只按 ID 查会把 `A-301` 当不存在 | 先按 ID 查、再按编号走仓库范围校验；两者与 `--lease` 交叉校验一致性 |
| `approve --dry-run` 旧实现会写台账 | 直接调用 `store.decide()`，规则正确但副作用错误 | 改为在**台账副本**上执行真实 `decide()`：校验规则只有一份实现，原台账/checkpoint 逐字节不变；副本用主库 + WAL/SHM 复制保证看到未 checkpoint 的提交 |
| `--thread-id` 是无效参数 | 定义后从未使用；允许覆盖反而可能恢复到错误线索 | 删除（另一选择"真正接通"会增加"恢复到非请求线索"的风险，且无调用方需要）；在帮助文本说明恢复以台账为准 |
| 退出码不区分失败层级 | 全部映射到 2 | 0/1/2/3 分开并写入 `--help` 与 README；调查"有结果但冲突/不完整"仍算成功（有效结论），零子任务/clarification 算业务失败 |
| 领域 YAML 模型配置不生效 | 工厂固定读 single.yaml，装配共享注入 | 逐 Agent 按 YAML 构造 + 缓存；`bundle.agent_models`/评测 `models_by_agent` 如实报告；非法配置启动期失败 |
| `deepseek-chat` 已下线（2026-07-24） | 配置沿用旧模型名。（返修 R2 更正：官方公告已下线；本项目 11-06 实测以该名字仍可调用，实际应答模型当时未记录） | 以官方文档核对后只改 YAML 为 `deepseek-flash`，记录依据 URL 与日期；未调用接口验证；返修 R2 起记录服务端实际应答模型 |
| 配置声明 chroma/bge 但只有 BM25 | Schema 定义了未实现字段，YAML 照写 | 从 Schema 移除未实现字段（`extra="forbid"` 即报错），YAML 只保留真实能力 |
| 未命中领域静默走 billing | Planner 硬编码兜底 | 词表唯一来源 + `needs_clarification` 分支；路由理由写报告；评测如实报告 H19/H25/H26/H27 变化 |
| 并行成员对 `cli.py` 的集成需求 | 多人同时改一个文件易冲突 | `cli.py` 只由负责人修改；成员在完成消息给出稳定契约（`build_investigation_bundle(model_provider=...)`、`evaluate(model_provider=...)`、`bundle.agent_models`），负责人统一接线 |
| 成员遗留临时探针脚本 | 改动前取证脚本放在仓库内 | 负责人核实归属后要求成员删除；归档前 `git status` 确认无 `backend/_*.py` 临时文件、无残留 worktree |
| PowerShell 重定向证据文件为 UTF-16 | Windows `>` 默认编码 | 统一用 Python 采集/转码为 UTF-8，脚本 `normalize_utf8.py` 留在证据目录可复现 |

## 8. 对应 Git Commit Hash

- **Commit**：`Pending`。HEAD 仍为 `e3b3594`；本轮改动全部未提交、未推送、未打 Tag。
- **回填（2026-11-21）**：Task 031 原实施与 R1–R4 返修已由用户提交为 `3be785e`（“任务重构”），并已在 `origin/main`；该提交同时包含用户侧 `tools/flowise/` 与 `.gitignore` 的 Flowise 三行。
- **待提交前检查**：`git status` 只含本轮预期文件；确认无 `.env`、密钥、临时脚本；`docs/evaluation/cases/`、评分规则、历史报告未被修改（用例/ fixture 校验和一致）。
- **建议 Commit Message**：`fix(core): close Z1-Z3, per-agent model config and CLI/route fallbacks (Task 031)`。

## 9. 后续待办事项

- [ ] 由**独立复查**判定 Task 031 验收（本文件是实施自检，不是最终验收）。
- [ ] 复查重点：① Z1 目标解析/注入与"有业务词无目标即失败"的边界是否符合预期；② Z2 的"合法零结果 vs 失败调用"判定与 LLM 路径证据过滤；③ 2.5 逐 Agent 客户端缓存的键是否覆盖全部行为参数、评测 `models_by_agent` 是否与实际调用一致。
- [ ] 复查次要项：`approve --dry-run` 副本预演方案是否接受（原台账零写入、规则单一实现）；H19/H25/H26/H27 的路由变化是否符合"不为分数调词"的要求。
- [x] **`ask` 的保守边界**（用户 2026-11-21 决定**保持现状**，见 10.7）：只要问题命中业务领域词却没有可信目标，就按用法错误（exit 2）拒绝，例如"免租期一般怎么约定？"会要求先给 `--lease/--unit`。这是为避免 Z1"业务问题静默变 explain"而做的保守选择；若复查认为过严，可增加显式 `--explain` 或"纯政策问题"判定，但需要新的词表/语义依据与回归。
- [ ] 历史文档与历史真实评测报告中的 `deepseek-chat` 保留原文；如需在展示材料中强调已下线，另加说明，不回写历史报告。
- [ ] `retrieval_settings.top_k` 目前是"声明值"（检索工具由 payload 的 `top_k` 决定）；如复查要求只保留被消费字段，可再收紧。
- [ ] `allowed_tools` 中 `lease.term_extract`、`compliance.checklist.read` 仍为历史未实现工具（Task 007 决策保留），由 `check` 显式暴露。
- [ ] API 对 `needs_clarification` 的 run 状态语义（当前仍记 `completed`）属 Task 032 展示层范围，本轮未改。
- [ ] Task 032（业务流程工作台前端）与 Task 033（MCP 工具网关）按 Prompt 要求**分开执行**，本任务完成前未启动。
- [ ] 正式真实模型 heldout/重复测量、PostgreSQL 实机、人工量表仍为长期未完成项；本轮未调用付费模型。

## 10. 返修（R1–R4）

- 执行者：Claude Code（2026-11-21），依据 [Task 031 复查](../../reviews/2026-11-21_task031_acceptance_review.md) 与交接文件 `docs/handoffs/CLAUDE_CODE_HANDOFF_2026-11-21.md`。R5 按交接要求**未改**；用户 2026-11-21 决定**保持现状**。
- 环境：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18），在 `backend/` 下运行，`PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`。
- 返修前基线（复跑，与第 6.1 节一致）：529 tests OK（skipped=1）、70 项契约。证据见 `docs/reviews/task031_evidence/repair/before_*.txt`。
- 本节是实施自检，**不是最终验收**；需要另一模型（DeepSeek 或 Codex）独立复查。

### 10.1 R3 换行符

| 做了什么 | 证据 |
|---|---|
| 新增 `.gitattributes`：`* text=auto eol=lf`；`*.bat`/`*.cmd` 为 CRLF；pdf/png/jpg/sqlite/db/zip/xlsx/docx/pptx/woff 等声明为 `binary` | 文件本身 |
| 把本轮改动和新增的文本文件（含评测报告 JSON/MD、证据文件、本归档）统一转为 LF：`\r+\n → \n`（证据文件里有 `\r\r\n`），没有碰二进制文件和 `tools/flowise/` | `git ls-files --eol -m -o --exclude-standard` 中除 `tools/` 外的文件全部为 `w/lf`（另有 3 个空文件为 `w/none`） |
| `.gitignore` 保留 HEAD 原有的“末尾无换行” | `git diff --ignore-cr-at-eol .gitignore` 只有 Flowise 三行 |
| 根因修复：`runner.write_report` 和 `cli` 写 summary 都加了 `newline="\n"` | `test_task031_r3_r4.TestR3ReportsAreWrittenWithLF`；返修后新生成的 `20261121T093757_*` 报告全部是 LF |
| 验收 | `git diff --stat` 与 `git diff --stat --ignore-cr-at-eol` 完全一致（`diff` 无输出）；`core.autocrlf=false` 下统计也一致 |

说明：本机 `core.autocrlf=true`（系统级配置），所以返修前 `git diff --stat` 已经被 Git 自动归一化，看不出 15k 行的噪音；复查里的“原始 diff”是按字节比较得到的。`.gitattributes` 生效后，不依赖各机器的 autocrlf 设置。其余**未改动**的已跟踪文件在工作区仍可能是 autocrlf 检出的 CRLF，但 Git 判定内容不变，不影响 diff；重新检出后会变成 LF。

### 10.2 R1 部分取证不能判成功

口径（全部复用既有定义）：
- 问题涉及哪些领域：`orchestration.vocabulary.matched_domains`；
- 工具属于哪个领域：先看工具名命名空间（`lease.*` / `billing.*` / `property.*`），命名空间不是领域时（`document.search`），再看工具声明的 `required_permissions`（`lease.read` → lease），只有恰好对应一个领域才归属；
- 某个领域取得了事实：这个领域有 accepted 工具产出了非空事实（`facts_of_executions` 的 per_tool；合法零结果同样算）。

判定（`evidence.domain_coverage` / `missing_domain_outcome`，只在**存在失败调用**时生效）：

| 情形 | 结果 |
|---|---|
| 问题涉及的领域都有事实 | 不变（SUCCESS） |
| 部分领域有事实、部分没有 | **PARTIAL**，warnings 写明缺哪个领域（“部分取证：问题涉及的领域 billing（账单/费用）没有取得任何事实……”） |
| 问题涉及的领域都没有事实，只有无关领域的事实 | **FAILED / insufficient_evidence** |

最后一行为什么不是 PARTIAL：PARTIAL 的意思是“回答了问题的一部分”。用户只问了欠款，账单调用失败，模型顺手查了合同。合同事实回答不了问题的任何部分，本质和“零事实”一样，只是被无关事实盖住了；判 PARTIAL 会让调用方把租期当成“还欠多少”的部分答案展示出来。没有失败调用时 R1 不介入（例如多查了一个无关工具），行为和 Task 031 一致。

- Single 路径（`agents/single/agent.py`）已接入；输出和失败详情都增加了 `domain_coverage`（asked/covered/missing），`ask` 默认摘要也会展示。
- **LLM 领域 Agent 路径不改**，理由：领域 Agent 只负责一个 capability，已经有 `check_capability_output` 契约。问题“租期和欠款”会被 Planner 拆成 lease/billing 两个子任务，billing 子任务失败时由 Coordinator 汇总为 PARTIAL（`coordinator.py` 的状态表）。如果在 lease 子任务里按问题领域判缺失，lease 子任务会因为 billing 的问题被错误降级。用例 `test_llm_domain_agent_judges_only_its_capability` 固定了这一点。
- PARTIAL 的含义在各处一致：CLI `ask` 的 PARTIAL 退出码为 0（与第 6.5 节“有结果但不完整算成功”一致），`status` 字段显示 `partial`，warnings 写明原因；评测中 B 基线 PARTIAL 照常按事实评分，并把 warnings 记入 `errors`；API 只暴露多 Agent 调查（单 Agent 不经 API），界面已把 `partial` 显示为“部分完成”。
- 测试（`test_task031_z2_evidence.py`）：原用例收紧为**只接受 PARTIAL**，并断言 `domain_coverage` 与告警内容；新增“两个领域都成功 → SUCCESS”“先失败后纠正 → SUCCESS”“只问一个领域且它失败、无关工具成功 → FAILED”“没有失败调用时不介入”、LLM 路径对照，以及 3 个领域归属单元用例。
- 评测影响：离线 B 基线走确定性取数（`model_calls=0`），不经过 `SingleToolAgent`，所以 R1 不改变离线评测结果（见 10.6）。真实模型 B 基线会受影响，本轮没有运行。

### 10.3 R2 报告区分配置模型名与实际应答模型

- `ModelTurn.served_model`：`langchain_client._to_model_turn` 从 `response_metadata["model_name"]`（没有时读 `model`）读取服务端声明的模型；没有或为空时是 `None`。已核对本机 langchain-openai 1.7.4：响应体的 `model` 写入 `response_metadata["model_name"]`。
- Agent 输出 `model` 增加 `served_models`（按出现顺序去重）和 `served_model_mismatch`（不一致为 `True`，一致为 `False`，**没有记录为 `None`，不当成一致**）；Single 和 LLM 领域 Agent 两条路径都有。
- 评测：B/C 基线逐题把 `served_models` 并入 `models_by_agent`，runner 在全部题目上合并；`model_name` 仍是配置名；Markdown 表新增“实际应答模型”列（`未记录` / 名称 / `⚠ …（与配置名不一致）`）；`bindings.model.note` 注明 `model_name` 是配置名。`ask` 默认摘要增加 `served_models` / `served_model_mismatch`。
- 测试（`test_task031_r2_served_model.py`，9 项，全部用伪造响应，**没有调用付费接口**）：真实 `AIMessage` 带 `response_metadata` → 正确读取；缺失 → `None`；Agent 输出配置名 `deepseek-chat`、实际 `deepseek-v4-flash` → mismatch；评测跨题合并、未记录 → `None`/“未记录”。`test_task031_model_config` 两处断言更新为“配置条目 + 两个 served 字段”，并断言替身客户端为 `[]`/`None`（是字段形状的预期变化，没有放松）。
- 文档：第 6.6 节、第 7 节表格中“真实调用会失败”已更正；`CURRENT_BASELINE.md` 真实模型一行注明“历史报告中的模型名为配置名”。**历史报告文件没有改。**
- 遗留限制：如果服务端响应不带 `model` 字段，langchain-openai 会用配置名回填 `model_name`，这时 `served_models` 等于配置名，无法区分“服务端确认一致”和“服务端没返回”。要完全区分，需要读原始响应体（例如 `include_response_headers` / 原始 JSON），本轮没做。

### 10.4 R4 dry-run 副本改用 SQLite 备份接口

- `ApprovalStore._copy_for_preview` 改为 `sqlite3.connect(源).backup(sqlite3.connect(副本))`，两个连接都在 `finally` 里关闭；不再复制 `-wal`/`-shm`；台账不存在时仍报错且不创建台账。
- 源连接为什么不用 `mode=ro`：实测 WAL 库在没有 `-wal`/`-shm` 时，只读连接会**创建**这两个文件，关闭时又删不掉，原台账目录会多出文件（现有 CLI 用例“目录逐字节不变”会失败）。改为普通连接 + `PRAGMA query_only=ON`：拒绝写语句；作为最后一个连接关闭时，SQLite 会删除自己创建的空 `-wal`/`-shm`，主库字节不变。
- 已知边界：如果进程崩溃留下了含未 checkpoint 帧的 `-wal`，而且此刻没有其他连接，关闭时 SQLite 会把这些已提交帧 checkpoint 进主库（内容等价，字节会变）。`ApprovalStore` 每次操作都关闭连接，正常运行不会出现。
- 并发写入（复查 C3 补充）：`backup()` 使用默认 `pages=-1`，在一个读事务里一次拷完全部页面。WAL 模式下读不阻塞写，另一进程此时提交的内容不会进入本次快照（快照是备份开始时的一致状态），备份也不会因此重启；如果另一进程持有排他锁（例如正在做 checkpoint 截断），源连接最多等待 `timeout=10s`，之后抛 `database is locked`，dry-run 失败且原台账不变。没有专门的并发用例。
- 测试（`test_task031_r3_r4.py`）：预演后主库 / `-wal` / `-shm` 的 SHA-256 不变，预演结果与随后真实 `decide()` 逐字段一致（时间戳除外）；另一个连接一直开着、第一阶段决定仍留在 WAL 时，第二阶段（财务）预演能看到它并通过；阶段顺序规则仍然生效；台账不存在时报错且不创建文件。原有 `test_task031_cli` 的 dry-run 用例（目录逐字节不变、真实审批随后可写）全部通过。

### 10.5 回归与命令

| 项 | 结果 |
|---|---|
| 全量回归 | **551 tests OK（skipped=1）**；返修前 529，新增 22 个：z2 增加 8 个（R1）、`test_task031_r2_served_model` 9 个（R2）、`test_task031_r3_r4` 5 个（R3 1 个 + R4 4 个） |
| 契约自检 | 70 项全部通过 |
| `python -m app.cli check` | exit 0 |
| `python -m app.cli ask "A-301 现在还有多少钱没交？"` | exit 0，`status=success`，可信结论“应收 52596.00、已收 34560.00、未收 18036.00（CNY）”，`domain_coverage` 为 billing 已覆盖，`served_models=[]`（脚本模型） |
| `python -m app.cli investigate --model-provider scripted` | exit 0，`route=fanout`，`verdict=conflicting`（与 Task 031 一致） |

证据：`docs/reviews/task031_evidence/repair/`（after_unittest / after_smoke / check / ask_scripted / investigate_scripted / eval / evaluation_compare）。

### 10.6 离线 heldout 重跑对比

`python -m app.cli evaluate --split heldout` 生成 `docs/evaluation/reports/20261121T093757_*`，与 Task 031 改动后的 `20261121T085431_*` 逐题对比（忽略延迟、时间戳和新增的 served 字段）：**A/B/C 三条基线 32 题的结果行全部一致**；汇总里只有 `cost.latency_*` 不同。通过数仍是 A 20/30、B 21/30、C 24/30。对比输出见 `repair/evaluation_compare.txt`。

### 10.7 遗留

- R2：服务端不返回 `model` 时无法区分（见 10.3）；历史真实报告的实际应答模型已无法追溯。
- R4：崩溃遗留 WAL 的边界（见 10.4）。
- R1：真实模型 B 基线没有重跑，结果可能变化（多领域题在工具失败时会由 success 变为 partial 或 failed）。
- R1 残余（复查 P3-2 / C2）：**没有失败调用**、模型只查了一部分已问领域时，结果仍为 success（`domain_coverage.missing` 非空但无告警）。这是本次 R1 的范围外残余，不能视为 R1 已完全覆盖；由 Task 034 §2.6 处理。
- R5：用户 2026-11-21 决定**保持现状**：有业务领域词但没有可信目标的问题（如“免租期一般怎么约定？”）继续按用法错误（exit 2）拒绝，不增加 `--explain` 或政策类判定。第 9 节对应待办关闭。
- 记录时改动未提交；之后由用户提交为 `3be785e`（见第 8 节回填）。`.gitignore` 的 Flowise 三行与 `tools/flowise/` 属于用户原有改动，原样保留。
