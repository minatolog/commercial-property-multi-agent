# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v2.jsonl`（sha256 `acc384b4dd93f1c8…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`48c5b84a2ca5b6dbba1fd04e422cef34920472ab`
- 评分规则：`scoring-v1`
- 模型：`offline_deterministic` / `none`
- 生成时间：`2026-11-06T11:23:54.945242+00:00`

> 无 DEEPSEEK_API_KEY，三基线均未调用真实模型；token/成本指标不可用于质量结论

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| A_deterministic | 32 | 15/27 | 0.5556 | 0.6481 | 24/32 | 27 | 0 | 0 | n/a（离线） | 0 |
| B_single_agent | 32 | 16/27 | 0.5926 | 0.6975 | 0/32 | 38 | 0 | 0 | n/a（离线） | 0 |
| C_multi_agent | 32 | 23/27 | 0.8519 | 0.8704 | 28/32 | 47 | 0 | 0 | n/a（离线） | 87 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## A_deterministic

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 7/7 | deterministic | 77 | 1 | - |
| H02 | ✅ | 7/7 | deterministic | 0 | 1 | - |
| H03 | ✅ | 7/7 | deterministic | 0 | 1 | - |
| H04 | ✅ | 7/7 | deterministic | 0 | 1 | - |
| H05 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H06 | ❌ | 1/2 | deterministic | 0 | 1 | permission_denied: 工具 'billing.statement.read' 需要权限 ['billing.read']，当前调用方不具备 |
| H07 | ❌ | 0/2 | deterministic | 0 | 1 | - |
| H08 | ❌ | 0/2 | deterministic | 0 | 1 | - |
| H09 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H10 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H11 | ❌ | 1/2 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H12 | ❌ | 1/2 | deterministic | 0 | 1 | permission_denied: 工具 'lease.lookup' 需要权限 ['lease.read']，当前调用方不具备 |
| H13 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H14 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H15 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H16 | ❌ | 1/2 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H17 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H18 | ❌ | 0/1 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H19 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H20 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H22 | — | 0/0 | deterministic | 0 | 1 | - |
| H23 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H24 | ❌ | 0/3 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H25 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H26 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H27 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H28 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H30 | — | 0/0 | deterministic | 0 | 1 | - |
| H31 | ✅ | 6/6 | deterministic | 0 | 1 | - |
| H32 | ✅ | 6/6 | deterministic | 0 | 1 | - |

## B_single_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 7/7 | single_agent | 74 | 1 | - |
| H02 | ✅ | 7/7 | single_agent | 0 | 1 | - |
| H03 | ✅ | 7/7 | single_agent | 0 | 1 | - |
| H04 | ✅ | 7/7 | single_agent | 0 | 1 | - |
| H05 | ✅ | 2/2 | single_agent | 0 | 1 | - |
| H06 | ❌ | 1/2 | single_agent | 0 | 1 | billing.statement.read: permission_denied |
| H07 | ❌ | 0/2 | single_agent | 0 | 1 | - |
| H08 | ❌ | 0/2 | single_agent | 0 | 1 | - |
| H09 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H10 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H11 | ❌ | 1/2 | single_agent | 0 | 1 | lease.lookup: project_scope_denied |
| H12 | ❌ | 1/2 | single_agent | 0 | 1 | lease.lookup: permission_denied |
| H13 | ✅ | 3/3 | single_agent | 0 | 1 | - |
| H14 | ❌ | 1/2 | single_agent | 0 | 1 | - |
| H15 | ✅ | 3/3 | single_agent | 0 | 2 | - |
| H16 | ❌ | 1/2 | single_agent | 0 | 1 | property.work_orders.read: project_scope_denied |
| H17 | ✅ | 1/1 | single_agent | 0 | 2 | - |
| H18 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H19 | ❌ | 0/1 | single_agent | 0 | 2 | - |
| H20 | ❌ | 0/1 | single_agent | 0 | 1 | - |
| H21 | ✅ | 2/2 | single_agent | 0 | 2 | - |
| H22 | — | 0/0 | single_agent | 0 | 1 | - |
| H23 | ✅ | 2/2 | single_agent | 1 | 3 | - |
| H24 | ❌ | 1/3 | single_agent | 0 | 1 | - |
| H25 | — | 0/0 | single_agent | 0 | 1 | - |
| H26 | — | 0/0 | single_agent | 0 | 1 | - |
| H27 | — | 0/0 | single_agent | 0 | 1 | - |
| H28 | ✅ | 2/2 | single_agent | 0 | 1 | - |
| H29 | ✅ | 1/1 | single_agent | 0 | 1 | - |
| H30 | — | 0/0 | single_agent | 0 | 1 | - |
| H31 | ✅ | 6/6 | single_agent | 0 | 1 | - |
| H32 | ✅ | 6/6 | single_agent | 0 | 1 | - |

## C_multi_agent

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 7/7 | deterministic | 88 | 1 | - |
| H02 | ✅ | 7/7 | deterministic | 88 | 1 | - |
| H03 | ✅ | 7/7 | deterministic | 88 | 1 | - |
| H04 | ✅ | 7/7 | deterministic | 85 | 1 | - |
| H05 | ✅ | 2/2 | deterministic | 85 | 1 | - |
| H06 | ✅ | 1/1 | deterministic | 85 | 0 | st_1_billing: permission_denied; st_1_billing: permission_denied |
| H07 | ❌ | 1/2 | fanout | 89 | 3 | - |
| H08 | ✅ | 2/2 | fanout | 88 | 3 | - |
| H09 | ✅ | 3/3 | deterministic | 86 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 86 | 2 | - |
| H11 | ✅ | 1/1 | deterministic | 86 | 2 | st_1_lease: project_scope_denied; st_1_lease: project_scope_denied |
| H12 | ✅ | 1/1 | deterministic | 86 | 0 | st_1_lease: permission_denied; st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 90 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 93 | 1 | - |
| H15 | ✅ | 3/3 | fanout | 88 | 2 | - |
| H16 | ✅ | 1/1 | deterministic | 86 | 2 | st_1_property: project_scope_denied; st_1_property: project_scope_denied |
| H17 | ✅ | 1/1 | fanout | 86 | 3 | - |
| H18 | ❌ | 0/1 | deterministic | 88 | 1 | - |
| H19 | ❌ | 0/1 | deterministic | 88 | 2 | - |
| H20 | ❌ | 0/1 | deterministic | 112 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 86 | 2 | - |
| H22 | — | 0/0 | deterministic | 87 | 2 | - |
| H23 | ✅ | 2/2 | fanout | 90 | 4 | - |
| H24 | ✅ | 3/3 | deterministic | 84 | 1 | - |
| H25 | — | 0/0 | deterministic | 85 | 1 | - |
| H26 | — | 0/0 | deterministic | 85 | 1 | - |
| H27 | — | 0/0 | deterministic | 85 | 1 | - |
| H28 | ✅ | 2/2 | deterministic | 86 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 86 | 1 | - |
| H30 | — | 0/0 | deterministic | 87 | 1 | - |
| H31 | ✅ | 6/6 | deterministic | 88 | 1 | - |
| H32 | ✅ | 6/6 | deterministic | 87 | 1 | - |
