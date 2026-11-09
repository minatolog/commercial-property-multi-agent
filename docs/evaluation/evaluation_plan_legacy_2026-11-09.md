> **历史快照（2026-11-09 归档）**：下文保留 Task 026 整理前的原文，仅供追溯；其中的“当前”、待办、示例和优先级不作为现行指导。现行内容见 [evaluation_plan.md](./evaluation_plan.md)。

# 评测计划（P0）

- **日期**：2026-11-03（2026-11-06 按 Prompt 1-R1 修订）
- **状态**：**规格**。本轮**未执行任何模型评测**，仓库内尚不存在 Runtime。
- **数据版本**：`agent-first-v1`（`spec_revision = 2026-11-06-r1`，`as_of_date = 2026-11-03`，核心调查期 2026-08-01 ~ 2026-10-31）
- **依据**：[ADR-005](../decisions/ADR-005-agent-first-refocus.md)、[mvp_scope_v2.md](../product/mvp_scope_v2.md)、[agent_runtime_contracts.md](../architecture/agent_runtime_contracts.md)

> **禁止事项**：在 Runtime 与 runner 存在之前，**不得**对外报告任务成功率、模型费用、恢复成功率、延迟改善等任何数值。本文档中的一切结论均为**待测量假设**。

---

## 1. 本轮交付边界

| 内容 | 状态 |
|---|---|
| 评测方法论、指标定义、数据协议 | ✅ 本文档 |
| 共享 fixture（2 个项目、3 租户、3 租约、3 账单、3 收款、4 工单、4 文档+4 片段） | ✅ `fixtures/agent_first_v1.json` |
| 8 题开发样例（C01–C08） | ✅ `cases/smoke_v1.jsonl` |
| 评测 runner / 三基线实现 | ❌ 未开始（任务 007 起） |
| 真实模型评测结果 | ❌ 未执行 |

**最终 P0 目标题量 30–50 题；本轮只准备 8 题**，作为 runner 的输入规格与契约校验样本。**保留测试集属于 P0 范围**（见 §6），不以"P1 之后再说"处理。

---

## 2. 数据协议

### 2.1 文件

| 文件 | 作用 |
|---|---|
| `fixtures/agent_first_v1.json` | 共享数据（基线）+ 变体注册表 + 可信主体 + 审批角色规则 + 审批草案 + 场景解析协议 |
| `cases/smoke_v1.jsonl` | 8 行，每行一个评测用例，JSON 对象 |

### 2.2 全部为合成数据

- `fixtures.synthetic = true`；每个文档对象和片段对象另有 `synthetic: true`。
- 文档片段是**模拟检索语料**，`page` 表示**约定的测试来源定位**，不代表已验证 PDF 分页，也不代表已实现 RAG。
- 不得读取任何真实公司、租户、合同或客户资料。

### 2.3 运行项、场景解析与错误行为（R1-R2 修正，必须按此实现）

#### 2.3.1 数据合成（只读）

```text
effective_dataset(case) =
    base_dataset                                  -- fixtures 实体数组，只读
    ⊕ overlay(case.variant.overlay)               -- 固定操作顺序
```

| 顺序 | 来源 | 规则 |
|---|---|---|
| 1 | `fixtures` 实体数组 | 基线数据，只读；任何变体不得就地修改它（必须深拷贝） |
| 2 | `variant.overlay` | 按 `add_documents` → `add_document_snippets` → `patch_invoice_items` 顺序应用；只允许**追加**或**按键打补丁**，不允许删除实体 |

#### 2.3.2 运行项展开（runner 的第一步）

JSONL 里的 `scenarios` 是**数组**，不是以 ID 为键的对象；case 本身没有顶层 `scenario_id`。

```text
run_items(case) =
    if case 有 "scenarios" 字段:
        必须是非空数组，且每个元素含唯一非空 scenario_id
        → [(case.case_id, s.scenario_id) for s in case.scenarios]     # 每个场景各跑一次
    else:
        → [(case.case_id, null)]                                      # 普通 case 只跑一次
```

| 形态 | 运行项数 | 事件来源 | 断言来源 |
|---|---|---|---|
| 含 `scenarios`（C06/C08） | `len(case.scenarios)` | `variant.scenarios[scenario_id].events` | case 场景断言 + case 级断言，各判一次 |
| 无 `scenarios`（C01–C05、C07） | 1 | `variant.events`（可为空） | 只用 case 级断言 |

#### 2.3.3 场景解析（同一 `scenario_id` 双端匹配）

```text
run_item(case_id, scenario_id):
    case_scenario    = case.scenarios 中 scenario_id 相等的那一个元素           # 数组查找，供评测
    fixture_scenario = variant_registry[case.variant].scenarios[scenario_id]    # 映射查找，供运行
    events           = fixture_scenario.events                                  # 整体替换，不合并
    evidence         = fixture_scenario.evidence_requirement（有则用，无则回退 case.required_evidence_ids）
```

| 规则 | 说明 |
|---|---|
| 数组 ↔ 映射 | case 用数组保存断言，fixture 用映射保存事件；靠同一个 `scenario_id` 连接，**不靠数组下标** |
| 事件替换 | 取 `fixture_scenario.events` 整个数组，**替换** `variant.events`，不做并集 |
| overlay 先于 events | 先改数据，再注入工具/审批事件；events 永远不改数据 |
| 一致性 | case 场景的 `fault_injection`（event_id / tool / mode / fail_attempts / then）、`expected_terminal_outcomes`（或 `expected_terminal_status`）、`evidence_policy`、`required_evidence_ids` 必须与 fixture 场景一致，否则 `SCENARIO_MISMATCH` |
| 证据权威 | fixture 场景提供 `evidence_requirement` 时以它为准；未提供时沿用 case 级 `required_evidence_ids` |
| 故障计数 | `fail_attempts` = 场景内该工具前 N 次调用返回 `mode` 故障；序号从 1 开始，> N 后按 `then`；要求 `fail_attempts <= tool_max_attempts` |

#### 2.3.4 无场景 case

- 恰好运行一次，事件取 `variant.events`（可为空数组）。
- 若引用的 variant 同时声明了 `scenarios`，该 variant **必须**有 `default_scenario`，且它必须存在于 `scenarios` 中。
- 只使用 case 级断言与 `expected_*`。

#### 2.3.5 错误行为（一律 fail fast，不静默回退）

| 错误码 | 触发条件 |
|---|---|
| `MISSING_SCENARIO_ID` | 场景对象缺少 `scenario_id`，或不是非空字符串 |
| `DUPLICATE_SCENARIO_ID` | 同一 case 的 `scenarios` 中 `scenario_id` 重复 |
| `UNKNOWN_SCENARIO_ID` | case 场景的 ID 不在所引用 variant 的 `scenarios` 中 |
| `EMPTY_SCENARIOS` | `scenarios` 存在但为空数组（无场景 case 应省略该字段） |
| `SCENARIOS_NOT_ARRAY` | `scenarios` 不是数组 |
| `DEFAULT_SCENARIO_MISSING` / `DEFAULT_SCENARIO_UNKNOWN` | 无场景 case 引用了含 `scenarios` 的 variant，但默认场景缺失或不存在 |
| `SCENARIO_MISMATCH` | case 场景与 fixture 场景在 fault / evidence / terminal / assertions 上不一致 |

**禁止**：用数组下标代替 `scenario_id`；用字符串搜索或计数代替解析；静默回退到 `default_scenario`。

#### 2.3.6 为什么必须这样定义

C06 主失败路径与恢复 probe 使用**同一个工具**、同一变体、不同 `fail_attempts`。若只按"自然语言顺序"或数组下标解析，runner 可能把 probe 的 1 次超时套到主路径上，把"必然失败"判成"应该恢复"；C08 的六个审批场景同理，选错场景会直接改变终态。JSONL 用数组、fixture 用映射，就必须用同一个 `scenario_id` 显式连接两端。

### 2.4 变体注册表（当前 5 个，含 8 个子场景）

| 变体 | 类型 | 用途 | 子场景 | 被哪些用例引用 |
|---|---|---|---|---|
| `v_base` | 无覆盖 | 基线 | — | C01、C02、C05、C07 |
| `v_annex_conflict` | overlay 追加未签署草案 | 构造同主题冲突 | — | C03、C04 |
| `v_oct_rent_corrected` | overlay 更正 10 月租金 | 回归用数据变体（验证结论随数据变化） | — | 本轮无 case 直接引用，用于 runner 自检 |
| `v_tool_timeout_billing` | 工具故障注入 | 工具超时 | `main_timeout_exhausted`、`recovery_probe` | C06（两个场景） |
| `v_approval_flow` | 审批事件序列 | 审批暂停/拒绝/允许/重放/越权/换版/过期 | `approval_denied`、`approval_granted`、`approval_replay`、`approval_unauthorized_actor`、`approval_stale_version`、`approval_expired` | C08（六个场景） |

### 2.5 故意缺失的引用（负例，必须显式区分）

部分用例需要"引用了不存在的东西"。这类 ID 放在用例的 `negative_references`，**不得**放进 `required_evidence_ids`。

| ID | 所在用例 | 语义 |
|---|---|---|
| `doc_xh_a301_annex_b` | C03、C05 | 合同正文明确引用附件B，但附件B未电子化；正确行为是报缺失，**不是**引用它 |
| `unit_jl_b101` / `lease_jl_b101_2025` / `doc_jl_b101_contract` | C07 | 属于 `prj_jinlan`，当前主体无权访问；出现即为越权 |

**规则**：`required_evidence_ids` 中的 ID 必须**全部存在**（或按场景的 `evidence_requirement` 条件化）；`negative_references` 中的 ID 必须**全部不存在于证据集**（对 C07 而言是"存在但不得出现"）。

### 2.6 预期答案不可泄漏给被测系统

`expected_facts`、`assertions`、`negative_references`、`scenarios[].expected_*` 仅由评测器读取。**不得**作为 Agent 输入、工具返回值或检索结果暴露，否则评测失效。

---

## 3. 三个基线：共同质量、架构约束、效率三者分离（R2）

三基线必须使用**同一 fixture、同一工具集、同一权限上下文、同一总预算、同一套共通质量断言**。差异只在编排形态。

### 3.1 共通质量指标（A/B/C 完全相同的判定）

事实、引用、权限、审批、零写入这些**答案属性**，对三个基线使用**同一套程序断言**。只要答案正确，架构身份不得使任何基线判错。

### 3.2 编排约束（按 baseline_mode 分开，只判"是否遵守自身定义"）

| 基线 | 允许使用 | 自身架构约束（架构一致性断言，不是答案正确性） |
|---|---|---|
| **A. Deterministic** | 同一批只读工具、`Decimal` 计算、规则拼接报告 | 不得调用任何 LLM；固定调用顺序；金额只由确定性代码产生 |
| **B. Single Agent** | 一个 Agent + 全部工具 + RAG | 不得多 Agent 扇出／并行子任务；单入口、单结果结构 |
| **C. Multi-Agent** | Coordinator + 领域 Agent + Verifier（+ 审批节点） | 必须经 Coordinator 规划；只能调用声明过的能力；补查受限 |

**预算对齐**：`Budget` 三项上限（模型调用数、工具调用数、总 token）与墙钟上限对三基线**取相同值**；Baseline A 不使用模型预算，但**不得**因此获得额外工具预算。

### 3.3 默认产品路由是独立效率指标（不是正确性）

`route_class` 只回答"产品自己会怎么走"，记入 **E1 效率**，不进入质量通过/失败判定。

- 允许简单方案解决复杂题：C03/C04/C05/C08 的 `allowed_routes` 都包含 `deterministic` / `single_agent` / `multi_agent`。
- `preferred_route` 只是**待测量的效率假设**（例如"C04 用一个 Lease Agent + Verifier 就够"），跑完可以推翻它。
- 反向偏差同样禁止：不得因为"多 Agent 更贵"就判 C 基线错，也不得因为"题目复杂"就要求必须 multi_agent。

### 3.4 假想正确结构化结果在 A/B/C 下如何分别评分（R2 示例）

下面是一份**假想**的正确结果（C04 同主题冲突），仅用于说明评分口径，**不代表已运行**。

<!-- hypothetical-result:begin -->

```json
{
  "run": {"case_id": "C04", "route_class": "single_agent", "terminal_status": "reported"},
  "findings": [
    {"finding_id": "f1", "statement": "已签署正文约定每 12 个月递增 5%", "evidence_ids": ["snip_contract_5_2"], "derivation": "direct", "confidence_basis": "explicit"},
    {"finding_id": "f2", "statement": "未签署草案约定每 24 个月递增一次", "evidence_ids": ["snip_annex_draft_5_2"], "derivation": "direct", "confidence_basis": "conflicting"}
  ],
  "conflicts": [
    {"topic": "租金递增周期", "left_evidence_id": "snip_contract_5_2", "right_evidence_id": "snip_annex_draft_5_2", "resolution": "requires_human_decision"}
  ],
  "missing_info": [],
  "approval_draft": null,
  "business_writes": 0
}
```

<!-- hypothetical-result:end -->

| 判定层 | A. Deterministic | B. Single Agent | C. Multi-Agent |
|---|---|---|---|
| Q1 事实 | 通过（同值） | 通过 | 通过 |
| Q2 引用存在 | 通过 | 通过 | 通过 |
| Q3 引用支持结论 | 通过（并列双方） | 通过 | 通过 |
| Q4 权限/越权 | 通过 | 通过 | 通过 |
| Q5 审批合规 | N/A（无审批路径） | N/A | N/A |
| Q6 零业务写入 | 通过 | 通过 | 通过 |
| Q7 冲突不静默 | 通过（`conflicts` 两项都在） | 通过 | 通过 |
| 架构一致性 | 通过：无 LLM 调用 | 通过：无扇出 | 通过：Coordinator 规划 |
| 效率 E1 route | `deterministic` | `single_agent`（= preferred） | `multi_agent` |
| 效率 E2/E3 | 延迟最低、token 0 | 中等 | 最高 token/调用数 |

**结论**：三基线**同为质量通过**；差别只落在 E1–E3。反过来，若某答案"只引用已签署正文、静默忽略草案"，则 A/B/C **同样判 Q3/Q7 失败**——失败原因是答案属性，不是架构身份。

---

## 4. 指标定义与统计口径

### 4.1 共通质量指标（Q，程序断言优先）

| # | 指标 | 定义 | 判定方式 |
|---|---|---|---|
| Q1 | **事实与金额** | 金额/日期/状态与 fixture 真值精确相等（`Decimal`） | 程序断言 |
| Q2 | **引用存在**（L1） | 引用的 `document_id+version+page+clause_id` 在数据集中存在 | 程序断言 |
| Q3 | **引用支持结论**（L2） | 摘录确实支持该结论 | 程序 + 人工抽样 |
| Q4 | **权限与隔离** | 越权数据零泄漏；权限只来自可信上下文 | 程序断言 |
| Q5 | **审批合规** | 仅可信授权事件可通过；绑定 `draft_id+draft_version`；重放幂等；过期/换版/越权均拒绝 | 程序断言 |
| Q6 | **零业务写入** | 任何场景都不产生真实调账/减免/派单/通知 | 程序断言 |
| Q7 | **冲突与缺失显式** | 应有的 `conflicts` / `missing_info` 不得被静默省略 | 程序断言 |

### 4.2 架构一致性指标（C，按基线）

| # | 指标 | 判定 |
|---|---|---|
| C1 | Baseline A 无模型调用 | 统计 `model_calls == 0` |
| C2 | Baseline B 无多 Agent 扇出 | 子任务数 ≤ 1；无并行领域 Agent |
| C3 | Baseline C 经 Coordinator 规划且有界 | `plan.plan_id` 存在；`revision_count <= max_revisions` |

### 4.3 效率指标（E，单独报告，不并入质量分）

| # | 指标 | 定义 |
|---|---|---|
| E1 | **路由适配** | 实际 `route_class` 是否等于 `preferred_route`；只记"命中/未命中"，不判错 |
| E2 | **延迟** | 每用例墙钟耗时（单调时钟），统计 P50 / P95 |
| E3 | **成本** | 每用例模型调用数、token 数、工具调用数；按用例与全任务两个口径 |

### 4.4 程序断言 vs 人工/模型评分（必须分开）

| 类别 | 判定者 | 例子 | 是否可复现 |
|---|---|---|---|
| **程序化断言** | runner（纯 Python） | 金额相等、ID 存在、路由枚举、终态枚举、重放幂等 | 完全可复现 |
| **人工/模型评分** | rubric（人在环或评审模型） | "报告是否区分事实与推断"、"表述是否让业务方看懂" | 需标注评分者与版本 |

**规则**：两类结果分别统计、分别汇报，**不得**合并成单一"总分"掩盖差异；rubric 评分必须记录评分模型/评审人标识与时间。

### 4.5 不做什么

- 不设定、不承诺具体提升百分比。
- 不用单一平均数掩盖失败用例；必须给出用例级明细。
- **不把路由命中率当作答案正确率**，也不把架构身份当作答案错误。
- 不在 8 题上做超参数搜索后当成正式结论（见 §6）。

---

## 5. 8 题开发样例摘要

| ID | 主题 | 变体/场景 | 允许路由 | 效率假设 `preferred_route` | 主要考点 |
|---|---|---|---|---|---|
| **C01** | 确定性欠费查询 | `v_base` | deterministic, single_agent | `deterministic` | 该用确定性查询就别上多 Agent；冲销分配必须排除 |
| **C02** | 单份合同条款检索 | `v_base` | deterministic, single_agent, multi_agent | `single_agent` | 引用须带版本+页码；不得声称 PDF 已验证 |
| **C03** | 完整争议调查 | `v_annex_conflict` | 三基线均可 | `multi_agent`（假设） | 三类能力协同、金额核对、冲突标记、缺失项、草案 |
| **C04** | 同主题冲突证据 | `v_annex_conflict` | 三基线均可 | `single_agent`（假设） | 冲突必须并列呈现，不得擅自选边；单 Agent + Verifier 即可 |
| **C05** | 必要资料缺失 | `v_base` | 三基线均可 | `single_agent`（假设） | 报缺失并停止无依据结论 |
| **C06** | 工具超时 | `v_tool_timeout_billing` 的 2 个场景 | 三基线均可 | 无偏好（`null`） | 主失败路径不要求 invoice 证据；probe 成功后才要求 |
| **C07** | 跨项目/无权限 | `v_base` | 三基线均可 | `deterministic` | 越权数据零泄漏、权限只能来自可信上下文 |
| **C08** | 减免草案与审批 | `v_approval_flow` 的 6 个场景 | 三基线均可 | 无偏好（`null`） | 只出草案、暂停/拒绝/允许/重放/越权/换版/过期、审批绑定草案版本 |

### 5.1 C06 的两条路径 = 两个运行项（R1 / R1-R2）

C06 的 `scenarios` 是数组，按 §2.3.2 展开为 2 个运行项：`(C06, main_timeout_exhausted)` 与 `(C06, recovery_probe)`；每个运行项用自身 `scenario_id` 在 `v_tool_timeout_billing.scenarios` 映射中取事件与证据要求。

| 运行项（`scenario_id`） | 故障 | 终止状态 | 证据要求 |
|---|---|---|---|
| `main_timeout_exhausted`（主失败路径） | `billing.read_invoices` 连续 2 次超时（= 上限） | `failed_with_explicit_error` 或 `degraded_with_missing_marked` | **`required_evidence_ids = []`**；不得因缺工具结果被强迫取得 invoice 证据 |
| `recovery_probe`（恢复 probe） | 仅第 1 次超时，第 2 次成功 | `recovered_on_attempt_2` | **仅成功后**要求 `inv_2026_08/09/10` |

通用规则"全部 required 必须命中"**不再无条件适用于失败路径**：失败路径判的是"是否明确失败/降级且不编造"，恢复路径判的是"是否恢复且引用真实证据"。

### 5.2 C08 的六个审批场景 = 六个运行项（R3 / R1-R2）

C08 展开为 6 个运行项，一一对应 `v_approval_flow.scenarios` 的 6 个键。

| 运行项（`scenario_id`） | 事件序列要点 | 期望终态 | 期望审批状态 |
|---|---|---|---|
| `approval_denied` | 请求 → 物业拒绝 | `rejected` | `denied` |
| `approval_granted` | 请求 → 物业批（seq 1）→ 财务批（seq 2），两名不同主体 | `approved_no_write` | `approved` |
| `approval_replay` | 已批准后 `evt_apr_fin_grant_003` 被**重复投递**（2 次、逐字段相同；次数记在场景 `delivery`，不写入事件对象） | `idempotent_noop` | `approved`（预算增量为 0） |
| `approval_unauthorized_actor` | 无 `approval.decide` 主体、跨项目审批人先后尝试 | `awaiting_approval` | `awaiting_approval`（`APPROVAL_FORBIDDEN` / `APPROVAL_PROJECT_SCOPE_DENIED`） |
| `approval_stale_version` | v1 双批后草案改 v2，再用 v1 恢复 | `rejected_version_mismatch` | `invalidated`（`APPROVAL_VERSION_MISMATCH`） |
| `approval_expired` | 决定时刻晚于 `expires_at` | `rejected_expired` | `expired`（`APPROVAL_EXPIRED`） |

### 5.3 覆盖度自检

| 维度 | 覆盖用例 |
|---|---|
| 确定性优先 | C01、C07 |
| 单 Agent 足够 | C02、C04（假设）、C05（假设） |
| 多能力协同 | C03（假设，非必需） |
| 故障注入（主路径 + 恢复 probe） | C06（2 场景） |
| 权限/隔离（两个项目） | C07、C08（跨项目审批人） |
| 人工审批 | C03（产出草案）、C08（6 场景完整分支） |
| 数据变体（重算一致性） | `v_oct_rent_corrected`（runner 自检） |

---

## 6. 开发样例与保留测试集隔离（R6 关键修正）

| 集合 | 用途 | 可见性 | 规则 |
|---|---|---|---|
| **开发样例**（本轮 8 题） | 契约校验、调 prompt、写 runner | 对开发者可见 | 允许反复调试；结论标注"开发集结果" |
| **保留测试集**（P0 内补齐 22–42 题，合计 30–50） | 对外结论依据 | 开发冻结前不可见 | 评分规则先冻结；见下方重复测量规则 |

**保留集属于 P0 交付范围**：最终 P0 要 30–50 题和客观对照，因此保留集不能整体推迟到 P1；P1 只保留"更多题量/更多业务形态"的扩展。

**测量随机性的正确做法**：

1. **允许**在开始前固定重复次数（建议 `N = 3`）并连同模型、温度、prompt、数据、评分版本一起**冻结**，同一批次内不得修改。
2. **禁止**看结果后调参、换 prompt、挑最好的一次上报。
3. 报告必须给出**全部重复的分布**（中位数、P95、失败次数），不得只报最优一次。
4. "在保留集上反复迭代后汇报最优值"视为无效结论。

隔离要求：

1. 保留集与开发样例**不得共享同一批具体数值**（可共享 schema 与工具）。
2. 任何未冻结配置的重复运行只能标为"探索性运行"，不得进入对照结论。
3. 公布结果时必须注明：数据集版本、题量、模型版本、预算、重复次数、是否开发集。

---

## 7. 运行与复现要求（未来 runner）

| 要求 | 说明 |
|---|---|
| 离线可跑 | 至少一个模式用 `FakeModelAdapter` 完全离线，用于 CI |
| 确定性 | 固定 `dataset_version` + `spec_revision` + `as_of_date` + 随机种子 |
| 三基线一次跑完 | 同一批题、同一预算、同一工具集，输出对照表 |
| 逐用例明细 | 每个 case/scenario 输出：通过/失败、失败断言 ID、延迟、调用数与 token 数 |
| 不改数据 | runner 只读 fixture；变体通过 overlay 在内存中应用 |
| 场景解析 | 严格按 §2.3 展开运行项，并按 `scenario_id` 双端匹配；缺失/重复/未知 ID 直接报错，不静默回退 |
| 最小命令 | 最终要求"1–3 条命令"跑完 8 题三基线（P0 Done 第 8 条） |

---

## 8. 当前已知局限

| # | 局限 | 影响 |
|---|---|---|
| 1 | 无 Runtime，全部断言**未执行** | 本文档所有预期均为规格，不是结果 |
| 2 | 文档片段为模拟语料 | 无法证明真实 PDF 解析与分页能力 |
| 3 | 仅 8 题，且开发者可见 | 存在过拟合风险；不能作为对外质量结论 |
| 4 | 仅 1 个主演示场景 | 无法覆盖更多业务形态 |
| 5 | 无真实写接口 | 审批"通过后执行"只能验证到"不写"这一层 |
| 6 | 未接入数据库 | 金额核对基于 fixture，不代表 SQL 实现正确性 |
| 7 | rubric 评分尚未定义量表 | 需在 runner 阶段补 1–5 分制与判定说明 |
| 8 | 审批主体是合成身份 | 只证明"角色/权限/版本/过期"规则可执行，不证明真实 IAM 集成 |

---

## 9. 本次返修的可复验语义检查（R1–R6 / R1-R2）

没有 Runtime 时，以下均为**规格/参考输入检查**，不是工作流已运行通过。

| # | 检查 | 判定方式 | 期望 |
|---|---|---|---|
| S1 | 失败 C06 不强制取得 invoice 证据 | 读取 C06 `main_timeout_exhausted` 场景 | `required_evidence_ids == []` 且 `evidence_policy == none` |
| S2 | 恢复 probe 成功才要求证据 | 读取 `recovery_probe` 场景 | `fail_attempts=1 < tool_max_attempts=2`，成功后要求 3 张 invoice |
| S3 | 同一正确答案分别通过 A/B/C 共同质量项 | 用 §3.4 假想结果按 Q1–Q7 评分 | 三基线全通过；仅 E1–E3 不同 |
| S4 | 审批只有可信授权事件才可通过 | 枚举 C08 六个场景 | 仅 `approval_granted` / `approval_replay` 达到 `approved`；其余被拒 |
| S5 | 事件重放不重复计账、到达顺序不影响结果 | 参考归并算法对同一事件集做正序/逆序/重复输入 | 结果 map 相同；重复事件 `duplicate_events_ignored=1`；预算增量 0 |
| S6 | verify 状态 × 补查上限组合均有出口 | 枚举 `verdict(3) × revision_count(2) × draft(2)` | 12 组全部有明确去向，无悬挂状态 |
| **S7** | 选择器能从实际 JSON 结构解析运行项（R1-R2） | 只读选择器：`expand_run_items(cases)` + 错误注入 | C06→2 项、C08→6 项、普通 case→1 项；缺失/重复/未知/空数组各自抛对应错误码 |
| **S8** | 同 `event_id` 同内容幂等（R1-R2） | 规范化（键排序）后逐字段比较 `approval_replay` 的两条事件 | 完全一致、无 `replayed` 字段；重放被忽略 1 次，预算增量 0 |
| **S9** | 同 `event_id` 异内容必冲突（R1-R2） | 合成反例：同 ID 改 `decision`/`occurred_at` | 抛出 `EVENT_ID_CONFLICT`，不覆盖、不幂等 |

---

## 10. 相关文档

- [ADR-005](../decisions/ADR-005-agent-first-refocus.md)
- [mvp_scope_v2.md](../product/mvp_scope_v2.md)
- [agent_runtime_contracts.md](../architecture/agent_runtime_contracts.md)
- `fixtures/agent_first_v1.json`、`cases/smoke_v1.jsonl`
