# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`2512a3b9ec36ed9bcb4acc59b91ce2e213bec031`
- 评分规则：`scoring-v3.3`
- 模型：`offline_deterministic` / `none`
- 生成时间：`2026-11-06T20:54:03.408539+00:00`

> 本报告未调用任何模型（确定性规则路径）；token/成本不适用

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| A_deterministic | 32 | 20/30 | 0.6667 | 0.7267 | 24/32 | 27 | 0 | 0 | n/a（离线） | 0 |
| B_single_agent | 32 | 21/30 | 0.7 | 0.7756 | 0/32 | 38 | 0 | 0 | n/a（离线） | 0 |
| C_multi_agent | 32 | 23/30 | 0.7667 | 0.8489 | 28/32 | 47 | 0 | 0 | n/a（离线） | 89 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## 指标分解（工具事实 / 资金结论 / 金额接地）

| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| A_deterministic | 33 | 0.8485 | 9 | 1.0 | 0 | 9/9 |
| B_single_agent | 33 | 0.8788 | 11 | 1.0 | 0 | 11/11 |
| C_multi_agent | 33 | 0.9091 | 11 | 1.0 | 3 | 11/11 |

> 工具事实准确率回答"取数对不对"；资金结论通过率回答"用户读到的应收/已收/未收对不对"；未验证题表示叙述没有把金额绑定到字段（**不算通过**）；金额接地是辅助检查，不能单独证明答案准确。

## A_deterministic

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | deterministic | 81 | 1 | - |
| H02 | ✅ | 9/9 | deterministic | 0 | 1 | - |
| H03 | ✅ | 9/9 | deterministic | 0 | 1 | - |
| H04 | ✅ | 9/9 | deterministic | 0 | 1 | - |
| H05 | ✅ | 4/4 | deterministic | 0 | 1 | - |
| H06 | ✅ | 3/3 | deterministic | 0 | 1 | permission_denied: 工具 'billing.statement.read' 需要权限 ['billing.read']，当前调用方不具备 |
| H07 | ❌ | 0/2 | deterministic | 1 | 1 | - |
| H08 | ❌ | 0/2 | deterministic | 0 | 1 | - |
| H09 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H10 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H11 | ✅ | 3/3 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H12 | ✅ | 3/3 | deterministic | 0 | 1 | permission_denied: 工具 'lease.lookup' 需要权限 ['lease.read']，当前调用方不具备 |
| H13 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H14 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H15 | ❌ | 4/5 | deterministic | 0 | 1 | - |
| H16 | ✅ | 3/3 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H17 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H18 | ❌ | 0/2 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H19 | ❌ | 0/1 | deterministic | 1 | 1 | - |
| H20 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H22 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H23 | ✅ | 4/4 | deterministic | 0 | 1 | - |
| H24 | ❌ | 0/4 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H25 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H26 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H27 | ✅ | 1/1 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H28 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H30 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H31 | ✅ | 8/8 | deterministic | 0 | 1 | - |
| H32 | ✅ | 8/8 | deterministic | 0 | 1 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## B_single_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | single_agent | 78 | 1 | - |
| H02 | ✅ | 9/9 | single_agent | 0 | 1 | - |
| H03 | ✅ | 9/9 | single_agent | 0 | 1 | - |
| H04 | ✅ | 9/9 | single_agent | 0 | 1 | - |
| H05 | ✅ | 4/4 | single_agent | 0 | 1 | - |
| H06 | ✅ | 3/3 | single_agent | 0 | 1 | billing.statement.read: permission_denied |
| H07 | ❌ | 0/2 | single_agent | 1 | 1 | - |
| H08 | ❌ | 0/2 | single_agent | 0 | 1 | - |
| H09 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H10 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H11 | ✅ | 3/3 | single_agent | 0 | 1 | lease.lookup: project_scope_denied |
| H12 | ✅ | 3/3 | single_agent | 0 | 1 | lease.lookup: permission_denied |
| H13 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H14 | ❌ | 1/2 | single_agent | 0 | 1 | - |
| H15 | ✅ | 5/5 | single_agent | 0 | 2 | - |
| H16 | ✅ | 3/3 | single_agent | 0 | 1 | property.work_orders.read: project_scope_denied |
| H17 | ✅ | 1/1 | single_agent | 0 | 2 | - |
| H18 | ❌ | 2/3 | single_agent | 1 | 1 | - |
| H19 | ❌ | 0/1 | single_agent | 1 | 2 | - |
| H20 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H21 | ✅ | 2/2 | single_agent | 0 | 2 | - |
| H22 | ✅ | 1/1 | single_agent | 0 | 1 | - |
| H23 | ✅ | 4/4 | single_agent | 1 | 3 | - |
| H24 | ❌ | 3/5 | single_agent | 0 | 1 | - |
| H25 | — | 0/0 | single_agent | 0 | 1 | - |
| H26 | — | 0/0 | single_agent | 0 | 1 | - |
| H27 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H28 | ✅ | 2/2 | single_agent | 0 | 1 | - |
| H29 | ✅ | 1/1 | single_agent | 0 | 1 | - |
| H30 | ❌ | 1/2 | single_agent | 0 | 1 | - |
| H31 | ✅ | 8/8 | single_agent | 0 | 1 | - |
| H32 | ✅ | 8/8 | single_agent | 0 | 1 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## C_multi_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | deterministic | 93 | 1 | - |
| H02 | ✅ | 9/9 | deterministic | 88 | 1 | - |
| H03 | ✅ | 9/9 | deterministic | 89 | 1 | - |
| H04 | ✅ | 9/9 | deterministic | 88 | 1 | - |
| H05 | ✅ | 4/4 | deterministic | 88 | 1 | - |
| H06 | ✅ | 3/3 | deterministic | 90 | 0 | st_1_billing: permission_denied |
| H07 | ❌ | 1/2 | fanout | 89 | 3 | - |
| H08 | ✅ | 2/2 | fanout | 87 | 3 | - |
| H09 | ✅ | 3/3 | deterministic | 86 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 86 | 2 | - |
| H11 | ✅ | 3/3 | deterministic | 89 | 2 | st_1_lease: project_scope_denied |
| H12 | ✅ | 3/3 | deterministic | 86 | 0 | st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 86 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 86 | 1 | - |
| H15 | ❌ | 4/5 | fanout | 87 | 2 | - |
| H16 | ✅ | 3/3 | deterministic | 90 | 2 | st_1_property: project_scope_denied |
| H17 | ✅ | 1/1 | fanout | 87 | 3 | - |
| H18 | ❌ | 2/3 | deterministic | 87 | 1 | - |
| H19 | ❌ | 0/1 | deterministic | 88 | 2 | - |
| H20 | ❌ | 0/1 | deterministic | 89 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 87 | 2 | - |
| H22 | ✅ | 1/1 | deterministic | 120 | 2 | - |
| H23 | ✅ | 4/4 | fanout | 93 | 4 | - |
| H24 | ✅ | 5/5 | deterministic | 93 | 1 | - |
| H25 | — | 0/0 | deterministic | 91 | 1 | - |
| H26 | — | 0/0 | deterministic | 89 | 1 | - |
| H27 | ❌ | 0/1 | deterministic | 90 | 1 | - |
| H28 | ✅ | 2/2 | deterministic | 86 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 88 | 1 | - |
| H30 | ❌ | 1/2 | deterministic | 91 | 1 | - |
| H31 | ✅ | 8/8 | deterministic | 90 | 1 | - |
| H32 | ✅ | 8/8 | deterministic | 92 | 1 | - |

人工量表待评：

- H07: H07-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H07: H07-AN: 答案未提及任何金额: 17280.00, 34560.00, 51840.00
- H08: H08-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H08: H08-AN: 答案未提及任何金额: 18036.00, 34560.00, 52596.00
- H17: H17-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H17: H17-AN: 答案未提及任何金额: 18036.00, 34560.00, 52596.00
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
