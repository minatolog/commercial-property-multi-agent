# MVP 范围 V2（Agent-first）

- **日期**：2026-11-03
- **状态**：建议范围（方向已由用户确认，具体条目待评审）
- **依据**：[ADR-005](../decisions/ADR-005-agent-first-refocus.md)、[PROJECT_REFOCUS_AGENT_FIRST_V1.0.md](../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)
- **取代**：历史 MVP 范围中"完整商业地产管理系统"的定义。历史文档保留，不删除。

---

## 1. 一句话范围

> P0 交付**一条**能跑通的、证据可核验的跨系统争议调查工作流，并用**三基线与固定评测集**证明它相对简单方案的真实代价与收益。

范围之外的一切功能，即使业务上合理，也不进入 P0。

## 2. 主场景（唯一 P0 演示场景）

**用户输入**：

> 商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，并要求减免费用。请核对合同、账单、付款和工单，分析争议原因，指出证据与缺失信息，形成供人工审核的处理方案。

**为什么是它**：同时具备异构证据源（合同文本 / 账单 / 付款 / 工单）、潜在冲突（合同条款 vs 未签署附件）、条件性下一步（是否补查）、以及必须由人决定的事项（是否减免）。**不适合**用单条 SQL 回答，因此能真实体现编排价值。

**明确不代表**：Agent 不判定法律责任，不直接减免，不对外发函。

## 3. P0 覆盖项与可验证完成标准

下表的"可验证行为"是未来用固定评测集 + 代码断言检查的对象，不是主观描述。

| # | P0 覆盖项 | 可验证行为（完成标准） |
|---|---|---|
| 1 | **Lease / Billing / Property 三类独立能力**；Compliance 保留且默认禁用 | Registry 能分别解析 `lease.*`、`billing.*`、`property.*`；`compliance` 在配置中 `enabled: false` 且 `disabled_capabilities()` 包含它；调用它返回 `AGENT_NOT_ENABLED` 而非"能力不存在" |
| 2 | 统一 Runtime、Registry、独立配置、受控 Tool Calling | 三个 Agent 共用同一 `handle()` 入口与同一 `AgentResult` 结构；每个 Agent 有独立 YAML；未授权工具调用返回 `TOOL_NOT_ALLOWED`；不存在任意 SQL / 任意代码工具 |
| 3 | 真实 LangGraph 条件路由、按需并发、合流、有限补查 | 图含至少 1 条条件边与 1 个并发扇出/合流点；C01（确定性查询）路由为"不并行"，C03（争议调查）路由为三路并发；补查轮次有硬上限且超限后转人工 |
| 4 | 精简合同 RAG、确定性金额核对、结构化 Evidence | 每个结论都能返回 `evidence_id`；`document_clause` 类证据含 `document_id + version + page + excerpt`；金额断言用 `Decimal` 与 fixture 真值精确相等 |
| 5 | 超时、预算、失败反馈、持久 checkpoint、审批暂停与授权恢复 | C06 的主失败路径与恢复 probe 分别验收（失败路径不要求 invoice 证据）；同一 `thread_id` 中断后可恢复；恢复前重新校验权限；**Trace** 记录 `latency_ms` / `error_code` / `attempt` / 重放次数。**不预设 `agent_runs` 表**：Trace 的落地存储方案单独决定 |
| 6 | Deterministic / Single Agent / Multi-Agent 三基线 | 三基线共用同一 fixture、同一工具集、同一权限上下文、同一总预算；**事实、引用、权限、审批使用同一套共通质量断言**；编排约束只按各基线自身形态判定；`route_class` 仅作效率指标，不参与答案正确性 |
| 7 | 固定评测集、Trace、最少命令演示 | `docs/evaluation/cases/smoke_v1.jsonl` 恰好 8 行且 case_id 唯一；一次演示从请求到报告不含手工干预（审批分支除外）；Trace 可导出并含调用数与重放记录 |
| 8 | 固定评测集总量 | P0 达 **30–50 题** = 本轮 8 题开发样例 + 后续 **22–42 题保留测试集**；**保留集属于 P0 交付范围**，不是 P1 |
| 9 | 审批只针对草案 | 任何"减免/调账/催缴/派单/对外通知"路径只产出 `ApprovalDraft`；批准需**串行双角色**（物业→财务，两名不同主体）、绑定 `draft_id+draft_version`、限时有效，并拒绝越权/重放/换版/过期事件；**即使审批通过也不产生真实业务写操作**（P0 无真实写接口） |
| 10 | 可统计的重复测量 | 允许在运行前预先固定重复次数并冻结配置（模型、温度、prompt、数据、评分版本）；同一批次内不调参；报告给出全部重复的分布，不得只报最优一次 |

## 4. 明确不做的判断规则

| 任务形态 | 正确做法 | 禁止做法 |
|---|---|---|
| "A-301 现在欠多少" | 确定性工具直接查（C01） | 拆成多个 Agent 讨论 |
| "合同递增条款怎么写" | 单 Agent + RAG（C02） | 编排三个 Agent 交叉验证 |
| 金额计算 | Python `Decimal` | 让 LLM 算或"估算" |
| 减免/调账/催缴 | 草案 + 人工审批 | 直接执行 |
| 多 Agent 是否更好 | 用评测结果回答 | 在文档/简历中预设结论 |

## 5. 数据库策略（P0）

- P0 **不启动**完整 14 表实施。14 表是长期设计参考，[database_design.md](../architecture/database_design.md) 保持不动。
- **最小表数待实施评审反推**，判据只有一条：能否确定性地支撑 C01–C08 与三基线。
- 本文档**不锁定**"10 表"或"14 表"中的任何一个作为用户已确认指标。
- P0 允许先用 fixture 内存数据集跑通 Runtime；数据库接入以"不改变工具契约"为前提。
- 完整计费、押金、能耗表计、核销写引擎 **暂停**，不作为 P0 依赖。

## 6. P1（P0 之后，按评测结果决定顺序）

| 项 | 触发条件 |
|---|---|
| 轻量 Trace UI / 演示页 | P0 报告已稳定，需要对外展示时 |
| 扩充题量（>50）与回归流水线 | P0 的 30–50 题（含保留集）稳定后，继续扩题与自动化回归 |
| 合同 RAG 混合检索（BM25 + 向量 + RRF） | 单路检索在评测中召回不足时 |
| 风险提示（显式规则，非 LLM 打分） | 有明确业务规则可编码时 |
| 更多领域能力（如合规检查） | 三基线证明编排有净收益后 |
| Docker / 部署 / 监控 | P0 可复现性已达标后 |

> **不再把保留测试集放进 P1**：P0 已经承诺 30–50 题与客观对照，保留集是 P0 的组成部分；P1 只做"在此之上继续扩题、扩形态、部署化"。

## 7. 暂停（明确不做，避免范围膨胀）

招商与铺位营销、会员与客流、工程项目、完整物业后台 CRUD、经营 BI 看板、多商业综合体运营、月度结账、发票税务、真实对外通知、Agent 热插拔与 Marketplace、分布式多进程。

## 8. 与"已完成/仅设计/未开始"的对应

| 状态 | 内容 |
|---|---|
| 已完成（代码） | `backend/app/agents/base/`（契约、BaseAgent、Registry）、`factory.py` 静态白名单、`config/`（Schema+加载器+3 个 YAML）、`llm/adapter.py`、`tools/base.py`（契约）、`orchestration/`（仅契约）、`tests/smoke_agent_contracts.py`（57 项） |
| 仅设计（文档） | 14 表数据库设计、P0 范围（本文档）、运行时契约、评测计划与 8 题样例、方向 ADR |
| 未开始（P0 待建） | LangGraph 图、真实 Tool 实现、Business Service/Repository、fixture loader、评测 runner、三基线、FastAPI 入口、持久 checkpoint |

## 9. 相关文档

- [ADR-005](../decisions/ADR-005-agent-first-refocus.md)
- [agent_runtime_contracts.md](../architecture/agent_runtime_contracts.md)
- [evaluation_plan.md](../evaluation/evaluation_plan.md)
- [agent_architecture.md](../architecture/agent_architecture.md)（历史骨架设计）
