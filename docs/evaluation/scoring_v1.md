# 评测评分规则（scoring-v1，已冻结）

> **冻结声明**：本文件在生成保留集（`heldout_v1.jsonl`）**之前**定稿。
> 版本号 `scoring-v1` 写入每份报告；任何判定逻辑变更都必须提升版本，并另建报告，不覆盖历史结果。
> 保留集运行后**不得**根据其结果回头修改本题或 Prompt。

## 1. 三基线定义

| 基线 | 架构 | 基准行为 | 明确不做 |
|---|---|---|---|
| `A_deterministic` | 意图表 → 单次只读工具调用 | 取数并模板化陈述 | 不拆任务、不交叉核验、不发起审批 |
| `B_single_agent` | 一个 Agent 汇总所有适用工具 | 多工具汇总成一个答案 | 不做角色分解、不做冲突核验、不发起审批 |
| `C_multi_agent` | LangGraph：规则规划 → 并发子 Agent → 确定性核验 → 审批门 | 分解、并发、核验、缺失标注、可选审批 | 不执行任何业务写操作 |

三条基线共用：同一 fixture、同一套只读工具白名单、同一 `max_tool_calls`（默认 12）。

## 2. 自动断言（计入 correctness）

| kind | 判定 | 说明 |
|---|---|---|
| `facts` | `expected_facts` 中每个 `key=value` 必须在基线 facts 或答案文本中**精确出现** | 金额按字符串比较，允许 `18036.00` 但不容忍 `约 1.8 万` |
| `evidence` | `required_evidence_ids` 全部出现在证据集合；`forbidden_substrings` 不得出现 | 证据缺失一律判败 |
| `evidence`（状态） | 基线状态为 `denied`/`failed` 时，记一条失败断言 | 权限被拒是预期行为时，该题不应包含 `expected_facts` |
| `approval` | `expected_approval.status` / `draft_version` 必须一致 | 只对需要审批的题生效 |

**单题 `correctness_rate` = 通过断言数 / 自动断言总数**；`passed` 要求全部通过。

## 3. 效率指标（不计入 correctness）

- `route_in_allowed`：基线路由是否落在 `allowed_routes` 内，**只作效率指标**；
- 延迟（`latency_ms`，P50 / max）、工具调用数、模型调用数、token。

历史教训：把"该走确定性路径"当成"答案正确"会让多 Agent 基线因为多拆一步而被误判，反之亦然。

## 4. 人工量表（不计入自动通过率）

`kind="rubric"` 的断言全部进入 `manual_queue`，由人工逐条评。自动报告只列出待评项，不给结论。

## 5. 成本口径

- 离线运行（无 `DEEPSEEK_API_KEY`）：`model.provider=offline_deterministic`，`total_tokens` 恒为 0，
  `cost_amount=null`、`cost_basis=unavailable_offline_no_pricing`；
- 真实模型运行必须记录：`provider`、`model_name`、`temperature`、`max_tokens`、重复次数，
  并且**同一批次内不得改配置**；
- **禁止**把 Fake/离线结果写成真实模型的成本或质量。

## 6. 数据切分

| 文件 | 题数 | 使用规则 |
|---|---|---|
| `cases/smoke_v1.jsonl` | 8 | 开发题：写 Prompt、调工具时可用 |
| `cases/heldout_v1.jsonl` | 32 | 保留题：冻结后只跑不改，跑完不据此调 Prompt |

两份数据都从 `fixtures/agent_first_v1.json` 的**合成数据**派生；期望事实由生成脚本从 fixture 计算，
不手抄金额，避免"答案是人拍脑袋写的"。

## 7. 判定失败的常见原因（写在这里避免争议）

1. 工具被权限拒绝 → `denied`，证据全缺 → 失败；
2. 证据 ID 对但页码/条款错 → 由 `evidence` 断言暴露（`document_clause` 证据 ID 含页码与条款号）；
3. 结论正确但用了禁用表述（如"约"） → `forbidden_substrings` 判败；
4. 该请求审批却直接给出结论 → `approval` 断言判败。
