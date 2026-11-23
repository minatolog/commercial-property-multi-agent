# 评测报告

- 数据切分：`heldout`
- 用例文件：`docs\evaluation\cases\heldout_v3.jsonl`（sha256 `cf22fd467992f6c2…`）
- fixture sha256：`bcff5ce93b9b815c…`
- 代码提交：`c6037fe0359973ae0378fcc4167e08471f2faa14`（工作区 dirty）
- 评分规则：`scoring-v3.3`
- 模型：`deepseek` / `deepseek-flash`
- 生成时间：`2026-11-23T14:28:52.516227+00:00`

> 模型按各 Agent 自己的 YAML 配置创建（provider/model 为合集，逐 Agent 明细见 bindings.models_by_agent）；model_name 为配置名，服务端实际应答模型见 models_by_agent.*.served_models；token 与延迟来自实际调用；成本未内置定价，故不换算金额

## 汇总

| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| C_multi_agent | 32 | 15/30 | 0.5 | 0.8082 | 27/32 | 76 | 93 | 183754 | n/a（未内置定价） | 5485 |

> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。

## 指标分解（工具事实 / 资金结论 / 金额接地）

| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | 未验证题 | 金额接地（辅助） |
|---|---|---|---|---|---|---|
| C_multi_agent | 33 | 0.9091 | 12 | 0.4167 | 1 | 13/13 |

> 工具事实准确率回答"取数对不对"；资金结论通过率回答"用户读到的应收/已收/未收对不对"；未验证题表示叙述没有把金额绑定到字段（**不算通过**）；金额接地是辅助检查，不能单独证明答案准确。

## 各 Agent 实际模型（models_by_agent）

### C_multi_agent

| Agent | provider | 配置模型名 | 实际应答模型 | temperature | max_tokens | timeout(s) | 共享客户端 | 配置来源 |
|---|---|---|---|---|---|---|---|---|
| billing | deepseek | deepseek-flash | deepseek-flash | None | 1024 | 20.0 | 是 | billing.yaml |
| lease | deepseek | deepseek-flash | deepseek-flash | 0.1 | 2048 | 30.0 | 否 | lease.yaml |
| property | deepseek | deepseek-flash | deepseek-flash | None | 1024 | 20.0 | 是 | property.yaml |
| single | deepseek | deepseek-flash | 未记录 | 0.0 | 1024 | 60.0 | 否 | single.yaml |

## C_multi_agent（规划模式：hybrid）

| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |
|---|---|---|---|---|---|---|
| H01 | ✅ | 9/9 | deterministic | 5485 | 2 | - |
| H02 | ❌ | 8/9 | deterministic | 5287 | 2 | - |
| H03 | ❌ | 7/9 | deterministic | 3516 | 2 | - |
| H04 | ❌ | 8/9 | deterministic | 4387 | 2 | - |
| H05 | ❌ | 3/4 | deterministic | 4270 | 2 | - |
| H06 | ✅ | 3/3 | deterministic | 166 | 0 | st_1_billing: permission_denied |
| H07 | ❌ | 3/4 | fanout | 9136 | 7 | - |
| H08 | ✅ | 4/4 | fanout | 12434 | 6 | - |
| H09 | ✅ | 3/3 | deterministic | 2890 | 2 | - |
| H10 | ✅ | 3/3 | deterministic | 3108 | 2 | - |
| H11 | ❌ | 1/3 | deterministic | 7601 | 4 | st_1_lease: insufficient_evidence |
| H12 | ✅ | 3/3 | deterministic | 141 | 0 | st_1_lease: permission_denied |
| H13 | ✅ | 3/3 | deterministic | 3690 | 1 | - |
| H14 | ✅ | 2/2 | deterministic | 3615 | 1 | - |
| H15 | ❌ | 3/5 | fanout | 19427 | 7 | - |
| H16 | ❌ | 1/3 | deterministic | 10678 | 2 | st_1_property: insufficient_evidence |
| H17 | ✅ | 1/1 | deterministic | 10196 | 3 | - |
| H18 | ❌ | 1/2 | deterministic | 12325 | 2 | - |
| H19 | ✅ | 1/1 | deterministic | 7119 | 2 | - |
| H20 | ❌ | 0/1 | deterministic | 5686 | 1 | - |
| H21 | ✅ | 2/2 | deterministic | 7710 | 2 | - |
| H22 | ✅ | 1/1 | deterministic | 8254 | 3 | - |
| H23 | ❌ | 3/4 | fanout | 9701 | 9 | - |
| H24 | ❌ | 4/5 | deterministic | 11152 | 2 | - |
| H25 | — | 0/0 | clarification | 2172 | 0 | - |
| H26 | — | 0/0 | fanout | 9710 | 2 | st_1_lease: permission_denied |
| H27 | ✅ | 1/1 | clarification | 1719 | 0 | - |
| H28 | ✅ | 2/2 | deterministic | 6745 | 2 | - |
| H29 | ❌ | 1/2 | clarification | 4733 | 0 | - |
| H30 | ❌ | 1/2 | deterministic | 4150 | 2 | - |
| H31 | ✅ | 8/8 | deterministic | 2184 | 2 | - |
| H32 | ❌ | 7/8 | deterministic | 3792 | 2 | - |

人工量表待评：

- H18: H18-FN: 叙述没有把金额绑定到应收/已收/未收字段，无法核对
- H25: H25: 该题声明为人工评定（scorable=false），不参与自动通过率
- H26: H26: 该题声明为人工评定（scorable=false），不参与自动通过率
