# 系统架构设计

> **状态**：骨架（Draft）· **已被 ADR-005 部分取代**
> **最后更新**：2026-11-03
> **方向说明**：项目已于任务 006 转向 Agent-first 工程基线。**业务目标、P0 优先级、模块边界以 [ADR-005](../decisions/ADR-005-agent-first-refocus.md) 与 [mvp_scope_v2.md](../product/mvp_scope_v2.md) 为准**；本文档保留为历史架构与后端骨架说明，冲突时以 ADR-005 为准。
> **编码级契约**：见 [agent_runtime_contracts.md](./agent_runtime_contracts.md)（本文件不重复字段定义）。

---

## 1. 文档目的

记录 `commercial-property-multi-agent` 的系统架构：模块划分、Agent 协作方式、数据流向、外部依赖与技术选型理由。本文件回答「系统由什么组成、为什么这样切分」，不记录代码实现细节。

---

## 2. 业务背景

面向**商业地产租约与物业运营**场景的多 Agent 协作系统。

该领域的典型业务对象（待与业务方确认后细化）：

- 物业（Property）：楼宇、楼层、单元
- 租户（Tenant）：企业主体、联系人
- 租约（Lease）：起止日期、租金、递增条款、免租期、押金
- 运营事项（Operation）：报修工单、费用账单、续租提醒、合规检查
- 文档（Document）：合同、附件、往来函件 —— RAG 知识库的来源

领域特点决定了架构重点：**数据准确性要求高**（金额、日期）、**文档检索需求强**（合同条款问答）、**流程有多步骤协作**（如「续租评估」需查合同 → 查账单 → 比市场价 → 生成建议）。

---

## 3. 规划的技术栈

| 层次 | 技术 | 用途 | 状态 |
|---|---|---|---|
| 语言运行时 | Python 3.11（conda env `commercial-agent`） | 全部后端逻辑 | ✅ 就绪 |
| API 层 | FastAPI | HTTP 接口、请求校验、依赖注入 | 未引入 |
| 数据校验 | Pydantic | 请求/响应模型、配置管理 | ✅ 已引入（2.14.2，用于契约与配置校验） |
| ORM | SQLAlchemy | 关系数据映射与查询 | 未引入 |
| 数据库 | PostgreSQL | 结构化业务数据持久化 | 未接入 |
| Agent 编排 | LangGraph / LangChain | 多 Agent 状态图、工具调用、上下文管理 | 未引入（仅契约） |
| LLM | DeepSeek API | 推理与生成 | 未接入（仅适配层骨架） |
| 向量库 | Chroma | 文档切片的向量存储与相似检索 | 未引入 |
| 向量化 | BGE Embedding | 中文语义向量化 | 未引入 |
| 检索增强 | BM25 + Reranker | 关键词召回 + 精排，与向量检索混合 | 未引入 |

**实际依赖现状（2026-11-03 核对）**：`commercial-agent` 环境仅安装 `pydantic`、`pyyaml` 及其传递依赖。其余依赖一律未安装。

---

## 4. 规划的模块划分

以下为**待验证的初步切分**，实际落地时可能调整：

```text
commercial-property-multi-agent/
├── backend/                      # 后端根（prompt_path / 配置相对路径的基准）
│   ├── app/
│   │   ├── agents/               # Agent 契约、注册表、各业务 Agent
│   │   │   ├── base/             # 唯一的 Agent 接口实现
│   │   │   ├── factory.py        # 配置 → 实例（静态白名单）
│   │   │   └── <agent_name>/     # 代码 + prompts 同居
│   │   ├── config/               # 配置 Schema、加载器、agents/*.yaml
│   │   ├── llm/                  # 模型适配层
│   │   ├── orchestration/        # LangGraph 状态图与 Coordinator
│   │   └── tools/                # 确定性业务工具
│   └── tests/
├── docs/                         # 文档与 Prompt 归档
└── pyproject.toml                # 依赖与工具配置（阶段 1）
```

已完成部分（阶段 0）：`agents/base/`、`agents/factory.py`、`agents/{lease,billing,compliance}/`、`config/`、`llm/`、`orchestration/`（仅契约）、`tools/`（仅契约）、`tests/smoke_agent_contracts.py`。

尚未创建：FastAPI 应用入口、`db/`、`rag/`、`services/`、`pyproject.toml`。

> Agent 层的详细设计见 [agent_architecture.md](./agent_architecture.md)，开发流程见 [agent_development_guide.md](./agent_development_guide.md)。

---

## 5. 待定架构问题

以下问题需要在后续任务中决策，**当前未决定**（带 ✅ 的已在阶段 0 部分决定）：

| # | 问题 | 影响 | 待决策时机 |
|---|---|---|---|
| 1 | Agent 如何划分？按业务域（租约 / 运营 / 合规）还是按职能（检索 / 计算 / 汇总）？ | 决定 LangGraph 状态图形状与通信成本 | 阶段 4 |
| 2 | 多 Agent 采用何种协作拓扑：主管调度（Supervisor）还是流水线（Pipeline）？ | 决定状态管理复杂度与可观测性 | 阶段 4 |
| 3 | 对话状态是否持久化？存 PostgreSQL 还是内存/Redis？ | 决定能否支持断点续聊与多轮长会话 | 阶段 4 |
| 4 | RAG 是否采用混合检索（BM25 + 向量）？融合策略用 RRF 还是加权？ | 影响检索准确率与实现复杂度 | 阶段 3 |
| 5 | 文档切片粒度与是否保留表格结构？合同类文档表格多 | 直接影响问答质量 | 阶段 3 |
| 6 | DeepSeek API 的失败重试、限流、成本控制策略 | 影响稳定性与费用 | 阶段 4 |
| 7 | 同步还是异步调用链（FastAPI async + SQLAlchemy async）？ | 影响全项目代码风格，越早定越省事 | 阶段 1 |
| 8 | ✅ Agent 配置与密钥管理已定为「每 Agent 独立 YAML + 环境变量」；应用级配置（数据库连接等）方式待定 | 影响部署安全性 | 阶段 1 补全应用级配置 |
| 9 | ✅ 已在任务 004 决策：隔离单元为 `projects`，叶子业务表冗余 `project_id` 并用复合外键强制一致；`tenants` 为全局主体 | 影响全部业务表结构 | 已完成，见 [database_design.md](./database_design.md) 2.7 |

---

## 6. 架构决策记录（ADR）

### ADR-004：数据层采用 14 张表 + Service/Repository 边界

- **日期**：2026-11-03｜**任务**：004｜**状态**：已采纳
- **决策**：在初始 13 张表基础上新增 `lease_units`，共 14 张；Agent 一律经 Tool → Service → Repository 访问数据，禁止直接接触 ORM 模型。
- **理由**：
  - 若把 `unit_id` 放在 `leases`，"未来支持多商铺租约"将需要破坏性迁移 + 全量查询改写；用关联表则只需 `DROP INDEX`。
  - Agent 若直接持有 ORM 实例，会依赖懒加载关系，表结构调整时静默崩坏。DTO + Service 把「对外形状」变成显式契约。
- **代价**：多一层间接调用；每个新查询需要写 Repository/Service 方法。对当前规模可接受。
- **可逆性**：Service 边界天然支持后续把数据源从 PostgreSQL 换成其他存储；`lease_units` 也可在多商铺需求确认后直接放开。

### ADR-003：采用 Modular Monolith 而非微服务

- **日期**：2026-11-03｜**任务**：003｜**状态**：已采纳
- **决策**：单进程内按模块划分 Agent，用接口契约而非网络边界实现解耦。
- **理由**：单人/小团队规模下，微服务的部署、监控、跨服务一致性问题成本远大于收益；Agent 间需高频共享租约/账单/合规上下文，跨进程调用会显著增加延迟与失败面。
- **代价**：模块边界约束依赖代码评审与自检脚本，无法由运行时强制；需要严格的 import 规则（见 `agent_development_guide.md` 硬规则 1–3）。
- **可逆性**：沿 `AgentProtocol` 边界可将单个 Agent 抽为独立服务，业务逻辑无需重写。

### ADR-002：能力发现使用字符串而非全局枚举

- **日期**：2026-11-03｜**任务**：003｜**状态**：已采纳
- **决策**：`capability` 为 `<domain>.<action>` 字符串，由各 Agent 自行声明，Registry 运行时汇总。
- **理由**：全局能力枚举会让「新增 Agent」必须修改一个公共文件，直接违背「新增 Agent 不应修改已有文件」的硬要求。
- **代价**：失去编译期校验，拼写错误只在运行时暴露；已通过正则格式校验 + 自检覆盖缓解。

### ADR-001：配置到 Agent 的映射使用静态白名单

- **日期**：2026-11-03｜**任务**：003｜**状态**：已采纳
- **决策**：`factory.py` 内维护 `AGENT_IMPLEMENTATIONS` 字典，禁止依据配置字符串动态导入模块。
- **理由**：配置文件可被修改，若用 `importlib.import_module(name)` 则等同把代码执行权限交给配置。静态白名单让被篡改的配置最多命中已登记实现。
- **代价**：新增 Agent 必须手工登记一行；忘记登记时配置被跳过。已通过 `build_registry(strict=True)` 与开发指南检查清单缓解。

---

## 7. 变更历史

| 日期 | 任务 | 变更 |
|---|---|---|
| 2026-11-03 | 004 | 待定问题 #9 决策完成（`projects` 为隔离单元）；补 ADR-004（14 张表 + Service/Repository 边界） |
| 2026-11-03 | 003 | 目录结构调整为 `backend/app/`；新增 Agent 架构文档与开发指南；补充 ADR-001~003；待定问题增至 9 项 |
| 2026-11-03 | 002 | 建立文档骨架，明确范围、技术栈清单与 8 项待定问题 |
