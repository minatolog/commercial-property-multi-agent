# 当前架构与文档基线

- 更新日期：2026-11-09（Asia/Shanghai），Task 026。
- 核对起点：本地 `main` / `d6577da`，工作区干净。该提交仅归档 Task 025，上一轮业务代码为 `66ded2b`；本轮不声明远端同步状态。
- 定位：以商业地产争议调查展示 Agent 工程能力的模块化单体项目。
- 总体状态：**版本候选，MVP 集成与最终验收中**。文档一致性修正不等于代码缺陷修复或最终验收通过。

## 1. 遇到冲突时如何判断

1. **用户最新明确指令优先**。流程、授权、范围发生变更时，记录变更，不重新执行早期交接中的首次接手步骤。
2. **需求与架构目标**以 [Agent-first V1.0](../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md) 和 [ADR-005](../decisions/ADR-005-agent-first-refocus.md) 为依据。本文件汇总其当前适用关系，不新增未经确认的业务范围。
3. **当前详细规范**分别看 [MVP 范围](../product/mvp_scope_v2.md)、[系统架构](system_design.md)、[运行时契约](agent_runtime_contracts.md)、[开发指南](agent_development_guide.md)、[评测计划](../evaluation/evaluation_plan.md)。[路线与进度表](../product/PROJECT_DEVELOPMENT_ROADMAP.md) 负责排期，不重新定义契约。
4. **实现事实**由当前源码、迁移、测试和对应版本报告证明。代码存在与目标要求不同，记录为差距；不能用现有实现取消需求，也不能把规范中的目标写成已经实现。
5. `*_legacy_2026-11-09.md`、旧交接、Prompt、日志、检查点、审查和评测报告都是**带日期/版本的记录**。其中“当前”“下一步”“未开始”仅指记录当时；新任务不照搬历史指令。新审查可推翻旧自检的完成判断。

## 2. 当前范围

| 类别 | 当前决定 |
|---|---|
| P0 工程核心 | Runtime、LangChain Tool Calling、LangGraph 条件路由/并发、Agent Registry、独立配置、RAG 证据、可靠性、审批、三基线评测、可复现演示 |
| 业务载体 | 合同、账单/付款、物业工单的跨系统争议调查；合成数据 |
| 计算与动作 | 金额用 Decimal/数据库；业务修改只生成审批草案；双角色批准后仍不执行真实调账、减免或派单 |
| 数据底座 | 只读 SQLAlchemy/fixture；PostgreSQL 为目标，SQLite 已有验证；14 表设计保留为长期参考 |
| 展示 | 现有 FastAPI + 同源轻量页面保留；完整管理后台与 BI 暂停 |
| 可选扩展 | 混合/向量检索、rerank、Docker、部署、详细监控；MCP 尚未实现，仅讨论过可选适配，不属于已确认 P0 |
| 暂停 | 完整计费/押金/能耗/核销写引擎、招商、营销、完整 CRUD、真实业务副作用、热插拔、Marketplace、分布式化 |

## 3. 现状与未完成项

| 内容 | 当前证据与边界 |
|---|---|
| Runtime / 工具 / Graph / RAG / 审批 / API / runner | 已有实现；源码路径见系统架构。不是“仅契约”或“未开始” |
| 真实模型 | 已有 DeepSeek 首跑、dev 和有界单题证据：`docs/evaluation/reports/real_model_dev/`、`real_model_v2/`；不再表述为“从未调用/统一缺密钥” |
| 评测 | 8 道开发题 + 32 道 heldout_v3；当前评分 scoring-v3.3；H25/H26 人工评定，30 题自动计分；已有离线结果不能证明真实模型质量 |
| 最新回归证据 | Task 026 同步 Markdown/运行提示词后重跑：399 tests OK（skipped=1）、57 项契约通过；不能替代尚未完成的反例修复与真实模型质量评测 |
| Z1 / Z2 / Z3 | 默认 ask 未装配可信目标；Single 将失败工具算作取证；CLI 默认摘要遗漏可信资金字段。**仍未修复**，见 [Task 025](../reviews/2026-11-07_q1_q3_acceptance_review.md) |
| 独立模型配置 | YAML 独立存在；当前模型工厂从 single.yaml 创建客户端并共享注入。不能承诺“只改任一领域 YAML 即独立换模型”；需明确配置生效策略并回归 |
| 数据层边界 | Agent 不接 ORM/Session；现有工具通过可替换只读仓库查询。目标 Service/Repository 职责分离尚未完整落成独立业务 Service 层；不能宣称完整分层已全部实现 |
| PostgreSQL | 尚无实机验收；当前 12 表精简映射不等于旧 14 表完整设计，EXCLUDE/RLS 等不能写成已实现并验证 |
| 最终验收 | 正式真实 heldout B/C 对照与预先冻结的重复测量、人工量表、当前最终版本独立环境复现尚待完成 |

## 4. 协作与维护

当前由 DeepSeek 连续实现、自检并归档，Codex 按用户要求提供 Prompt 或独立审查；**Codex 逐任务审查不是强制前置环节**。Git 操作以当次用户有效授权为准，本次仅更新 Markdown，不提交、不推送。

每次独立任务使用全局新编号，保留原始 Prompt，更新日志与检查点。历史报告与冻结评测数据不回写；新结果另建版本。变更涉及范围、契约或配置行为时，同步维护对应当前文档和进度表，禁止只在长文顶部叠加新结论、正文仍保留相反的“当前状态”。

[本轮矛盾修正清单与验证](../reviews/2026-11-09_document_consistency_review.md)
