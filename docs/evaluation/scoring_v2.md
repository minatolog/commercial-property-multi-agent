# 评测评分规则（scoring-v2，已冻结）

> **已被 `scoring_v3.md` 取代（Task 021 / N6）**：v3 增加"最终答案准确性"断言。
> 本文件与 v2 报告全部保留，作为历史口径。
> **继承关系**：本版取代 `scoring_v1.md`。v1 的规则与报告全部保留，不得覆盖。
> **冻结声明**：本文件在生成保留集 `heldout_v3.jsonl` **之前**定稿。
> 版本号 `scoring-v2` 写入每份报告；任何判定逻辑变更都必须提升版本并另建报告。

## 0. 为什么升到 v2（对应审查 F1 / F2）

| 缺陷 | v1 行为 | v2 行为 |
|---|---|---|
| **F1** 金额评分不绑定字段 | 把答案与全部事实拼成一个字符串做子串匹配，三个金额互换仍满分 | 按 `expected_facts[key]` **逐字段**比较；金额用 `Decimal` 比到 `0.01` |
| **F2** 预期拒绝被判失败 | 任何 `status=denied` 无条件加一条失败断言；C 用 `failed` 状态绕过同样扣分 | 用例显式声明 `expected_outcome`；三条基线用**同一套**状态推导（拒绝=`denied`、其它失败=`failed`） |

## 1. 三基线定义（未变）

| 基线 | 架构 | 明确不做 |
|---|---|---|
| `A_deterministic` | 意图表 → 单次只读工具调用 | 不拆任务、不交叉核验、不发起审批 |
| `B_single_agent` | 一个 Agent 汇总所有适用工具 | 不做角色分解、不做冲突核验、不发起审批 |
| `C_multi_agent` | LangGraph：规划 → 并发子 Agent → 确定性核验 → 审批门 | 不执行任何业务写操作 |

三条基线共用：同一 fixture、同一套只读工具白名单、同一 `max_tool_calls`。

**状态语义（v2 统一）**：

- `ok`：产出了至少一个结构化事实；
- `denied`：没有事实，且**所有**错误都是 `permission_denied` / `project_scope_denied`；
- `failed`：其它没有事实的情况（含意图不明、工具异常、预算耗尽）。

## 2. 自动断言（计入 correctness）

| kind | 判定 |
|---|---|
| `facts` | `expected_facts[key]` 必须**等于**基线 `facts[key]`：金额 → `Decimal` 到分；布尔 → 真值；列表 → 集合；其余 → 去空白字符串全等 |
| `evidence` | `required_evidence_ids` 全部出现；`forbidden_substrings` 不得出现在答案或事实中 |
| `outcome` | 由 `expected_outcome` 判定：`ok` → 不得 denied/failed；`denied` → 必须 denied（可选 `expected_error_code` 精确核对）；`failed` → 必须 failed |
| `approval` | `expected_approval.status` / `draft_version` 必须一致 |

**字段比较的硬规则**：

1. 只在**同名字段**间比较，绝不使用"这个数字在文本里出现过"；
2. 金额只接受可解析为 `Decimal` 的值，`52596.009` 不等于 `52596.00`；
3. 基线未提供该字段 → 判失败，说明写"基线未提供该字段"；
4. 用例声明了基线事实契约（`BASELINE_FACT_VOCABULARY`）之外的键 → 该断言**不进分母**，
   只进 `manual_queue`，说明写"基线事实契约未定义键…，转人工核对"。

第 4 条为什么不判失败：`BASELINE_FACT_VOCABULARY` 记录的是"基线确实会产出的字段"。
开发集（`smoke_v1.jsonl`）是为人工量表写的，含 `verdict`、`valid_paid_total` 这类
基线不产出的键；若把它们记成答错，一道只因契约缺口而缺字段的题就会变成 `0/N`，
报告会被读成"实现全面失败"。契约缺口必须被看见，但不能混进准确率分母。
"键在契约内但基线没给值"仍然判失败——那是基线该做没做。

## 3. 效率指标（不计入 correctness）

`route_in_allowed`、延迟、工具调用数、模型调用数、token。路由命中永远只作效率参考。

## 4. 人工量表

`kind="rubric"` 与 `scorable=false` 的用例全部进入 `manual_queue`，自动报告只列待评项。

**`scorable=false` 必须显式声明在数据集里**（v3 起），而不是"恰好没有断言"——
这样报告的"未计分题数"是可解释的，而不是数据缺口。

## 5. 成本口径

- 离线：`provider=offline_deterministic`、`total_tokens=0`、`cost_amount=null`、
  `cost_basis=unavailable_offline_no_pricing`；
- 真实模型：必须记录 provider / model / temperature / max_tokens / 重复次数，批次内不得改配置；
- **禁止**把离线结果写成真实模型的质量或成本。

## 6. 数据切分

| 文件 | 题数 | 说明 |
|---|---|---|
| `cases/smoke_v1.jsonl` | 8 | 开发题（Task 006 冻结，结构较老） |
| `cases/heldout_v1.jsonl` | 32 | 作废（期望值缺陷） |
| `cases/heldout_v2.jsonl` | 32 | 已跑过 v1 评分器，保留历史 |
| `cases/heldout_v3.jsonl` | 32 | **当前版本**：新增 `expected_outcome` / `scorable`，补齐 H22/H27/H30 断言 |

保留集 v3 的可计分题数为 30（H25/H26 声明为人工评定）。

> v2 的报告（A 15/27、B 16/27、C 23/27）是 `scoring-v1` 下的结果，**与 v3 不可比**：
> 规则变了（字段绑定、结局断言），题目也变了（多 5 项可判定断言、2 题显式转人工）。
> v3 在 `scoring-v2` 下为 A 20/30、B 21/30、C 23/30。

## 7. 与历史报告的关系

| 报告 | 评分版本 | 数据 |
|---|---|---|
| `20261106T111758_dev_*`、`20261106T112354_heldout_*` | scoring-v1 | v2 |
| 本次新增（scoring-v2） | scoring-v2 | v3（heldout） |

**不得**用 v2 报告与 v1 报告做"提升/下降"对比：评分规则与数据集都变了。
