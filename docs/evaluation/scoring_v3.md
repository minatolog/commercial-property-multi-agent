# 评测评分规则（scoring-v3，已冻结）

> **继承关系**：本版取代 `scoring_v2.md`。v1 / v2 的规则与报告全部保留，不得覆盖。
> 版本号 `scoring-v3` 写入每份报告；任何判定逻辑变更都必须提升版本并另建报告。

## 0. 为什么升到 v3（对应 Task 021 审查 N6）

`scoring-v2` 只比对**内部** `facts`。于是出现过这样的组合：工具算出 A-301 未收
`18036.00`，模型回答"A301 未收金额为 0.00 元，账单已经全部结清"，而评测仍判
`outstanding_total` 通过。内部取数正确 ≠ 用户看到的答案正确。

v3 增加第五类断言 `answer`，并把"工具事实准确性"与"最终答案准确性"在报告里
**分开统计**，不允许任何一方替另一方背书。

| 项 | v2 | v3 |
|---|---|---|
| 断言类别 | `facts` / `evidence` / `outcome` / `approval` | 增加 `answer` |
| 汇总口径 | 只有总体 correctness | 增加 `by_kind`：`tool_facts` 与 `final_answer` 分开 |
| 金额来源 | 只校验 `facts` | `facts` + 答案文本内的金额 |

## 1. `answer` 断言的判定规则

判定实现在 `backend/app/agents/base/narrative.py`（Agent 与评测共用同一份规则，
不维护两套）。

- **可信金额集合**：`facts` 中金额类键的取值（`invoiced_total`、`paid_total`、
  `valid_paid_total`、`outstanding_total`、`oct_rent_*`、`draft_amount`）；
- **答案金额**：答案文本里"两位小数"的金额字形（`18036.00`、`18,036.00`），
  或与某个可信金额**完全相等**的整数；
- `mismatch`：答案出现了可信集合之外的金额 → **判失败**；
- `not_mentioned`：可信金额没出现在答案里 → **转人工**（不是失败：回答可以只答被问的一项）；
- `consistent`：两者一致 → 判通过；
- `not_checkable`：本次没有金额事实（例如工单类结论）→ **不产生断言**，不进分母。

**登记条件**：只有用例本身声明了可判定的内容断言（`expected_facts` 中有可判定键，
或有 `required_evidence_ids`）时才登记 `answer` 断言。只声明路由/结局的题仍然
`correctness_total=0`——路由永远只算效率。

**已知边界（不得当作已验证）**：

1. 只校验金额，不校验叙述里的因果、建议与免责声明；
2. 用"1.8 万"这类改写表达的金额会被视为未提及（转人工）；
3. 合同条款号（`5.2`）、百分比（`20%`）、日期不会被当成金额；
4. 整数形式的金额（`21600`）只有恰好等于可信金额时才会被识别与核对，
   因此"引用其他工具输出的整数金额"既不会被误判，也不会被核验。

## 2. 其余断言（沿用 v2，未改）

| kind | 判定 |
|---|---|
| `facts` | 按字段类型化比较：金额 `Decimal` 到分、布尔真值、列表集合、其余全等 |
| `evidence` | `required_evidence_ids` 全部出现；`forbidden_substrings` 不得出现 |
| `outcome` | 由 `expected_outcome` 判定（`ok` / `denied` / `failed`，拒绝与失败完全对称） |
| `approval` | `expected_approval.status` / `draft_version` 一致 |
| `facts` 契约缺口 | 基线契约外的键 → 转人工，不进分母 |

## 3. 报告口径

- `summary.by_kind.tool_facts`：`facts` 断言的通过/失败数；
- `summary.by_kind.final_answer`：`answer` 断言的通过/失败数；
- 任一为 `null` 表示**本次没有可判定断言**（既不是通过，也不是失败）；
- 每题 `rows[].answer_check` 记录 `status` / `trusted_amounts` / `unverified_amounts`
  / `missing_amounts` / `detail`，便于人工复核。

## 4. 本次结果（scoring-v3，离线，代码提交 `45af0cb`）

| 基线 | 可计分题 | 通过 | 工具事实断言 | 最终答案断言 |
|---|---|---|---|---|
| `A_deterministic` | 30 | 20 | 28/33 | 9/9 |
| `B_single_agent` | 30 | 21 | 29/33 | 11/11 |
| `C_multi_agent` | 30 | 23 | 30/33 | 11/11 |

报告：`docs/evaluation/reports/20261106T191222_heldout_*`、`20261106T191233_dev_*`。

**读法**：这里的"最终答案断言 11/11"只说明**离线规则路径的答案由事实渲染而来、金额一致**，
不能说明真实模型的叙述质量——真实模型答案准确性尚未测量（缺凭据/未跑）。
`scoring-v2` 的 A 20/30、B 21/30、C 23/30 与本版通过题数相同，但分母不同
（v3 每题多一条 `answer` 断言，部分题多一条 `not_mentioned` 人工项），
**不得跨版本比较通过率高低**。

## 5. 与历史报告的关系

| 报告 | 评分版本 | 数据 |
|---|---|---|
| `20261106T111758_dev_*`、`20261106T112354_heldout_*` | scoring-v1 | v2 |
| `20261106T130749_heldout_*`、`20261106T130753_dev_*` | scoring-v2 | v3 |
| `real_model_dev/20261106T183449_*` | scoring-v2 | v3（真实模型历史测量，**不重算**） |
| 本次新增 | scoring-v3 | v3 |

历史报告一律保留。真实模型的历史测量不得用新规则回写。
