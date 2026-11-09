# Agent 开发指南（当前版）

- 更新：2026-11-09，Task 026。
- 上位依据：[当前基线](CURRENT_BASELINE.md)、[ADR-005](../decisions/ADR-005-agent-first-refocus.md)、[运行时契约](agent_runtime_contracts.md)。
- 旧示例和原文：[历史快照](agent_development_guide_legacy_2026-11-09.md)，不再用其中直接 invoke 工具的示例开发。

## 1. 模块规则

1. Agent 不 import 其他 Agent 实现；Coordinator 不 import 具体 Agent；具体实现只在受信任工厂装配。
2. 子类 _execute(request, context) 返回 AgentOutput，由 BaseAgent 包装 AgentResult。
3. Agent 不直接访问 ORM、Session、SQL、环境密钥或外部服务；业务能力通过受控工具、模型通过注入客户端获得。
4. **工具调用必须经过 ToolExecutor 或共用工具循环**；仅调用 assert_tool_invocable 后直接 tool.invoke 不能替代预算、schema、deadline、结果范围和 Trace 校验。
5. 金额/日期/状态取自确定性工具，不在 Prompt 中计算或编造。业务规则新增到合适的 Service；现有仓库聚合与目标分层的差距不能继续扩大。
6. Prompt 位于 Agent 自己的 prompts 目录；YAML 独立、schema 严格，密钥只引用环境变量名。禁止配置字符串动态 import。
7. 业务目标和权限分别校验：授权范围来自可信上下文，任务范围来自可信入口装配，模型只能在范围内选择参数。
8. 取证失败不能满足完成条件；零金额、空工单等合法成功结果应保留。公共契约或共享执行器修改需检查全部调用方与恢复语义。
9. 业务写操作只生成审批草案，当前 P0 即使批准也不执行真实业务修改。
10. 文档与实现必须区分“目标/已实现/已验证/仍有缺陷”。字段存在不等于运行时已消费。

## 2. 新增 Agent

1. 先确认属于已批准范围；Compliance/风险等扩展不能仅因示例存在而进入 P0。
2. 创建 `backend/app/agents/<name>/`，放实现、`__init__.py` 与 `prompts/system.md`。参考现有 ToolBackedAgent 或 LLMToolAgent，避免复制一套执行器。
3. 创建 `backend/app/config/agents/<name>.yaml`；name 与文件名一致；类属性和 YAML 的 version/capabilities 必须一致。能力名用 `<domain>.<action>`，工具按最小授权声明。
4. 在 agents/factory.py 的静态白名单登记所需引擎：AGENT_IMPLEMENTATIONS / AGENT_LLM_IMPLEMENTATIONS。依赖通过已有注入边界传入，不让编排直接构造具体类。
5. 使用 Registry 检查能力 available/disabled/missing；检查未知实现是否被跳过，不能把“配置加载了”当“实现已注册”。strict 是否启用须考虑各引擎有意缺少的实现。
6. 运行契约、独立 Agent、相关工作流测试；涉及共享边界时运行完整回归。补充实际 CLI/API 装配测试，不能仅手工构造理想 AgentRequest。

## 3. 新增工具

当前接口在 tools/base.py：BaseTool 声明 name、required_permissions、input_model、output_model、timeout_seconds、max_attempts；invoke(validated_payload, context) 返回 **ToolInvocation(data, evidence)**，证据为 EvidenceDraft，不能返回 ORM 对象。

输入/输出模型应严格校验；工具自身只实现确定性只读操作；执行器补齐证据来源。注册 ToolRegistry，并在允许使用的 Agent YAML 中声明 allowed_tools。调用方只通过 ToolExecutor.execute(tool_name, payload, context=..., agent_config=...) 或已有工具循环执行。

工具新增后验证参数拒绝、权限/项目/目标范围、结果 schema、超时、预算、Trace、成功后的证据。不得用直接 invoke 的测试替代真实执行器边界验证。

## 4. 禁用、替换和配置

| 操作 | 实施与验收 |
|---|---|
| 禁用 | YAML enabled=false，重建装配；Registry 报 disabled，相关图路径明确降级/失败 |
| 替换实现 | 工厂指向兼容实现，同步类/YAML version 和 capabilities；检查 Registry 原子替换及相关工作流 |
| 修改 Prompt | 修改独立文件，重建装配，验证相关工具选择、证据与回答；不写死业务真值 |
| 修改模型 | 当前共享客户端来自 single.yaml；每 Agent 独立模型策略仍待完成，不能承诺只改领域 YAML 就能换模型 |
| 修改检索 | 只承诺实际消费的参数；BM25 以外的字段为预留，需实现与评测后才能宣称生效 |
| 移除模块 | 当前默认保留历史实现；确需删除须先确认任务范围并检查能力引用、配置、工厂和迁移 |

## 5. State、恢复和回归

实际调查图使用 InvestigationState；results/failures/warnings 追加，verify/report 按 run/subtask 收敛。并发字段需明确 reducer，覆盖字段需单写者；不能把旧设计的 map reducer 直接当成当前接口。

一条 thread 仅承载一次新调查；恢复须复核身份、授权、草案版本和台账。不得以重放为由跳过工具闸门或无视新物理模型请求消耗。

在 backend 目录执行：

```powershell
python tests/smoke_agent_contracts.py
python -m unittest discover -s tests -p "test_*.py"
python -m app.cli check
```

按变更选择相关回归；纯文档修正检查引用、格式、事实与历史保护即可，不强制付费调用或重建数据库。当前规范中的未闭合要求见 Task 025 Z1–Z3，不通过弱化要求来让测试变绿。

## 6. 文档与 Git

按 [docs 规范](../README.md) 分配新全局编号、逐字存原始 Prompt，记录实际变更、验证和未完成项，更新进度/日志/检查点。DeepSeek 负责连续实现和自检；Codex 按用户要求独立审查，不设逐任务强制审查门。

提交/推送按用户当次有效授权执行；未执行写 Pending，真实发生后回填 hash，不编造提交。本轮文档整理不授权安装、数据库改造、付费评测、提交或推送。
