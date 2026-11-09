# ADR-005：项目转向 Agent-first 工程基线

- **日期**：2026-11-03
- **状态**：已采纳（方向由用户确认；实现细节为本 ADR 建议，待逐项评审）
- **任务**：006（Prompt 1）
- **取代/影响**：[system_design.md](../architecture/system_design.md)、[database_design.md](../architecture/database_design.md)、[agent_architecture.md](../architecture/agent_architecture.md)
- **最高依据**：[PROJECT_REFOCUS_AGENT_FIRST_V1.0.md](../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)

> **2026-11-09 适用关系（Task 026）**：本文保留 2026-11-03 的决策及当时建议。项目方向继续生效；下文 C2 的逐任务 Codex 审查已被用户 2026-11-06 的流程变更替代，现为 DeepSeek 连续实现/自检/归档，Codex 按需审查。S1 的 V2 迁移为历史提案，不能视为已经切换；其余建议的落实情况以现行契约和验证证据判断。[当前基线](../architecture/CURRENT_BASELINE.md) 汇总当前适用范围和差距，不改写历史决策。

> **适用范围冲突规则**：本文档与历史 Proposal、历史 MVP 范围、历史优先级冲突时，**以本文档与 V1.0 基线为准**。历史文档保留，不删除、不改写，仅标注新的优先级关系。

---

## 1. 背景

项目最初按"商业地产综合管理软件 + AI 功能"规划，产出过完整业务愿景、Proposal/PPT、14 张表的数据库设计草案，以及一套 Agent 接口骨架。

问题不在这些产物本身，而在于**目标函数错了**：如果首要交付物是"功能齐全的地产管理系统"，开发资源会集中在 CRUD、业务规则和 UI 上，而这些正是成熟商业软件已经饱和的部分；"多 Agent"如果只是把确定性查询拆给几个 LLM，反而不是技术优势，而是缺陷。

## 2. 决策

**项目目标调整为：以商业地产争议调查为验证场景，交付一个可配置、可解释、可评测、可恢复的多 Agent 工作流系统工程作品。**

三条不可动摇的工程主张：

1. **能力证明优先于功能数量**。P0 只做能体现 LangGraph 条件路由、Tool Calling、RAG 证据、状态恢复、人工审批与客观评测的闭环。
2. **确定性计算不交给 LLM**。金额、日期、状态一律由 Python `Decimal` 或数据库计算；LLM 只负责理解、选择与表述。
3. **不预设多 Agent 更优**。必须同时实现 Deterministic / Single-Agent / Multi-Agent 三基线，用同一套题、同一套工具、同一预算测量，结果如实记录。

## 3. 用户已确认 vs 本 ADR 建议（必须区分）

### 3.1 用户已确认（不可由实现者更改）

| 项 | 内容 |
|---|---|
| C1 | 项目方向转为 Agent 工程能力核心，商业地产为验证场景 |
| C2 | 原流程：Codex 写 Prompt → DeepSeek 落地 → Codex 审查；**逐任务审查已于 2026-11-06 取消**，当前按需独立审查 |
| C3 | LangGraph 编排、LangChain 模型/Tool Calling、Agent Registry、独立配置为 P0 |
| C4 | 三基线（Deterministic / Single Agent / Multi Agent）必须构建并对照 |
| C5 | 修改性操作（减免、调账、催缴、派单、对外通知）一律先出草案，经人工审批 |
| C6 | 历史文档与 14 表设计保留，不删除、不擅自重构 |
| C7 | 敏感信息不入库；未经确认不提交、不推送、不强制推送 |

### 3.2 本 ADR 建议的实现细节（可被后续任务推翻，需评审）

| 编号 | 建议 | 说明 |
|---|---|---|
| S1 | 历史 V2 契约迁移提案；当前未正式切换 contract_version=2.0，不维护并行的两套生命周期 | 原提案见 [Runtime 历史快照](../architecture/agent_runtime_contracts_legacy_2026-11-09.md)；当前见 [运行时契约](../architecture/agent_runtime_contracts.md) |
| S2 | 区分权限主体与商业租户 | TrustedContext 已承载该区别；AgentContext 保留兼容字段，见现行契约 §1 |
| S3 | 金额使用 Decimal，序列化为十进制字符串并保留币种语义 | 历史 Money 对象为提案；现有工具采用其实际 schema，不强行改成统一 Money 类 |
| S4 | Evidence 区分 `db_fact` 与 `document_clause` 两类，附 `tool_call_id` | 当前结构见现行契约 §1–2 |
| S5 | 引用校验拆成“引用存在”与“引用支持结论”两级 | 当前见现行契约 §2；不夸大机械核验的语义范围 |
| S6 | 原提案为 `(subtask_id, attempt)` map 归并；目标是可解释、不重复混入旧结果 | 当前使用追加通道 + run 过滤/subtask 收敛及单 thread 单新任务约束；不是原 map reducer 已实现。差异见现行契约 §3、§5 |
| S7 | 审批为独立 Graph 节点，审批绑定草案版本 | 当前见现行契约 §5 |
| S8 | 单任务共享预算约束全部调用，禁止重试层各自放大额度 | 当前各层有限尝试与物理/逻辑计量见现行契约 §4 |
| S9 | 评测先做 8 题开发样例，P0 共 30–50 题 | 当前 8 dev + 32 heldout；题量已具备，正式实验未完成，见 [评测计划](../evaluation/evaluation_plan.md) |
| S10 | P0 按演示必要性确定模型，不锁定 10 表或 14 表 | 当前已有 12 表映射；不把实现表数改写为用户业务指标，见 [MVP 范围](../product/mvp_scope_v2.md) §5 |

## 4. 取舍与代价

| 取舍 | 放弃什么 | 换得什么 |
|---|---|---|
| 收缩业务广度 | 招商、会员、客流、完整物业后台、经营 BI | 把时间投入到图编排、证据链、故障恢复、评测 |
| 暂停完整计费引擎 | 阶梯租金/押金/能耗表计/核销写引擎的运行时实现 | 保留设计文档作为扩展参考；P0 只需"读账 + 确定性核对" |
| P0 不做热插拔 | 无重启替换 Agent、Agent Marketplace | 换来明确的"改哪些文件、不改哪些文件"清单与可回归验证 |
| 数据全部合成 | 真实客户数据 | 可提交、可复现、无合规风险 |
| 不承诺提升百分比 | 简历上好看的数字 | 只写经测试证实的结论 |

## 5. 与既有产物关系的明确结论

| 既有产物 | 关系 | 处置 |
|---|---|---|
| `docs/architecture/database_design.md`（14 表） | **长期设计参考，不是 P0 建表清单** | 设计正文保留，可补充适用范围与现行实现差异说明 |
| 早期 Proposal / PPT / 研发基线 | 历史业务愿景 | 保留；视为"长期愿景/非当前 MVP"，不删不改 |
| `backend/app/agents/base/` 等原骨架代码 | 有效的接口基础 | 保留并复用；K1–K5 为当时的任务 007 清单，已由后续任务收敛，当前待修见 Task 025 |
| `docs/prompts/001–005` 归档 | 历史记录 | 只读保留，不回填、不改写原始 Prompt |

## 6. 影响

1. **P0 交付物改变**：从"业务功能 + AI"变为"可运行工作流 + 证据 + 评测报告"。
2. **数据库策略改变**：14 表冻结为设计参考，P0 建表以"能支撑 C01–C08 与三基线"为唯一标准。
3. **验收标准改变**：以"能否复现、能否解释、能否对照"为准，而非"功能条目是否齐全"。
4. **文档结构扩展**：新增 `docs/decisions/`、`docs/product/`、`docs/evaluation/`。

## 7. 不做什么（防止范围回弹）

- 本 ADR 不授权删除任何历史代码或文档。
- 本 ADR 不授权安装依赖、创建数据库、调用付费 API。
- 本 ADR 不把"多 Agent"确立为默认方案——默认方案是**按任务复杂度选择**。
- 本 ADR 不承诺具体性能/准确率提升数值。

## 8. 相关文档

- 方向基线：[PROJECT_REFOCUS_AGENT_FIRST_V1.0.md](../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)
- MVP 范围：[mvp_scope_v2.md](../product/mvp_scope_v2.md)
- 运行时契约：[agent_runtime_contracts.md](../architecture/agent_runtime_contracts.md)
- 评测计划：[evaluation_plan.md](../evaluation/evaluation_plan.md)
- 历史架构：[system_design.md](../architecture/system_design.md)、[agent_architecture.md](../architecture/agent_architecture.md)
