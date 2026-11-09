# Agent 架构设计（当前版）

- 更新：2026-11-09，Task 026。
- 依据：[当前基线](CURRENT_BASELINE.md)、[ADR-005](../decisions/ADR-005-agent-first-refocus.md)。
- 整理前的概念设计、风险和旧示例：[历史快照](agent_architecture_legacy_2026-11-09.md)。

## 1. 协作方式

Agent 通过 AgentProtocol、Registry 和结构化结果协作；互不引用对方实现。Coordinator 依据能力而非具体类名调度。项目采用模块化单体，不要求热插拔、微服务或 Agent Marketplace。

| 角色 | P0 职责 | 实现 |
|---|---|---|
| Coordinator | 选择能力、短路径/并发路由、有限补查 | RuleBasedPlanner / LangGraph，规则实现 |
| Lease | 租约与合同条款证据 | 确定性 Agent + LLM Agent |
| Billing | 账单/付款/欠费事实 | 确定性 Agent + LLM Agent；金额来自 Decimal 工具 |
| Property | 工单与维修事实 | 确定性 Agent + LLM Agent |
| Single | 同一组受控工具的单 Agent 路径 | SingleToolAgent；保留已知 Z1/Z2/Z3 |
| Verifier | 完成条件、缺失、冲突、金额/证据核验 | 确定性节点，不必另起 LLM |
| Human Approval | 物业→财务两名不同主体串行审批草案 | 独立节点与台账；批准后仍不执行业务写操作 |
| Compliance | 扩展占位 | 保留、默认禁用，不作为 P0 必须实现的第四业务 Agent |

## 2. 接口与工厂

agents/base/contracts.py 定义 AgentRequest、AgentContext、AgentOutput、AgentResult 和 TaskStatus。子类 _execute() 返回 AgentOutput，BaseAgent.handle() 统一包装结果、错误与元数据。Runtime 的可信边界在 runtime/types.py 和 agent_runtime.py。

静态工厂有 AGENT_IMPLEMENTATIONS 和 AGENT_LLM_IMPLEMENTATIONS 两张表。新增一种实现时登记所需引擎，不能从 YAML 动态 import。工厂校验 YAML 的 version/capabilities 与实现声明一致；Registry 区分缺失、禁用和能力冲突，并支持受控替换。

字段、预算与状态语义只在 [agent_runtime_contracts.md](agent_runtime_contracts.md) 维护，避免重复的 V1/V2 定义。

## 3. 配置独立性及当前限制

每个 Agent 有独立 YAML 和 Prompt。enabled、allowed_tools、执行超时/重试等由相关代码消费；修改后需重建装配并做回归，不承诺在运行中热更新。

**每 Agent 独立模型配置仍待闭合**：llm/factory.py 当前从 single.yaml 创建 DeepSeek 客户端，然后由调查/评测装配共享注入。领域 YAML 的 model_name/model_provider 声明存在，并不能证明各 Agent 运行时使用不同客户端。新增独立客户端策略时必须验证实际 provider、参数、usage 和报告一致。

retrieval_settings 含向量/rerank 预留字段；当前检索只有 BM25，不能把配置字段存在当作该检索能力已实现，也不能保证每项参数均已接入。

## 4. 低耦合边界与已知缺口

Agent 只通过受控执行器使用工具。工具负责类型化输入输出，业务数据来自只读仓库，知识来自 KnowledgeService。目标中的独立 Business Service 层尚未完整实现；后续业务规则应按 [系统架构](system_design.md) 收敛。

改一个 Agent 的 Prompt 或实现，应只影响该 Agent 与相关工作流；修改公共契约、工厂或共享工具则需扩大回归范围。新增/禁用/替换的操作规范见 [开发指南](agent_development_guide.md)。

Z1–Z3 是 [Task 025](../reviews/2026-11-07_q1_q3_acceptance_review.md) 尚未关闭的问题，不能以现有 399 项测试或某项旧自检的“全部修复”替代修复验收。
