# 规划器领域词表与路由兜底（Task 031 / 2.7；Task 034 起为快速路径）

> **Task 034 之后的定位**：词表是**快速路径**，不再是唯一路由依据。规划模式由 `backend/app/config/planner.yaml` 的 `mode` 决定（默认 `rule`，行为与本文 §1–§7 完全一致）；`hybrid` 下规则命中恰好 1 个领域且无歧义信号时仍直接用本词表，其余交给 LLM Supervisor（见 §9 与 [ADR-006](../decisions/ADR-006-hybrid-planner.md)）。

- 更新：2026-11-21，Task 031 工作项 2.7。
- 代码唯一来源：[`backend/app/orchestration/vocabulary.py`](../../backend/app/orchestration/vocabulary.py)。
- 相关实现：[`backend/app/orchestration/investigation.py`](../../backend/app/orchestration/investigation.py) 的 `RuleBasedPlanner` / `plan_node` / `clarification_node` / `report_node`。
- 回归测试：[`backend/tests/test_task031_planner_fallback.py`](../../backend/tests/test_task031_planner_fallback.py)。

## 1. 目的与边界

`RuleBasedPlanner` 是 P0 默认规划器：用确定性关键词规则把问题分到
`lease / billing / property` 三个领域，再按能力名解析领域 Agent。

本文件规定三件事：

1. **词表口径**：每个词属于哪个领域、来源依据是什么；
2. **兜底契约**：一个词都没命中时**不许猜**领域，必须回问用户（`needs_clarification`），
   禁止像 Task 009 那样静默落到 `billing`；
3. **可排查性**：每次运行都把路由理由（命中哪些词、落到哪个子任务）写进报告
   `routing_reason`，普通运行也要有。

边界：

- 本词表只服务**多 Agent 图的 C 基线**（`RuleBasedPlanner`）。A/B 基线的意图识别
  在 `backend/app/evaluation/baselines.py::detect_intents`，是另一份表；改这里不影响 A/B。
- 路线值：`deterministic`（单领域）/ `fanout`（多领域）/ `clarification`（未命中）。
- 不调用任何模型；命中规则是**子串匹配**（见 §2）。

## 2. 命中规则（为什么是子串）

- 中文没有天然空格分词，当前规划器一直是 `hint in text` 的子串匹配，确定性、可复现；
- 因此词表必须"短、专、无歧义"：**禁止裸单字**（如 `费` 会命中"免费"），
  也不放会跨领域误伤的宽词；
- `matched_domains(text)` 只返回真的命中的领域，顺序与 `DOMAINS` 一致；完全未命中返回 `{}`；
- 词表内**不区分大小写/同义归一**，新增词必须本身就是用户会打出来的那串字。

## 3. 领域 → 同义词（逐词来源）

`DOMAIN_LABELS`：`lease` = 合同/租约、`billing` = 账单/费用、`property` = 物业工单。

### 3.1 合同/租约（lease → `lease.query`）

| 词 | 类型 | 来源依据 |
|---|---|---|
| 合同 | Task 009 原有 | Task 009 `RuleBasedPlanner._LEASE_HINTS` |
| 租约 | Task 009 原有 | Task 009 `_LEASE_HINTS` |
| 条款 | Task 009 原有 | Task 009 `_LEASE_HINTS` |
| 递增 | Task 009 原有 | Task 009 `_LEASE_HINTS`（合同递增条款） |
| 免租 | Task 009 原有 | Task 009 `_LEASE_HINTS`（免租期） |
| 押金 | Task 009 原有 | Task 009 `_LEASE_HINTS` |
| 续租 | Task 009 原有 | Task 009 `_LEASE_HINTS` |
| 租期 | Task 009 原有 | Task 009 `_LEASE_HINTS` |
| 租赁 | Task 031 新增 | fixture 合同条款原文"自第二个**租赁**年度起，租金每十二（12）个月递增百分之五"（`docs/evaluation/fixtures/agent_first_v1.json`，`doc_xh_a301_contract`）；"租赁合同 / 租赁期限"是合同标准用语，用户常说"租赁期限"而不是"租期" |

### 3.2 账单/费用（billing → `billing.statement`）

| 词 | 类型 | 来源依据 |
|---|---|---|
| 账单 | Task 009 原有 | Task 009 `RuleBasedPlanner._BILLING_HINTS` |
| 租金 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 费用 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 欠费 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 付款 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 核销 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 多收 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 少收 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 金额 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 发票 | Task 009 原有 | Task 009 `_BILLING_HINTS` |
| 欠 | Task 031 新增 | Task 013 既有欠费意图词表 `backend/app/evaluation/baselines.py::_ARREARS_HINTS`（"欠 / 未交 / 没交 / 未收 / 余额 / 已收 / 对账 / 应收"，早于本任务；本任务只是把同一业务口径复用到领域词表，**没有改评测代码**） |
| 未交 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`） |
| 没交 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`）；"还有多少钱没交"这类口语在无该词时会命中不到任何领域 |
| 未收 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`） |
| 余额 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`） |
| 已收 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`） |
| 对账 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`） |
| 应收 | Task 031 新增 | 同上（Task 013 `_ARREARS_HINTS`） |
| 物业费 | Task 031 新增 | fixture 发票明细 `itm_inv08_pf / itm_inv09_pf / itm_inv10_pf` 的 `description` 为"2026年8月/9月/10月**物业费**"（账单科目真实叫法）；Prompt §2.7 明示举例 |
| 管理费 | Task 031 新增 | Prompt §2.7 明示举例；fixture 合同条款"经**物业管理**部门与财务部门共同审批后生效"（`doc_xh_a301_contract`）说明"物业管理费/管理费"是同一业务口径的常用简称 |

### 3.3 物业工单（property → `property.work_orders`）

| 词 | 类型 | 来源依据 |
|---|---|---|
| 空调 | Task 009 原有 | Task 009 `RuleBasedPlanner._PROPERTY_HINTS` |
| 维修 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 工单 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 报修 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 故障 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 投诉 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 漏水 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 电梯 | Task 009 原有 | Task 009 `_PROPERTY_HINTS` |
| 冷气 | Task 031 新增 | Prompt §2.7 明示举例（南方口语，等同"空调"；用户可能只说"冷气坏了"） |
| 不制冷 | Task 031 新增 | Prompt §2.7 明示举例；fixture 工单标题"空调**制冷**不足"（`wo_2026_07_12`，`agent_first_v1.json`）表明"制冷"是工单真实用词 |
| 空调不凉 | Task 031 新增 | Prompt §2.7 明示举例（口语：空调制冷效果差）。该词已含"空调"，保留是为了让 Prompt 明示的口语路径在词表里可被核对 |

### 3.4 与 HVAC 过滤的联动

`property` 子任务在命中 HVAC 相关词时会下发 `category="hvac"` 过滤参数。
Task 031 把判断从"只认 `空调`"扩展为 `空调 / 冷气 / 不制冷`，避免
"冷气不制冷"路由到物业却拿不到 HVAC 过滤参数。

## 4. 路由规则（有命中时行为不变）

| 命中的领域数 | 路由 | 子任务 |
|---|---|---|
| 0 | `clarification` | 无（回问用户，零工具调用） |
| 1 | `deterministic` | 1 个（`st_1_<domain>`） |
| ≥2（普通问题） | `fanout` | 每个领域 1 个（并发） |
| ≥2 且是"纯欠费"问题 | `deterministic` + 收窄到 billing | 1 个（`st_1_billing`） |

"纯欠费"由 `_is_pure_arrears_question` 判定（标记词："欠多少 / 欠费多少 /
还有多少钱没交 / 未收多少 / 余额多少"）。收窄是为了避免"问一个数字却扇出三个 Agent"，
这属于 Task 009 的既有策略，Task 031 未改判定，只是把收窄行为写进 `routing_reason.narrowing`。

## 5. 未命中兜底契约（核心变更）

Task 009 的行为是 `selected = ["billing"]` 静默兜底：问"请帮我看看这个事情"会真的
去跑账单工具，返回一堆与问题无关的数字，且报告里没有任何理由说明"为什么是账单"。
Task 031 / 2.7 起改为**明确回问**：

- `InvestigationResult.verdict == "needs_clarification"`；
- `InvestigationResult.route == "clarification"`；
- 零子任务（`results == ()`）、零工具调用（Trace 为空、预算 `used_tool_calls == 0`）、
  `failures == ()`；
- 不进入审批：`approval_status == "not_required"`，`approval_request` / `approved_draft` 为空；
- `report["completeness"] == "not_executed"`（不是"证据不全"，而是"根本没开始"）；
- `report["requires_human_review"] == true`（需要用户补充信息才能继续）；
- `report["routing_reason"] == []`，排查信息全在 `report["clarification"]`。

`report["clarification"]` 的稳定形状（CLI 的 `_investigation_payload` 直接读取，
字段名不可改）：

```json
{
  "reason": "no_domain_matched",
  "message": "无法判断这个问题属于合同、账单还是物业，因此本次没有执行调查，也没有调用任何工具。",
  "available_domains": [
    {"domain": "lease", "label": "合同/租约", "capability": "lease.query"},
    {"domain": "billing", "label": "账单/费用", "capability": "billing.statement"},
    {"domain": "property", "label": "物业工单", "capability": "property.work_orders"}
  ],
  "question": "请说明要核实的是哪一类：合同/租约（例如租期、免租期、递增条款）、账单/费用（例如租金、欠费、发票），还是物业工单（例如空调维修、漏水）？"
}
```

`reason` 目前只有 `no_domain_matched` 一种，保留字段便于未来扩展。
图结构上这是 `plan` 之后的一条独立分支：`plan →(clarification)→ END`，
不经过 `dispatch / verify / report / approval`。

## 6. 报告中的路由理由 `routing_reason`

**每次运行（普通运行、补查、审批恢复）都必须有**，且可 JSON 序列化。
形状是"每个已执行子任务一条"的 list：

| 字段 | 含义 |
|---|---|
| `domain` | 领域名（`lease` / `billing` / `property`） |
| `label` | 中文标签（`DOMAIN_LABELS`） |
| `matched` | 该领域**实际命中**的词，按词表顺序；一定能在原问题文本里找到 |
| `capability` | 该子任务能力名 |
| `subtask_id` | 子任务编号（与 `plan` / `agent_results` 对齐） |
| `narrowing` | 仅"纯欠费收窄"时出现：`{"reason": "pure_arrears_question", "dropped": [{"domain","label","matched"}]}`，说明为什么另外几个领域命中了却没派发 |

示例（三领域扇出，真实运行输出）：

```json
[
  {"domain": "lease", "label": "合同/租约", "matched": ["合同"], "capability": "lease.query", "subtask_id": "st_1_lease"},
  {"domain": "billing", "label": "账单/费用", "matched": ["账单", "金额"], "capability": "billing.statement", "subtask_id": "st_2_billing"},
  {"domain": "property", "label": "物业工单", "matched": ["空调", "维修"], "capability": "property.work_orders", "subtask_id": "st_3_property"}
]
```

纯欠费收窄示例：

```json
[
  {
    "domain": "billing",
    "label": "账单/费用",
    "matched": ["欠"],
    "capability": "billing.statement",
    "subtask_id": "st_1_billing",
    "narrowing": {
      "reason": "pure_arrears_question",
      "dropped": [
        {"domain": "lease", "label": "合同/租约", "matched": ["免租", "租期"]},
        {"domain": "property", "label": "物业工单", "matched": ["空调"]}
      ]
    }
  }
]
```

实现上 `routing_reason` 由 `plan_node` 写入 state 通道、`report_node` 输出；
补查只重跑子任务、不改计划，审批恢复读的是 checkpoint，所以两者都不会丢理由。

## 7. 新增词门禁（今后任何人加词都必须满足）

1. **必须有来源依据**，并写进本文件 §3 对应表格的"来源依据"列。可接受的来源：
   - Task 009 原始规则表（迁移，不算新增）；
   - fixture 字段/单据/合同条款原文里的真实说法；
   - 有 Prompt 或项目文档明文授权的业务口语补充；
   - 既有仓库内业务词表（如 Task 013 `_ARREARS_HINTS`）的复用。
2. **禁止为了让某道评测题通过而加词**：不得查看 `docs/evaluation/cases/` 的题目来挑词；
   评测跑分只用于如实报告影响，不能反过来调词表；
3. 同步更新 `backend/tests/test_task031_planner_fallback.py`：词表契约测试会强制
   "Task 009 词一个不丢""每个词能命中自己的领域""`matched` 的词确实出现在问题里"；
4. 遵守"短、专、无歧义"：禁止裸单字与跨领域宽词（如 `费`、`款`）；
5. 词表改动属于**路由行为变更**：需要同时说明对现有问题/评测题的影响，不能悄悄改。

## 8. 变更记录

| 日期 | 任务 | 变更 |
|---|---|---|
| 2026-11-07 前后 | Task 009 | 建立 `RuleBasedPlanner._LEASE_HINTS / _BILLING_HINTS / _PROPERTY_HINTS`；未命中时静默 `billing` |
| 2026-11-22 | Task 034 | 词表定位为快速路径；新增歧义信号（§9），决定 hybrid 何时交给 LLM Supervisor；词表本身未增删 |
| 2026-11-21 | Task 031 / 2.7 | 词表迁到 `backend/app/orchestration/vocabulary.py`（唯一来源，`ask` 路径共用）；删除静默 billing 兜底，改为 `needs_clarification` + 回问；新增 `routing_reason` 报告字段；按 §3 增补 14 个来源可追溯的词（lease 1 / billing 10 / property 3） |

## 9. 与 LLM Supervisor 的关系（Task 034）

| 规划模式 | 本词表的作用 |
|---|---|
| `rule`（默认） | 唯一路由依据，行为与 §1–§7 相同 |
| `hybrid` | 快速路径：规则命中恰好 1 个领域且无歧义信号 → 直接用规则（零模型调用）；规则命中多个领域且无歧义 → `hybrid_multi_domain=rule` 用规则、`=llm` 交给 Supervisor；0 命中或有歧义信号 → Supervisor |
| `llm` | 不参与派发决策；只在 Supervisor 失败时作为回退（`fallback_rule`），并在报告里记录 `rule_domains` / `rule_domains_not_planned` 供审计 |

**歧义信号**（确定性，代码在 `backend/app/orchestration/supervisor.py::ambiguity_signals`）：

| 信号 | 规则 | 例 |
|---|---|---|
| `negation` | 否定词（不是/并非/不用/不要/除了/无关/别查/别管）出现在某个命中词之前 6 个字以内 | “不是租金的问题，是空调” |
| `target_reference` | 出现指代别家商户的说法（隔壁/那家/另一家/另外一家/对面/别家/其他店） | “隔壁那家空调的事处理到哪了” |
| `unit_code_mismatch` | 问题中的铺位号（如 `A-12`）与可信目标的铺位号不同 | “A-12 那家合同什么时候到期” |
| `too_short` | 去掉铺位号、空白与标点后少于 4 个字 | “A-301 欠？” |
| `weak_hint_only` | 命中的词全部是单字（目前只有“欠”） | “我欠你一顿饭” |

歧义信号只决定“要不要交给模型”，不改变词表、不改变规则规划的结果；Supervisor 的 System Prompt 不包含词表（否则退化为让模型做关键词匹配）。
