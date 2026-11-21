# 项目总开发路线与进度表 V1.1

- 更新：2026-11-21，Task 031；本地 main / e3b3594，027–031 成果与本轮自检未提交。原主体规划由 Task 026 整理。
- 目标与范围：[当前架构基线](../architecture/CURRENT_BASELINE.md)、[Agent-first V1.0](../handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md)。
- 旧版完整路线与逐次更新：[历史快照](PROJECT_DEVELOPMENT_ROADMAP_legacy_2026-11-09.md)。下表为现状，不用旧版“剩余 9 次 Prompt”等首次规划数字判断进度。

> **2026-11-10 用户追加的展示任务（Task 027）**：优先美化现有前端，采用 GitHub 开源模板呈现多 Agent 合作。Codex 已完成 [模板调研](../reviews/2026-11-10_multi_agent_ui_template_review.md)、[DeepSeek 实施 Prompt](../handoffs/DEEPSEEK_TASK027_MULTI_AGENT_UI_PROMPT.md) 与 [027 归档](../prompts/05_frontend/2026-11-10_027_multi_agent_ui_refresh.md)；DeepSeek 随后完成实施（Tabler starter/core 1.7.4 本地资源 + Langflow 节点视觉参考），自检见 [实施与视觉自检报告](../reviews/2026-11-10_multi_agent_ui_implementation_review.md)：403 tests OK（skipped=1）、57 项契约、7 张真实浏览器截图。
>
> **2026-11-10 当前修复判断（Task 030）**：028 发现 U1–U3，DeepSeek 在 [029](../reviews/2026-11-10_task029_ui_mapping_fix_report.md) 自检称修复；[030 独立复查](../reviews/2026-11-10_task029_ui_fixes_acceptance_review.md) 确认 U1/U2 原始反例通过，U3 error 路径已改但缺字段/类型异常及联合状态仍有缺口。独立 409 tests OK（skipped=1）、57 契约、实际 JS 17 用例 / 84 断言通过，不能替代补充异常边界验收。展示任务**仍未提交，U3 尚未闭合**。
>
> **2026-11-21 核心正确性收尾（Task 031，实施自检）**：Z1–Z3、CLI 清理、逐 Agent 模型配置、配置真实性与路由兜底已完成实施并自检：529 tests OK（skipped=1）、70 项契约、`check` exit 0、无效配置 exit 2；离线 heldout 改动后 A 20/30、B 21/30、C 24/30（C 的 H27 由失败变通过；另 3 题只变路由效率/人工评定），用例、fixture、评分校验和未变。**待独立复查**，不据此关闭最终验收。见 [031 归档](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)。

下一步：① 独立复查 Task 031（重点 Z1 目标边界、Z2 取证分界、2.5 逐 Agent 模型与报告一致性）；② 小范围补完 U3-A/U3-B；③ 之后按 Prompt 分开推进 Task 032（业务流程工作台前端）与 033（MCP 工具网关）。现有网页默认规则演示，不能把命令行模型接入当作网页已经使用 AI。展示修复不关闭下方正式实验、人工量表与 PostgreSQL 实机验收。

## 1. 项目要交付什么

一个以商业地产收费争议为场景的 Agent 工程作品：请求 → 按能力规划 → 受控工具取证 → 合并核验 → 有限补查 → 报告/审批草案 → 可检查的 Trace 和三基线评测。目标是证明 LangChain、LangGraph、Tool Calling、RAG、可靠性与评测能力。

金额计算使用 Decimal；P0 无真实业务写操作。14 表长期设计保留，完整 ERP、BI、计费写引擎和大量 CRUD 暂停。

## 2. 十步主线与当前进度

原定**理想主线为 10 个开发步骤**，对应 Task 006–015；它不是实际总对话次数或必须停止开发的上限。Task 016–025 是后续审查、修复、装配、真实调用及证据归档，Task 026 是本次文档一致性整理。返修和审查不伪装成原主线新增的“第 11～13 次正式 Prompt”。

| 主线步骤 / 任务 | 产物 | 当前判断与验收边界 |
|---|---|---|
| 1 / 006 | Agent-first 范围、契约、8 题样例 | 已有独立验收记录；当时契约提案不等于当前全部字段已实现 |
| 2 / 007 | Runtime、受控工具、预算与 Trace | 已实现，后续有修复/回归；Task 031 完成 Single 入口 Z1/Z2 与 CLI 契约（待独立复查） |
| 3 / 008 | LangChain/DeepSeek 工具循环 | 已实现；018–020 补齐领域装配与真实首跑/dev；Task 031 起按各 Agent YAML 独立建客户端（待独立复查） |
| 4 / 009 | 三领域与 LangGraph | 分支、Send 并发、verify、有限补查已有实现和测试；Task 031 起未命中领域返回 `needs_clarification`，不再静默落 billing |
| 5 / 010 | 精简 SQLAlchemy/Alembic 只读数据层 | 12 表映射、SQLite 已验；PostgreSQL 实机与必要约束待验，分层差距明确记录 |
| 6 / 011 | 合同 PDF、检索、证据 | 合成 PDF 实际解析/页码核对、BM25 已有；配置已只声明真实能力（无 chroma/bge/rerank）；向量/混合检索为未来可选 |
| 7 / 012 | 持久恢复、审批 | 单机 SQLite checkpoint + 独立台账、串行双角色、批准草案已有；Task 031 起 `approve --dry-run` 只校验不写台账；分布式语义不在 P0 |
| 8 / 013 | 三基线与 40 题 | 8 dev + 32 heldout_v3；离线 scoring-v3.3 新报告 A 20/30、B 21/30、C 24/30；真实 heldout B/C、重复测量与人工量表待做 |
| 9 / 014 | FastAPI/轻量演示页 | 已实现规则演示与 Tabler 协作界面；030 确认 U1/U2 原始反例通过、U3 部分修复。网页真实模型装配/回答展示/综合分析未完成（Task 032）；生产鉴权/部署非 P0 前置 |
| 10 / 015 | 最终复现与展示材料 | README/脚本/候选版本已有；当前最终版本复现与未闭合关口完成前，不记 MVP 全部验收 |

**进度判断：MVP 集成与最终验收阶段，版本候选。** Task 031 自检 529 tests OK（skipped=1）、70 项契约；Z1–Z3、CLI、逐 Agent 模型配置、配置真实性与路由兜底已实施，但**待独立复查**；U3 部分修复、网页真实模型链路、正式真实评测、PostgreSQL 实机与人工量表仍开放。未以自检全绿替代独立验收。

## 3. 后续五个工作包（建议顺序）

若每个工作包一次交付且验收通过，可按 **5 次实施 Prompt** 安排；这是当前建议，不承诺在修复、外部条件或新增需求出现后仍固定五次。

| 顺序 | 做什么 | 验收标准 |
|---|---|---|
| 1 | 收尾 Z1/Z2/Z3 | **Task 031 已实施并自检（待独立复查）**：真实 ask 装配传可信目标；换目标拒绝；失败工具不满足取证；合法零结果保留；ask/investigate 默认输出展示可信资金字段；覆盖默认/完整输出并回归 |
| 2 | 明确独立模型配置策略 | **Task 031 已实施并自检（待独立复查）**：每 Agent 按自己 YAML 创建/缓存客户端；实际 provider/model/参数逐 Agent 写入 `agent_models`/`models_by_agent`；无效配置启动期失败；离线装配测试通过 |
| 3 | PostgreSQL 实机与数据边界验收 | 可重建测试库迁移/seed/只读限制/项目隔离/精度与 fixture 等价通过；清点 12 表与旧 14 表差异，验证 P0 必要约束；不照搬整套旧设计 |
| 4 | 正式真实评测与人工量表 | 冻结代码/数据/评分/Prompt/模型/预算与重复次数；同一工具/权限/预算下完成 B/C、配 A 确定性基线；保存全部重复、失败题和人工结果；揭示旧保留题已被开发查看的限制 |
| 5 | 最终版本复现、演示与交付 | 独立环境按 README 重建运行；完整测试、调查/冲突/审批/失败案例及可插拔回归；文档与结果一致；完成验收后才建议发布 |

工作包 1、2 已按 Prompt 实施并自检，仍需独立复查确认；3 需要可用 PostgreSQL 实例；4 需要有效模型配置、预算和人工评分。生产鉴权、Docker、部署、混合检索、MCP 为另行决定的扩展，不阻塞现定 P0；Task 032/033 按用户要求与本任务分开执行。

## 4. 评测与完成判断

scoring-v3.3 离线 heldout（Task 031 后新报告）：A 20/30、B 21/30、C 24/30；相对 Task 025 时期 C 从 23 变为 24，唯一影响通过的题是 H27（`expected_outcome=failed`，旧逻辑静默 billing 反而"答出内容"，新逻辑回问＝明确失败），H19/H25/H26 只影响路由效率或人工评定题，没有"通过变失败"的题。它们是离线规则路径结果，不证明真实模型质量或多 Agent 的普遍优势。真实 DeepSeek 已有 dev/单题证据，不再等同“缺密钥从未调用”，但不足以替代正式实验；历史模型名 `deepseek-chat` 已下线，当前配置为 `deepseek-flash`（未新增真实调用）。

旧 heldout 已被多次运行和检查，不能无证据宣称从未暴露的独立盲测。正式报告需如实标注，若需要盲测结论则另冻结未用于开发的集；保留原题、原评分与原结果。人工量表不因自动回归通过而完成。

## 5. 工作流程与记录

DeepSeek 连续实施 → 自检 → 保存证据 → 更新当前文档、Prompt、日志、问题和检查点。用户需要时另请 Codex 编写 Prompt 或独立审查；不恢复逐任务强制审查环节。

任务编号以 [docs/README](../README.md) 全局登记表为准。每次交付区分“已实现”“自检通过”“独立验证”“未完成”，Git 提交/推送按有效授权执行，实际 hash 事后记录。本轮不提交或推送。

## 6. 最近证据入口

- [Task 031：核心正确性收尾实施自检与证据](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)
- [Task 031：改动前独立复查（Z1–Z3 原始反例）](../reviews/2026-11-07_q1_q3_acceptance_review.md)
- [Task 024：Q1–Q3 修复自检](../prompts/06_testing/2026-11-07_024_q1_q3_model_fixes.md)
- [当前评分规则](../evaluation/scoring_v3.md)
- [路由词表与兜底契约](../architecture/planner_vocabulary.md)
- [本轮文档一致性整理](../reviews/2026-11-09_document_consistency_review.md)
