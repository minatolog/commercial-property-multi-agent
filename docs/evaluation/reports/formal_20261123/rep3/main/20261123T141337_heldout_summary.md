# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`c6037fe0359973ae0378fcc4167e08471f2faa14`（工作区 dirty）
- 评分规则：`scoring-v3.3`
- 模型：`deepseek` / `deepseek-flash`
- 生成时间：`2026-11-23T14:13:37.148154+00:00`

> 模型按各 Agent 自己的 YAML 配置创建（provider/model 为合集，逐 Agent 明细见 bindings.models_by_agent）；model_name 为配置名，服务端实际应答模型见 models_by_agent.*.served_models；token 与延迟来自实际调用；成本未内置定价，故不换算金额

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| B_single_agent | 32 | 11/30 | 0.3667 | 0.6428 | 0/32 | 70 | 74 | 167411 | n/a（未内置定价） | 5417 |
| C_multi_agent | 32 | 16/30 | 0.5333 | 0.8353 | 27/32 | 74 | 80 | 150716 | n/a（未内置定价） | 5132 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## 指标分解（工具事实 / 资金结论 / 金额接地）

| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| B_single_agent | 33 | 0.9394 | 11 | 0.4545 | 1 | 9/10 |
| C_multi_agent | 33 | 0.9091 | 14 | 0.6429 | 1 | 15/15 |

> 工具事实准确率回答"取数对不对"；资金结论通过率回答"用户读到的应收/已收/未收对不对"；未验证题表示叙述没有把金额绑定到字段（**不算通过**）；金额接地是辅助检查，不能单独证明答案准确。

## 各 Agent 实际模型（models_by_agent）

### B_single_agent

| Agent | provider | 配置模型名 | 实际应答模型 | temperature | max_tokens | timeout(s) | 共享客户端 | 配置来源 |
|---|---|---|---|---|---|---|---|---|
| single | deepseek | deepseek-flash | deepseek-flash | 0.0 | 1024 | 60.0 | 否 | single.yaml |

### C_multi_agent

| Agent | provider | 配置模型名 | 实际应答模型 | temperature | max_tokens | timeout(s) | 共享客户端 | 配置来源 |
|---|---|---|---|---|---|---|---|---|
| billing | deepseek | deepseek-flash | deepseek-flash | None | 1024 | 20.0 | 是 | billing.yaml |
| lease | deepseek | deepseek-flash | deepseek-flash | 0.1 | 2048 | 30.0 | 否 | lease.yaml |
| property | deepseek | deepseek-flash | deepseek-flash | None | 1024 | 20.0 | 是 | property.yaml |
| single | deepseek | deepseek-flash | 未记录 | 0.0 | 1024 | 60.0 | 否 | single.yaml |

## B_single_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ❌ | 8/9 | single_agent | 5147 | 3 | - |
| H02 | ✅ | 9/9 | single_agent | 7887 | 3 | - |
| H03 | ❌ | 7/9 | single_agent | 6537 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 invoiced_total 写成了 17280.00，可信值为 52596.00；答案声称已结清/未收 0 |
| H04 | ❌ | 7/8 | single_agent | 4036 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 0.00，可信值为 18036.00；答案声称已结清/未收 0， |
| H05 | ❌ | 3/4 | single_agent | 4114 | 2 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H06 | ❌ | 1/3 | single_agent | 6466 | 1 | insufficient_evidence: 问题涉及的领域 billing（账单/费用） 没有取得任何事实（查询失败：相关工具调用失败）；其他领域的事实回答不 |
| H07 | ❌ | 1/3 | single_agent | 6940 | 2 | 模型叙述与工具事实不一致，已标记为待人工核对: 答案写了金额但没有一个是经核验的合计金额（应为 17280.00, 34560.00, 51840.00） |
| H08 | ✅ | 3/3 | single_agent | 8744 | 2 | - |
| H09 | ✅ | 3/3 | single_agent | 2871 | 1 | - |
| H10 | ✅ | 3/3 | single_agent | 3619 | 1 | - |
| H11 | ❌ | 1/3 | single_agent | 5034 | 1 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H12 | ❌ | 1/3 | single_agent | 4417 | 2 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H13 | ✅ | 3/3 | single_agent | 4260 | 1 | - |
| H14 | ❌ | 1/2 | single_agent | 4587 | 2 | - |
| H15 | ❌ | 4/5 | single_agent | 10194 | 5 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 invoiced_total 写成了 756.00，可信值为 52596.00 |
| H16 | ❌ | 1/3 | single_agent | 3056 | 2 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H17 | ❌ | 0/1 | single_agent | 4804 | 1 | 部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具），结果只回答了一部分 |
| H18 | ❌ | 0/2 | single_agent | 6797 | 1 | insufficient_evidence: 问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具）；其他领域的事实回答 |
| H19 | ❌ | 0/1 | single_agent | 2876 | 1 | 部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具），结果只回答了一部分 |
| H20 | ❌ | 0/1 | single_agent | 5417 | 2 | - |
| H21 | ✅ | 2/2 | single_agent | 4609 | 1 | - |
| H22 | ✅ | 1/1 | single_agent | 4619 | 1 | - |
| H23 | ❌ | 3/4 | single_agent | 15360 | 5 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 17280.00，可信值为 18036.00；答案声称已结清/未 |
| H24 | ❌ | 2/5 | single_agent | 15786 | 4 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 52596.00，可信值为 18036.00 |
| H25 | — | 0/0 | single_agent | 5022 | 0 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H26 | — | 0/0 | single_agent | 7184 | 2 | - |
| H27 | ❌ | 0/1 | single_agent | 7952 | 4 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H28 | ✅ | 2/2 | single_agent | 5510 | 3 | - |
| H29 | ✅ | 1/1 | single_agent | 6240 | 3 | 达到最大轮次 3，未得到最终答案 |
| H30 | ✅ | 2/2 | single_agent | 5503 | 4 | 达到最大轮次 3，未得到最终答案 |
| H31 | ✅ | 8/8 | single_agent | 2211 | 1 | - |
| H32 | ❌ | 7/8 | single_agent | 5869 | 3 | - |

人工量表待评：

- H04: H04-AN: 答案未提及这些金额: 34560.00, 52596.00
- H07: H07-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H08: H08-AN: 答案未提及这些金额: 52596.00
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## C_multi_agent（规划模式：rule）

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ❌ | 8/9 | deterministic | 4103 | 2 | - |
| H02 | ❌ | 8/9 | deterministic | 5132 | 2 | - |
| H03 | ❌ | 7/9 | deterministic | 4218 | 2 | - |
| H04 | ❌ | 7/9 | deterministic | 4428 | 2 | - |
| H05 | ✅ | 4/4 | deterministic | 4844 | 2 | - |
| H06 | ✅ | 3/3 | deterministic | 149 | 0 | st_1_billing: permission_denied |
| H07 | ❌ | 2/3 | fanout | 5523 | 6 | - |
| H08 | ✅ | 4/4 | fanout | 6117 | 6 | - |
| H09 | ✅ | 3/3 | deterministic | 3595 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 3348 | 1 | - |
| H11 | ❌ | 1/3 | deterministic | 5798 | 2 | st_1_lease: insufficient_evidence |
| H12 | ✅ | 3/3 | deterministic | 145 | 0 | st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 4040 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 3360 | 1 | - |
| H15 | ❌ | 4/5 | fanout | 6318 | 3 | - |
| H16 | ❌ | 1/3 | deterministic | 8676 | 2 | st_1_property: insufficient_evidence |
| H17 | ✅ | 3/3 | fanout | 11863 | 4 | - |
| H18 | ❌ | 2/3 | deterministic | 6923 | 2 | - |
| H19 | ✅ | 3/3 | fanout | 5640 | 4 | - |
| H20 | ❌ | 0/1 | deterministic | 5161 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 5726 | 2 | - |
| H22 | ✅ | 1/1 | deterministic | 6763 | 3 | - |
| H23 | ❌ | 3/4 | fanout | 8440 | 12 | - |
| H24 | ❌ | 4/5 | deterministic | 8395 | 2 | - |
| H25 | — | 0/0 | clarification | 146 | 0 | - |
| H26 | — | 0/0 | clarification | 151 | 0 | - |
| H27 | ✅ | 1/1 | clarification | 147 | 0 | - |
| H28 | ✅ | 2/2 | deterministic | 5072 | 2 | - |
| H29 | ✅ | 1/1 | deterministic | 5664 | 2 | - |
| H30 | ❌ | 1/2 | deterministic | 5900 | 2 | - |
| H31 | ✅ | 8/8 | deterministic | 2811 | 2 | - |
| H32 | ❌ | 7/8 | deterministic | 4468 | 2 | - |

人工量表待评：

- H07: H07-FN: 叙述里同一字段出现多个不同金额，无法判定哪个是结论: invoiced_total
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
