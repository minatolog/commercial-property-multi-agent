# 当前架构与文档基线

- 更新日期：2026-11-23（Asia/Shanghai），Task 033 MCP 工具网关（stdio 第一版）**已实施并自检，待独立复查；未推送**（[归档](../prompts/04_agents/2026-11-23_033_mcp_gateway.md)）；Task 032 / 034 [DeepSeek 独立复查](../reviews/2026-11-22_task032_independent_review.md)均为**有条件通过**，P2/P3 已返修（未新增付费调用）；2026-11-23 [返修确认复查](../reviews/2026-11-22_task032_034_repair_review.md)确认 P2 条件全部关闭、无新 P1/P2，其提出的 3 项 P3 已再修（不等于最终验收）；Task 032 为业务流程工作台改版 + U3 收尾（网页仍未接模型），Task 034 为 LLM Supervisor / 混合规划（默认仍为规则规划）；此前 Task 031；主体由 Task 026 整理，027 新增界面，029 修复映射，030 独立复查确认 U1/U2 原始反例通过、U3 部分修复；031 完成 Z1–Z3、CLI 清理、逐 Agent 模型配置、配置真实性与路由兜底的实施与自检；Claude 复查（有条件通过）提出 R1–R5，R1–R4 已由 Claude Code 返修并自检，[DeepSeek 独立复查](../reviews/2026-11-21_task031_repair_independent_review.md)**有条件通过**（C1 文档同步已完成，C2 R1 残余由 Task 034 处理，C3 已补说明）；R5 用户 2026-11-21 决定**保持现状**（`ask` 有业务词无目标即拒绝）。
- 核对起点：`main` / `3be785e`（已在 `origin/main`），包含 Task 027–031 与 Task 031 返修。Task 030 起点为 `8569cc2`，保留在历史归档。
- 定位：以商业地产争议调查展示 Agent 工程能力的模块化单体项目。
- 总体状态：**版本候选，MVP 集成与最终验收中**。Task 031 是实施自检，不等于代码缺陷修复的最终验收通过；Z1–Z3 与模型/配置/路由问题已按 Prompt 实现并有回归，仍需独立复查。

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
| 展示 | FastAPI + 同源静态资源（Task 027：Tabler 1.7.4 本地化 + 自写协作画布；Task 029 修复展示映射）；完整管理后台与 BI 暂停 |
| 可选扩展 | 混合/向量检索、rerank、Docker、部署、详细监控；MCP 的 stdio 第一版已按 Task 033 实施（已自检、待独立复查），Streamable HTTP + OAuth、TLS 与真实 Flowise 接入仍未做，不属于已确认 P0 |
| 暂停 | 完整计费/押金/能耗/核销写引擎、招商、营销、完整 CRUD、真实业务副作用、热插拔、Marketplace、分布式化 |

## 3. 现状与未完成项

| 内容 | 当前证据与边界 |
|---|---|
| Runtime / 工具 / Graph / RAG / 审批 / API / runner | 已有实现；源码路径见系统架构。不是“仅契约”或“未开始” |
| 真实模型 | 已有 DeepSeek 首跑、dev 和有界单题证据：`docs/evaluation/reports/real_model_dev/`、`real_model_v2/`；不再表述为“从未调用/统一缺密钥”。历史报告当时使用的模型名是 `deepseek-chat`（官方公告 2026-07-24 下线；本项目 11-06 实测以该名字仍可调用）。**历史报告中的模型名为配置名**，服务端实际应答模型当时未记录；返修 R2 起真实调用会在 `models_by_agent.*.served_models` 记录实际应答模型并标注不一致。Task 031 核对官方文档后把配置改为 `deepseek-flash`，**未新增真实调用** |
| 网页模型链路 | 当前 WorkflowService 未注入模型，默认 deterministic / model_client=None / max_model_calls=0；网页仍是规则演示。已有 CLI 模型路径不等于网页接入；领域回答展示和最终综合分析尚未完成 |
| 评测 | 8 道开发题 + 32 道 heldout_v3；当前评分 scoring-v3.3；H25/H26 人工评定，30 题自动计分；Task 031 后离线 heldout A 20/30、B 21/30、C 24/30；返修 R1–R4 后重跑逐题一致（`20261121T093757_*`），仍不能证明真实模型质量 |
| 最新回归证据 | Task 033 后：**651 tests OK（skipped=1，此前 610；+41 为 `test_mcp_gateway.py`）**、70 项契约；SDK stdio 手动连接成功（5 个工具、金额为字符串、自报身份被拒），证据 `docs/reviews/task033_evidence/`（`unittest.txt`、`smoke.txt`、`stdio_probe.txt`）。032/034 复查返修后：610 tests OK（skipped=1，复查时 607）、70 项契约、`check` exit 0、JS 回归 48 用例 / 185 断言，证据 `docs/reviews/task032_evidence/repair_unittest.txt`；返修确认复查后再修 3 项 P3：610 tests OK（skipped=1）、70 项契约、JS 48 用例 / **190** 断言，证据 `docs/reviews/task032_evidence/repair_p3_unittest.txt`、`js_harness.json`。Task 032 后：606 tests OK（skipped=1，此前 595）、70 项契约、JS 回归 45 用例 / 163 断言，证据 `docs/reviews/task032_evidence/`；随后补静态资源 `Cache-Control: no-cache`（+1 测试）→ **607 tests OK（skipped=1）**。复查交接：[`REVIEW_TASK032_034_PROMPT.md`](../handoffs/REVIEW_TASK032_034_PROMPT.md)。Task 034 后：595 tests OK（skipped=1，此前 551）、70 项契约；`check` / `investigate --planner rule|llm|hybrid --model-provider scripted` exit 0。Task 031 返修后：551 tests OK（skipped=1，返修前 529）、70 项契约、`check` / `ask` / `investigate --model-provider scripted` exit 0；离线 heldout 与 Task 031 报告逐题一致；换行符统一为 LF（`.gitattributes`）。见 [Task 031 归档第 10 节](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md) |
| 协作界面 U1 / U2 / U3 | **U1/U2 原始反例通过（Task 030）；U3-A/U3-B 已在 Task 032 修复；独立复查有条件通过，摘要渲染路径的残余（P2-2）已返修，待确认**：核验解释集中为 `interpretVerification`，核验节点、报告节点、结论卡、步骤条、摘要共用；必需布尔字段缺失或类型异常不再显示通过；15 行反例逐条参数化。见 [Task 032 归档](../prompts/05_frontend/2026-11-22_032_business_workbench_ui.md)；原始缺口见 [Task 030 独立复查](../reviews/2026-11-10_task029_ui_fixes_acceptance_review.md) |
| 业务流程工作台（Task 032） | **独立复查有条件通过，P2/P3 已返修并自检，待确认**（[复查](../reviews/2026-11-22_task032_independent_review.md)、[归档 §10](../prompts/05_frontend/2026-11-22_032_business_workbench_ui.md)）：案件列表 / 新建调查抽屉 / 案件头 / 7 步流程条 / 4 张结论卡 / 页签；只读展示元数据 `display`（`app/api/display.py`，按可信项目范围过滤、不落库、无写接口）。回问运行 API 仍记 `completed`，界面显示“需要补充信息”。网页仍是规则演示，未接模型；静态资源无版本号 |
| MCP 网关（Task 033） | **已实施并自检，待独立复查；未推送**（[归档](../prompts/04_agents/2026-11-23_033_mcp_gateway.md)、[手动连接](../reviews/task033_evidence/stdio_probe.txt)）：stdio + 开发模式固定主体；只开放 5 个只读工具；`ToolExecutor.execute()` 唯一入口；一个连接一个会话与独立预算；保留键拦截；金额全程十进制字符串；`mcp==2.3.0` 的 low-level `Server`（构造函数回调）。未做 Streamable HTTP / OAuth / TLS，未在 Flowise 中实连；下一版最大风险是身份与传输会话生命周期错配（归档 §9.2） |
| Z1 / Z2 / Z3 | **已实现，独立复查有条件通过**：`ask` 可信目标解析/注入与拒绝；失败/越界工具调用不进入取证、有目标零事实失败而合法零结果保留；单 Agent 存在失败调用且问题涉及的领域缺事实时为 PARTIAL（全部缺失为 insufficient_evidence，返修 R1；Task 034 §2.6 起没有失败调用、只是漏查已问领域时同样处理，告警区分“未查询 / 查询失败”）；`ask`/`investigate` 默认摘要分栏展示可信资金结论与核验状态。见 [Task 031 归档](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md) |
| CLI 契约 | **已清理并自检**：`ask`/`investigate` 统一 `--model-provider`（旧 `--provider` 为弃用别名）；`approve --dry-run` 只校验、不写台账/不恢复图（副本用 SQLite 备份接口生成一致性快照，返修 R4）；删除无效的 `approve --thread-id`；退出码 0/1/2/3 分离并写入帮助与 backend README；`--principal` 默认读 `DEMO_PRINCIPAL_ID`，显式传入提示开发模式并记录 `identity_source` |
| 独立模型配置 | **已实现并自检**：客户端按各 Agent 自己的 YAML 创建（provider/model_name/temperature/max_tokens/api_key_env/timeout），同参数缓存共享；非法配置启动期失败；`bundle.agent_models` 与评测 `models_by_agent` 按 Agent 报告实际模型。领域 YAML 与评测报告的模型名在 Task 031 后为 `deepseek-flash` |
| 规划层（Task 034） | **独立复查有条件通过，P2/P3 已返修并自检，待确认**（[复查](../reviews/2026-11-22_task034_independent_review.md)、[归档 §13](../prompts/04_agents/2026-11-22_034_llm_supervisor_planner.md)；真实对照的服务端实际应答模型**未记录、不可复核**，返修后逐题记录）：`planner.yaml` 的 `mode` 默认 `rule`（CLI/API/评测行为不变，离线 heldout 与 `20261121T093757_*` 逐题一致）；`llm` / `hybrid` 由 LLM Supervisor 规划（`submit_plan` 结构化输出、只能选领域、目标只来自可信上下文、失败/超时/非法/超预算回退并记录 `planning.fallback_reason`）。改写问法评测集 `planner_paraphrase_v1`（30 题）/`v2`（66 题，含 36 道实习场景题）已冻结在代码之前；离线 scripted 对照零越权；真实模型（deepseek-flash）单次对照 v2 66 题：rule 36、llm 61、hybrid 58（省 26% 调用）、四组均零越权，尚无重复测量。API/网页仍为规则规划。见 [Task 034 归档](../prompts/04_agents/2026-11-22_034_llm_supervisor_planner.md) 与 [ADR-006](../decisions/ADR-006-hybrid-planner.md) |
| 配置真实性 / 路由兜底 | `RetrievalSettings` 只接受真实能力（`enabled`/`top_k`，检索仅 BM25）；声明 chroma/bge/rerank 等未实现项时 `check` 报错。`RuleBasedPlanner` 未命中任何领域时返回 `needs_clarification`（`route=clarification`、零工具、不审批），不再静默落 billing，报告始终写 `routing_reason`；词表见 [planner_vocabulary](../architecture/planner_vocabulary.md) |
| 数据层边界 | Agent 不接 ORM/Session；现有工具通过可替换只读仓库查询。目标 Service/Repository 职责分离尚未完整落成独立业务 Service 层；不能宣称完整分层已全部实现 |
| PostgreSQL | 尚无实机验收；当前 12 表精简映射不等于旧 14 表完整设计，EXCLUDE/RLS 等不能写成已实现并验证 |
| 最终验收 | 正式真实 heldout B/C 对照与预先冻结的重复测量、人工量表、当前最终版本独立环境复现尚待完成；Z1–Z3 与返修 R1–R4 独立复查有条件通过，R1 残余已在 Task 034 §2.6 修复（待复查）；Task 034 的 Supervisor 规划质量已有单次真实模型对照，需重复测量；Task 032 / 034 独立复查有条件通过、返修待确认；R5（`ask` 有业务词无目标即拒绝的边界）用户 2026-11-21 决定**保持现状**，不放宽 |

## 4. 协作与维护

当前由 DeepSeek 连续实现、自检并归档，Codex 按用户要求提供 Prompt 或独立审查；Task 031 返修由 Claude Code 实施，复查需交给另一模型；**Codex 逐任务审查不是强制前置环节**。Git 操作以当次用户有效授权为准；Task 031 由用户提交为 `3be785e`，Claude Code 不提交、不推送。

Task 031 按 Prompt 允许的方式使用 Agent Teams 协作：`backend/app/cli.py` 只由负责人修改，成员写作用域互斥；成员完成后由负责人合并、复核、清理临时文件，再统一运行全量回归与离线评测（不用成员各自跑的结果拼对比表）。

每次独立任务使用全局新编号，保留原始 Prompt，更新日志与检查点。历史报告与冻结评测数据不回写；新结果另建版本。变更涉及范围、契约或配置行为时，同步维护对应当前文档和进度表，禁止只在长文顶部叠加新结论、正文仍保留相反的“当前状态”。

[本轮矛盾修正清单与验证](../reviews/2026-11-09_document_consistency_review.md)
