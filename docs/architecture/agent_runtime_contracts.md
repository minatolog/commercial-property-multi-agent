# Agent Runtime 契约与 Graph 语义（当前版）

- 更新：2026-11-09，Task 026；代码基线 d6577da。
- 需求依据：[当前基线](CURRENT_BASELINE.md)、[MVP 范围](../product/mvp_scope_v2.md)。
- 原始 V2 迁移提案与 K1–K5 问题记录：[历史快照](agent_runtime_contracts_legacy_2026-11-09.md)。其中 V2 类型、字段和节点名为当时提案，不可直接当作当前 API。

## 1. 已有类型与可信边界

| 类型/位置（相对 backend/app） | 当前契约 |
|---|---|
| agents/base/contracts.py:AgentRequest | request_id、task_id、capability、payload；request_id 是 UUID；没有 contract_version 字段 |
| 同文件 AgentContext | trace_id、run_id、principal_id、project_ids、permissions、subtask_id、deadline_at 等；tenant_id/user_id 为兼容字段，不作为用户自报授权来源 |
| 同文件 AgentOutput / AgentResult | 子类返回 data/warnings/token_usage；BaseAgent 包装 success/partial/failed/skipped、output/error/metadata |
| runtime/types.py:TrustedContext | 从可信主体记录构造，含主体、项目、权限、可选商业租户范围和 deadline；不是公开请求体 |
| 同文件 RuntimeResult | 包装 Agent 结果、证据、工具 Trace、预算快照与 run/trace ID |
| 同文件 EvidenceDraft / Evidence | 工具产出证据草稿；执行器补 source_tool/tool_call_id/collected_at 等；文档详细定位在 fields 内 |
| 同文件 ToolExecution | call_id、tool_name、status、data、evidence、error、attempts、duration_ms、traces；不使用历史示例的 ToolResultV2 |

payload 只承载问题、目标与筛选；权限/项目/预算等保留键由 Runtime/执行器拒绝。外部文档和模型参数均不能扩大授权。工具 schema 严格校验，不允许任意 SQL/代码。

当前没有完成 contract_version=2.0 的正式切换。更改公共契约必须显式评审兼容、检查点恢复和全部调用方；不能照历史目标表添加全部字段后宣布已迁移。

## 2. 工具、证据与完成条件

所有业务工具通过 ToolExecutor.execute() 调用：注册表 → Agent 白名单/业务权限 → 参数与保留键 → 预算 → deadline/工具超时及有限尝试 → 输出与项目范围核验 → 证据/Trace。

金额由 Decimal/数据库计算，输出采用十进制字符串；工具返回类型化数据和 EvidenceDraft，不向 Agent 暴露 ORM/Session。Evidence 的 db_fact/document_clause、数据版本、业务基准日、记录与调用来源用于回查。合同定位需核对文档版本、页码、条款和原文；L1 引用存在与 L2 支持结论分别检查，不能把机械核验当作完整语义证明。

完成要求是**得到与当前目标相关的有效成功结果**，失败调用只能作审计。零欠费、零条工单可以是合法结果，不能简单要求非空数组。领域 Agent/verify 已有最低结果契约；Single 尚有 Z2：失败 ToolExecution 被计入 accepted。默认 ask 还存在 Z1：未装配可信目标。这两项为当前实现缺陷，不能因规范写了要求而记为已实现。

资金结论由 conclusions.py 从 facts 构造；fund_check 是字段级机械核验，narrative.py 是辅助金额接地检查。mismatch 判失败/降级，unverified 不能当通过。CLI 默认展示遗漏可信字段为 Z3，仍待修复。细则见 [scoring-v3.3](../evaluation/scoring_v3.md)。

## 3. 当前 Graph 与状态合并

实际图定义在 orchestration/investigation.py，State 是 **InvestigationState**。orchestration/state.py 的 WorkflowState 是早期类型，不作为实际调查图 schema。

```text
START → plan → deterministic_answer ──────────→ verify
             → dispatch → run_subtask(Send) ─→ verify
verify → revise(有上限) → dispatch
verify → report → approval → END
```

- plan 由 RuleBasedPlanner 生成，每个子任务携带原问题及显式目标/筛选。
- results/failures/warnings 是追加通道；verify/report 按当前 run 过滤，并以 subtask 取当前结果。不是历史提案的 (subtask_id, attempt) map reducer 已经落地。
- expected_subtasks 由计划定义；缺少预期结果必须明确失败，不能按“实际收到了几条”假装齐全。
- conflicts/missing 每轮重新计算覆盖，防止补查后残留旧缺口。
- 默认 max_revisions=1，有限补查针对可恢复子任务；补查不代表可以绕过预算。
- report 在 approval 之前形成，审批状态由图和恢复结果携带；不能照旧示意图要求所有报告节点都放在审批之后。

## 4. 预算、重试与计量

| 项 | 当前行为与约束 |
|---|---|
| 全任务预算 | 同一任务注入共享 Budget/Trace；Agent 不得自建更宽松预算绕过限制 |
| 模型调用 | 每次物理请求有独立 model_call_id（含 request_seq）；重试/补查新请求不能复用旧 ID 隐去消耗 |
| token | None 不设上限；0 拒绝所有模型请求；已耗尽时拒绝新增预留。响应后计实际用量与 exceeded_tokens |
| 并发 token 边界 | 已在途请求的响应消耗不能事先精确预测；闸门阻止耗尽后的新请求，不承诺所有在途响应之和绝不超限 |
| 工具调用 | 按逻辑调用计一次；内部尝试数另记 attempts/Trace；参数/权限等静态拒绝不执行工具 |
| 重试 | BaseAgent 按配置有限重试；工具按 max_attempts 有限尝试；图最多有限补查；应共同受任务预算约束，不新增隐式重试层 |
| 时间 | deadline 与单次超时取较小值；任务延迟按墙钟测量，不能把并发节点耗时相加冒充延迟 |

Budget 当前不包含历史提案的 max_wall_clock_ms 字段；不能通过文档声称已实现。工具调用 ID 当前由执行器分配，不能承诺跨进程任意重放均会自动复用工具结果。单进程预算幂等与持久化恢复的保证应分别描述。

## 5. 标识符、恢复与审批

- request_id 是一次 Agent 请求；run_id 标识本次执行，Trace/审批/公开运行标识应对齐；trace_id 串联调用链。
- thread_id 用于持久 checkpoint；**一条 thread 只承载一次新调查**。换目标、换主体或用旧 thread 发新任务会被拒绝；恢复不等于新调查。
- checkpoint 使用 AsyncSqliteSaver，审批台账另存 SQLite；按现有恢复入口重新校验主体、权限、草案版本和状态。不宣称完整 dataset/config/graph/contract 哈希迁移校验全部实现。
- 审批要求物业→财务串行、两名不同主体、禁止自批、项目/权限/版本/过期校验、重复操作幂等。
- 当前暂停/恢复状态包含 pending_approval、pending_next_stage、approved 等；批准草案为 approved_draft_only，executed_side_effects=[]。历史规格的 approved_no_write 等用例术语不自动等同于公开 API 字段。
- 资料不足应报告 missing/partial、请求补充；不把它冒充动作审批，也不宣称已有独立 request_human_input 图节点。
- checkpoint 与台账只验证当前单机边界，不保证分布式“恰好一次”，也不提供真实业务副作用。

## 6. 验证状态

K1–K5 作为早期骨架问题已在后续 Runtime 任务收敛，不再列为本轮待修清单；历史缺陷记录保留。当前未关闭事项以 [Task 025](../reviews/2026-11-07_q1_q3_acceptance_review.md) 和 [当前基线](CURRENT_BASELINE.md) 为准。测试结果必须标注对应版本，文档整理不新增业务通过证据。
