# Commercial Property Multi-Agent — VS Code Codex 项目交接文件

> **历史交接（2026-11-09 标注）**：下文保留最初业务愿景和首次接手指令，非当前开发基线。方向已由 [Agent-first V1.0](PROJECT_REFOCUS_AGENT_FIRST_V1.0.md) 与 [ADR-005](../decisions/ADR-005-agent-first-refocus.md) 替代；当前实现/流程见 [当前基线](../architecture/CURRENT_BASELINE.md)。下文的待办、Git hash、工具分工和“未开始”均是当时记录，不作为今天的状态或重新申请授权的理由。

> 交接日期：2026-11-03  
> 项目仓库：`commercial-property-multi-agent`  
> 建议存放位置：`docs/handoffs/2026-11-03_codex_handoff.md`  
> 交接对象：VS Code 中能够读取当前工作区文件的 Codex  
> 本文件内容来自项目讨论及 DeepSeek 的阶段汇报；**尚未由交接方直接读取或审查本地仓库源码**。实际状态必须以当前工作区、Git 历史与已存在的文档为准。

---

## 0. 给 Codex 的第一条指令（请优先执行）

你现在接手 `commercial-property-multi-agent` 项目，负责在 VS Code 工作区**实际阅读和审查仓库代码与文档**，并在用户明确布置开发任务后实施变更。请先完整阅读本交接文件，再执行以下只读检查：

1. 确认工作区根目录、当前 Git 分支、`git status`、当前 `HEAD`，以及未提交的修改；**不要假设汇报里的 Git Commit 仍是当前版本**。
2. 阅读根目录 `README.md`、`docs/README.md`、`docs/architecture/system_design.md`、`docs/architecture/database_design.md`、`docs/architecture/agent_development_guide.md`，及 `docs/development_logs/development_log.md`；如有其他架构规范、ADR、`AGENTS.md`，也一起阅读。文件不存在时报告事实，不要杜撰。
3. 检查 `docs/architecture/database_design.md` 第 13.2 节及最新变更，确定 Task 003 Review 是否已由 DeepSeek 执行，以及提出的三项业务决策是否真正落入设计。
4. 核对目前文件、数据库建表脚本、Python 模型、Alembic 配置、FastAPI 服务、测试和文档的**真实存在情况**，区分“已实现、仅设计、计划中”。
5. 对照交接文件与实际仓库，给出**按严重程度排序的审查发现**（文件路径 / 定位 / 影响 / 修改建议），尤其检查多商铺租约的时间排他约束、付款核销一致性及模块边界。
6. 在完成只读审查后，先汇报项目真实状态、风险清单、建议的下一项最小开发任务与验收标准。**未经用户明确授权，不要安装依赖、创建数据库、批量重构、提交 Git 或推动远程代码。**

---

## 1. 项目定位与真实业务背景

项目全称：**Commercial Property Lease & Operations Multi-Agent System**（商业地产租约与物业运营多 Agent 协作系统）。

开发者有房地产企业实习背景：企业涉及住宅开发、综合商业体及小区物业；开发者接触过**收费与物业管理系统**，参与过**问题排查与系统配置**，认为商业运营与租约管理存在值得优化的业务痛点。不要将其描述为已负责过未获证实的研发、数据库维护或生产系统改造。

项目目标不是通用聊天机器人，而是构建一个**可解释、可审计、可评测、可以逐步扩展的企业 AI 业务应用**：连接商业租赁合同、应收账单、收款记录、商铺档案、物业工单，协作回答跨系统业务问题、识别风险，并生成可追溯的人工审核建议。

典型任务：

- 找出**未来 90 天内租约到期且存在欠费**的商铺，并逐项提供证据。
- 比较合同收费条款与系统账单，定位金额差异及来源。
- 综合欠费、租约到期、服务工单，生成需要人工确认的风险清单。
- 回溯合同 PDF 原文、版本、条款和页码，避免仅凭模型生成结论。

**所有演示业务数据均为模拟/合成数据**，不得假装接入了实习公司的真实生产系统，也不得使用未经授权的租户资料、商业合同或个人信息。

## 2. 工作方式与当前进度

原先协作方式：**ChatGPT 网页端负责业务方案、架构、任务 Prompt 和阶段 Review；DeepSeek（VS Code AI 对话助手）负责落地执行。** 现在希望把仓库内直接阅读、审核与后续编码工作转移给 **VS Code Codex**。未来是否继续用其他助手由用户决定，不假定 DeepSeek 与 Codex 会自动同步状态。

### 已由用户确认的启动事项

- [x] 新建 GitHub 仓库并绑定本地项目文件夹：`commercial-property-multi-agent`。
- [x] 已建立独立 Conda 环境：预期环境名 `commercial-agent`，Python 3.11；**请以终端实际输出确认解释器路径与版本**。
- [ ] PostgreSQL 数据库设计：**文档已经交付，但仍有业务与约束审查待确认**。
- [ ] 模拟商业体数据准备。
- [ ] FastAPI 最小服务和数据库连接。

### DeepSeek 关于 Task 003 的阶段报告（待仓库实证）

DeepSeek 报告“PostgreSQL 数据库架构设计”已完成、仅生成文档、**未安装 PostgreSQL、未建表、未提交**。具体报告：

- `docs/architecture/database_design.md`：约 46,000 字符、14 章，保留已有原则与历史。
- `docs/prompts/02_database/2026-11-03_004_postgresql_database_design.md`：保存原始 Prompt 和执行归档。
- 更新了开发日志、Git 检查点记录、Docs README 编号表、经验总结、架构 ADR 及 Agent 开发指南等。
- 初始建议 13 张表，新增 `lease_units` 后为 **14 张表**。
- 提到 **2 条 `EXCLUDE USING gist` 排他约束**，需 `btree_gist`；以及 17 项唯一约束、21 个索引。
- 余额、逾期和部分占用状态作为派生数据（如 `v_invoice_outstanding`），而非冗余落库；`invoice_items.amount` 作为必要快照。
- 数据访问分层：**Agent → Tool → Service → Repository → Model**。
- 当时报告 `HEAD` 为 `7ed2665`、未提交；这只是历史快照，**不可作为当前 Git 状态**。
- 文档第 13.2 节当时有 8 个待确认业务问题。

随后 ChatGPT 已拟好 **Task 003 Review** 提示词，计划由 DeepSeek 再做一次数据库设计审查。**用户说“这次 Prompt 提交之后转到 VS Code Codex”，但交接时没有收到 Review 已执行完成的确认。Codex 必须从仓库检查真实结果。**

## 3. 业务数据模型：当前候选 14 张表

| 模块 | 表 | 主要职责 |
|---|---|---|
| 资产 | `projects` | 商业综合体 |
| 资产 | `buildings` | 楼栋 |
| 资产 | `units` | 商铺 |
| 租赁 | `tenants` | 租户 |
| 租赁 | `leases` | 租赁合同及状态 |
| 租赁 | `lease_units` | 合同与一个或多个商铺的关联 |
| 租赁 | `lease_charge_rules` | 免租、基础租金、物业费、阶梯/分段计费 |
| 收费 | `invoices` | 应收账单抬头 |
| 收费 | `invoice_items` | 账单明细与必要金额快照 |
| 收费 | `payments` | 收款流水 |
| 收费 | `payment_allocations` | 付款对账单/明细的核销分配 |
| 物业 | `work_orders` | 报修与物业工单 |
| 文档 | `documents` | 合同 PDF、制度及来源版本 |
| 系统 | `agent_runs` | Agent 工作流执行记录 |

这是**待审架构**，不是已经实现的数据库。对表数、字段、类型、约束、索引的最终判断应基于实际文档和业务测试场景，不能因为先前定了 14 张表就强行保留问题结构。

### Task 003 Review 必须复核的高风险点

1. **跨表租期冲突**：若 `leases` 保存生效日期、`lease_units` 保存 `unit_id`，PostgreSQL 原生 `EXCLUDE` 不能通过跨表 JOIN 直接约束组合字段；审查所谓“EXCLUDE 限制同商铺时间重叠”的具体 SQL 设计是否真的可执行。考虑把占用区间放到同一表、设置一致性机制及并发边界，或者限制 MVP 的多商铺功能。
2. **租约状态与占用**：草签、待签、生效、退租、终止、过期等状态的含义及转移规则；是否防止正式占用冲突。不能只写一行 `CHECK` 就声称涵盖全部跨表业务规则。
3. **付款核销并发**：不能核销超过 `payments` 的可用金额，也不能超过账单未结金额；需要考虑数据库事务、行级锁/串行化、幂等性及并发测试，不能仅靠普通行内 `CHECK`。
4. **免租与阶梯计费**：时间段边界、同费用类型规则重叠、调整生效日期及合同版本。
5. **索引冗余**：唯一与排他约束可能隐式创建索引；核查额外 21 个索引是否必要。
6. **权限与审计**：多项目数据隔离、数据权限、文档证据、合同修订历史及敏感数据保护。

### 上一次 Review Prompt 拟定的三项 MVP 业务决策

**这些是提出的设计建议；是否已纳入文档待查验。**

- 押金：**暂不并入普通租金账单和租金收入**；将来单独设计押金收退、抵扣和资金流水。
- 能耗：**MVP 不做表计抄表系统**；可支持固定费用或经过验证的人工导入费用。
- `pending_signature`：**不代表正式占用商铺**；如有“预留商铺”需求，单独定义预留状态或规则。

Review 还应列出文档中剩余五项待决问题并逐条提出建议，不能凭本交接文件猜测其原文。

## 4. 强制工程架构原则

### 4.1 架构风格

采用 **Modular Monolith + Agent Registry + LangGraph Orchestration + Configuration-Driven Design**。初期**不拆微服务**。目标是高内聚、低耦合、可测试、可替换；不要为追求“零改动”而做不必要的动态插件系统或复杂抽象。

### 4.2 Agent 可扩展性（硬性需求）

- 一个 Agent 一个模块：自己的逻辑、Prompt、Schema、工具适配和测试。
- 统一 `AgentProtocol` / `BaseAgent`：明确 `AgentRequest`、`AgentContext`、`AgentResult`、错误协议和执行元数据。
- `Agent Registry` 负责注册、按能力发现和启用/禁用；注册清单必须可审计；禁止按不可信配置任意动态导入/执行代码。
- 模型经统一 Adapter 调用；每个 Agent 有**独立配置**：`enabled`、model/provider、Prompt 路径、温度（支持时）、超时、重试、工具白名单、检索参数、版本标识等。
- Coordinator/Graph Builder 使用标准能力接口，不应直接导入其它业务 Agent 的内部类或把所有 Agent 路由写死在庞大 `if/else` 中。
- 被禁用或不可用的 Agent 应明确报错或降级/人工转交，不得静默丢失子任务。
- LangGraph 共享 State 只存跨步骤需要的内容；并行结果合并/Reducer、断点恢复、超时和故障隔离必须有明确策略。
- 公共 RAG、LLM 客户端、Repository、业务 Service 不要每个 Agent 各自复制。
- 改一个 Agent 的模型或 Prompt 不应要求修改其他 Agent 的代码；接口或共享 Schema 变化仍必须回归测试。

### 4.3 数据与模型职责分离

- **LLM**：任务理解、调用工具、提炼合同条款、解释证据及协调。
- **确定性 Python/SQL**：租金/费用计算、账单核销、日期比较、风险规则、事务与权限。
- **RAG**：查询 PDF/制度原文、返回正确文档与页码/条款证据；不作为结构化财务事实的唯一来源。
- **业务服务**：Agent → Tool → Service → Repository → Model；Agent 不应绕过权限直接执行任意 SQL。
- **重要操作**：正式修改账单、催缴、发送通知、派单等都需要明确权限与必要的人工确认、审计。输入文档不可信，防范 Prompt Injection。

### 4.4 技术路线（计划，不等于已经安装）

| 层 | 计划技术 |
|---|---|
| 语言/环境 | Python 3.11 / Conda `commercial-agent` |
| 后端 | FastAPI、Pydantic |
| DB | PostgreSQL、SQLAlchemy 2.x、Alembic |
| Agent | LangGraph；必要时使用 LangChain 工具层 |
| LLM | DeepSeek API（统一适配层，可替换） |
| RAG | BGE、Chroma、BM25、RRF、Cross-Encoder Reranker |
| 前端 | React + TypeScript（后期） |
| 追踪与评测 | 结构化日志、Agent Trace、任务成功率、引用准确率、成本与时延；可考虑 LangSmith |
| 部署 | Docker（后期） |

原有的 `enterprise-knowledge-agent` 是**独立的 CNOOC 企业 RAG 项目**。可以借鉴其检索设计和工程经验，但不能混用知识库、Conda 环境或未经审核地复制全部代码。

## 5. 项目开发规划与 MVP 边界

### 目前的启动五步

1. ✅ GitHub 仓库与本地目录。
2. ✅ Conda 独立环境。
3. 🔎 数据库 ER、表字段、约束和业务规则**待最终评审**。
4. ⏳ 模拟数据规则与生成。
5. ⏳ FastAPI 最小服务和 DB 连接。

### 推荐后续顺序

- **Task 003 Review**：确认数据库设计，解决待决业务问题与约束可实现性。
- **Task 004**：经用户审核同意后，安装/配置 PostgreSQL，创建 SQLAlchemy 模型、Alembic 首次迁移、建立约束和数据库测试。
- **Task 005**：生成稳定可复现的模拟项目、商铺、租户、合同、账单、付款和工单数据。
- **Task 006**：FastAPI 最小服务、数据查询/收费工具及端到端基础测试。
- 随后实现合同 PDF 解析、RAG、Lease Agent、Billing Agent、Coordinator，评测后再加 Property/Risk Agent 与前端。

### MVP 模拟数据的建议规模（非硬限制）

- 约 30 个商铺、25 个租户、30 份合同。
- 约 150 条账单、100 条付款记录、50 条物业工单。
- 应有边界案例：免租期、阶梯计费、合同临期、部分付款、跨账单核销、未付/逾期、合同与账单不符、重复报修等。
- 数据生成脚本要可复现（固定随机种子）、可清理重建，并确保金额与合同规则一致。

### MVP 核心演示任务

1. 上传合同 PDF，提取租期/租金/免租条款，附原文证据。
2. 查询商铺应收/实收/未收，准确处理付款核销。
3. 找出未来 90 天内到期租约。
4. 找出同时到期且欠费的商铺。
5. 使用多 Agent 协作回答跨系统问题，带证据、日志和失败反馈。

**不要为了“多 Agent”而滥用 LLM：** 能用 SQL 查询、固定计算、普通工作流做的就用确定性代码。用对照实验评估多 Agent 是否真正优于单 Agent。

## 6. 文档归档与 Git 工作规范（长期约束）

用户明确要求**完整保存每次 AI 开发任务及经验**，以便复盘、迁移、回滚与简历总结。请阅读并沿用项目实际存在的 `docs/` 规范，不要另起一套互相冲突的体系。

预期的核心目录：

```text
docs/
├── README.md
├── architecture/
│   ├── system_design.md
│   ├── database_design.md
│   ├── agent_architecture.md
│   └── agent_development_guide.md
├── prompts/
│   ├── 01_environment/
│   ├── 02_database/
│   ├── 03_rag/
│   ├── 04_agents/
│   ├── 05_frontend/
│   └── 06_testing/
├── development_logs/
│   └── development_log.md
├── issues/
│   └── issue_log.md
├── lessons_learned/
│   └── knowledge_notes.md
├── checkpoints/
│   └── git_history.md
└── handoffs/
    └── 2026-11-03_codex_handoff.md
```

此结构为建议与已讨论约定的汇总；**实际目录以仓库为准**，不要凭空填充不存在的开发成果。

每次开发任务应：

1. 按现有编号和分类保存**原始用户 Prompt**（无法准确取得原文时注明不可得，不得编造）。
2. 更新开发日志：任务目标、修改文件、关键决策、测试结果、未解决问题与下一步。
3. 产生问题时更新 Issue Log；产生技术理解时整理 Lessons Learned。
4. 给出建议的 Git Commit Message 和可复验的测试方法。
5. 只有真实提交后才记录真实 Commit Hash；提交前标记 `Pending`。
6. 不提交 `.env`、API Key、真实租户敏感信息等；不要把 `.gitignore` 设置成忽略 `docs/`。
7. 默认不要自动提交/推送，尤其不能擅自 `reset --hard`、force-push、批量删除历史或覆盖用户未提交变更。

## 7. Codex 接手后的代码审查重点

请按以下顺序检查，并提供可执行的修复建议：

**P0 — 正确性**

- 14 张表的字段、主键、外键、唯一约束、索引及对应查询场景是否自洽。
- `lease_units` 的多商铺关联与重叠租期排他约束是否可实际创建；状态更新和并发交易是否存在漏洞。
- 欠费派生视图是否正确处理部分付款、跨账单分配、账单取消/作废、到期日及账单明细。
- 付款核销不能超额；是否具备事务隔离/行锁/幂等处理方案。
- 免租、阶梯租金及收费规则生效日期是否可在模型和计算代码中一致表达。

**P1 — 可维护性与扩展性**

- Agent 接口、配置与注册方案是否清晰，不要过早依赖某个供应商 SDK。
- SQL/业务规则与 Prompt/Agent 是否分层，避免大模型承担金额计算。
- Agent 配置、Prompt、工具白名单是否能独立变更与单测。
- 是否将数据库 Schema 改动与 Agent 数量变化错误地绑定。

**P2 — 工程落地**

- 是否有适当的 `.gitignore`、环境说明、确定性测试、类型检查/格式规范、日志与错误处理。
- 文档是否与实际代码一致；是否有“实现了”但源码中不存在的功能声明。
- README 能否让他人在独立环境中复现基础开发环境。

审查结果不要只说“整体没问题”，要尽可能给出**文件路径、具体问题、影响、优先级和建议测试**。若尚无源码可供审查，直说“目前主要是架构文档”，重点审查设计可执行性。

## 8. 与用户的协作约定

- 用户主要用中文沟通，技术术语保留英文；偏好循序渐进、解释设计原因和取舍。
- **先核验真实仓库状态，再回答“已完成”。** 不要把模型生成的报告当作完成证明。
- 用户会先确认重大设计决策；不要在缺乏授权时越过阶段边界提前实现整套系统。
- 用户重视求职价值，但简历只能写真实完成且可测量的工作，不编造部署效果或性能提升。
- 优先提供可运行、可测试、可回滚的最小变更，避免为了表面复杂度引入六 Agent/微服务或过度设计。

---

## 9. 本次交接之后的首个预期产出

请 Codex 在读完真实仓库后先给出下列报告，而不是立即大规模实现：

1. **实际仓库状态表**：项目路径、分支/HEAD、未提交变更、已存在模块与文档。
2. **Task 003 Review 检查结论**：DeepSeek 是否执行、审查结果是否落地、还有哪些未定问题。
3. **数据库设计 Review Findings**：优先级排序，尽可能指向文档位置、规则和 SQL 可实施性。
4. **架构维护性检查**：Agent 模块化、Registry、独立配置、公共业务工具边界是否在文档中已明确。
5. **建议的 Task 004 实施计划**：分步建模/迁移/约束测试的顺序、改动文件清单、验收命令和回滚策略；**先请用户确认，再开始执行**。

> 最终原则：代码与测试是事实来源，文档是设计与历史依据，ChatGPT/DeepSeek 的陈述只是需要核对的上下文。
