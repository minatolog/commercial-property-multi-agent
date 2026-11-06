# 评测评分规则（scoring-v3 / v3.3，已冻结）

> **继承关系**：本版取代 `scoring_v2.md`。v1 / v2 的规则与报告全部保留，不得覆盖。
> 版本号写入每份报告；任何判定逻辑变更都必须提升版本并另建报告。
> - `scoring-v3`：首次引入 `answer` 断言（报告 `20261106T191222_heldout_*`、`20261106T191233_dev_*`）。
> - `scoring-v3.1`：可信金额集合扩展到工具输出、新增 `ungrounded` 状态
>   （报告 `20261106T192311_heldout_*`、`20261106T192319_dev_*`）。
> - `scoring-v3.2`（Task 024 / Q3）：资金结论改为**按字段**核对（`fund` 主断言），
>   `answer` 降为辅助；`unverified` 单独统计。中间产物报告未归档（规则在同一次任务内被 v3.3 取代）。
> - `scoring-v3.3`（Task 024 收尾）：字段绑定精度修正（合计词优先 / 跳过表格行 / 多合计值判 `unverified`），
>   当前报告 `20261106T205403_heldout_*`、`20261106T205407_dev_*`。
>   原因：v3.2 的真实 DeepSeek 首测把明细"应收租金 15,120.00"当成应收合计，见 [real_model_v2](reports/real_model_v2/)。

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

## 1. `answer` 与 `fund` 断言的判定规则

判定实现在两个模块，Agent 运行时与评测共用同一份实现（不维护两套）：

- `backend/app/agents/base/conclusions.py`：`FundConclusion`（只从工具 facts 赋值）、
  `render_fund_conclusion`（用户可见金额由可信字段渲染）、`check_fund_statements`（字段级核对）；
- `backend/app/agents/base/narrative.py`：金额接地（辅助检查）。

### 1.1 主判据：`fund`（字段级资金结论）

| 状态 | 含义 | 处理 |
|---|---|---|
| `verified` | 叙述里至少一个"字段↔金额"与可信值一致，且无矛盾结论 | **通过** |
| `mismatch` | 某字段写成了别的值，或"已结清/未收 0"与未收金额矛盾 | **失败** |
| `unverified` | 没有把金额绑定到字段，或同一字段出现多个互相矛盾的合计值 | **未验证**（转人工，不算通过也不算失败） |
| `not_checkable` | 本次没有资金事实（工单类结论） | 不产生断言 |

字段绑定是**机械规则**（不做语义理解）：

1. 标签 → 字段：应收/应缴 → 应收；已收/实收 → 已收；未收/欠费/欠款/尚欠 → 未收；
2. 取标签邻近的金额字形（两位小数，或与可信金额相等的整数），`5.2 条`、`20%`、日期不算；
3. 同一字段既有"合计应收 X"又有逐期明细时，**优先带合计词的那条**；
4. **跳过 Markdown 表格行**里的标签（表格是明细数据，不是结论）；
5. 同一字段出现多个不同合计值 → `unverified`（无法判定哪个是结论，不硬判对错）。

### 1.2 辅助判据：`answer`（金额接地）

- `mismatch`：答案出现任何工具都没给过的金额（编造或模型自算）；
- `ungrounded`：写了钱数，但没有任何一个经核验的合计金额；
- `not_mentioned` / `incomplete`：没写金额或只写一部分 → 转人工；
- `consistent`：金额都能对上。

**辅助断言不能单独证明答案准确**：v3.1 的教训正是"三个金额互换仍判 `consistent`"。
因此报告里 `fund_conclusions` 与 `answer_grounding` 分开统计，且未验证题单独计数。

**已知边界（不得当作已验证）**：

1. 只校验金额，不校验叙述里的因果、建议与免责声明；
2. 用"1.8 万"这类改写表达的金额会被视为未提及（转人工）；
3. 合同条款号（`5.2`）、百分比（`20%`）、日期不会被当成金额；
4. 整数形式的金额（`21600`）只有恰好等于可信金额时才会被识别与核对；
5. "写了部分金额又漏了合计"只会转人工，机械规则无法区分"回答范围更窄"与"算错"。

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
- `summary.by_kind.fund_conclusions`：`fund` 断言（字段级资金结论）的通过/失败数；
- `summary.by_kind.answer_grounding`：`answer` 断言（金额接地，辅助）的通过/失败数；
- `summary.fund_conclusions`：`verified / mismatch / unverified / not_checkable` 分布，
  **未验证题单独计数**，不得读成通过；
- 任一 `rate` 为 `null` 表示**本次没有可判定断言**（既不是通过，也不是失败）；
- 每题 `rows[].fund_check` / `rows[].answer_check` / `rows[].answer_verified` 记录判定细节，
  便于人工复核。

## 4. 本次结果（`scoring-v3.3`，离线）

| 基线 | 可计分题 | 通过 | 工具事实断言 | 资金结论断言 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| `A_deterministic` | 30 | 20 | 28/33 | 9/9 | 0 | 9/9 |
| `B_single_agent` | 30 | 21 | 29/33 | 11/11 | 0 | 11/11 |
| `C_multi_agent` | 30 | 23 | 30/33 | 11/11 | 3 | 11/11 |

报告：`docs/evaluation/reports/20261106T205403_heldout_*`、`20261106T205407_dev_*`。

**读法**：离线规则路径的答案由事实渲染而来，所以"资金结论 11/11"只说明**规则自洽**；
C 的 3 题"未验证"说明其答案没有把金额绑定到字段——这两类数字都不能当作真实模型质量。

## 4.1 真实模型的有界核验（非质量结论）

`docs/evaluation/reports/real_model_v2/20261106T2053_real_model_q1q3_deepseek.json`
（`--budget-tokens 30000`、`max_model_calls=12`，只跑 A-301 争议调查一题）：

| 观测 | 结果 |
|---|---|
| 物理模型请求次数 vs 账本 `used_model_calls` | 7 vs 7（一致） |
| token | 13,452（`exceeded=0`、`tokens_exhausted=false`） |
| 结论 | `verdict=conflicting`、`completeness=partial`（缺附件 B，属既有事实） |
| 资金结论 | billing 子任务 `verified`；`narrative_discrepancies=0` |
| 首次同题运行（`20261106T2051_*`） | `mismatch` **误报**（把明细"应收租金 15,120.00"当成应收合计）；v3.3 已修正 |

它不是"模型质量对照"，也不含成本换算：只证明 token 闸门与字段级核对在真实 provider 上可运行。

## 5. 与历史报告的关系

| 报告 | 评分版本 | 数据 |
|---|---|---|
| `20261106T111758_dev_*`、`20261106T112354_heldout_*` | scoring-v1 | v2 |
| `20261106T130749_heldout_*`、`20261106T130753_dev_*` | scoring-v2 | v3 |
| `real_model_dev/20261106T183449_*` | scoring-v2 | v3（真实模型历史测量，**不重算**） |
| `20261106T191222_heldout_*`、`20261106T191233_dev_*` | scoring-v3 | v3 |
| `20261106T192311_heldout_*`、`20261106T192319_dev_*` | scoring-v3.1 | v3 |
| `20261106T205403_heldout_*`、`20261106T205407_dev_*` | scoring-v3.3 | v3（**当前**） |
| `real_model_v2/20261106T1917_*`、`20261106T1922_*` | scoring-v3 / v3.1 | v3（N6 两题，含一次已修正误报） |
| `real_model_v2/20261106T2051_*`、`20261106T2053_*` | scoring-v3.2 / v3.3 | v3（Q3 两题，含一次已修正误报） |

历史报告一律保留。真实模型的历史测量不得用新规则回写。
`scoring-v2` 与 v3.3 的通过题数相同（A 20/30、B 21/30、C 23/30），但分母不同（v3.x 每题多两条金额断言），
**不得跨版本比较通过率高低**。
