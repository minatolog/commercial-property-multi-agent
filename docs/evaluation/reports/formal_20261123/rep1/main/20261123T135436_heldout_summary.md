# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`c6037fe0359973ae0378fcc4167e08471f2faa14`（工作区 dirty）
- 评分规则：`scoring-v3.3`
- 模型：`deepseek` / `deepseek-flash`
- 生成时间：`2026-11-23T13:54:36.711026+00:00`

> 模型按各 Agent 自己的 YAML 配置创建（provider/model 为合集，逐 Agent 明细见 bindings.models_by_agent）；model_name 为配置名，服务端实际应答模型见 models_by_agent.*.served_models；token 与延迟来自实际调用；成本未内置定价，故不换算金额

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| B_single_agent | 32 | 9/30 | 0.3 | 0.6268 | 0/32 | 69 | 78 | 180038 | n/a（未内置定价） | 5747 |
| C_multi_agent | 32 | 16/30 | 0.5333 | 0.8096 | 27/32 | 75 | 83 | 155191 | n/a（未内置定价） | 5380 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## 指标分解（工具事实 / 资金结论 / 金额接地）

| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| B_single_agent | 33 | 0.9091 | 11 | 0.3636 | 2 | 11/11 |
| C_multi_agent | 33 | 0.9091 | 13 | 0.3846 | 1 | 13/14 |

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
| H01 | ❌ | 7/9 | single_agent | 7710 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H02 | ✅ | 9/9 | single_agent | 10724 | 3 | - |
| H03 | ❌ | 7/9 | single_agent | 2827 | 2 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H04 | ❌ | 8/9 | single_agent | 5225 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 0.00，可信值为 18036.00；答案声称已结清/未收 0， |
| H05 | ❌ | 3/4 | single_agent | 4143 | 2 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H06 | ❌ | 1/3 | single_agent | 6130 | 1 | insufficient_evidence: 问题涉及的领域 billing（账单/费用） 没有取得任何事实（查询失败：相关工具调用失败）；其他领域的事实回答不 |
| H07 | ❌ | 1/2 | single_agent | 6032 | 2 | - |
| H08 | ✅ | 3/3 | single_agent | 6668 | 2 | - |
| H09 | ✅ | 3/3 | single_agent | 4898 | 1 | - |
| H10 | ✅ | 3/3 | single_agent | 4429 | 1 | - |
| H11 | ❌ | 1/3 | single_agent | 5156 | 1 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H12 | ❌ | 1/3 | single_agent | 3922 | 2 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H13 | ✅ | 3/3 | single_agent | 3205 | 1 | - |
| H14 | ❌ | 1/2 | single_agent | 4968 | 2 | - |
| H15 | ❌ | 4/5 | single_agent | 14550 | 5 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 invoiced_total 写成了 15120.00，可信值为 52596.00；答案声称已结清/未收 0 |
| H16 | ❌ | 1/3 | single_agent | 5656 | 2 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H17 | ❌ | 0/1 | single_agent | 4052 | 1 | 部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具），结果只回答了一部分 |
| H18 | ❌ | 1/2 | single_agent | 11130 | 2 | - |
| H19 | ❌ | 0/1 | single_agent | 3061 | 1 | 部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具），结果只回答了一部分 |
| H20 | ❌ | 0/1 | single_agent | 6205 | 2 | - |
| H21 | ✅ | 2/2 | single_agent | 4416 | 1 | - |
| H22 | ✅ | 1/1 | single_agent | 5747 | 1 | - |
| H23 | ❌ | 3/4 | single_agent | 10449 | 4 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 52596.00，可信值为 18036.00 |
| H24 | ❌ | 3/5 | single_agent | 15479 | 4 | - |
| H25 | — | 0/0 | single_agent | 7282 | 2 | - |
| H26 | — | 0/0 | single_agent | 7155 | 2 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H27 | ❌ | 0/1 | single_agent | 7291 | 4 | - |
| H28 | ✅ | 2/2 | single_agent | 7126 | 3 | - |
| H29 | ✅ | 1/1 | single_agent | 16079 | 3 | - |
| H30 | ❌ | 0/2 | single_agent | 3225 | 2 | - |
| H31 | ❌ | 7/8 | single_agent | 2245 | 1 | - |
| H32 | ❌ | 6/8 | single_agent | 4498 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 0.00，可信值为 18036.00；答案声称已结清/未收 0， |

人工量表待评：

- H07: H07-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H07: H07-AN: 答案未提及这些金额: 51840.00
- H08: H08-AN: 答案未提及这些金额: 34560.00, 52596.00
- H18: H18-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## C_multi_agent（规划模式：rule）

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | deterministic | 4891 | 2 | - |
| H02 | ❌ | 7/9 | deterministic | 6332 | 2 | - |
| H03 | ❌ | 8/9 | deterministic | 4207 | 2 | - |
| H04 | ❌ | 8/9 | deterministic | 3516 | 2 | - |
| H05 | ❌ | 3/4 | deterministic | 4892 | 2 | - |
| H06 | ✅ | 3/3 | deterministic | 153 | 0 | st_1_billing: permission_denied |
| H07 | ❌ | 2/3 | fanout | 6158 | 5 | - |
| H08 | ✅ | 4/4 | fanout | 5693 | 7 | - |
| H09 | ✅ | 3/3 | deterministic | 4325 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 3736 | 2 | - |
| H11 | ❌ | 1/3 | deterministic | 7349 | 3 | st_1_lease: insufficient_evidence |
| H12 | ✅ | 3/3 | deterministic | 143 | 0 | st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 4302 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 2542 | 1 | - |
| H15 | ❌ | 3/5 | fanout | 6920 | 3 | - |
| H16 | ❌ | 1/3 | deterministic | 8571 | 3 | st_1_property: insufficient_evidence |
| H17 | ✅ | 1/1 | fanout | 10485 | 3 | st_2_billing: insufficient_evidence |
| H18 | ❌ | 1/3 | deterministic | 9448 | 2 | - |
| H19 | ❌ | 2/3 | fanout | 5608 | 4 | - |
| H20 | ❌ | 0/1 | deterministic | 5380 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 7619 | 3 | - |
| H22 | ✅ | 1/1 | deterministic | 10207 | 4 | - |
| H23 | ❌ | 3/4 | fanout | 9118 | 9 | - |
| H24 | ❌ | 4/5 | deterministic | 9296 | 2 | - |
| H25 | — | 0/0 | clarification | 138 | 0 | - |
| H26 | — | 0/0 | clarification | 138 | 0 | - |
| H27 | ✅ | 1/1 | clarification | 144 | 0 | - |
| H28 | ✅ | 2/2 | deterministic | 4894 | 2 | - |
| H29 | ✅ | 1/1 | deterministic | 7899 | 2 | - |
| H30 | ❌ | 1/2 | deterministic | 5452 | 2 | - |
| H31 | ✅ | 8/8 | deterministic | 3853 | 2 | - |
| H32 | ✅ | 8/8 | deterministic | 4569 | 2 | - |

人工量表待评：

- H07: H07-FN: 叙述里同一字段出现多个不同金额，无法判定哪个是结论: invoiced_total
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
