# Agent Runtime 契约与 Graph 规格（P0 规格，尚未实现）

- **日期**：2026-11-03
- **状态**：规格草案（Spec only）— **本文件不含 Python 实现**
- **契约版本**：`contract_version = "2.0"`（目标）
- **依据**：[ADR-005](../decisions/ADR-005-agent-first-refocus.md)、[mvp_scope_v2.md](../product/mvp_scope_v2.md)
- **基线代码**：`backend/app/agents/base/`、`backend/app/config/`、`backend/app/llm/`、`backend/app/tools/`、`backend/app/orchestration/`
- **与历史文档关系**：概念设计见 [agent_architecture.md](./agent_architecture.md)；本文件是其**编码级细化**，冲突时以本文件为准并回写更新历史文档

> 阅读顺序建议：§1 兼容策略 → §2 请求/上下文/结果 → §3 证据与结论 → §9 State 与图 → §12 审批。

---

## 1. 与现有类型的兼容策略

### 1.1 现状（已核对源码，非汇报转述）

| 现有类型 | 位置 | 关键字段 |
|---|---|---|
| `AgentRequest` | `agents/base/contracts.py` | `request_id`, `task_id`, `capability`, `payload` |
| `AgentContext` | 同上 | `trace_id`, `tenant_id`, `user_id`, `permissions`, `deadline_at`, `metadata` |
| `AgentResult` | 同上 | `request_id`, `status`, `output`, `error`, `warnings`, `metadata` |
| `TaskStatus` | 同上 | `success` / `partial` / `failed` / `skipped` |
| `AgentDescriptor` | 同上 | `name`, `version`, `description`, `capabilities`, `enabled` |
| `AgentOutput` | 同上 | `data`, `warnings`, `token_usage` |
| `ErrorCode` | `agents/base/errors.py` | 枚举 + `RETRYABLE_CODES` |

### 1.2 兼容策略（受控增量迁移，不预建多套生命周期）

只保留**一条**迁移路径，不为占位类型预先设计"三阶段并存"的类型体系：

| 规则 | 说明 |
|---|---|
| 增量加字段 | 新增字段一律**可空 / 有默认值**，旧调用方无需改动 |
| 一次一个边界 | 一次任务只迁移一个边界：Tool/Service → Runtime → 最后 `AgentResult.output` |
| 版本号后置 | 仅当 3 个 Agent 与 57 项自检全部迁移完成，才在**同一次**任务里把 `contract_version` 升到 `"2.0"` 并删除过渡字段 |
| 不允许 | 同时维护 V1/V2 两套类型、用 `deprecated` 字段长期并存、为"以后可能兼容"提前写抽象层 |

**必须保留的接口与回归范围**：

| 必须保留 | 回归范围 |
|---|---|
| `BaseAgent.handle()` 签名与 `AgentResult` 既有字段 | `backend/tests/smoke_agent_contracts.py` 57 项 |
| `capability` 命名 `<domain>.<action>` | 三个 YAML 的 capabilities 校验 |
| `AgentRegistry` 按能力解析 | registry 自检分组 |
| `AgentContext` 现有字段语义（迁移解释见 §5.2） | 权限/租户拆分相关断言 |

每一步迁移都必须让 57 项自检保持通过；失败则回退该步，不得留下半迁移状态。

### 1.3 明确不做的兼容

- **不做** `AgentResult.output: dict[str, Any]` → 强类型的一次性替换。`BaseAgent` 已依赖 `dict` 产出；改为强类型会同时破坏 3 个 Agent 与 57 项自检。做法是**在 Service/Tool 边界强类型化**，`AgentResult.output` 最后再收敛。
- **不做** `capability` 格式变更。`<domain>.<action>` 正则已冻结。

---

## 2. 核心契约（V2）

### 2.1 `AgentRequestV2`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `request_id` | UUID | 是 | 单次调用唯一；重试**复用**同一 `request_id`，用于幂等去重 |
| `task_id` | str | 是 | 业务任务标识（一次用户请求一个） |
| `capability` | str | 是 | 匹配 `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` |
| `payload` | object | 是 | 该 capability 的参数对象，**必须经 JSON Schema 校验** |
| `contract_version` | str | 是 | `"2.0"` |

**禁止**：把权限、项目范围、金额真值塞进 `payload`。`payload` 只承载"问什么"，不承载"能看什么"。

### 2.2 `AgentContextV2`

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `trace_id` | str | 是 | 全链路追踪 ID，跨所有节点与日志 |
| `run_id` | UUID | 是 | 一次图执行；checkpoint 以它为主键之一 |
| `thread_id` | str | 是 | 会话/任务线程，可跨多次 `run_id`（见 §11） |
| `principal_id` | str | 是 | **权限主体**（谁在调用）。只能由可信入口注入 |
| `project_ids` | frozenset[str] | 是 | 允许访问的项目白名单 |
| `commercial_tenant_ids` | frozenset[str] \| None | 否 | **商业租户**范围；`None` 表示不按租户收窄 |
| `permissions` | frozenset[str] | 是 | 业务权限点，如 `lease.read`、`billing.read` |
| `deadline_at` | datetime(tz) | 否 | 上游给定截止时刻 |
| `budget` | `Budget` | 是 | 剩余预算（见 §10） |
| `attempt` | int ≥ 1 | 是 | 当前尝试序号，供归并去重 |
| `contract_version` | str | 是 | `"2.0"` |

### 2.3 `AgentResultV2`（增量，非替换）

在现有 `AgentResult` 基础上增加：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `subtask_id` | str | 是 | 对应 `InvestigationPlan` 中的步骤 ID |
| `attempt` | int ≥ 1 | 是 | 与 `context.attempt` 一致，用于归并 |
| `evidence` | `Evidence[]` | 否 | 本次产出的结构化证据 |
| `findings` | `Finding[]` | 否 | 结构化结论（必须引用 evidence） |
| `degraded` | bool | 否 | 是否降级产出（默认 `false`） |
| `partial_reason` | str \| None | 否 | `status=partial` 时必须说明缺什么 |

---

## 3. 证据与结论

### 3.1 `Evidence`（联合类型，二选一）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `evidence_id` | str | 是 | 稳定 ID，可被 `Finding` 引用 |
| `kind` | str | 是 | `"db_fact"` \| `"document_clause"` |
| `source_tool` | str | 是 | 产出它的工具名 |
| `tool_call_id` | str | 是 | **必填**：从工具执行 ID 追踪到数据来源 |
| `project_id` | str | 是 | 数据所属项目，用于权限复核 |
| `dataset_version` | str | 是 | **基线数据版本**；跨版本证据不得混用 |
| `as_of_date` | date | 是 | **基线数据基准日**（业务日期，不是采集时刻） |
| `collected_at` | datetime(tz) | 是 | 采集时刻（事件时间，非业务日期） |
| `synthetic` | bool | 是 | 数据是否合成 |
| `content_hash` | str | 是 | 规范化内容摘要（用于同 ID 幂等合并，见 §9.2） |

**`db_fact` 专有字段**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `entity` | str | 是 | 表/实体名，如 `invoice` |
| `record_id` | str | 是 | **数据记录主键** |
| `record_version` | str | 是 | 行版本/更新时间戳；用于判断证据是否过期 |
| `fields` | object | 是 | 结论实际依赖的字段子集（不是整行） |

**`document_clause` 专有字段**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `document_id` | str | 是 | 文档 ID |
| `document_version` | int | 是 | **版本号**，必须与文档库一致 |
| `page` | int | 是 | **页码**（模拟语料中为约定定位，见 §3.4） |
| `clause_id` | str | 是 | 条款编号，如 `5.2` |
| `excerpt` | str | 是 | **原文摘录**，不得改写、不得翻译后冒充原文 |
| `checksum` | str | 是 | 文档内容摘要，用于检测版本漂移 |
| `document_status` | str | 是 | `signed` / `draft_unsigned` / `superseded` |

### 3.2 `Finding`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `finding_id` | str | 是 | 稳定 ID |
| `statement` | str | 是 | 一句话结论，**不含未引用的断言** |
| `evidence_ids` | str[] | 是 | 至少 1 个；为空则该结论不能进入报告 |
| `derivation` | str | 是 | `direct`（证据直述）/ `computed`（Decimal 计算）/ `inferred`（跨证据推理） |
| `confidence_basis` | str | 是 | `explicit` / `derived` / `conflicting` / `insufficient` |
| `computation` | `Computation` \| null | 条件必填 | `derivation = computed` 时**必须**提供，其余为 `null` |

**`Computation`（完整类型，不是"关键字段"占位）**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `computation_id` | str | 是 | 稳定 ID，可被多个 Finding 复用 |
| `formula` | str | 是 | 人类可读表达式，如 `(132.3000 - 126.0000) * 120.0000` |
| `inputs` | `ComputationInput[]` | 是 | 每个输入值必须可追溯到 `evidence_id` 或常量 |
| `operation` | str | 是 | `subtract` / `multiply` / `sum` / `divide` / `round`（枚举，禁止自由文本） |
| `rounding` | str | 是 | `ROUND_HALF_UP`（P0 唯一允许值） |
| `scale` | int | 是 | 结果小数位；金额为 2，单价为 4 |
| `result` | `Money` | 是 | `{amount: string, currency: "CNY"}`，由确定性代码产生 |
| `computed_at` | datetime(tz) | 是 | 计算时刻（事件时间） |

`ComputationInput`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | str | 是 | 表达式中的变量名 |
| `value` | str | 是 | 十进制字符串（禁止 float） |
| `source` | str | 是 | `evidence` \| `constant` |
| `evidence_id` | str \| null | 条件必填 | `source=evidence` 时必填，且必须存在于本次 `evidence` map |

**硬规则**：

1. `derivation = computed` 但缺 `computation` → 该 Finding **作废**，不得进入报告。
2. `computation.result` 必须与 `statement` 中的金额完全一致（`Decimal` 比较）。
3. 计算由确定性代码执行；模型只允许描述，不允许生成 `result`。

### 3.3 引用验证分两级（关键设计）

| 级别 | 名称 | 检查什么 | 失败后果 |
|---|---|---|---|
| L1 | `reference_exists` | 引用的 `document_id + version + page + clause_id` 在文档库中真实存在 | 该证据作废；报告不得使用 |
| L2 | `supports_claim` | 摘录文本是否**支持**该结论 | 结论降级为 `conflicting` 或 `insufficient`；需补查或转人工 |

```text
CitationCheck {
  evidence_id: str
  claim_id: str
  reference_exists: bool
  supports_claim: "supports" | "partial" | "contradicts" | "unrelated"
  method: "exact_span_match" | "structured_field_match" | "human_review"
  checked_at: datetime
}
```

**为什么必须分开**：引用存在 ≠ 引用支持结论。最常见的事故是"文件确实有、页码确实对，但那段话说的是别的意思"。只做 L1 会让报告看起来有据可查，实质是伪引用。

### 3.4 关于 `page` 的诚实说明

P0 的文档片段是**模拟检索语料**（`synthetic: true`），不是真实 PDF 解析结果。因此：

- `page` 表示**约定的测试来源定位**，不代表已验证 PDF 分页。
- 在未实现真实 RAG 之前，任何文档不得声称"已通过 PDF 页码校验"。
- 评测中 L1 只校验"该定位在 fixture 中存在"，不校验 PDF 物理页码。

### 3.5 `ToolResult`（含证据输出）

所有工具统一返回该结构，**证据由工具产出并随结果返回**，Agent 不得自行拼装证据。

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `tool_call_id` | str | 是 | 稳定调用 ID（见 §11.1），失败调用也必须有 |
| `idempotency_key` | str | 是 | 默认 = `tool_name + 规范化参数哈希`；同键重放必须复用结果 |
| `tool_name` | str | 是 | 须在调用方 `allowed_tools` 内 |
| `status` | str | 是 | `ok` / `error` / `timeout` / `denied` |
| `data` | object \| null | 否 | `denied` 时必须为 `null` |
| `evidence` | `Evidence[]` | 否 | `status=ok` 时产出；`error`/`timeout`/`denied` 必须为空数组 |
| `error_code` | str \| null | 否 | `status=ok` 时为 `null` |
| `attempt` | int ≥ 1 | 是 | 同一次逻辑调用的第几次尝试 |
| `duration_ms` | int ≥ 0 | 是 | 单调时钟测量，仅用于统计，不参与预算加总 |
| `started_at` / `finished_at` | datetime(tz) | 是 | 事件时间 |

**硬规则**：`status != ok` 时 `evidence` 必须为空；任何金额都必须出现在 `data` 或 `evidence.fields` 中，禁止只在自然语言里出现。

### 3.6 `InvestigationPlan`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `plan_id` | str | 是 | 稳定 ID；同一任务内唯一 |
| `revision` | int ≥ 0 | 是 | 0 为初版；补查后 +1 |
| `max_revisions` | int | 是 | **硬上限 1**；`revision > max_revisions` 视为非法 |
| `steps` | `SubTask[]` | 是 | `subtask_id` 唯一且非空 |
| `rationale` | str | 是 | 为什么这样拆；不得作为权限或金额依据 |
| `created_by` | str | 是 | 固定 `"planner"`（见 §9.1 唯一写入者） |
| `base_plan_id` | str \| null | 否 | `revision > 0` 时指向被修订的上一版 |

`SubTask`：`subtask_id`、`capability`、`depends_on[]`（必须指向**本计划内**已存在的 `subtask_id`）、`expected_evidence_kinds[]`、`optional`(bool)。

### 3.7 `VerificationResult`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `verdict` | str | 是 | `supported` / `conflicting` / `insufficient` |
| `claim_checks` | `ClaimCheck[]` | 是 | 每条关键结论一条，含 `claim_id`、`verdict`、`reason` |
| `citation_checks` | `CitationCheck[]` | 是 | 见 §3.3；L1 失败的证据必须标 `reference_exists=false` |
| `conflicts` | `Conflict[]` | 否 | `verdict=conflicting` 时**非空**，且每项含 `left_evidence_id` 与 `right_evidence_id` |
| `missing` | `str[]` | 否 | 缺失的文档/字段 ID；`verdict=insufficient` 时**非空** |
| `next_action` | str | 是 | `finish` / `revise` / `human` |
| `revision_count` | int ≥ 0 | 是 | 与 State 的 `revision_count` 一致 |

**硬规则**：`conflicting` 不得只列一方证据；`insufficient` 不得 `missing=[]`。

### 3.8 `ApprovalDraft`（只描述，不执行）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `draft_id` | str | 是 | 稳定 ID；改版时**不变** |
| `draft_version` | int ≥ 1 | 是 | 每次实质修改 +1 |
| `action_type` | str | 是 | `rent_reduction_draft` 等；P0 只允许草案类动作 |
| `project_id` | str | 是 | 必须 ∈ `context.project_ids` |
| `target` | object | 是 | 如 `{invoice_id, invoice_item_id, lease_id}` |
| `proposed_changes` | `ProposedChange[]` | 是 | 只见金额/科目/期间，不含执行结果 |
| `amount` / `currency` | string / str | 是 | 十进制字符串 + 币种（`Money`） |
| `evidence_ids` | str[] | 是 | 至少 1 个，必须存在于本次证据集 |
| `required_roles` | str[] | 是 | 角色 ID，按 `seq` 串行 |
| `generated_at` / `expires_at` | datetime(tz) | 是 | `expires_at > generated_at` |
| `status` | str | 是 | `draft` / `awaiting_approval` / `approved` / `denied` / `expired` / `invalidated` |
| `approval_ids` | str[] | 否 | 已接受的批准事件 ID（去重后） |

### 3.9 `WorkflowResult` 与状态枚举

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `run_id` / `thread_id` / `trace_id` | str | 是 | 见 §11.1 |
| `status` | `WorkflowStatus` | 是 | 见下表 |
| `findings` | `Finding[]` | 是 | 只含通过 L1 的结论 |
| `evidence` | `Evidence[]` | 是 | 去重后的最终证据集 |
| `conflicts` | `Conflict[]` | 是 | 无冲突时为空数组，**不得省略字段** |
| `missing_info` | `MissingInfo[]` | 是 | 含 `id`、`kind`、`reason`、`required_from`（`human` / `tool`） |
| `approval_draft` | `ApprovalDraft \| null` | 否 | 无动作时 `null` |
| `approval` | `ApprovalOutcome \| null` | 否 | 审批状态、已满足/待满足角色、拒绝原因、过期时刻 |
| `report` | str | 是 | 面向用户的文本；金额必须与 `findings` 一致 |
| `budget_used` | `BudgetUsage` | 是 | 见 §10 |
| `trace_summary` | object | 是 | 调用数、重放次数、补查次数、降级原因 |

`WorkflowStatus`（**唯一枚举**，其他文档不得自造同义状态）：

| 状态 | 含义 | 是否终态 |
|---|---|---|
| `running` | 执行中 | 否 |
| `awaiting_human_input` | **缺少事实**，需人补充资料（不是审批） | 否（可恢复） |
| `awaiting_approval` | 存在待批**动作草案** | 否（可恢复） |
| `approved_no_write` | 审批通过，但 P0 无写接口，未改动业务数据 | 是 |
| `rejected` | 审批被拒绝 | 是 |
| `rejected_version_mismatch` | 批准版本与当前草案版本不一致 | 是 |
| `rejected_expired` | 审批在草案过期后进行 | 是 |
| `idempotent_noop` | 重放已生效的决议，未产生新状态变化 | 是（重放专用） |
| `partial` | 部分完成，`partial_reason` 必填 | 是 |
| `failed` | 失败，`error_code` 必填 | 是 |
| `reported` | 正常完成报告（无待批动作） | 是 |

**关键约束**：

1. `awaiting_human_input ≠ awaiting_approval`：前者缺**事实**，后者待批**动作**。没有 `approval_draft` 时**不得**进入 `awaiting_approval`，也不得索取减免审批。
2. `approved_no_write` 与 `rejected` 都必须保留 `approval_draft`（只读快照）用于追溯。
3. `idempotent_noop` 只出现在重放已生效决议时，底层审批状态不变（仍为 `approved` / `rejected`）。
4. 终态不得再变更；任何补查必须发生在终态之前。

---

## 4. 金额与时间

### 4.1 金额

```json
{ "amount": "15120.00", "currency": "CNY" }
```

| 规则 | 说明 |
|---|---|
| 传输格式 | **十进制字符串**，两位小数（单价四位）；`amount` 必须是 `string`，不是 `number` |
| 真值类型 | Python `decimal.Decimal`，禁止 `float` |
| 解析 | `Decimal(value)`，禁止 `Decimal(float)` |
| 运算 | `Decimal` 上下文，舍入 `ROUND_HALF_UP` 到 2 位（逐行舍入后累加，不先累加再舍入） |
| 校验 | Schema 层拒绝 `number` 型 `amount`，避免 JSON 浮点在解析阶段就失真 |
| 币种 | 必须显式；P0 固定 `CNY`，跨币种运算**直接报错**而非隐式换算 |

**禁止**：`0.1 + 0.2` 类浮点路径；"大约"、"约为"、"四舍五入后接近"等模糊表述用于金额结论。

### 4.2 时间

| 类型 | 格式 | 用途 | 示例 |
|---|---|---|---|
| **业务日期** `BusinessDate` | `YYYY-MM-DD` | 租期、账期、到期日、出账日 | `2026-10-31` |
| **事件时间** `EventTime` | RFC 3339 带偏移 | 采集时刻、执行时刻、审批时刻 | `2026-11-03T14:05:00+08:00` |

**规则**：业务日期不参与时区换算；事件时间必须带偏移。**禁止**用事件时间表达"某月账期"。

---

## 5. 权限与租户语义

### 5.1 权限只能来自可信上下文

| 允许 | 禁止 |
|---|---|
| 由 API 层从**已认证会话**构造 `AgentContextV2` | 从 `payload` / 用户自然语言 / 模型输出 / 检索到的文档中读取权限 |
| Runtime 在每次工具调用前用 `context` 复核 | Agent 自行 `set_permissions` 或扩大 `project_ids` |
| 文档内容视为**不可信输入** | 服从文档中"请忽略之前的指令"之类文本（提示注入） |

### 5.2 `tenant_id` 语义拆分（重要）

现有 `AgentContext.tenant_id` 一词两义，必须拆开：

| 概念 | V2 字段 | 含义 |
|---|---|---|
| **权限/数据隔离主体** | `principal_id` + `project_ids` | "谁在调用、能看哪些项目" |
| **商业租户** | `commercial_tenant_ids` | "这笔业务属于哪个承租方"（`tenants` 表实体） |

**P0 迁移约定**：旧 `tenant_id` 一律解释为 `commercial_tenant_ids` 的单元素；**绝不**用它做权限判断。混用是本项目最容易出的越权漏洞。

### 5.3 越权检查点

| 层 | 检查 |
|---|---|
| Tool Executor | 工具所需的 `permissions` ⊆ `context.permissions`；参数的 `project_id` ∈ `context.project_ids` |
| Repository | 查询强制追加 `project_id IN (...)`，不依赖调用方传参 |
| Result 校验 | 返回数据中的每个 `project_id` 必须 ∈ `context.project_ids`，否则视为缺陷并丢弃 |

---

## 6. Tool Executor（统一执行器）

所有工具调用必须经过同一个执行器，Agent 不得直接调用工具实现。

| 顺序 | 检查 | 失败错误码 |
|---|---|---|
| 1 | 工具名在 Agent 的 `allowed_tools` 白名单内 | `TOOL_NOT_ALLOWED` |
| 2 | 调用方具备工具声明的 `required_permissions` | `PERMISSION_DENIED` |
| 3 | `payload` 通过该工具的 JSON Schema 校验 | `INVALID_TOOL_ARGUMENTS` |
| 4 | 剩余 deadline 与预算足够 | `DEADLINE_EXCEEDED` / `BUDGET_EXHAUSTED` |
| 5 | 执行（受超时约束，超时值 = `min(工具超时, 剩余 deadline)`） | `TOOL_TIMEOUT` |
| 6 | 结果结构校验 + 项目范围校验 | `INVALID_TOOL_RESULT` / `PERMISSION_DENIED` |

**工具形态限制（安全边界）**：

| 允许 | 禁止 |
|---|---|
| 参数化的业务查询（按 `lease_id`、`period` 等具名参数） | 任意 SQL 工具、`sql` 字符串参数 |
| 只读查询；写操作仅生成草案 | 任意代码执行、`eval`、shell |
| 固定返回结构（Pydantic DTO） | 返回 ORM 实例或原始连接 |

---

## 7. Model Adapter

| 要求 | 说明 |
|---|---|
| 复用现有层 | 扩展现有 `app/llm/adapter.py`（已含 provider 白名单、参数裁剪、密钥仅从环境变量读取），**不另造客户端** |
| 可注入 | 通过构造参数注入 `ModelAdapterProtocol`；测试注入 `FakeModelAdapter`（确定性输出，零网络） |
| 真实 Provider | `DeepSeekAdapter` 保留，凭 `DEEPSEEK_API_KEY` |
| 参数裁剪 | 继续由 adapter 决定实际下发的参数（`temperature` 为 `None` 时不下发） |
| 成本计量 | adapter 返回 `TokenUsage`；Runtime 换算预算消耗 |
| 缺失密钥 | 抛 `MissingApiKeyError`，**不得**回显密钥值 |

**P0 必须能全程离线跑通**：8 个评测样例至少要有一种模式用 `FakeModelAdapter` 跑完，用于 CI 与回归。

---

## 8. Registry 与 Graph Builder

### 8.1 按能力工作

| 组件 | 输入 | 输出 | 禁止 |
|---|---|---|---|
| `AgentRegistry` | Agent 实例 | 能力 → Agent 映射 | 接受字符串模块路径 |
| `GraphBuilder` | Registry + 图配置 | 可编译的图 | import 具体 Agent 类 |

图节点通过 `capability` 解析到 Agent，**不通过类名**。这样替换实现时图定义不变。

### 8.2 增删改 Agent 的影响面

| 操作 | 必须改 | 不必改 |
|---|---|---|
| 新增 Agent | ① `agents/<name>/agent.py` + `prompts/`；② `config/agents/<name>.yaml`；③ `factory.AGENT_IMPLEMENTATIONS` 一行；④ 该 Agent 的测试 | 其他 Agent、Registry、GraphBuilder、其他 YAML |
| 禁用 Agent | 仅 YAML：`enabled: false` | 任何代码 |
| 替换实现 | `factory.AGENT_IMPLEMENTATIONS` 指向新类（`name`/`version` 语义不变） | 图定义、其他 Agent、配置 |
| 换模型 / 改 Prompt / 调工具 | 仅 YAML 或 Prompt 文件 | 任何代码 |

### 8.3 明确不做

不做运行时热插拔、不做插件市场、不做 Agent 动态发现。变更 = 改配置 + 重启 + 跑回归。

---

## 9. State 与图规格

### 9.1 State 字段与**唯一写入者**

每个字段只有一个写入节点，其他节点只读。并发节点一律通过返回值归并，不得直接改共享 dict。

| 字段 | 类型 | 唯一写入者 | 归并方式 | 说明 |
|---|---|---|---|---|
| `thread_id` / `run_id` / `trace_id` | str | `init` | 单一写入 | 初始化后全图只读 |
| `user_request` | object | `init` | 单一写入 | 原始请求快照（只读） |
| `context_snapshot` | object | `init` | 单一写入 | 权限与预算快照（**不可由模型修改**） |
| `plan` | `InvestigationPlan` | **仅 `planner`** | 单一写入 | `revise` 不得追加子任务；只能发出 `RevisionRequest` 回到 `planner`（见 §9.4） |
| `subtask_attempts` | `map[(subtask_id, attempt), AttemptRecord]` | `run_subtask`（并发） | **按复合键归并** | 见 §9.2 |
| `evidence` | `map[evidence_id, EvidenceRecord]` | `run_subtask` / 工具结果归并器 | **按键幂等合并** | 同 ID 同内容幂等；同 ID 不同内容**报冲突**，禁止按到达顺序覆盖 |
| `findings` | `map[finding_id, Finding]` | `run_subtask` | 按键归并 | 同 ID 冲突处理同 `evidence` |
| `verification` | `VerificationResult` | `verifier` | 单一写入 | 补查后**整体替换**，保留上一版于 `verification_history` |
| `approval` | `ApprovalState` | `approval` 节点 | 单一写入 | 含 `draft`、`decisions[]`、`state` |
| `budget_used` | `BudgetUsage` | `budget_ledger` | **按调用 ID 去重后累加** | 见 §10.2，禁止裸 `+` |
| `errors` | `map[subtask_id, ToolError[]]` | `run_subtask` | 按键归并 | |
| `revision_count` | int | `planner` | 单一写入 | 与 `plan.revision` 同步，硬上限 1 |
| `clock` | `{started_monotonic_ms, ended_monotonic_ms}` | `init` / 终态节点 | 单一写入 | 任务墙钟，见 §10.3 |

### 9.2 归并：稳定 ID、幂等合并、顺序无关

**归并键必须是稳定标识，不是到达顺序**：

| 对象 | 稳定键 | 重放判定 |
|---|---|---|
| 子任务结果 | `(subtask_id, attempt)` | 同键重复到达即重放，取首次，记 `replayed=true` |
| 工具调用 | `tool_call_id`（或 `idempotency_key`） | 同键复用首次结果，不重复计预算 |
| 模型调用 | `model_call_id` | 同上 |
| 审批/业务事件 | `event_id` | 同 `event_id` 且内容相同 → 幂等；内容不同 → `EVENT_ID_CONFLICT` |
| 证据 | `evidence_id` | 同 ID 且 `content_hash` 相同 → 幂等；不同 → `EVIDENCE_CONFLICT` |

**Evidence 合并规则（禁止"后写覆盖"）**：

```text
on_evidence(e):
  if e.evidence_id not in map:            map[e.evidence_id] = {record: e, seen: 1}
  elif map[e.evidence_id].record.content_hash == e.content_hash:
                                          map[e.evidence_id].seen += 1      # 幂等，不写新值
  else:                                   raise EVIDENCE_CONFLICT(e.evidence_id,
                                            existing_hash, incoming_hash)   # 不覆盖
```

冲突后的处理只有两条出口：由上游产生**显式新版本**（`evidence_id` 不变但 `record_version` 提升，需人工/Verifier 确认），或将该结论降级为 `conflicting` 并进入人工。**不存在**"较晚到达者胜出"。

**交换顺序示例（同一事件多重集，两种到达顺序，结果必须相同）**：

| 步骤 | 顺序 X | 顺序 Y |
|---|---|---|
| 1 | `inv_2026_10` (h=aaa) 到达 | `inv_2026_10` (h=aaa) 到达 |
| 2 | `inv_2026_09` (h=bbb) 到达 | 重放 `inv_2026_10` (h=aaa) |
| 3 | 重放 `inv_2026_10` (h=aaa) | `inv_2026_09` (h=bbb) 到达 |
| 结果 | map `{inv_2026_10: aaa, inv_2026_09: bbb}`；`seen` `{10: 2, 09: 1}` | **完全相同**（map 与 `seen` 都一致） |

**冲突示例**：同 `evidence_id=inv_2026_10`，先到 `h=aaa`，后到 `h=zzz`（金额不同）。无论先后，结果都是 `EVIDENCE_CONFLICT`，报告必须列出两个版本，不得静默采用任一。

**重放不重复计账示例**：

| 输入 | 处理 | 预算 |
|---|---|---|
| `tool_call_id=tc_01` 成功，`model_calls=1` | 记账 1 次 | `tool_calls=1` |
| 同 `tc_01` 再次到达（内容相同） | 复用结果，`replayed=true` | **不变**（仍 1） |
| 同 `tc_01` 再次到达但 `data` 不同 | 拒绝，`IDEMPOTENCY_CONFLICT` | 不变 |

### 9.3 节点与边

| 节点 | 输入 | 输出 |
|---|---|---|
| `parse_intent` | `user_request` | `intent`, `required_capabilities[]` |
| `plan` | `intent`、可选 `RevisionRequest` | `plan`（`revision` 递增） |
| `dispatch`（扇出） | `plan` | 触发各子任务节点 |
| `run_subtask` | 单步 `SubTask` | `subtask_attempts` / `evidence` / `findings` / `errors` |
| `join`（合流） | 本轮全部预期子任务终态 | 汇总 |
| `verify` | 汇总结果 | `verification` |
| `revise` | `verification.next_action = revise` | **只产出 `RevisionRequest`**，回到 `plan`；不直接改 `plan` |
| `request_human_input` | 缺**事实**（`missing_info.required_from = human`） | `status=awaiting_human_input`，**不产生审批** |
| `approval` | 存在待批**动作草案** | `approval` 状态机（§12） |
| `report` | 全部状态（含审批结果） | `WorkflowResult`（含 `approval` 结果与拒绝原因） |

**前段条件边**（`parse_intent` 之后）：

| 起点 | 条件 | 去向 |
|---|---|---|
| `parse_intent` | 任务可由确定性工具单步回答（如 C01/C07） | 直达 `run_subtask` → `report`（**不扇出**） |
| `parse_intent` | 需要多能力 | `plan` |
| `parse_intent` | 请求超出 `context.project_ids` | 直接拒绝（`denied`），不进入任何工具 |

### 9.4 穷尽转移表（6 种出口，无悬挂状态）

`verify` 之后的所有组合都必须有明确去向。`max_revisions = 1`（P0 固定）。

| # | verdict | `revision_count` | 是否存在动作草案 | 去向 | 终态/中间态 |
|---|---|---|---|---|---|
| 1 | `supported` | 任意 | 否 | `report` | `reported` |
| 2 | `supported` | 任意 | 是 | `approval` | `approved_no_write` / `rejected` / `rejected_expired` / `rejected_version_mismatch` |
| 3 | `conflicting` | `< max_revisions` | 否 | `revise` → `plan` | 继续（`running`） |
| 4 | `conflicting` | `< max_revisions` | 是 | `revise` → `plan`，重验后再走 #2 | 继续（`running`） |
| 5 | `conflicting` | `>= max_revisions` | 否 | `report`（并列冲突，`requires_human_decision`） | `reported`（rubric 要求不选边） |
| 6 | `conflicting` | `>= max_revisions` | 是 | `report` 保留冲突 + `approval` 暂停 | `awaiting_approval`（人决定是否继续） |
| 7 | `insufficient` 且**可补查**（`missing.required_from = tool` 或存在未试工具） | `< max_revisions` | 否 | `revise` → `plan` | 继续（`running`） |
| 8 | `insufficient` 且**可补查** | `< max_revisions` | 是 | `revise` → `plan` | 继续（`running`） |
| 9 | `insufficient` 且**需人补事实**（`required_from = human`） | 任意 | 否 | `request_human_input` | `awaiting_human_input` |
| 10 | `insufficient` 且需人补事实 | 任意 | 是 | `request_human_input`（**先补事实，不批动作**） | `awaiting_human_input` |
| 11 | `insufficient` 且**补查上限已到** | `>= max_revisions` | 否 | `report` 列缺失并停止判断 | `partial` |
| 12 | `insufficient` 且补查上限已到 | `>= max_revisions` | 是 | `report` 列缺失 + **禁止**索取减免审批 | `partial` |

**判定优先级（防止同一输入有两种去向）**：

1. 先判 `insufficient` 是否**需人补事实** → 是则 `awaiting_human_input`（#9/#10），与审批无关。
2. 再判是否还能补查（`revision_count < max_revisions` 且存在可行动作）→ `revise`（#3/#4/#7/#8）。
3. 否则进入 `report`（#1/#5/#11），只有**存在动作草案**时才允许追加 `approval`（#2/#6）。

**强制约束**：

- 没有 `approval_draft` 时**不得**进入 `approval` 节点；"缺资料"不能伪装成"待审批"。
- `approval` 只在图的后段出现；`report` 必须在 `approval` 之后执行（#2），以便把审批状态、拒绝原因写进 `WorkflowResult.approval`。
- `revise` 永远回到 `planner` 写入新 `plan`；`run_subtask` 不得追加子任务。

### 9.5 合流条件（易错点）

`join` **必须等待本轮计划中的所有预期子任务进入终态**（`success` / `partial` / `failed` / `skipped` / `cancelled`），而不是"等到任意结果"。

| 规则 | 说明 |
|---|---|
| 预期集合 | 由本轮 `plan.steps` 的 `subtask_id` 集合决定，**不是**由已到达的消息决定 |
| 缺一处理 | 未到达的子任务按 `failed` + `error_code=MISSING_SUBTASK_RESULT` 计入，不得静默跳过 |
| 禁止 | 用"超时后有几条算几条"作为合流条件（会产生随机的部分报告） |

### 9.6 重试与补查上限

| 层 | 上限 | 归属 |
|---|---|---|
| 单节点执行 | 1 次尝试（不做同层内重试） | 由 Graph 的 retry policy 决定，默认关闭 |
| 工具调用 | 最多 `tool_max_attempts = 2` | Tool Executor |
| 补查轮次 | `max_revisions = 1` | Graph（`revision_count`） |
| 总尝试 | `task_max_attempts = 1`（用户重发视为新 `request_id`） | Runtime |

**原则**：重试只能有一个归属层，见 §10。

---

## 10. 预算与重试归属

### 10.1 预算账本：原子预留与结算

```text
Budget {
  max_model_calls: int
  max_tool_calls: int
  max_total_tokens: int
  max_wall_clock_ms: int        # 任务墙钟上限（单调时钟）
}

BudgetUsage {
  model_calls: int
  tool_calls: int
  total_tokens: int
  wall_clock_ms: int            # 实际经过时间，见 §10.3（不是节点之和）
}
```

`Budget` 由 Runtime 独占持有，节点不能放大，也不能直接写 `BudgetUsage`。调用必须走两阶段：

| 阶段 | 操作 | 语义 |
|---|---|---|
| 预留 | `reserve(call_id, kind, estimated)` | 原子地检查"已用 + 预留 + 本次 ≤ 上限"并记入 `reservations[call_id]`；不足则返回 `BUDGET_EXHAUSTED`，**不扣减** |
| 结算 | `settle(call_id, actual)` | 用实际消耗替换该 `call_id` 的预留；释放差额；`call_id` 已结算则幂等返回 |
| 取消 | `release(call_id)` | 调用未发生（如参数校验失败）时释放预留 |

**并发安全**：`reserve` 必须是原子的（单写者 + 锁 / CAS）。两个并发节点不得同时通过 `max_tool_calls` 的检查；预留是"先记账再执行"，因此**不会**出现"都已执行、才发现超额"的超发。

**重放安全**：`call_id` 是幂等键。同一 `call_id` 重复 `reserve` 返回既有预留，不重复计数；重复 `settle` 返回首次结果。`reservations` 与 `settled` 都以 `call_id` 为键，**不是**列表。

> 反例（必须避免）：`budget_used += cost` 直接相加。重放节点会把同一次调用计两次，导致"预算耗尽"随重放次数漂移。

### 10.2 记账去重（稳定调用 ID）

| 调用类型 | 稳定 ID | 生成规则 | 重放行为 |
|---|---|---|---|
| 工具 | `tool_call_id` | `hash(run_id, subtask_id, attempt, tool_name, canonical_args)` 或执行器显式分配 | 同 ID 复用结果，预算不变 |
| 模型 | `model_call_id` | `hash(run_id, node, attempt, prompt_hash, params_hash)` | 同上 |
| 审批/业务事件 | `event_id` | 由事件源提供（见 §12） | 同 ID 同内容幂等；同 ID 不同内容报冲突 |

**禁止**用时间戳、随机数或自增列表下标作为幂等键——它们在重放时会变。

### 10.3 墙钟口径（不与并发节点相加）

- **任务墙钟** = `ended_monotonic_ms - started_monotonic_ms`，由启动节点与终态节点各读一次**单调时钟**（`time.monotonic_ns()` 类），与系统时间调整无关。
- 并发子任务的耗时可另存 `node_durations[]`，用于分析并行收益，**不得**把它们求和当成墙钟。
- `budget_used.wall_clock_ms` 只取任务墙钟；`sum(node_durations)` 只出现在 `trace_summary` 里并明确标注"节点耗时合计 ≠ 墙钟"。

### 10.4 重试归属（防止相乘）

| 层 | 是否重试 | 理由 |
|---|---|---|
| Runtime / 图 | **否**（除非用户重发） | 最外层重试会把内层重试整轮重放，成本指数放大 |
| 节点 | 否（P0 关闭） | 节点失败交由 Verifier 判定是否补查 |
| 工具 | **是**，上限 2 次 | 唯一有明确瞬时故障语义的层（网络、超时）；每次尝试共用一个 `tool_call_id`，`attempt` 递增 |
| 模型 | 否（P0） | 模型错误通过上层降级处理，不做静默重试 |

> 反例（必须避免）：图重试 2 × 节点重试 2 × 工具重试 2 = 8 倍调用，且每层都以为自己在"温和重试"。

### 10.5 预算耗尽行为

| 场景 | 行为 |
|---|---|
| 模型预算耗尽 | 停止新增 LLM 调用，已获得的结构化结论仍可输出，标 `degraded=true` |
| 工具预算耗尽 | 对应子任务 `failed` + `BUDGET_EXHAUSTED`，进入 `insufficient` |
| 墙钟耗尽 | 中断，`status=partial`，`partial_reason` 写明未完成项 |

---

## 11. 标识符与持久恢复

### 11.1 各类标识符的区别

| ID | 生命周期 | 用途 | 是否可重复 |
|---|---|---|---|
| `request_id` | 单次调用 | 幂等与去重键 | 重试**复用** |
| `run_id` | 一次图执行 | checkpoint 主键、Trace 根 | 每次执行新值 |
| `thread_id` | 一个任务线程，可跨多次 run | 会话/任务归属、恢复入口 | 同一任务复用 |
| `trace_id` | 一条完整调用链 | 日志与证据串联 | 每个 run 一个，子调用继承 |
| `tool_call_id` | 一次**逻辑**工具调用（跨多次 attempt） | 工具幂等、预算去重（§10.2） | 重试**复用**，`attempt` 递增 |
| `event_id` | 一条审批/业务事件 | 事件幂等、审批去重（§12） | 同一事件**复用**；内容不同则冲突 |

**禁止**用时间戳、随机 ID 或列表下标做幂等键：重放时它们必然变化，去重失效。

### 11.2 持久化必须记录的内容

| 类别 | 必存 | 说明 |
|---|---|---|
| 数据 | `dataset_version`, `as_of_date` | 恢复时必须校验数据未被替换 |
| 配置 | `config_version`（Agent YAML 内容哈希） | 配置变了必须提示重跑或确认 |
| 契约 | `contract_version` | 契约不兼容时禁止静默恢复 |
| 图 | `graph_version`（图定义哈希） | 图结构变更后旧 checkpoint 不可继续 |
| 审批 | `draft_id + draft_version` | 见 §11.4 |

### 11.3 恢复流程

```text
resume(thread_id, resume_event_id?)
 → 读取 checkpoint（校验 dataset/config/contract/graph 版本一致）
 → 重新构造 AgentContextV2（重新授权：principal、project_ids、permissions、剩余预算）
 → 若上下文与 checkpoint 快照不一致 → 拒绝恢复并要求人工确认
 → 进入 checkpoint 记录的**待执行节点**（不保证"从下一节点"开始）
 → 该节点按 §9.2 归并键重放：已有结果则复用，不重复计预算、不重复产出证据
```

**必须重新授权**：checkpoint 里的权限是**历史快照**，不能作为当前授权依据（用户可能已被撤权）。

**不承诺"永远只从下一节点继续"**：LangGraph 的 checkpoint 是节点级快照，恢复时最后完成的节点**可能被重放**（写 checkpoint 前崩溃、或外部事件重投递）。因此：

| 保证 | 手段 |
|---|---|
| 结果幂等 | 归并键 `(subtask_id, attempt)` + `tool_call_id` / `event_id` 去重（§9.2、§10.2） |
| 不重复计预算 | `reserve/settle` 以 `call_id` 为键，重放命中既有记录 |
| 不重复产出证据 | `evidence_id` + `content_hash` 幂等合并 |
| 不重复审批 | `event_id` 幂等；同 ID 不同内容报冲突 |
| 可解释 | `trace_summary.replayed_nodes[]` 记录被重放的节点与次数 |

**恢复的终态**：重放已生效的审批决议时返回 `status=idempotent_noop`（§3.9），而不是再执行一次。

### 11.4 审批与草案版本绑定

- 审批对象是 `ApprovalDraft` 的**一个具体版本**。
- 恢复时必须校验 `draft_version` 与待执行版本一致；草案被修改后旧审批**自动失效**。
- 重启/恢复后的批准**不得**作用于更新版本的草案。

### 11.5 恰好一次的诚实边界

`checkpoint` **不承诺外部副作用恰好一次**。P0 的应对：

| 事实 | 应对 |
|---|---|
| 恢复可能重放节点 | 归并键 `(subtask_id, attempt)` 保证结果幂等 |
| 未来若有真实写操作 | 必须带业务幂等键（如 `draft_id + draft_version`），由下游去重 |
| P0 无真实写接口 | 因此不引入分布式事务，也不宣称"恰好一次" |

---

## 12. 审批节点

审批是**独立 Graph 节点**，不是通用异常兜底分支，也不是"缺资料"的替代出口。

### 12.1 两类人工介入必须分开

| 场景 | 缺什么 | 去向 | 是否产生审批 |
|---|---|---|---|
| 缺**事实**（附件未电子化、字段缺失、权限不足需换人） | 信息 | `request_human_input` → `awaiting_human_input` | **否**，不得索取减免审批 |
| 待批**动作**（减免、调账、催缴、派单、对外通知） | 授权 | `approval` → `awaiting_approval` | 是，且必须先有 `ApprovalDraft` |

**硬规则**：没有 `approval_draft` 时不得进入 `approval`；"信息不足"不能被改写成"待审批"。

### 12.2 触发与产出

| 规则 | 说明 |
|---|---|
| 触发条件 | 存在需要影响业务的动作，且已生成 `ApprovalDraft`（含 `evidence_ids`） |
| 输出物 | 仅 `ApprovalDraft` + `ApprovalOutcome`；动作、目标、建议变更、依据、所需角色、过期时间 |
| 禁止 | 在异常处理里顺手调用写接口；把"审批通过"等同于"已执行" |
| 暂停语义 | 图在此处 `interrupt()`，返回 `status=awaiting_approval`，不阻塞进程 |
| 恢复语义 | 见 §11.3–11.4 |
| P0 执行 | 即使批准，也只到 `approved_no_write`，不产生真实业务写操作（无写接口） |

### 12.3 角色规则（P0 采用最简单串行 AND）

以 `rent_reduction_draft` 为例（与 `docs/evaluation/fixtures/agent_first_v1.json` 的 `approval_role_rules` 一致）：

| 规则 | 取值 | 说明 |
|---|---|---|
| 组合方式 | `all_of` | 物业管理部门 **且** 财务部门都批准才生效 |
| 顺序 | `serial` | 先 `property_manager`（seq 1），后 `finance`（seq 2）；未完成 seq 1 前收到的 seq 2 批准**不生效** |
| 审批人数量 | 2 个不同主体 | `distinct_principals_required = true`；同一人不能同时充当两个角色 |
| 自批 | 禁止 | 申请草案的主体不得批准自己的草案 |
| 过期 | 72 小时 | `expires_at = generated_at + 72h` |
| 拒绝 | 立即终止 | 任一角色拒绝即 `denied`，不再请求后续角色 |

> 不建设复杂审批平台：不做会签比例、不做代理审批、不做多级转授权。

### 12.4 审批状态机

| 当前状态 | 事件 | 生效条件 | 迁移 |
|---|---|---|---|
| `awaiting_approval` | `approval.decided`(granted) | 主体具备 `approval.decide`、角色 = `property_manager`、项目匹配、版本匹配、未过期、非自批 | `partially_approved`（satisfied=[`property_manager`]） |
| `partially_approved` | `approval.decided`(granted) | 角色 = `finance`、**且主体不同于上一审批人**、其余条件同上 | `approved` |
| `awaiting_approval` / `partially_approved` | `approval.decided`(denied) | 任一有权角色 | `denied`（终态） |
| 任一 pending | `approval.decided` | `occurred_at > draft.expires_at` | `expired`（终态） |
| 任一 pending | `draft.revised`（版本 +1） | — | `invalidated`（终态；旧批准全部作废） |
| `approved` | 同 `event_id`、同内容重放 | 内容哈希一致 | 保持 `approved`，`resume` 返回 `idempotent_noop` |
| `approved` | `approval.resumed`（旧 `draft_version`） | 版本不一致 | 终态 `rejected_version_mismatch` |
| 任意 | 无权限主体批准 | — | **不迁移**；记录拒绝事件 `APPROVAL_FORBIDDEN` / `APPROVAL_PROJECT_SCOPE_DENIED` |
| `approved` | `report` | — | `status=approved_no_write` |
| `denied` | `report` | — | `status=rejected` |

### 12.5 审批事件契约（可信性来自服务端，不来自模型）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `event_id` | str | 是 | **稳定 ID**，由事件源提供；重放必须复用 |
| `type` | str | 是 | `approval.requested` / `approval.decided` / `draft.revised` / `approval.resumed` |
| `occurred_at` | datetime(tz) | 是 | 事件发生时刻（判定过期的唯一依据） |
| `actor_principal_id` | str | 是 | 由已认证会话解析，**不接受** payload 自报 |
| `actor_role` | str | 条件必填 | `approval.decided` 必填；必须是该主体的真实角色，不是请求参数 |
| `approval_id` | str | 条件必填 | 一次决定一条，便于去重 |
| `draft_id` / `draft_version` | str / int | 是 | 绑定到具体草案版本 |
| `decision` | str | 条件必填 | `granted` / `denied` |
| `reason` | str \| null | 否 | 拒绝时必填（进入 `WorkflowResult.approval.reject_reason`） |

**可信性检查顺序**（任一失败即拒绝该事件，工作流状态不变）：

1. `actor_principal_id` 由服务端会话解析，与 payload 无关；
2. 主体存在且具有 `approval.decide`；
3. 主体 `approval_roles` 包含所需角色（角色来自主体记录，不来自模型输出）；
4. `draft.project_id ∈ principal.project_ids`；
5. 顺序满足 seq（未完成前序角色时，后续角色的批准不入账）；
6. 主体 ≠ 草案申请人；
7. `occurred_at <= draft.expires_at`；
8. `draft_version` 等于当前版本；
9. `event_id` 未出现过（或内容哈希一致）。

### 12.6 重放、窗口与"不重复"保证

- **重放只能用"重复投递"表达**：同一事件对象被再次送达（同一 `event_id`、逐字段相同）。投递次数属于**注入配置**（如 fixture 的 `delivery.duplicates`），**不属于事件内容**；禁止在事件对象里加入 `replayed`、`delivery_index` 之类字段来"标记重放"——那会改变内容哈希，把幂等变成冲突。
- 同 `event_id` + 同 `content_hash` → 幂等：`approval_ids` 不追加，预算增量为 0，记录 `duplicate_events_ignored += 1`。
- 同 `event_id` + 不同内容 → `EVENT_ID_CONFLICT`，不覆盖、不幂等，转人工。
- 过期判定只看 `occurred_at`，不看"恢复时刻"；恢复发生在过期之后但决定发生在过期之前，仍然有效。
- 批准记录集合以 `approval_id` 去重，不以列表追加计数。
- 注意：`AttemptRecord.replayed` 是**运行时归并标记**（§9.2），与事件来源字段无关，不得写回审批事件对象。

### 12.7 结果如何进入最终报告

`report` 必须在 `approval` 之后执行；`WorkflowResult.approval` 至少包含：

| 字段 | 说明 |
|---|---|
| `state` | `awaiting_approval` / `partially_approved` / `approved` / `denied` / `expired` / `invalidated` |
| `decided_roles` | 已产生**有效决定**的角色（批准或拒绝都算） |
| `satisfied_roles` | 已**批准**的角色；被拒绝的角色不计入 |
| `pending_roles` | 仍需批准的角色；流程进入终态（denied/expired/invalidated）后为空 |
| `reject_reason` | 拒绝理由（`denied` 必填） |
| `decided_events[]` | 已接受的 `event_id` 与时刻 |
| `rejected_events[]` | 被拒事件与错误码（`APPROVAL_FORBIDDEN` 等） |

**禁止**在 `report` 中只写"已提交审批"而不带上述状态；也禁止把 `approved` 写成"已执行"。

---

## 13. 已知骨架问题（任务 007 修复清单，本轮不改代码）

以下 K1–K5 均**已核对源码**，是可复现的运行时缺陷，不是历史汇报转述。

| # | 问题 | 证据位置 | 影响 | 建议修复 |
|---|---|---|---|---|
| **K1** | **Registry 多能力替换非原子** | `agents/base/registry.py` `register(replace=True)`：先 `self.unregister(...)` 与被占能力所有者，再写入新 Agent。中途无回滚 | 替换时若新 Agent 注册失败，Registry 处于"旧已删、新未加"的残缺状态；且会**连带删除被冲突 Agent 的全部能力** | 改为"先在副本上计算新索引，成功后一次性替换" |
| **K2** | **配置与类描述符不一致** | `BaseAgent.descriptor` 用类属性 `version` / `description` / `capabilities`；`AgentConfig` 也有 `version` / `description` / `capabilities`；`factory.build_agent` 不做一致性校验 | YAML 改 `version` 或 `capabilities` 会被**静默忽略**，实际生效的是类属性；`config.capabilities` 校验形同虚设 | 启动时校验二者一致（至少 `version` 与 `capabilities`），不一致即失败 |
| **K3** | **deadline 不限制单次执行** | `base_agent.py` `handle()`：`_assert_deadline` 只在每次尝试前检查一次；`asyncio.wait_for(timeout=self._config.timeout_seconds)` 用的是配置超时，未与"剩余 deadline"取小 | 单次执行可越过上游 deadline；多次重试各自跑满超时 | `timeout = min(config.timeout_seconds, deadline_remaining)` |
| **K4** | **`allow_partial=False` 未完整覆盖 PARTIAL** | `orchestration/coordinator.py` `summarize_results`：无 FAILED 时**无条件**返回 `PARTIAL`（`allow_partial` 未参与）；有 FAILED 且非全失败时才受 `allow_partial` 影响 | 语义不一致：关闭部分成功后仍可能得到 `PARTIAL` | 无 FAILED 时也按 `allow_partial` 决定 `PARTIAL` → `FAILED` |
| **K5** | **`TaskStatus.SKIPPED` 未参与聚合** | 同 `summarize_results`：只统计 `FAILED` 与 `PARTIAL` | 全 `SKIPPED` 会被判为 `SUCCESS` | 单列分支：全 `SKIPPED` → `FAILED`（或 `partial` + 理由） |

修复顺序建议：K3（影响可靠性基线）→ K2（影响可配置性主张）→ K1（影响替换安全性）→ K4/K5（影响评测口径）。

### 13.1 未来数据库映射注意事项（不是已复现的运行时 bug）

| # | 事项 | 位置 | 处理时机 |
|---|---|---|---|
| **N1** | 数据库设计 v2 的 `UNIQUE(lease_id)`（一商铺一有效租约）**在现有代码层没有对应表达**。当前 P0 尚未建库、也没有 Repository/ORM 模型，因此这不是"已复现的运行时缺陷"，只是接入数据库时的映射注意事项。 | 数据库设计 v2 §6.6（文档侧） | 任务 010（数据库实施）随 Repository 一起处理；本轮不改 `database_design.md`，也不把它列为 K 类缺陷 |

> 原始记录把该项编号为 K6 并归入"已复现缺陷"；按 Prompt 1-R1 的 R6 修正，现改记为 N1，避免在无数据库模型阶段虚报已复现问题。

---

## 14. 相关文档

- [ADR-005](../decisions/ADR-005-agent-first-refocus.md)
- [mvp_scope_v2.md](../product/mvp_scope_v2.md)
- [evaluation_plan.md](../evaluation/evaluation_plan.md)
- [agent_architecture.md](./agent_architecture.md)（概念设计与历史 ADR）
- [agent_development_guide.md](./agent_development_guide.md)（新增 Agent 的硬规则）
- [database_design.md](./database_design.md)（P0 参考，非建表清单）
