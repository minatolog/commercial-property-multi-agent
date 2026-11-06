# ADR-005：项目转向 Agent-first 工程基线

- **日期**：2026-11-03
- **状态**：已采纳（方向由用户确认；实现细节为本 ADR 建议，待逐项评审）
- **任务**：006（Prompt 1）
- **取代/影响**：[system_design.md](../architecture/system_design.md)、[database_design.md](../architecture/database_design.md)、[agent_architecture.md](../architecture/agent_architecture.md)
- **最高依据**：[PROJECT_REFOCUS_AGENT_FIRST_V1.0.md](../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)

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
| C2 | 协作流程：Codex 写 Prompt → DeepSeek 落地 → Codex 审查 → 下一项 |
| C3 | LangGraph 编排、LangChain 模型/Tool Calling、Agent Registry、独立配置为 P0 |
| C4 | 三基线（Deterministic / Single Agent / Multi Agent）必须构建并对照 |
| C5 | 修改性操作（减免、调账、催缴、派单、对外通知）一律先出草案，经人工审批 |
| C6 | 历史文档与 14 表设计保留，不删除、不擅自重构 |
| C7 | 敏感信息不入库；未经确认不提交、不推送、不强制推送 |

### 3.2 本 ADR 建议的实现细节（可被后续任务推翻，需评审）

| 编号 | 建议 | 说明 |
|---|---|---|
| S1 | 契约版本号机制：`contract_version = "2.0"`，与现有骨架并存过渡 | 见 [agent_runtime_contracts.md](../architecture/agent_runtime_contracts.md) §2 |
| S2 | `AgentContext` 拆分 `principal_id`（权限主体）与 `commercial_tenant_ids`（商业租户） | 现有 `tenant_id` 语义过载，见契约 §5 |
| S3 | 金额统一为 `{"amount": "15120.00", "currency": "CNY"}` 十进制字符串对 | 禁止浮点真值，见契约 §4 |
| S4 | Evidence 区分 `db_fact` 与 `document_clause` 两类，附 `tool_call_id` | 见契约 §3 |
| S5 | 引用校验拆成"引用存在"与"引用支持结论"两级 | 见契约 §3.3 |
| S6 | State 归并键为 `(subtask_id, attempt)`，禁止裸列表追加 | 修复重放不可判定问题，见契约 §9 |
| S7 | 审批为独立 Graph 节点，审批绑定草案版本 | 见契约 §12 |
| S8 | 单任务预算上限由 Runtime 独占持有，模型/工具/图不得各自独立重试 | 见契约 §10 |
| S9 | 评测先做 8 题开发样例，正式集 30–50 题后续补齐 | 见 [evaluation_plan.md](../evaluation/evaluation_plan.md) |
| S10 | P0 最小数据库表数**待实施评审反推**，不锁定 10 表或 14 表 | 见 [mvp_scope_v2.md](../product/mvp_scope_v2.md) §5 |

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
| `docs/architecture/database_design.md`（14 表） | **长期设计参考，不是 P0 建表清单** | 保留不动；P0 按演示场景反推最小子集，另行评审 |
| 早期 Proposal / PPT / 研发基线 | 历史业务愿景 | 保留；视为"长期愿景/非当前 MVP"，不删不改 |
| `backend/app/agents/base/` 等骨架代码 | 有效的接口基础 | **保留并复用**；已知缺陷列入任务 007 修复清单，本轮不改代码 |
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
