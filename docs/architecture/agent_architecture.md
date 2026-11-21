# Agent 架构设计（当前版）

- 更新：2026-11-21，Task 031。
- 依据：[当前基线](CURRENT_BASELINE.md)、[ADR-005](../decisions/ADR-005-agent-first-refocus.md)。
- 整理前的概念设计、风险和旧示例：[历史快照](agent_architecture_legacy_2026-11-09.md)。

## 1. 协作方式

Agent 通过 AgentProtocol、Registry 和结构化结果协作；互不引用对方实现。Coordinator 依据能力而非具体类名调度。项目采用模块化单体，不要求热插拔、微服务或 Agent Marketplace。

| 角色 | P0 职责 | 实现 |
|---|---|---|
| Coordinator | 选择能力、短路径/并发路由、有限补查；未命中领域时回问 | RuleBasedPlanner / LangGraph，规则实现；词表见 [planner_vocabulary](planner_vocabulary.md) |
| Lease | 租约与合同条款证据 | 确定性 Agent + LLM Agent |
| Billing | 账单/付款/欠费事实 | 确定性 Agent + LLM Agent；金额来自 Decimal 工具 |
| Property | 工单与维修事实 | 确定性 Agent + LLM Agent |
| Single | 同一组受控工具的单 Agent 路径 | SingleToolAgent；`ask` 由装配层解析并注入可信目标（Task 031 / Z1），失败/越界调用不计取证（Z2） |
| Verifier | 完成条件、缺失、冲突、金额/证据核验 | 确定性节点，不必另起 LLM |
| Human Approval | 物业→财务两名不同主体串行审批草案 | 独立节点与台账；批准后仍不执行业务写操作 |
| Compliance | 扩展占位 | 保留、默认禁用，不作为 P0 必须实现的第四业务 Agent；业务逻辑未实现（`NOT_IMPLEMENTED`） |

## 2. 接口与工厂

agents/base/contracts.py 定义 AgentRequest、AgentContext、AgentOutput、AgentResult 和 TaskStatus。子类 _execute() 返回 AgentOutput，BaseAgent.handle() 统一包装结果、错误与元数据。Runtime 的可信边界在 runtime/types.py 和 agent_runtime.py。

静态工厂有 AGENT_IMPLEMENTATIONS 和 AGENT_LLM_IMPLEMENTATIONS 两张表。新增一种实现时登记所需引擎，不能从 YAML 动态 import。工厂校验 YAML 的 version/capabilities 与实现声明一致；Registry 区分缺失、禁用和能力冲突，并支持受控替换。

Task 031 起，llm 引擎按 Agent 名注入各自的模型客户端（`build_registry(model_clients=...)`），缺少客户端时显式失败而不是回退到某个全局实例。

字段、预算与状态语义只在 [agent_runtime_contracts.md](agent_runtime_contracts.md) 维护，避免重复的 V1/V2 定义。

## 3. 配置独立性及当前限制

每个 Agent 有独立 YAML 和 Prompt。enabled、allowed_tools、执行超时/重试等由相关代码消费；修改后需重建装配并做回归，不承诺在运行中热更新。

**每 Agent 独立模型配置已实现（Task 031 / 2.5，待独立复查）**：`llm/factory.py` 按各 Agent 自己的 YAML 创建客户端（provider、model_name、temperature、max_tokens、api_key_env、timeout），参数完全相同的客户端通过缓存共享，缓存键包含全部影响行为的参数；未知 provider、缺 `api_key_env`、参数越界在启动期失败，不回退。`InvestigationBundle.agent_models` 与评测 `BaselineResult.models_by_agent` 按 Agent 记录实际 provider/model/参数。当前 YAML 的模型名为 `deepseek-flash`（官方文档核对：`deepseek-chat` 已于 2026-07-24 下线）。

`retrieval_settings` 只接受当前真实实现的能力：`enabled` 与 `top_k`（检索实现只有 BM25）。向量库（chroma）、嵌入模型（bge）、rerank/混合权重等**未实现**，已从 Schema 移除；声明即加载失败，未来计划写进文档而不是运行配置。`top_k` 当前是声明值，检索工具的实际条数由调用 payload 决定。

## 4. 低耦合边界与已知缺口

Agent 只通过受控执行器使用工具。工具负责类型化输入输出，业务数据来自只读仓库，知识来自 KnowledgeService。目标中的独立 Business Service 层尚未完整实现；后续业务规则应按 [系统架构](system_design.md) 收敛。

改一个 Agent 的 Prompt 或实现，应只影响该 Agent 与相关工作流；修改公共契约、工厂或共享工具则需扩大回归范围。新增/禁用/替换的操作规范见 [开发指南](agent_development_guide.md)。

取证与用户可见结论的边界（Task 031）：只有"执行成功且输出属于本次可信目标"的调用才算取证；失败/被拒绝/超预算/超时/越界只作审计。合法零结果（零工单、条款无命中）仍是成功事实。用户可见资金结论由工具字段渲染，模型叙述单独标注核验状态，不一致时显示差异。

Z1–Z3 已在 Task 031 实现并有回归（默认 `ask` 可信目标、失败调用不计取证、默认输出展示可信资金结论），但**仍需独立复查**才能视为关闭；不能以本轮 529 项测试或自检结论替代修复验收。见 [Task 031 归档](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)。
