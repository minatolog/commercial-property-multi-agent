# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`c6037fe0359973ae0378fcc4167e08471f2faa14`（工作区 dirty）
- 评分规则：`scoring-v3.3`
- 模型：`deepseek` / `deepseek-flash`
- 生成时间：`2026-11-23T14:32:19.705921+00:00`

> 模型按各 Agent 自己的 YAML 配置创建（provider/model 为合集，逐 Agent 明细见 bindings.models_by_agent）；model_name 为配置名，服务端实际应答模型见 models_by_agent.*.served_models；token 与延迟来自实际调用；成本未内置定价，故不换算金额

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| B_single_agent | 32 | 11/30 | 0.3667 | 0.6443 | 0/32 | 66 | 77 | 175564 | n/a（未内置定价） | 5490 |
| C_multi_agent | 32 | 18/30 | 0.6 | 0.8538 | 27/32 | 73 | 82 | 151794 | n/a（未内置定价） | 5349 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## 指标分解（工具事实 / 资金结论 / 金额接地）

| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| B_single_agent | 33 | 0.9091 | 12 | 0.4167 | 0 | 9/9 |
| C_multi_agent | 33 | 0.9394 | 15 | 0.6 | 0 | 15/15 |

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
| H01 | ❌ | 7/9 | single_agent | 8768 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 invoiced_total 写成了 18036.00，可信值为 52596.00；答案声称已结清/未收 0 |
| H02 | ❌ | 8/9 | single_agent | 8380 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 paid_total 写成了 18036.00，可信值为 34560.00；字段 outstanding_t |
| H03 | ❌ | 8/9 | single_agent | 7511 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 invoiced_total 写成了 18036.00，可信值为 52596.00 |
| H04 | ❌ | 7/8 | single_agent | 5188 | 3 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 0.00，可信值为 18036.00；答案声称已结清/未收 0， |
| H05 | ✅ | 4/4 | single_agent | 4151 | 2 | - |
| H06 | ❌ | 1/3 | single_agent | 8591 | 1 | insufficient_evidence: 问题涉及的领域 billing（账单/费用） 没有取得任何事实（查询失败：相关工具调用失败）；其他领域的事实回答不 |
| H07 | ❌ | 2/3 | single_agent | 5088 | 2 | - |
| H08 | ✅ | 3/3 | single_agent | 7893 | 2 | - |
| H09 | ✅ | 3/3 | single_agent | 5028 | 1 | - |
| H10 | ✅ | 3/3 | single_agent | 3667 | 1 | - |
| H11 | ❌ | 1/3 | single_agent | 3750 | 1 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H12 | ❌ | 1/3 | single_agent | 3695 | 2 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H13 | ✅ | 3/3 | single_agent | 2879 | 1 | - |
| H14 | ❌ | 1/2 | single_agent | 3948 | 2 | - |
| H15 | ✅ | 5/5 | single_agent | 11887 | 5 | - |
| H16 | ❌ | 1/3 | single_agent | 3295 | 1 | insufficient_evidence: 这是有目标的业务查询，但没有取得任何属于本次目标的工具事实（失败、被拒绝或越界的调用都不算取证） |
| H17 | ❌ | 0/1 | single_agent | 4811 | 1 | 部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具），结果只回答了一部分 |
| H18 | ❌ | 0/2 | single_agent | 7728 | 1 | insufficient_evidence: 问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具）；其他领域的事实回答 |
| H19 | ❌ | 0/1 | single_agent | 4066 | 1 | 部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实（未查询：没有调用该领域的工具），结果只回答了一部分 |
| H20 | ❌ | 0/1 | single_agent | 5490 | 2 | - |
| H21 | ✅ | 2/2 | single_agent | 5261 | 1 | - |
| H22 | ✅ | 1/1 | single_agent | 7733 | 1 | - |
| H23 | ❌ | 3/4 | single_agent | 13757 | 5 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 756.00，可信值为 18036.00 |
| H24 | ❌ | 2/5 | single_agent | 17665 | 4 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 756.00，可信值为 18036.00；答案声称已结清/未收  |
| H25 | — | 0/0 | single_agent | 6873 | 1 | - |
| H26 | — | 0/0 | single_agent | 6229 | 2 | 资金结论与工具事实矛盾，已标记为待人工核对: 答案声称已结清/未收 0，但未收金额为 18036.00，结论与工具事实矛盾 |
| H27 | ❌ | 0/1 | single_agent | 6672 | 4 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 outstanding_total 写成了 52596.00，可信值为 18036.00；答案声称已结清/未 |
| H28 | ✅ | 2/2 | single_agent | 4202 | 3 | 达到最大轮次 3，未得到最终答案 |
| H29 | ✅ | 1/1 | single_agent | 9225 | 2 | 工具 lease__lookup 调用被拒绝: 参数 lease_id='null' 超出本次任务范围（应为 'lease_xh_a302_2025'）；工具  |
| H30 | ❌ | 1/2 | single_agent | 5640 | 2 | - |
| H31 | ✅ | 8/8 | single_agent | 2200 | 1 | - |
| H32 | ❌ | 6/8 | single_agent | 4807 | 2 | 资金结论与工具事实矛盾，已标记为待人工核对: 字段 paid_total 写成了 52596.00，可信值为 34560.00 |

人工量表待评：

- H04: H04-AN: 答案未提及这些金额: 34560.00, 52596.00
- H07: H07-AN: 答案未提及这些金额: 34560.00, 51840.00
- H08: H08-AN: 答案未提及这些金额: 34560.00, 52596.00
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## C_multi_agent（规划模式：rule）

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | deterministic | 6069 | 2 | - |
| H02 | ✅ | 9/9 | deterministic | 5337 | 2 | - |
| H03 | ✅ | 9/9 | deterministic | 3706 | 2 | - |
| H04 | ❌ | 8/9 | deterministic | 5349 | 2 | - |
| H05 | ❌ | 3/4 | deterministic | 4572 | 2 | - |
| H06 | ✅ | 3/3 | deterministic | 153 | 0 | st_1_billing: permission_denied |
| H07 | ❌ | 3/4 | fanout | 6262 | 5 | - |
| H08 | ❌ | 3/4 | fanout | 6930 | 5 | - |
| H09 | ✅ | 3/3 | deterministic | 4791 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 3981 | 1 | - |
| H11 | ❌ | 1/3 | deterministic | 6779 | 3 | st_1_lease: insufficient_evidence |
| H12 | ✅ | 3/3 | deterministic | 151 | 0 | st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 3756 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 4720 | 2 | - |
| H15 | ❌ | 4/5 | fanout | 6002 | 3 | - |
| H16 | ❌ | 1/3 | deterministic | 9460 | 2 | st_1_property: insufficient_evidence |
| H17 | ✅ | 3/3 | fanout | 13487 | 4 | - |
| H18 | ❌ | 2/3 | deterministic | 7213 | 2 | - |
| H19 | ❌ | 2/3 | fanout | 5433 | 4 | - |
| H20 | ❌ | 0/1 | deterministic | 4698 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 6996 | 2 | - |
| H22 | ✅ | 1/1 | deterministic | 7578 | 3 | - |
| H23 | ✅ | 4/4 | fanout | 7969 | 10 | - |
| H24 | ❌ | 4/5 | deterministic | 9917 | 2 | - |
| H25 | — | 0/0 | clarification | 139 | 0 | - |
| H26 | — | 0/0 | clarification | 144 | 0 | - |
| H27 | ✅ | 1/1 | clarification | 146 | 0 | - |
| H28 | ✅ | 2/2 | deterministic | 4708 | 2 | - |
| H29 | ✅ | 1/1 | deterministic | 6293 | 2 | - |
| H30 | ✅ | 2/2 | deterministic | 7052 | 3 | - |
| H31 | ✅ | 8/8 | deterministic | 4107 | 2 | - |
| H32 | ❌ | 7/8 | deterministic | 4953 | 2 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
