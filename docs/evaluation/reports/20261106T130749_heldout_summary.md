# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`43b48efddd385af88e509a176fe9253e8176ae49`
- 评分规则：`scoring-v2`
- 模型：`offline_deterministic` / `none`
- 生成时间：`2026-11-06T13:07:49.625798+00:00`

> 无 DEEPSEEK_API_KEY，三基线均未调用真实模型；token/成本指标不可用于质量结论

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| A_deterministic | 32 | 20/30 | 0.6667 | 0.7222 | 24/32 | 27 | 0 | 0 | n/a（离线） | 0 |
| B_single_agent | 32 | 21/30 | 0.7 | 0.7444 | 0/32 | 38 | 0 | 0 | n/a（离线） | 0 |
| C_multi_agent | 32 | 23/30 | 0.7667 | 0.8222 | 28/32 | 47 | 0 | 0 | n/a（离线） | 90 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## A_deterministic

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 7/7 | deterministic | 85 | 1 | - |
| H02 | ✅ | 7/7 | deterministic | 0 | 1 | - |
| H03 | ✅ | 7/7 | deterministic | 0 | 1 | - |
| H04 | ✅ | 7/7 | deterministic | 0 | 1 | - |
| H05 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H06 | ✅ | 3/3 | deterministic | 0 | 1 | permission_denied: 工具 'billing.statement.read' 需要权限 ['billing.read']，当前调用方不具备 |
| H07 | ❌ | 0/2 | deterministic | 1 | 1 | - |
| H08 | ❌ | 0/2 | deterministic | 0 | 1 | - |
| H09 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H10 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H11 | ✅ | 3/3 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H12 | ✅ | 3/3 | deterministic | 0 | 1 | permission_denied: 工具 'lease.lookup' 需要权限 ['lease.read']，当前调用方不具备 |
| H13 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H14 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H15 | ❌ | 2/3 | deterministic | 0 | 1 | - |
| H16 | ✅ | 3/3 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H17 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H18 | ❌ | 0/2 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H19 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H20 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H22 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H23 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H24 | ❌ | 0/4 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H25 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H26 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H27 | ✅ | 1/1 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H28 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H30 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H31 | ✅ | 6/6 | deterministic | 0 | 1 | - |
| H32 | ✅ | 6/6 | deterministic | 0 | 1 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## B_single_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 7/7 | single_agent | 80 | 1 | - |
| H02 | ✅ | 7/7 | single_agent | 0 | 1 | - |
| H03 | ✅ | 7/7 | single_agent | 0 | 1 | - |
| H04 | ✅ | 7/7 | single_agent | 0 | 1 | - |
| H05 | ✅ | 2/2 | single_agent | 0 | 1 | - |
| H06 | ✅ | 3/3 | single_agent | 0 | 1 | billing.statement.read: permission_denied |
| H07 | ❌ | 0/2 | single_agent | 1 | 1 | - |
| H08 | ❌ | 0/2 | single_agent | 0 | 1 | - |
| H09 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H10 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H11 | ✅ | 3/3 | single_agent | 0 | 1 | lease.lookup: project_scope_denied |
| H12 | ✅ | 3/3 | single_agent | 0 | 1 | lease.lookup: permission_denied |
| H13 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H14 | ❌ | 1/2 | single_agent | 0 | 1 | - |
| H15 | ✅ | 3/3 | single_agent | 0 | 2 | - |
| H16 | ✅ | 3/3 | single_agent | 0 | 1 | property.work_orders.read: project_scope_denied |
| H17 | ✅ | 1/1 | single_agent | 0 | 2 | - |
| H18 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H19 | ❌ | 0/1 | single_agent | 0 | 2 | - |
| H20 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H21 | ✅ | 2/2 | single_agent | 0 | 2 | - |
| H22 | ✅ | 1/1 | single_agent | 0 | 1 | - |
| H23 | ✅ | 2/2 | single_agent | 1 | 3 | - |
| H24 | ❌ | 1/3 | single_agent | 0 | 1 | - |
| H25 | — | 0/0 | single_agent | 0 | 1 | - |
| H26 | — | 0/0 | single_agent | 0 | 1 | - |
| H27 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H28 | ✅ | 2/2 | single_agent | 0 | 1 | - |
| H29 | ✅ | 1/1 | single_agent | 0 | 1 | - |
| H30 | ❌ | 1/2 | single_agent | 0 | 1 | - |
| H31 | ✅ | 6/6 | single_agent | 0 | 1 | - |
| H32 | ✅ | 6/6 | single_agent | 0 | 1 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率

## C_multi_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 7/7 | deterministic | 97 | 1 | - |
| H02 | ✅ | 7/7 | deterministic | 90 | 1 | - |
| H03 | ✅ | 7/7 | deterministic | 89 | 1 | - |
| H04 | ✅ | 7/7 | deterministic | 94 | 1 | - |
| H05 | ✅ | 2/2 | deterministic | 91 | 1 | - |
| H06 | ✅ | 3/3 | deterministic | 93 | 0 | st_1_billing: permission_denied; st_1_billing: permission_denied |
| H07 | ❌ | 1/2 | fanout | 93 | 3 | - |
| H08 | ✅ | 2/2 | fanout | 92 | 3 | - |
| H09 | ✅ | 3/3 | deterministic | 90 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 87 | 2 | - |
| H11 | ✅ | 3/3 | deterministic | 92 | 2 | st_1_lease: project_scope_denied; st_1_lease: project_scope_denied |
| H12 | ✅ | 3/3 | deterministic | 86 | 0 | st_1_lease: permission_denied; st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 85 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 84 | 1 | - |
| H15 | ❌ | 2/3 | fanout | 89 | 2 | - |
| H16 | ✅ | 3/3 | deterministic | 90 | 2 | st_1_property: project_scope_denied; st_1_property: project_scope_denied |
| H17 | ✅ | 1/1 | fanout | 86 | 3 | - |
| H18 | ❌ | 0/1 | deterministic | 84 | 1 | - |
| H19 | ❌ | 0/1 | deterministic | 85 | 2 | - |
| H20 | ❌ | 0/1 | deterministic | 119 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 90 | 2 | - |
| H22 | ✅ | 1/1 | deterministic | 89 | 2 | - |
| H23 | ✅ | 2/2 | fanout | 107 | 4 | - |
| H24 | ✅ | 3/3 | deterministic | 93 | 1 | - |
| H25 | — | 0/0 | deterministic | 90 | 1 | - |
| H26 | — | 0/0 | deterministic | 88 | 1 | - |
| H27 | ❌ | 0/1 | deterministic | 89 | 1 | - |
| H28 | ✅ | 2/2 | deterministic | 89 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 88 | 1 | - |
| H30 | ❌ | 1/2 | deterministic | 85 | 1 | - |
| H31 | ✅ | 6/6 | deterministic | 94 | 1 | - |
| H32 | ✅ | 6/6 | deterministic | 93 | 1 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
