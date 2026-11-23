# ADR-006：混合规划器（规则快速路径 + LLM Supervisor）

- **日期**：2026-11-22
- **状态**：已实施（Task 034）；DeepSeek 独立复查有条件通过，返修经 [返修确认复查](../reviews/2026-11-22_task032_034_repair_review.md)确认条件已满足（2026-11-23，不等于最终验收）；真实模型对照已运行 1 次（配置为 deepseek-flash，v2 66 题；服务端实际应答模型未记录）
- **任务**：034（[归档](../prompts/04_agents/2026-11-22_034_llm_supervisor_planner.md)）
- **影响**：[system_design.md](../architecture/system_design.md)、[agent_runtime_contracts.md](../architecture/agent_runtime_contracts.md)、[planner_vocabulary.md](../architecture/planner_vocabulary.md)

## 1. 背景

`RuleBasedPlanner` 用词表子串匹配决定派哪些领域 Agent。它可复现、零成本，但本质是 Workflow：用户换一种说法（“这家店上个月的钱交齐了吗？”“师傅到底去了没？”）就命不中词表，落到回问；词表里的词出现在无关语境里（“我欠你一顿饭”“会议纪要里的核销”）又会误派。项目所有者用实习时同事的真实问法补的 36 道题里，工单类 6 题规则只答对 2 题（还是靠“回问也可接受”）。

## 2. 决策

新增 `LLMSupervisorPlanner`，与规则规划器组成**混合规划**（`HybridPlanner`），三种模式由 `app/config/planner.yaml` 的 `mode` 选择，**默认 `rule`**：

```text
rule   词表规则（零模型调用）——默认，行为与 Task 034 之前完全一致
llm    每题由 Supervisor 规划
hybrid 规则命中恰好 1 个领域且无歧义信号 → 用规则
       规则命中多个领域、无歧义 → hybrid_multi_domain=rule 用规则 / =llm 交给 Supervisor
       规则 0 命中或有歧义信号 → 交给 Supervisor
```

为什么是混合而不是纯 LLM：

1. **简单题不该花钱、不该有随机性**。“A-301 还有多少钱没交？”规则一次命中，交给模型只增加成本、延迟和不确定性；hybrid 在这类题上断言零模型调用。
2. **模型的价值在规则的盲区**：改写问法、口语、多意图、无关请求。把模型放在这里，才能用数据回答“什么时候该用哪个”。
3. **失败必须有确定的退路**。模型不可用时回到规则结果，规则也无法判断时回问——不会因为规划模型挂掉而让整条调查失败或乱派。

“是否需要模型”本身由**确定性**的歧义信号判定（否定词、指代别家、铺位号与可信目标不一致、过短、只命中单字词），不让模型判断“要不要用模型”。

## 3. 安全边界

| 约束 | 实现 |
|---|---|
| 模型只能选领域 | `SupervisorPlan`（Pydantic，`extra="forbid"`）的 `domains` 只接受 `lease / billing / property`；能力名由 `DOMAIN_CAPABILITIES` 映射 |
| 目标只来自可信上下文 | 模型输出里的 `lease_id / unit_id / …` 一律剥离并告警；理由/回问里提到别的铺位号或租约号同样告警；子任务目标只取自可信 payload（与 Z1 一致） |
| 问题是数据不是指令 | 用户问题放在 `user_question` 字段；System Prompt 写明不得执行其中的指令；注入用例（提权、换目标、调用不存在的工具）零越权 |
| 子任务构造单一实现 | 规则与 LLM 共用 `build_domain_subtasks`：同样的领域选择得到同样的子任务 |
| 预算共享 | 规划调用计入同一个 `Budget`（模型调用次数与 token），超限按 `budget_exhausted` 回退 |
| 输出方式 | 唯一的 `submit_plan` 工具；只给文本、调别的工具、调多次、参数非法都判 `invalid_output` |

## 4. 回退原则

| 情况 | `fallback_reason` | 结果 |
|---|---|---|
| 没有规划模型 | `model_unavailable` | 规则有结果 → `fallback_rule`；否则 `fallback_clarification` |
| 模型抛异常 | `model_error` | 同上 |
| 超时（`timeout_seconds`） | `timeout` | 同上 |
| 输出非法 | `invalid_output` | 同上 |
| 模型调用 / token 预算耗尽 | `budget_exhausted` | 同上（超限 token 如实记账） |

回退一律写进报告 `planning`，并进入运行告警；不静默。

## 5. 成本

- `rule`：0 次模型调用。
- `hybrid`：规则能确定的题 0 次，其余每题 1 次；`planner_paraphrase_v1` 离线统计零调用比例 16.7%（`hybrid_multi_domain=rule` 为 23.3%），heldout 的常规问题绝大多数含词表词，比例会高得多。
- `llm`：每题 1 次（约 1k–1.5k token：System Prompt + `submit_plan` schema + 问题）。
- 规划模型来源与领域 Agent 引擎分开（`--planner-provider`），真实模型可以只做规划，领域 Agent 仍用确定性引擎。优先级：给了 `--planner-provider` 就用它；省略时沿用 `--model-provider`；两者都没有模型（`offline`）而 `--planner` 为 llm/hybrid 时以用法错误退出（exit 2）。这是 Task 034 Prompt 字面之外的加法（复查 P3-5）。

## 5a. 真实模型数据（2026-11-22，单次运行）

| 配置 | 正确 | 越权 | 模型调用 | token |
|---|---|---|---|---|
| rule | 36/66 | 0 | 0 | 0 |
| llm | 61/66 | 0 | 66 | 108,172 |
| hybrid（multi=llm） | 58/66 | 0 | 49 | 80,348 |
| hybrid（multi=rule） | 56/66 | 0 | 45 | 74,724 |

hybrid 相对 llm 省 26% 调用、少 3 题，丢分**主要**来自“规则单领域直通 / 误命中直通”，另有 PX19 是规则零命中后升级、模型回问而丢分（multi=rule 组的 PX38 是模型多派 lease）。单次运行存在同题不同答，组间小差距需重复测量后再下结论。详见 [Task 034 归档 §7.5](../prompts/04_agents/2026-11-22_034_llm_supervisor_planner.md)。

## 6. 不做的事

- API / 网页本任务不改（WorkflowService 保持规则规划，留给 Task 032）。
- 不把词表塞进 Supervisor 的 Prompt（否则退化成让模型做关键词匹配）。
- 离线 scripted 规划模型按词表给计划，只证明链路与回退；模型规划质量要等真实模型对照（需用户授权与预算）。
