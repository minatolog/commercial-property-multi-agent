# commercial-property-multi-agent

商业地产租约与物业运营场景下的 **Agent-First 多 Agent 工作流**项目：
Runtime → 受控只读工具 → LangGraph 编排 → 合同条款证据 → 人工审批 → 评测 → 演示界面。

> **状态**：可运行、可演示、可解释的版本候选（release candidate）。
> 所有业务数据均为**合成数据**。PostgreSQL 已有实机证据。正式模型对照的原始运行已归档，评分审计和人工量表仍待完成。
> 当前指导入口：[架构与文档基线](docs/architecture/CURRENT_BASELINE.md)、[LangChain 架构及接手指南](docs/architecture/langchain_integration.md)。
> 未完成项在 [§8 已知限制](#8-已知限制不夸大) 中逐条列出，本文不夸大任何能力。

---

## 1. 这个项目在做什么

商业地产运营里，"租户投诉租金算错、要求减免"这类问题需要同时看**合同条款**、**账单与付款**、
**维修工单**，再走**两级审批**。LLM 单轮问答做不了这件事，因为它需要：

| 需求 | 本项目的做法 |
|---|---|
| 金额不能靠模型猜 | 全部由确定性工具用 `Decimal` 计算，模型只做陈述 |
| 结论要能回溯到原文 | 合同 PDF → 逐页条款分块 → 证据带**真实页码与条款号** |
| 不能越权看别家数据 | 权限/项目范围来自可信上下文，工具层强制过滤 |
| 该人工决定的不能自动化 | 审批是独立节点，批准只产出"已批准草案"，不写业务数据 |
| 说了要能验证 | 三基线评测 + 冻结评分规则 + 可复查报告 |

---

## 2. 快速开始

```bash
# 1) 环境（已建好，见 docs/prompts/01_environment/）
conda activate commercial-agent

# 2) 安装依赖（仅首次）
cd backend && python -m pip install -e .

# 3) 自检：工具清单 + Agent 配置一致性 + 契约自检
python -m app.cli tools
python -m app.cli check
python tests/smoke_agent_contracts.py

# 4) 跑一遍完整回归
python -m unittest discover -s tests -p "test_*.py"
```

需要演示界面时：

```bash
python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000
# 运营总览（含 3D 商场）：http://127.0.0.1:8000/
# 争议案件处理台：http://127.0.0.1:8000/workbench
```

运营总览使用示例指标和浏览器侧协同演示。可从 A-301、A-302 商铺打开调查草稿，提交后由项目现有调查 API 处理。

环境变量（全部可选，脚本与演示都能离线运行）：

| 变量 | 作用 | 缺省 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek 模式所需的服务端密钥 | 离线和 scripted 模式可直接使用 |
| `COMMERCIAL_WEB_MODEL_PROVIDER` | 设为 `deepseek` 并重启服务后，工作台新调查会调用模型 | `offline` |
| `DEMO_PRINCIPAL_ID` | 演示 API 的可信主体 | `principal_ops_xinghui` |
| `DEMO_APPROVERS` | 演示 API 允许的审批人（逗号分隔） | 物业经理 + 财务 |
| `CONTRACT_PDF_OUT` / `DOC_OUT_DIR` | 合成 PDF 输出目录 | `docs/evaluation/documents/` |

**在哪里填 Key（两种方式，任选其一）**

1. **推荐：写进 `.env`（一次配置，CLI 与 API 都自动读取）**

```powershell
cd D:\commercial-property-multi-agent
Copy-Item .env.example .env      # 首次：生成 .env（已被 .gitignore 忽略）
notepad .env                     # 找到这一行，把值填在等号后面：
# DEEPSEEK_API_KEY=sk-你的真实密钥
```

2. **当前终端临时导出**（关掉终端即失效，适合单次验证）

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的真实密钥"
```

填好之后这样验证（不会打印密钥本身）：

```powershell
cd backend
python -m app.cli investigate --model-provider deepseek
```

未配置或填错时**会明确报错**（`MissingApiKeyError` / 鉴权失败），不会静默退回离线结果。
`DEEPSEEK_API_KEY` 只从环境变量或 `.env` 读取，YAML / 代码 / 文档里都没有它的位置。

模板见 [.env.example](.env.example)（**只有键名，无任何真实密钥**）。
优先级：**已导出的环境变量优先**，`.env` 只补空缺。

---

## 3. 架构

```mermaid
flowchart TB
    subgraph 入口层
        CLI[CLI app.cli]
        API[FastAPI app.api<br/>身份由服务端注入]
    end

    subgraph 编排层
        G[LangGraph 调查图<br/>plan → dispatch → verify → report → approval]
        P[RuleBasedPlanner]
        V[确定性核验<br/>conflict / missing / completeness]
    end

    subgraph Agent层
        L[Lease Agent]
        B[Billing Agent]
        PR[Property Agent]
    end

    subgraph 工具层
        EX[受控 ToolExecutor<br/>白名单·权限·参数·结果·超时·重试·预算·Trace]
        T1[lease.lookup]
        T2[billing.statement.read]
        T3[property.work_orders.read]
        T4[document.search]
        T5[billing.arrears.calculate]
    end

    subgraph 数据与知识
        F[(fixture 只读仓库<br/>合成数据)]
        DB[(只读 SQLAlchemy 层<br/>SQLite 已验 / PG 未验)]
        RAG[合同 PDF 索引<br/>分块 + BM25 + 引用验证]
    end

    subgraph 控制面
        CP[(checkpoint<br/>data/checkpoints)]
        AL[(审批台账<br/>data/control)]
    end

    CLI --> G
    API --> G
    G --> P
    G --> L & B & PR
    L & B & PR --> EX
    EX --> T1 & T2 & T3 & T4 & T5
    T1 & T2 & T3 & T5 --> F
    T1 & T2 & T3 & T5 -.可选数据源.-> DB
    T4 --> RAG
    G <--> CP
    G <--> AL
    G --> V
```

**分层纪律**（有测试守着）：

- Coordinator **不 import 任何具体 Agent**，按 `capability` 从 Registry 解析；
- Agent **不 import 具体工具实现**，只认工具契约；
- 展示层只经 `WorkflowService`，`app.cli` / `app.evaluation` **不 import** `app.api`；
- 工具执行必须经过统一执行器的权限、参数、结果、预算和 Trace 等控制，评测基线也不能绕过。当前业务工具使用只读仓库，完整独立 Business Service 层仍有差距，见现行系统架构。

详细设计见：
[agent_architecture](docs/architecture/agent_architecture.md) ·
[database_design](docs/architecture/database_design.md) ·
[agent_runtime_contracts](docs/architecture/agent_runtime_contracts.md)。

---

## 4. 端到端演示（A-301 三个场景）

完整脚本（含期望输出与讲解词）见 [docs/demo/demo_script.md](docs/demo/demo_script.md)。

### 场景 A：确定性路径（不该惊动多 Agent）

```bash
python -m app.cli investigate "A-301 现在还有多少钱没交？" --lease lease_xh_a301_2025
```
→ `route=deterministic`，只走 billing，金额 `应收 52596.00 / 已收 34560.00 / 未收 18036.00`。

### 场景 A2：单 Agent 问答（必须带可信目标）

```bash
python -m app.cli ask "A-301 现在还有多少钱没交？"            # 目标从问题里的商铺编号解析
python -m app.cli ask "现在还欠多少钱？" --lease lease_xh_a301_2025
```
→ 目标由装配层注入 `TaskScope`，模型不能换目标/省略；默认摘要分栏展示**可信资金结论**与**模型原话**，
不一致时给差异提示。有业务词但没有可信目标时是**用法错误（exit 2）**，不会被当成纯说明问题。
退出码：`0` 成功、`1` 业务结果失败（如零事实）、`2` 用法/配置错误、`3` 审批错误。

### 场景 B：跨系统冲突（必须扇出并且不擅自选边）

```bash
python -m app.cli investigate --lease lease_xh_a301_2025
```
→ `route=fanout`，三个子 Agent 并发，`verdict=conflicting`，冲突 `rent_variance=756.00`，
并列出缺失资料（附件B 未电子化）。

### 场景 C：需要人工审批（暂停 → 两人串行批准 → 只产出草案）

```bash
python -m app.cli investigate --with-approval --thread-id demo_thread_01
python -m app.cli pending
python -m app.cli approve <request_id> --principal principal_property_manager_xinghui --draft-version 2
python -m app.cli approve <request_id> --principal principal_finance_xinghui --draft-version 2
```
→ 第一次批准后仍是 `pending_next_stage`；第二次后 `approved`，返回
`approved_draft.status=approved_draft_only`、`executed_side_effects=[]`（**没有真实调账**）。

> 每条 `thread_id` 只能承载**一次**运行：重复用同一个 `--thread-id` 做新调查会被明确拒绝
> （`invalid_context`），因为持久化状态里的旧结果不能混进新结论。再演示一次请换
> `demo_thread_02`，或使用新的 `--control-dir`。

### 场景 D：证据可回溯

```bash
python -m app.cli search "租金递增比例" --verify-claim "自第二个租赁年度起租金递增百分之五"
```
→ 命中真实 PDF 第 12 页 5.2 条；`citation_check` 给出 L1（引用存在）与 L2（是否支持结论）。

---

## 5. 评测（三基线）

数据：8 道开发题（`cases/smoke_v1.jsonl`，为人工量表写的自然语言题）+ 32 道保留题
（`cases/heldout_v3.jsonl`，冻结后只跑不改；其中 H25/H26 显式声明为人工评定，30 题参与自动计分）。
评分规则先冻结：[scoring_v3.md](docs/evaluation/scoring_v3.md)（v1/v2 规则与历史报告保留在
[scoring_v1.md](docs/evaluation/scoring_v1.md)、[scoring_v2.md](docs/evaluation/scoring_v2.md)
与 reports 目录，**不同版本不可做通过率对比**）。

```bash
python -m app.cli evaluate --split heldout
```

保留集 v3（离线，`scoring-v3.3`，报告见 [docs/evaluation/reports/](docs/evaluation/reports/)；Task 031 后新版本）：

| 基线 | 架构 | 计分题通过 | 自动断言通过率 | 工具事实断言 | 资金结论断言 | 未验证题 | 工具调用 | token | 成本 |
|---|---|---|---|---|---|---|---|---|---|
| `A_deterministic` | 意图表 → 单次工具 | 20/30 | 0.7267 | 28/33 | 9/9 | 0 | 27 | 0 | n/a（离线） |
| `B_single_agent` | 单 Agent 汇总全部工具 | 21/30 | 0.7756 | 29/33 | 11/11 | 0 | 38 | 0 | n/a（离线） |
| `C_multi_agent` | LangGraph 分解 + 核验 | 24/30 | 0.8822 | 30/33 | 11/11 | 4 | 45 | 0 | n/a（离线） |

Task 031 对 C 相对 Task 025 时期（23/30）只有 H27 由失败变为通过：该题 `expected_outcome=failed`（要求明确失败），
旧逻辑静默落 billing 反而"答出内容"，路由兜底修复后回问＝明确失败。H19 路由由 deterministic 变 fanout、
H25/H26 变为 clarification，均只影响效率指标或人工评定题；**没有"通过变失败"的题**。用例、fixture 与评分校验和未变。

**怎么读这张表**：

- 通过率只统计**可机械复核**的断言；人工量表（rubric）与 `scorable=false` 的题另列，
  不参与自动分。断言必须是**同名字段**比较（金额用 `Decimal` 比到分），不允许"数字在文本里出现过"即通过；
- **"工具事实 / 资金结论 / 金额接地"三者分开统计**（`scoring-v3.3`）：分别回答"取数对不对"、
  "用户读到的应收/已收/未收对不对"、"金额是否都有工具来源"。三个金额互换或"未收 0 元已结清"
  都会判失败；叙述没有把金额绑定到字段则记为**未验证**（单独计数，不算通过）；
  辅助检查不能替主判据背书；
- 基线事实契约之外、无法自动判定的断言进人工队列，**不进分母**——所以"0/0"表示"没有可判定的题"，
  与"0/7（全错）"不是一回事；
- 路由命中只作**效率**指标（`B` 为 0/32 是架构使然，不是错误）；
- `C` 的领先主要来自"跨领域扇出 + 权限/审批边界"这类 A/B 结构上做不到的题；
  **单领域单工具的题上，A 一样对，且更省**；
- 开发集（8 题）三基线都是 0/7：那批题是自然语言断言、面向人工量表，离线基线不解析自然语言，
  因此**不能**用它的通过率评价实现质量；
- `token=0`、`cost=null` 是因为**没有调用真实模型**；不得把这些数字当作真实成本或质量。

旧 heldout 已在开发过程中多次运行、查看；这些结果应标注为回归/探索证据，不能宣称从未曝光的独立盲测。需要独立泛化结论时，应另冻结未用于开发的测试集。

---

## 6. 文档地图

| 位置 | 内容 |
|---|---|
| [docs/architecture/CURRENT_BASELINE.md](docs/architecture/CURRENT_BASELINE.md) | 当前指导关系、架构范围、实现差距与验证状态 |
| [docs/README.md](docs/README.md) | 文档规范、Prompt 全局编号表（001–031） |
| [docs/architecture/](docs/architecture/) | Agent 架构、接口契约、Runtime 契约、数据库设计 |
| [docs/prompts/](docs/prompts/) | 每个任务的完整存档（原始 Prompt + 实施 + 验证 + 问题） |
| [docs/development_logs/development_log.md](docs/development_logs/development_log.md) | 逐任务开发日志 |
| [docs/issues/issue_log.md](docs/issues/issue_log.md) | 问题、根因、修法、如何避免复发 |
| [docs/lessons_learned/knowledge_notes.md](docs/lessons_learned/knowledge_notes.md) | 按任务记录的技术原理与取舍 |
| [docs/checkpoints/git_history.md](docs/checkpoints/git_history.md) | 里程碑与回滚参考 |
| [docs/evaluation/](docs/evaluation/) | 评测规则、数据集、报告 |
| [docs/demo/demo_script.md](docs/demo/demo_script.md) | 演示脚本与失败示例 |
| [backend/README.md](backend/README.md) | 工程细节、模块职责、命令清单 |

---

## 7. 质量证据

下表包含既有任务证据；Task 031 在完成 Z1–Z3、CLI、逐 Agent 模型配置、配置真实性与路由兜底后，统一重跑 **529 项回归**（skipped=1）与 **70 项契约**；随后返修 R1–R4（Claude Code）后为 **551 项回归**（skipped=1）与 70 项契约，并通过 `check`、无效配置反例与脚本化 ask/investigate。Task 031 与返修已提交为 `3be785e`（“任务重构”，已在 `origin/main`），[DeepSeek 独立复查](docs/reviews/2026-11-21_task031_repair_independent_review.md)结论为有条件通过。没有新增真实模型请求。

| 证据 | 命令 | 结果 |
|---|---|---|
| 契约自检 | `python tests/smoke_agent_contracts.py` | 70 项通过 |
| 单元/集成回归 | `python -m unittest discover -s tests -p "test_*.py"` | Task 038 共 723 项，678 项通过，45 项跳过（含 44 项 PostgreSQL 测试） |
| 冻结评测 | `python -m app.cli evaluate --split heldout` | 3 份 JSON + 汇总 Markdown（绑定提交与校验和） |
| 模型预算按物理请求记账 | `tests/test_model_budget.py`（6 项） | `max_model_calls=1` 时只发出 1 次请求；重试/补查逐次记账 |
| 模型不能换目标/丢筛选 | `tests/test_task_scope.py`（15 项） | 越界租约被拒、省略即注入、文档范围取交集、受控调用双省略默认拒绝 |
| 领域能力的最低结果契约 | `tests/test_evidence_and_answer.py`（23 项） | 领域 Agent/verify 回归；Single 与 LLM 路径均改为"成功且属于目标"才算取证（Z2） |
| 答案金额必须来自事实 | `tests/test_evidence_and_answer.py`（N6 部分） | facts 全对但回答写 0.00 → 答案断言失败；报告列出 `narrative_discrepancies` |
| token 耗尽后不再发请求 | `tests/test_token_budget_gate.py`（11 项） | 零额度 0 次请求；首次超额后物理调用保持 1 次；并发/重试/补查一致 |
| 单 Agent 显式目标范围 | `tests/test_single_agent_scope.py`（15 项） | B 基线传入目标后取错租约被拒、省略即注入；默认 `ask` 目标装配由 Task 031 补齐（`--lease`/`--unit` 与问题编号解析） |
| Z1 可信目标（含原始反例） | `tests/test_task031_z1_ask_target.py`（11 项） | 原始反例由 exit 0/success 变为 exit 1/failed；换目标拒绝、省略注入、无目标业务问题为用法错误 |
| Z2 失败调用不计取证 | `tests/test_task031_z2_evidence.py`（17 项） | schema 错/超时/预算耗尽/范围拒绝 → 失败且零证据；合法零结果保留；纠正后成功 |
| Z3 默认输出可信资金结论 | `tests/test_task031_z3_default_output.py`（5 项） | ask/investigate 默认摘要分栏、verified/mismatch/unverified 与差异提示 |
| CLI 契约 | `tests/test_task031_cli.py`（26 项） | `--model-provider` 统一、dry-run 前后台账逐字节不变、删除无效参数、退出码 0/1/2/3、身份来源可见 |
| 逐 Agent 模型配置 | `tests/test_task031_model_config.py`（37 项） | 改单个领域 YAML 只影响该 Agent；同参数共享缓存；非法配置启动期失败；`models_by_agent` 报告 |
| 配置真实性与路由兜底 | `tests/test_task031_planner_fallback.py`（18 项） | 未命中领域 → clarification 且零工具；路由理由写入报告；配置声明未实现检索字段即报错 |
| 资金结论按字段核对 | `tests/test_fund_conclusions.py`（28 项） | 金额写反、错结清判失败；只答未收/合法明细通过；未验证不计通过 |
| 真实模型记账与资金核验 | `docs/evaluation/reports/real_model_v2/`（Task 024，30k token 上限、单题） | 物理请求 7 = 账本 7；13,452 tokens；scoring-v3.3 下资金结论 `verified`；旧 13,714-token 核验记录保留 |
| SQLite + RAG 真实装配 | `python -m app.cli investigate --backend sqlite` | 退出码 0（含合同条款检索） |
| 审批意见落库 | `python -m app.cli approve <id> --draft-version N --reason "..."` → `pending` | 台账 `stages[].reason` 为提交的意见 |
| Agent 可禁用/替换 | `tests/test_graph_workflow.py::test_disabled_capability_degrades_explicitly`、`tests/test_runtime.py::test_replace_success_swaps_capabilities_atomically` | 禁用后明确报能力不可用；替换原子生效 |
| 审批只出草案 | `tests/test_approval.py`（31 项） | `approved_draft_only` + `executed_side_effects=[]`；终态重复提交受幂等保护 |
| 证据页码真实 | `tests/test_rag.py`（42 项） | fixture 声明页码 == 真实 PDF 页码；条款检索限定本租约文档 |
| 评分字段绑定 | `tests/test_evaluation.py::TestFactFieldBinding`（6 项） | 金额互换、错字段、差一分均判失败 |
| 主体隔离 | `tests/test_api.py::TestRunOwnership` | 跨项目读取按"不存在"处理（404） |
| 运行身份一致 | `tests/test_api.py::TestRunIdentity`（4 项） | 公开 `run_id` == checkpoint context == 审批 == 每条 trace |
| 持久线索不被复用 | `tests/test_approval.py::TestThreadIdentityBoundary`（5 项） | 跨主体/换租约/重复调查均被拒绝，越权主体拿不到他人旧结果 |
| 运行范围归属 | `tests/test_api.py::TestLegacyRunScope`、`TestReportScopeIsNotCreatorGrant` | 空范围默认拒绝；数据范围 ≠ 创建者授权范围 |
| 文档签署状态 | `tests/test_rag.py::TestDocumentStatusPolicy`（6 项） | 默认不返回未签署草案；草案显式单列 |
| 证据精确绑定 | `tests/test_rag.py::TestFindingEvidenceBinding`（3 项） | 同条号不同版本/5.1 与 5.1.1 各绑各的 chunk |
| 完成条件 | `tests/test_llm_tool_loop.py::TestInvalidModelResponses` | 调过工具但空回答 → `MODEL_ERROR` |
| 模型驱动装配 | `tests/test_llm_agents.py`（27 项） | 同一题在确定性/LLM 引擎下判定一致；事实取自工具；并发预算逐次记账 |
| 缺密钥不降级 | `python -m app.cli investigate --model-provider deepseek` | EXIT=2 + `MissingApiKeyError`（不静默退回离线） |
| `.env` 真实生效 | `tests/test_env.py`（15 项） | 填了就读取；环境变量优先；值不回显；`.env` 不入库 |
| 真实模型闭环（已实测） | `investigate --model-provider deepseek` | `conflicting` + 756.00；8 次模型调用 / 12 次工具 / 14,421 tokens（历史记录，当时模型名 `deepseek-chat`） |
| 真实模型评测（dev 8 题） | `evaluate --split dev --model-provider deepseek` | B 1/7、C 0/6；报告头部当时标注 `deepseek/deepseek-chat`（见 [real_model_dev](docs/evaluation/reports/real_model_dev/)）。该模型名已于 2026-07-24 下线，当前配置为 `deepseek-flash` |
| 报告不得谎报模型 | `tests/test_evaluation.py::test_report_names_the_real_model_when_one_is_used` | 接入模型后报告必须写真实 provider |
| 展示层可删除 | `tests/test_api.py::test_cli_and_evaluation_do_not_import_api` | 子进程断言通过 |
| 独立环境复现 | 全新 `venv`（隔离已确认）→ `pip install -e .` → 全量测试 | Task 016 当时为 238 项测试 + 57 项契约通过；Task 025 已有环境回归为 399 项；Task 031 返修后 551 项仍不能替代当前最终版本的新环境复现 |
| 演示页可用 | 本地 `uvicorn` + 浏览器实访 | 运行/线程 ID、结论、证据、冲突、审批阶段与 Trace 均正确渲染 |

---

## 8. 已知限制（不夸大）

1. **正式对照仍待评分审计**。迁移前的四组各五次 heldout 运行已归档。待核查资金字段评分、拒绝状态及跨主体用例，人工量表尚未完成。见 [正式原始结果](docs/evaluation/reports/formal_20261123/summary.md) 和 [Task 036 审查](docs/reviews/2026-11-24_current_architecture_review.md)。
2. **PostgreSQL 已有实机验证记录**。Task 035 覆盖迁移、只读角色、金额精度、项目隔离和约束。RLS、多实例并发与生产部署仍待验证，Task 038 未复跑 PostgreSQL 套件。见 [Task 035](docs/prompts/02_database/2026-11-23_035_postgresql_verification.md)。
3. **检索只有 BM25**：长问题召回不足（评测 H18–H20 已暴露）；向量/混合检索/rerank 属下一阶段，
   当前 `retrieval_settings` 只接受 `enabled`/`top_k`，声明未实现字段会加载失败；`top_k` 是声明值，
   检索工具的实际条数由调用参数决定。
4. **没有外部副作用实现**：调账/派单未实现，接入前必须先定义幂等键与补偿。
5. **演示鉴权是演示级**：服务端固定主体 + 审批人白名单，`X-Actor-Id` 不是认证；CLI 的 `--principal`
   是开发模式自报身份（显式传入会提示并记录 `identity_source=cli_flag`），不是生产身份来源。
6. **人工量表未评**：rubric 仍是待评队列，自动分不含表述质量；H25/H26 已显式声明为人工评定。
7. **开发集不是自动评测集**：8 道开发题为自然语言断言、面向人工量表，离线三基线在它上面都是 0/7，
   因此不能用它的通过率评价实现质量。
8. **失败路径只覆盖单机**：checkpoint 与审批台账是本机 SQLite，未验证多实例并发与分布式"恰好一次"。
9. **一条 `thread_id` 只能承载一次运行**：重复用它做新调查会被明确拒绝（`invalid_context`）；
   恢复请用 `resume`/`approve`，新任务请换线索。这是有意的安全约束，不是缺陷。
10. **网页模型链路待真实服务验证**。工作台默认离线，可通过 `COMMERCIAL_WEB_MODEL_PROVIDER=deepseek` 启用领域 Agent 和最终证据综合。API 与页面已通过脚本模型及模拟 HTTP 验证。见 [Task 038](docs/prompts/04_agents/2026-11-24_038_langchain_standardization.md)。
11. **Z1–Z3、CLI、逐 Agent 模型配置、配置真实性与路由兜底已实施并自检（Task 031），但待独立复查**：
    默认 `ask` 现在必须携带可信目标（从 `--lease`/`--unit` 或问题里的商铺编号解析），失败调用不再算取证，
    默认摘要分栏展示可信资金结论；模型客户端按各 Agent 自己的 YAML 创建；路由未命中返回澄清。
    Task 031 返修后 551 项测试，[DeepSeek 独立复查](docs/reviews/2026-11-21_task031_repair_independent_review.md)为有条件通过（文档同步 C1 已完成，R1 残余 C2 由 Task 034 §2.6 处理），见 [Task 031](docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)。
12. **模型名是配置事实**：历史真实评测报告中的 `deepseek-chat` 是当时实际使用的模型名，官方已于
    2026-07-24 下线；当前配置为 `deepseek-flash`（Task 031 核对官方文档后只改配置，未新增真实调用）。
13. **API 状态语义未同步**：调查返回 `needs_clarification` 时，API 层仍把 run 记为 `completed`
    （非 `insufficient` 分支）；Task 032 起界面显示“需要补充信息”，后端语义未改。

---

## 9. 版本候选与后续

- 分支 `main`，当前提交见 `git log -1`；里程碑记录见 [git_history](docs/checkpoints/git_history.md)。
- **未打 Tag、未发布、未部署**——这些动作需要项目所有者确认。
- 下一步先验证迁移后的实际 DeepSeek 网页链路，同时审计已有正式评测的评分与安全题，补齐人工量表和最终复现。验收标准见 [当前路线图](docs/product/PROJECT_DEVELOPMENT_ROADMAP.md)。
