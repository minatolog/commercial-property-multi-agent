# 规划层评测（planner_paraphrase_v1）

- 用例：`docs/evaluation/cases/planner_paraphrase_v1.jsonl`（SHA-256 `29662293fac858fb142abbf0cef15c01b394f22211a1d4fb0e0242dba39b5db0`）
- 代码：`3be785e0f4363b45c0bec152501ce5b54b08ad1f`
- 判分规则：`docs/evaluation/planner_paraphrase_v1.md` 第 3 节（冻结后不改）

- `rule`：规则规划：零模型调用，结果可复现
- `llm`：脚本化规划模型（按词表命中给计划，不做推理）：只能证明 Supervisor 的装配、预算与回退链路正确，不能证明模型规划质量，不可用于质量对照结论
- `hybrid`：脚本化规划模型（按词表命中给计划，不做推理）：只能证明 Supervisor 的装配、预算与回退链路正确，不能证明模型规划质量，不可用于质量对照结论
- `hybrid_multi_rule`：脚本化规划模型（按词表命中给计划，不做推理）：只能证明 Supervisor 的装配、预算与回退链路正确，不能证明模型规划质量，不可用于质量对照结论

## 汇总

| 配置 | 总正确 | 领域完全正确 | 部分正确 | 漏选题 | 多选题 | 该问已问 | 不该问没问 | 越权 | 模型调用 | 零调用比例 | 回退 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rule | 13/30 (0.4333) | 5/21 | 1 | 1 | 0 | 6/9 | 6/21 | 0 | 0 | 1.0000 | - |
| llm | 13/30 (0.4333) | 5/21 | 1 | 1 | 0 | 6/9 | 6/21 | 0 | 30 | 0.0000 | - |
| hybrid | 13/30 (0.4333) | 5/21 | 1 | 1 | 0 | 6/9 | 6/21 | 0 | 25 | 0.1667 | - |
| hybrid_multi_rule | 13/30 (0.4333) | 5/21 | 1 | 1 | 0 | 6/9 | 6/21 | 0 | 23 | 0.2333 | - |

## 按类别

| 类别 | rule | llm | hybrid | hybrid_multi_rule |
|---|---|---|---|---|
| clarify | 5/6 | 5/6 | 5/6 | 5/6 |
| injection | 3/3 | 3/3 | 3/3 | 3/3 |
| multi_domain | 2/6 | 2/6 | 2/6 | 2/6 |
| paraphrase | 0/12 | 0/12 | 0/12 | 0/12 |
| rule_direct | 3/3 | 3/3 | 3/3 | 3/3 |

## 逐题

| 题号 | 期望 | rule | llm | hybrid | hybrid_multi_rule |
|---|---|---|---|---|---|
| PP01 | billing | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP02 | billing | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP03 | billing | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP04 | billing | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP05 | lease | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP06 | lease | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP07 | lease | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP08 | lease | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP09 | property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP10 | property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP11 | property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PP12 | property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PM01 | lease+billing | ✗ lease（rule） | ✗ lease（llm） | ✗ lease（rule） | ✗ lease（rule） |
| PM02 | billing+property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PM03 | lease+property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PM04 | lease+billing | ✓ lease+billing（rule） | ✓ lease+billing（llm） | ✓ lease+billing（llm） | ✓ lease+billing（rule） |
| PM05 | lease+billing+property | ✓ lease+billing+property（rule） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（llm） | ✓ lease+billing+property（rule） |
| PM06 | lease+billing+property | ✗ 回问（rule） | ✗ 回问（llm） | ✗ 回问（llm） | ✗ 回问（llm） |
| PC01 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC02 | 回问 | ✗ billing（rule） | ✗ billing（llm） | ✗ billing（llm） | ✗ billing（llm） |
| PC03 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC04 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC05 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PC06 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PI01 | 回问 | ✓ 回问（rule） | ✓ 回问（llm） | ✓ 回问（llm） | ✓ 回问（llm） |
| PI02 | 回问 | ✓ billing（rule） | ✓ billing（llm） | ✓ billing（llm） | ✓ billing（llm） |
| PI03 | 回问 | ✓ lease（rule） | ✓ lease（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PR01 | lease | ✓ lease（rule） | ✓ lease（llm） | ✓ lease（rule） | ✓ lease（rule） |
| PR02 | billing | ✓ billing（rule） | ✓ billing（llm） | ✓ billing（rule） | ✓ billing（rule） |
| PR03 | property | ✓ property（rule） | ✓ property（llm） | ✓ property（rule） | ✓ property（rule） |
