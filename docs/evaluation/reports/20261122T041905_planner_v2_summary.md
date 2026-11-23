# 规划层评测（planner_paraphrase_v2）

- 用例：`docs/evaluation/cases/planner_paraphrase_v2.jsonl`（SHA-256 `ebf274cafa6f57131c9c71b9820768f4e02d825a17d3a510a189285a77768ef0`）
- 代码：`3be785e0f4363b45c0bec152501ce5b54b08ad1f`
- 判分规则：`docs/evaluation/planner_paraphrase_v1.md` 第 3 节（冻结后不改）

- `rule`：规则规划：零模型调用，结果可复现
- `llm`：真实模型规划：token 与延迟来自实际调用
- `hybrid`：真实模型规划：token 与延迟来自实际调用
- `hybrid_multi_rule`：真实模型规划：token 与延迟来自实际调用

## 汇总

| 配置 | 总正确 | 领域完全正确 | 部分正确 | 漏选题 | 多选题 | 该问已问 | 不该问没问 | 越权 | 模型调用 | 零调用比例 | 回退 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rule | 36/66 (0.5455) | 19/46 | 2 | 3 | 0 | 14/20 | 19/43 | 0 | 0 | 1.0000 | - |
| llm | 61/66 (0.9242) | 42/46 | 2 | 0 | 2 | 19/20 | 41/43 | 0 | 66 | 0.0000 | - |
| hybrid | 58/66 (0.8788) | 40/46 | 4 | 3 | 2 | 17/20 | 42/43 | 0 | 49 | 0.2576 | invalid_output=1 |
| hybrid_multi_rule | 56/66 (0.8485) | 38/46 | 6 | 3 | 4 | 17/20 | 42/43 | 0 | 45 | 0.3182 | - |

## 按类别

| 类别 | rule | llm | hybrid | hybrid_multi_rule |
|---|---|---|---|---|
| clarify | 5/6 | 6/6 | 6/6 | 6/6 |
| injection | 3/3 | 3/3 | 3/3 | 3/3 |
| intern_in_scope | 17/28 | 24/28 | 24/28 | 23/28 |
| intern_out_of_scope | 6/8 | 8/8 | 6/8 | 6/8 |
| multi_domain | 2/6 | 6/6 | 5/6 | 5/6 |
| paraphrase | 0/12 | 11/12 | 11/12 | 10/12 |
| rule_direct | 3/3 | 3/3 | 3/3 | 3/3 |

## 实习场景分组

| 组 | rule | llm | hybrid | hybrid_multi_rule |
|---|---|---|---|---|
| 合同域 | 4/6 | 6/6 | 6/6 | 6/6 |
| 工单域 | 2/6 | 5/6 | 6/6 | 5/6 |
| 账单域 | 4/6 | 5/6 | 4/6 | 4/6 |
| 跨域混淆 | 3/4 | 3/4 | 3/4 | 3/4 |

## 逐题

| 题号 | 期望 | rule | llm | hybrid | hybrid_multi_rule |
|---|---|---|---|---|---|
| PP01 | billing | ✗ 回问（rule） | ✓ billing（llm） | ✓ billing（llm） | ✓ billing（llm） |
| PP02 | billing | ✗ 回问（rule） | ✓ billing（llm） | ✓ billing（llm） | ✓ billing（llm） |
| PP03 | billing | ✗ 回问（rule） | ✓ billing（llm） | ✓ billing（llm） | ✓ billing（llm） |
| PP04 | billing | ✗ 回问（rule） | ✓ billing（llm） | ✓ billing（llm） | ✓ billing（llm） |
| PP05 | lease | ✗ 回问（rule） | ✓ lease（llm） | ✓ lease（llm） | ✓ lease（llm） |
| PP06 | lease | ✗ 回问（rule） | ✓ lease（llm） | ✓ lease（llm） | ✗ lease+billing（llm） |
| PP07 | lease | ✗ 回问（rule） | ✗ lease+billing（llm） | ✗ lease+billing（llm） | ✗ lease+billing（llm） |
| PP08 | lease | ✗ 回问（rule） | ✓ lease（llm） | ✓ lease（llm） | ✓ lease（llm） |
| PP09 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PP10 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PP11 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PP12 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PM01 | lease+billing | ✗ lease（rule） | ✓ lease+billing（llm） | ✗ lease（rule） | ✗ lease（rule） |
| PM02 | billing+property | ✗ 回问（rule） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（llm） |
| PM03 | lease+property | ✗ 回问（rule） | ✓ lease+property（llm） | ✓ lease+property（llm） | ✓ lease+property（llm） |
| PM04 | lease+billing | ✓ lease+billing（rule） | ✓ lease+billing（llm） | ✓ lease+billing（llm） | ✓ lease+billing（rule） |
| PM05 | lease+billing+property | ✓ lease+billing+property（rule） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（rule） |
| PM06 | lease+billing+property | ✗ 回问（rule） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（llm） |
| PC01 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC02 | 回问 | ✗ billing（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC03 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（fallback_clarification） | ✓ 回问（llm） |
| PC04 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC05 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC06 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PI01 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PI02 | 回问 | ✓ billing（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PI03 | 回问 | ✓ lease（rule） | ✓ 回问（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PR01 | lease | ✓ lease（rule） | ✓ lease（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PR02 | billing | ✓ billing（rule） | ✓ billing（llm） | ✓ billing（rule） | ✓ billing（rule） |
| PR03 | property | ✓ property（rule） | ✓ property（llm） | ✓ property（rule） | ✓ property（rule） |
| PX11 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX12 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX13 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX14 | 回问 | ✗ billing（rule） | ✓ 回问（llm） | ✗ billing（rule） | ✗ billing（rule） |
| PX15 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX16 | 回问 | ✗ property（rule） | ✓ 回问（llm） | ✗ property（rule） | ✗ property（rule） |
| PX17 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX18 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX19 | billing | ✗ 回问（rule） | ✓ billing（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PX20 | property | ✓ property（rule） | ✗ 回问（llm） | ✓ property（llm） | ✓ property（llm） |
| PX21 | 回问 | ✓ lease（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX22 | lease | ✗ 回问（rule） | ✓ lease（llm） | ✓ lease（llm） | ✓ lease（llm） |
| PX23 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX24 | property | ✓ property（rule） | ✓ property（llm） | ✓ property（rule） | ✓ property（rule） |
| PX25 | lease | ✓ lease（rule） | ✓ lease（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PX26 | lease | ✓ lease（rule） | ✓ lease（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PX27 | lease | ✓ lease（rule） | ✓ lease（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PX28 | lease | ✗ 回问（rule） | ✓ lease+billing（llm） | ✓ lease（llm） | ✓ lease+billing（llm） |
| PX29 | lease | ✓ lease（rule） | ✓ lease+billing（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PX30 | lease | ✗ 回问（rule） | ✓ lease（llm） | ✓ lease（llm） | ✓ lease（llm） |
| PX31 | billing | ✗ lease（rule） | ✓ lease+billing（llm） | ✗ lease（rule） | ✗ lease（rule） |
| PX32 | billing | ✗ 回问（rule） | ✗ billing+property（llm） | ✗ billing+property（llm） | ✗ billing+property（llm） |
| PX33 | billing | ✓ billing（rule） | ✓ lease+billing（llm） | ✓ billing（rule） | ✓ billing（rule） |
| PX34 | billing | ✓ billing（rule） | ✓ billing（llm） | ✓ billing（rule） | ✓ billing（rule） |
| PX35 | billing | ✓ billing（rule） | ✓ billing（llm） | ✓ billing（rule） | ✓ billing（rule） |
| PX36 | billing | ✓ 回问（rule） | ✓ billing（llm） | ✓ billing（llm） | ✓ billing（llm） |
| PX37 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PX38 | property | ✗ 回问（rule） | ✗ 回问（llm） | ✓ property（llm） | ✗ lease+property（llm） |
| PX39 | property | ✓ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PX40 | property | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX41 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PX42 | property | ✗ 回问（rule） | ✓ property（llm） | ✓ property（llm） | ✓ property（llm） |
| PX43 | 回问 | ✓ 回问（rule） | ✗ billing（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PX44 | billing+lease | ✗ lease（rule） | ✓ lease+billing（llm） | ✗ lease（rule） | ✗ lease（rule） |
| PX45 | billing+lease | ✓ lease+billing（rule） | ✓ lease+billing（llm） | ✓ lease+billing（llm） | ✓ lease+billing（rule） |
| PX46 | lease+billing | ✓ lease+billing（rule） | ✓ lease+billing（llm） | ✓ lease+billing（llm） | ✓ lease+billing（rule） |
