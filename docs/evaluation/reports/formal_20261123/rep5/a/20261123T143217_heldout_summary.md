# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`c6037fe0359973ae0378fcc4167e08471f2faa14`（工作区 dirty）
- 评分规则：`scoring-v3.3`
- 模型：`offline_deterministic` / `none`
- 生成时间：`2026-11-23T14:32:17.712840+00:00`

> 本报告未调用任何模型（确定性规则路径）；token/成本不适用

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| A_deterministic | 32 | 20/30 | 0.6667 | 0.7267 | 24/32 | 27 | 0 | 0 | n/a（离线） | 0 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## 指标分解（工具事实 / 资金结论 / 金额接地）

| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| A_deterministic | 33 | 0.8485 | 9 | 1.0 | 0 | 9/9 |

> 工具事实准确率回答"取数对不对"；资金结论通过率回答"用户读到的应收/已收/未收对不对"；未验证题表示叙述没有把金额绑定到字段（**不算通过**）；金额接地是辅助检查，不能单独证明答案准确。

## 各 Agent 实际模型（models_by_agent）

- `A_deterministic`：离线 = 确定性引擎，无模型参与（`models_by_agent` 为空）
> 本次全部基线均为离线确定性引擎，没有调用任何模型；`models_by_agent` 为空表示"无模型参与"，不是"未记录"。

## A_deterministic

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | deterministic | 106 | 1 | - |
| H02 | ✅ | 9/9 | deterministic | 1 | 1 | - |
| H03 | ✅ | 9/9 | deterministic | 1 | 1 | - |
| H04 | ✅ | 9/9 | deterministic | 1 | 1 | - |
| H05 | ✅ | 4/4 | deterministic | 1 | 1 | - |
| H06 | ✅ | 3/3 | deterministic | 0 | 1 | permission_denied: 工具 'billing.statement.read' 需要权限 ['billing.read']，当前调用方不具备 |
| H07 | ❌ | 0/2 | deterministic | 1 | 1 | - |
| H08 | ❌ | 0/2 | deterministic | 0 | 1 | - |
| H09 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H10 | ✅ | 3/3 | deterministic | 0 | 1 | - |
| H11 | ✅ | 3/3 | deterministic | 1 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H12 | ✅ | 3/3 | deterministic | 0 | 1 | permission_denied: 工具 'lease.lookup' 需要权限 ['lease.read']，当前调用方不具备 |
| H13 | ✅ | 3/3 | deterministic | 1 | 1 | - |
| H14 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H15 | ❌ | 4/5 | deterministic | 1 | 1 | - |
| H16 | ✅ | 3/3 | deterministic | 0 | 1 | project_scope_denied: 无权访问租约（项目 'prj_jinlan' 不在可信上下文的项目范围内） |
| H17 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H18 | ❌ | 0/2 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H19 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H20 | ❌ | 0/1 | deterministic | 0 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H22 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H23 | ✅ | 4/4 | deterministic | 1 | 1 | - |
| H24 | ❌ | 0/4 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H25 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H26 | — | 0/0 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H27 | ✅ | 1/1 | deterministic | 0 | 0 | 未能识别意图（确定性基线不做猜测） |
| H28 | ✅ | 2/2 | deterministic | 0 | 1 | - |
| H29 | ✅ | 1/1 | deterministic | 0 | 1 | - |
| H30 | ❌ | 1/2 | deterministic | 0 | 1 | - |
| H31 | ✅ | 8/8 | deterministic | 1 | 1 | - |
| H32 | ✅ | 8/8 | deterministic | 1 | 1 | - |

人工量表待评：

- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
