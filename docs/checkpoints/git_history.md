# Git 开发检查点

记录每个开发阶段对应的 Git 提交，用于追溯与回滚。

> 下文 Pending/未提交是记录时状态；实际当前提交以 Git 为准，不用旧条目反推未提交变更。当前规划见 [路线图](../product/PROJECT_DEVELOPMENT_ROADMAP.md)。

## [2026-11-09] 任务 026 - 文档一致性整理（Pending）

- **起点**：main / d6577da，工作区干净。本轮不声明远端同步状态。
- **本轮 Commit**：Pending；未提交、未推送。
- **变更**：当前基线、六份现行文档及其原文归档、入口/范围/历史适用说明、五份 Agent 运行提示词边界、026 Prompt/审查/日志。
- **历史回填说明**：Task 025 文档已由 d6577da 纳入 Git；下方原“未提交/Pending”保留为当时快照。
- **验证**：文档一致性与历史保护检查，以及本轮实际重跑 399 tests OK（skipped=1）、57 项契约；详情见 [报告](../reviews/2026-11-09_document_consistency_review.md)。
- **建议 Summary**：docs: reconcile Agent-first architecture and project status
- **建议 Description**：统一当前架构、契约、MVP 与进度说明；保留旧文原文和冻结记录，明确真实模型/数据库/独立配置及 Z1–Z3 的验收边界。仅文档变更。
- **回滚参考**：以 Git diff 与六份 legacy 原文审查差异；不自动执行 reset、覆盖或删除。

## [2026-11-07] 任务 025 - Q1–Q3 独立复查文档（未提交）

- **代码基线**：`f2cc67d`；实际 GitHub main hash 一致，开始时工作区干净。
- **本轮 Commit**：`Pending`，未提交或推送。
- **变更**：新增独立复查报告与 025 Prompt；更新索引、进度提示、日志和问题入口；清理重复编号行，不改业务源码。
- **验证**：399 tests OK（skipped=1）、57 项契约、scripted CLI、离线评测；独立复现 Z1–Z3。
- **建议 Commit Message**：`docs: verify Q1-Q3 fixes and record remaining Single CLI gaps`。
- **回滚说明**：仅未提交文档，先看差异，不自动回滚或改写历史。

## [2026-11-07] 任务 024 - 修复 Q1–Q3（token 闸门 / 单 Agent 范围 / 资金结论）

- **开发阶段**：缺陷修复 / 测试。
- **代码基线**：`main` / `2512a3b`（保留 Codex 的 Task 022/023 文档）。
- **Git 分支**：`main`。
- **Commit Hash**：`66ded2b`（代码与测试、v3.3 报告）、`158ab55`（文档、Prompt 归档、Task 022/023 文档）；
  已推送 `2512a3b..158ab55 → origin/main`。
- **本次变更**：

  | 文件 | 变更类型 |
  |---|---|
  | `backend/app/runtime/budget.py`、`types.py` | 修改（token 闸门、`max_total_tokens` 三态、`tokens_exhausted`） |
  | `backend/app/agents/base/scope.py` | 修改（`from_payload` / `mode` / `lease_ids` / `scope_arguments_hook` 共用） |
  | `backend/app/agents/base/conclusions.py` | 新增（结构化资金结论 + 渲染 + 字段级核对） |
  | `backend/app/agents/base/llm_agent.py`、`single/agent.py` | 修改（共用 scope 钩子；Q2 单 Agent 接入；资金结论输出） |
  | `backend/app/orchestration/investigation.py` | 修改（`authoritative_amounts`、discrepancy 分类） |
  | `backend/app/evaluation/scoring.py`、`runner.py`、`baselines.py` | 修改（`scoring-v3.3`、`fund` 主断言、`by_kind` 三分解） |
  | `backend/tests/test_token_budget_gate.py`、`test_single_agent_scope.py`、`test_fund_conclusions.py` | 新增 54 项回归 |
  | `docs/evaluation/scoring_v3.md`、`reports/20261106T205403_*`、`20261106T205407_*`、`reports/real_model_v2/*` | 新增/更新（规则、v3.3 报告、真实核验） |

- **验证结果**：

  | 验证项 | 结果 |
  |---|---|
  | `python -m unittest discover -s tests -p "test_*.py"` | 399 tests，OK（skipped=1） |
  | `python tests/smoke_agent_contracts.py` | 57 项通过 |
  | `investigate --model-provider scripted --budget-tokens 5000` | exit 0，`conflicting`、`failures=[]` |
  | `investigate`（offline） / `--backend sqlite` | 均 exit 0 |
  | `evaluate --split heldout` | A 20/30、B 21/30、C 23/30（`scoring-v3.3`） |
  | 真实 DeepSeek 单题（30k token 上限） | 物理请求 7 = 账本 7、13,452 tokens、`fund_status=verified`、0 discrepancy |

- **建议 Commit Message**：`fix(runtime,agents,eval): gate model calls on token budget, share task scope, bind fund conclusions`
- **回滚参考命令**：`git revert <hash>` / `git show <hash> --stat`

## [2026-11-07] 任务 023 - 仓库状态与项目进度文档（未提交）

- **代码基线**：`2512a3b`，本地和通过 `git ls-remote` 查询的 GitHub main 一致；没有新的业务代码交付。
- **本轮 Commit**：`Pending`，未提交或推送。
- **变更**：进度说明、023 Prompt、索引/路线图入口/开发日志/检查点。保留原 Task 022 未提交审查文档。
- **验证**：Git 分支、唯一 worktree、工作区和远端状态核实；本轮没有重新运行测试或验收新修复。
- **建议 Commit Message**：`docs: record repository delivery state and concrete MVP progress`。
- **范围确认**：用户补充的 N1–N6 完成说明与 `2512a3b` 一致；后续 Q1–Q3 尚未交付。下一步实施并复验 Q1–Q3；不自动执行回滚或改写历史。

## [2026-11-07] 任务 022 - 模型修复复查文档（未提交）

- **代码基线**：`main` / `2512a3b`，开始时工作区干净、与本地 origin/main 一致。
- **本轮 Commit**：`Pending`，未提交或推送。
- **变更**：新增 022 Prompt、N1–N6 复查报告；更新索引、路线图提示、开发日志与问题入口。没有业务代码修复。
- **验证**：345 tests OK（skipped=1）、57 项契约、scripted CLI 通过；离线评测重现；独立发现 Q1–Q3。
- **建议 Commit Message**：`docs: recheck model fixes and record remaining Q1-Q3 defects`。
- **回滚说明**：本轮仅未提交文档，先审查差异，不自动执行回滚或改写历史。

## [2026-11-07] 任务 021（实施）- 修复模型链路 N1–N6

- **开发阶段**：缺陷修复 / 测试。
- **代码基线**：`main` / `45af0cb`（含 Codex 未提交审查文档，已保留）。
- **Git 分支**：`main`。
- **Commit Hash**：`7a6c31a`（代码与测试、`scoring-v3` 规则与报告）、`6e18721`（文档归档）、
  `aa05d28`（回填 hash）；随后真实模型核验暴露一次误报，修正后按 `scoring-v3.1` 追加提交
  （见下一条"任务 021 收尾"）。
- **推送状态**：已推送 `45af0cb..aa05d28 → origin/main`。
- **本次变更**：

  | 文件 | 变更类型 |
  |---|---|
  | `backend/app/agents/base/scope.py`、`evidence.py`、`narrative.py` | 新增（可信任务范围、能力结果契约、叙述一致性） |
  | `backend/app/runtime/tool_loop.py`、`budget.py`、`types.py` | 修改（物理请求编号、未预算 token 记账、`exceeded_tokens`） |
  | `backend/app/agents/base/llm_agent.py`、`errors.py`、`single/agent.py` | 修改（契约与答案校验、`INSUFFICIENT_EVIDENCE`） |
  | `backend/app/tools/knowledge_tools.py` | 修改（`lease_id` 范围解析、默认拒绝） |
  | `backend/app/orchestration/investigation.py` | 修改（planner 传 `question`、能力契约核验、`narrative_discrepancies`） |
  | `backend/app/evaluation/scoring.py`、`runner.py`、`baselines.py` | 修改（`scoring-v3`、`by_kind` 指标、B 条款检索带租约） |
  | `backend/tests/test_model_budget.py`、`test_task_scope.py`、`test_evidence_and_answer.py` | 新增 42 项回归 |
  | `backend/tests/test_evaluation.py`、`test_graph_workflow.py`、`test_rag.py` | 修改（同步契约与 v3 口径） |
  | `docs/evaluation/scoring_v3.md`、`docs/evaluation/reports/20261106T191222_*`、`20261106T191233_*` | 新增（规则与 `scoring-v3` 报告） |

- **验证结果**：

  | 验证项 | 结果 |
  |---|---|
  | `python -m unittest discover -s tests -p "test_*.py"` | 345 tests，OK（skipped=1） |
  | `python tests/smoke_agent_contracts.py` | 57 项通过 |
  | `python -m app.cli investigate` / `--model-provider scripted` | exit 0，`conflicting`，无失败 |
  | `python -m app.cli evaluate --split heldout --quiet` | A 20/30、B 21/30、C 23/30（`scoring-v3.1`） |
  | 真实 DeepSeek 有界核验（`real_model_v2/`，单题 30k token 上限） | 物理请求 7 = 账本 7，13,714 tokens，`narrative_discrepancies=0` |

- **建议 Commit Message**：`fix(model-path): enforce trusted scope, evidence contracts and answer accuracy`
- **回滚参考命令**：

```bash
git revert <hash>
git show <hash> --stat
```

## [2026-11-07] 任务 021（收尾）- scoring-v3.1：真实模型核验暴露的可信金额误报

- **开发阶段**：缺陷修复（由真实服务核验驱动）。
- **代码基线**：`main` / `aa05d28`。
- **Git 分支**：`main`。
- **Commit Hash**：`70758c3`（代码与测试）、`c74183d`（文档与报告）；已推送
  `aa05d28..c74183d → origin/main`。
- **问题**：`scoring-v3` 只用 `facts` 当可信金额集合，真实 DeepSeek 在账单答案里照实列出
  每期租金/已核销金额（15120.00 / 15876.00 / 17280.00 / 2160.00）时被判为"编造金额"
  （证据：`docs/evaluation/reports/real_model_v2/20261106T1917_*`）。
- **本次变更**：可信金额集合扩展为 `facts` + 工具输出里出现过的全部金额（运行时
  `amounts_in_payload`，评测 `BaselineResult.verified_amounts`）；新增 `ungrounded`
  状态（写了钱数却没有任何经核验的合计数 → 失败）；评分版本升 `scoring-v3.1`；
  `test_runtime.py` 的 deadline 用例改为断言"策略上限 6 次尝试"以消除全量连跑抖动。
- **验证结果**：

  | 验证项 | 结果 |
  |---|---|
  | 全量 unittest | 345 项 OK（skipped=1） |
  | heldout / dev 评测 | 重新生成 `20261106T192311_*`、`20261106T192319_*`；A 20/30、B 21/30、C 23/30 |
  | 真实 DeepSeek 同题重跑 | `20261106T1922_*`：物理请求 7 = 账本 7、13,714 tokens、`narrative_discrepancies=0` |

- **回滚参考命令**：`git revert <hash>`

## [2026-11-07] 任务 021 - 模型链路审查文档（未提交）

- **代码基线**：`main` / `45af0cb`，开始时工作区干净，与本地 origin/main 一致。
- **本轮 Commit**：`Pending`；没有提交或推送。
- **变更**：021 Prompt、模型链路审查报告、文档索引/开发日志/问题记录/路线图提示；未修业务代码。
- **验证**：301 tests OK（skipped=1）、57 项契约检查、scripted CLI 通过；独立复现 N1–N6。
- **建议 Commit Message**：`docs: review model-driven paths and record reproducible defects`。
- **回滚说明**：仅未提交审查文档，先查看差异，不自动回滚或修改 Git 历史。

## [2026-11-07] 任务 017 - 修复复查文档（未提交）

- **代码基线**：`main` / `bf30dd5`，开始时与本地 origin/main 一致，工作区干净。
- **本轮 Commit**：`Pending`，没有提交或推送。
- **变更**：新增 Task 017 复查报告和 Prompt；更新文档索引、路线图提示、开发日志和问题记录；未修业务代码。
- **验证**：238 项 unittest、57 项契约检查、SQLite CLI 入口通过；保留集离线结果重现；新增反例发现 R1–R7。
- **建议 Commit Message**：`docs: recheck release fixes and record remaining boundary defects`。
- **回滚说明**：本轮仅未提交文档，先审查差异，不自动执行回滚或修改 Git 历史。

> **重要**：本文档只用于**追溯**，真正的代码回滚依赖 Git 提交记录。不要把本文档当作代码快照。
> 所有回滚操作必须先经项目所有者确认，不自动执行 `git reset` / `git rebase` / `git push --force`。

---

## 模板

```markdown
## [YYYY-MM-DD] 阶段名称 - 任务 NNN

- **开发阶段**：
- **对应任务**：NNN - 任务标题
- **Git 分支**：
- **Commit Hash**：`<hash>` / `Pending`
- **Commit Message**：

### 本次变更

| 文件 | 变更类型 |
|---|---|

### 验证结果

| 验证项 | 结果 |
|---|---|

### 回滚参考命令

```bash
# 撤销该提交（保留改动到工作区）
git revert <hash>

# 查看该提交内容
git show <hash> --stat
```
```

---

## 仓库基本信息

- **远端**：`https://github.com/minatolog/commercial-property-multi-agent.git`
- **默认分支**：`main`
- **Conda 环境**：`commercial-agent` → `D:\anacada\envs\commercial-agent`（Python 3.11.18）

---

## [2026-11-07] 任务 020 - 真实 DeepSeek 首跑与 3 项装配修复

- **开发阶段**：真实服务集成 / 缺陷修复。
- **对应任务**：020（项目所有者填入真实密钥后首次真实调用）。
- **Git 分支**：`main`。
- **Commit Hash**：提交后回填。
- **变更**：工具名暴露映射、token 预算、报告模型绑定与成本口径、真实调用证据归档。
- **验证结果**：
  - `python -m unittest discover -s tests -p "test_*.py"` → **301 项通过**（1 项 skip）；
  - `python tests/smoke_agent_contracts.py` → **57 项通过**；
  - `ask --provider deepseek` 成功（3 模型 / 3 工具 / 6325 tokens）；
  - `investigate --model-provider deepseek` → `conflicting` + 756.00，8 模型 / 12 工具 / 14,421 tokens；
  - `evaluate --split dev --model-provider deepseek` → B 1/7、C 0/6，报告头部正确标注 `deepseek/deepseek-chat`。
- **未完成**：heldout 真实对照、重复测量稳定性、成本定价、PostgreSQL、人工量表、部署。
- **回滚参考**（仅在项目所有者确认后执行）：

```powershell
git --no-pager show <hash> --stat
```

---

## [2026-11-07] 任务 019 - 让 `.env` 真正生效

- **开发阶段**：环境配置 / 可用性修复。
- **对应任务**：019（用户问"在哪里填写 key"触发的核对）。
- **Git 分支**：`main`。
- **Commit Hash**：提交后回填。
- **变更**：新增 `backend/app/env.py`；CLI 与 API 入口加载 `.env`；`.env.example` / 两个 README 说明；新增 15 项测试。
- **验证结果**：
  - `python -m unittest discover -s tests -p "test_*.py"` → **299 项通过**；
  - `python tests/smoke_agent_contracts.py` → **57 项通过**；
  - `git check-ignore -v .env` → 确认不入库；
  - `.env` 填占位值后 `build_model_client("deepseek")` 可构造客户端（证明填了就被用上）；
  - `.env` 留空时 `--model-provider deepseek` → EXIT=2 + `MissingApiKeyError`。
- **未完成**：真实 DeepSeek 调用（需项目所有者填入自己的 Key）。
- **回滚参考**（仅在项目所有者确认后执行）：

```powershell
git --no-pager show <hash> --stat
```

---

## [2026-11-07] 任务 018 - 模型驱动的领域 Agent 与 B/C 真实运行入口

- **开发阶段**：Agent / Runtime / 评测装配。
- **对应任务**：018（Task 017 复查报告第 3 节第 4 条）。
- **Git 分支**：`main`。
- **Commit Hash**：提交后回填。
- **变更**：新增 `LLMToolAgent` 与三个领域 LLM 实现、`facts.py` 共享事实契约、`llm/scripted.py`、`llm/factory.py`；`engine` 装配参数；B/C 的 `model_client` 入口；CLI `--model-provider`；修复并发模型预算记账。
- **验证结果**：
  - `python -m unittest discover -s tests -p "test_*.py"` → **284 项通过**；
  - `python tests/smoke_agent_contracts.py` → **57 项通过**；
  - `investigate --model-provider scripted` → EXIT=0，3 子任务 success，`used_model_calls=6`、`used_tool_calls=4`，`conflicting` + `partial`；
  - `--model-provider deepseek`（investigate 与 evaluate）→ EXIT=2 + `MissingApiKeyError`。
- **未完成**：真实 DeepSeek 调用（无密钥）、PostgreSQL 实机、人工量表、部署验证。
- **回滚参考**（仅在项目所有者确认后执行）：

```powershell
git --no-pager show <hash> --stat
```

---

## [2026-11-07] 任务 017 修复 - 复查缺陷 R1–R7

- **开发阶段**：编排 / 数据层 / RAG / Runtime / API（缺陷修复）。
- **对应任务**：017（依据 `docs/reviews/2026-11-07_release_candidate_recheck.md`）。
- **Git 分支**：`main`。
- **Commit Hash**：提交后回填（本轮改动集中在 `investigation.py`、`api/service.py`、`rag/*`、`tools/*`、`agents/lease/agent.py`、`runtime/tool_loop.py` 与 5 个测试文件）。
- **变更**：thread 身份守卫与按 run 过滤、范围默认拒绝与回填、数据范围/授权范围拆分、文档签署状态贯穿、空回答判失败、补查闸门改为可重试子任务、证据按 chunk_id 精确绑定。
- **验证结果**：
  - `python -m unittest discover -s tests -p "test_*.py"` → **261 项通过**；
  - `python tests/smoke_agent_contracts.py` → **57 项通过**；
  - R1 CLI 实测：同 `--thread-id` 第二次 `EXIT=2` 并给出 `invalid_context`；
  - R1 图实测：复用被拒，新线索对越权主体返回 `insufficient` 且不含他人金额；
  - R5 实测：工具后空回答 → `model_error` / `completed=False`。
- **未完成**：真实模型、PostgreSQL、人工量表、部署验证。
- **回滚参考**（仅在项目所有者确认后执行）：

```powershell
git --no-pager show <hash> --stat
```

---

## [2026-11-06] 任务 016 第三批 - 独立环境复现与运行态文件治理

- **开发阶段**：交付验证 / 仓库卫生。
- **对应任务**：016 第三批（可离线完成的部分）。
- **Git 分支**：`main`。
- **Commit Hash**：
  - `9da7189` — `chore(repo): stop tracking the local SQLite migration fallback`
  - 文档同步：见下一条记录（本轮文档提交后回填）。
- **变更**：`.gitignore` 增加 `*.db` 系列；`backend/commercial_agent_migrate.db` 退出 Git 跟踪（本地可重建）。
- **验证结果**：
  - 全新 venv（base=conda `commercial-agent`）隔离确认后 `pip install -e .`，全量 **238 项测试 + 57 项契约**通过，`check` 与 `investigate --backend sqlite` 均 `EXIT=0`；
  - 本地 `uvicorn` + 浏览器实访演示页，运行/线程 ID、结论、证据、冲突、审批阶段与 Trace 渲染正确；
  - `alembic upgrade head` 重新生成被忽略的 SQLite 文件（`EXIT=0`）。
- **未完成**：真实 DeepSeek 调用（无 `DEEPSEEK_API_KEY`）、PostgreSQL 实机（无服务，5432 不可达）、人工量表评分。
- **回滚参考**（仅在项目所有者确认后执行）：

```powershell
git --no-pager show 9da7189 --stat
git --no-pager revert --no-commit 9da7189   # 恢复跟踪该 SQLite 文件（不推荐）
```

---

## [2026-11-06] 任务 016 实施 - 版本候选缺陷修复（第一批 + 第二批）

- **开发阶段**：评测 / Runtime / 编排 / 审批 / API / 数据层（缺陷修复）。
- **对应任务**：016（依据 `docs/reviews/2026-11-06_release_candidate_review.md`）。
- **Git 分支**：`main`。
- **Commit Hash**：
  - `a9c6355` — `fix(runtime): repair scoring, ownership isolation and failure recovery`（F1–F8、S1–S4 与 reason 持久化）
  - `43b48ef` — `fix(eval): treat contract gaps as manual review, not as wrong answers`（评分器契约缺口语义）
  - `97b4e9f` — `docs: record the release candidate review and the fixes that closed it`（文档、Prompt 归档与评测报告）
- **变更**：见开发日志「任务 016 实施」；新增 `backend/app/rag/catalog.py`、`docs/evaluation/scoring_v2.md`、`docs/evaluation/cases/heldout_v3.jsonl`。
- **验证结果**：
  - `python -m unittest discover -s tests -p "test_*.py"` → **238 项通过**；
  - `python tests/smoke_agent_contracts.py` → **57 项检查通过**；
  - `investigate --backend sqlite` → 退出码 0（修复前崩溃）；
  - `approve --reason` → 台账 `stages[0].reason` 落库；
  - 评测（`scoring-v2`，绑定 `43b48ef`）：heldout A 20/30、B 21/30、C 23/30；dev 三基线 0/7（人工量表题）。
- **回滚参考**（仅在项目所有者确认后执行）：

```powershell
git --no-pager show a9c6355 --stat
git --no-pager revert --no-commit 43b48ef   # 撤销评分契约缺口语义
```

---

## [2026-11-06] 任务 016 - 版本候选审查文档（未提交）

- **开发阶段**：独立审查；仅文档归档。
- **被审查基线**：`main` / `041b2c5`，检查开始时与 `origin/main` 一致，工作区干净。
- **本轮 Commit Hash**：`Pending`（审查阶段的文档随后与实施记录一起提交，见 `97b4e9f`）。
- **变更**：新增完整审查报告与 016 Prompt；更新文档编号、当前进度提示、开发日志与问题记录。审查轮次未修复业务代码；修复在后续实现轮次完成。
- **验证**：192 项 unittest 与 57 项契约检查通过；离线评测重现原结果，额外反例揭示评分/集成/恢复/隔离缺陷。
- **报告**：`docs/reviews/2026-11-06_release_candidate_review.md`。
- **建议 Commit Message**：`docs: audit agent-first release candidate and record reproducible defects`。
- **回滚参考**：当前仅未提交的文档改动，审查差异后由用户决定是否保留，不自动执行回滚。

---

## [2026-11-06] 任务 007 返修 - Prompt 2-R1（F1/F2，待复验，未提交）

- **开发阶段**：阶段 1' - Agent Runtime（返修）
- **对应任务**：007 - Prompt 2-R1
- **Git 分支**：`main`；**现有 HEAD**：`7ed2665bb9201568a8d74a12af37bf0a502378f1`（既有提交，非本次）
- **本任务 Commit Hash**：`Pending`（未暂存、未提交、未推送）
- **当前状态**：R1 已修复，待 Codex 复验

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/app/fixtures/repository.py` | 修改（F1：按本租约账单过滤 allocations / payments） |
| `backend/app/runtime/agent_runtime.py` | 修改（F2：run_id 生成 + 本 run Trace 过滤） |
| `backend/app/runtime/types.py` | 修改（F2：`ToolTrace.run_id`、`to_agent_context(run_id=...)`） |
| `backend/app/agents/base/contracts.py` | 修改（F2：`AgentContext.run_id`，可空） |
| `backend/app/tools/executor.py` | 修改（F2：Trace 写入 run_id） |
| `backend/tests/test_runtime.py` | 修改（新增 F1 2 个 + F2 2 个回归，共 51 个测试） |
| `docs/prompts/04_agents/2026-11-06_007_agent_runtime_controlled_tools.md` | 修改（§1 状态、§10/§11 计数、新增 §16） |
| `docs/development_logs/development_log.md` | 修改（R1 记录） |
| `docs/checkpoints/git_history.md` | 修改（本记录） |
| `docs/README.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | 修改（状态：R1 已修复，待复验） |

**无数据库/模型/依赖变更**：`docs/architecture/database_design.md` 未变；未安装依赖、未调用模型、未建库。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 既有骨架自检 | ✅ 57 项通过（退出码 0） |
| 自动化测试 | ✅ 51 个测试通过（退出码 0） |
| CLI `--help`/`tools`/`check`/`demo` | ✅ 退出码 0 |
| 数据变体 | ✅ 未收 `17280.00` |
| 预算耗尽 | ✅ 退出码 2，`BUDGET_EXHAUSTED` 可见 |
| F1 回归 | ✅ A-301 仍为 `52596.00 / 34560.00 / 18036.00`，不含 A-302 的 `alloc_test_a302` |
| F2 回归 | ✅ 连续/并发 run 各 3 条 Trace、互不交叉；共享 TraceLog 保留全部 6 条 |
| `git diff --check` | ⚠️ 仍仅有 `database_design.md:1661` EOF 空行（Task 005 遗留） |

### 建议 Commit Message（复验通过且用户确认后）

`fix: scope billing payments per lease and isolate per-run traces`

### 回滚边界

未提交，无 hash 可回退。若需撤销本次返修，仅回退上表 6 个代码/测试文件与 5 个文档到执行前内容；不影响 Task 007 首轮实现与此前未提交变更。

---

## [2026-11-06] 任务 007 - Agent Runtime 与受控工具执行（待验收，未提交）

- **开发阶段**：阶段 1' - Agent Runtime 与受控 Tool Calling
- **对应任务**：007 - Prompt 2（Runtime 与 Tool Executor 最小实现）
- **Git 分支**：`main`；**现有 HEAD**：`7ed2665bb9201568a8d74a12af37bf0a502378f1`（既有提交，非本次）
- **本任务 Commit Hash**：`Pending`（未暂存、未提交、未推送）
- **当前状态**：DeepSeek 已交付并自检，待 Codex 验收

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/pyproject.toml` | 新增（依赖声明 / pytest 配置 / CLI 入口） |
| `backend/README.md` | 新增（运行命令、模块地图、安全边界） |
| `backend/app/fixtures/{__init__,repository}.py` | 新增（fixture 只读仓库、Decimal、项目范围、变体） |
| `backend/app/runtime/{__init__,types,budget,agent_runtime}.py` | 新增（可信上下文、证据、预算、Runtime） |
| `backend/app/tools/registry.py` | 新增（工具静态白名单） |
| `backend/app/tools/executor.py` | 新增（统一执行器：权限/参数/超时/重试/预算/Trace） |
| `backend/app/tools/fixture_tools.py` | 新增（Lease/Billing/Property 只读工具） |
| `backend/app/demo.py` | 新增（Fake ScriptedToolAgent + 接线，无模型调用） |
| `backend/app/cli.py` | 新增（`--help` / `tools` / `check` / `demo`） |
| `backend/tests/test_runtime.py` | 新增（47 个 unittest 测试，pytest 可收集） |
| `backend/app/agents/base/{errors,contracts,base_agent,registry}.py` | 修改（K1、K3、错误码与可选上下文字段） |
| `backend/app/agents/factory.py` | 修改（K2 一致性校验） |
| `backend/app/orchestration/coordinator.py` | 修改（K4/K5 聚合语义） |
| `backend/app/paths.py`、`backend/app/tools/base.py` | 修改（fixture 路径；`BaseTool`/`ToolInvocation`） |

**文档同步**：007 归档、Docs README、开发日志、Issue、路线状态、本检查点。
**未改**：`docs/architecture/database_design.md`、三个 Agent 业务实现与 YAML、历史 Prompt 原文。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 既有骨架自检 | ✅ 57 项通过（退出码 0） |
| 新增自动化测试 | ✅ 47 个测试通过（退出码 0） |
| CLI `--help` / `tools` / `check` | ✅ 均退出码 0 |
| CLI `demo` | ✅ `success`；3 调用、3 Trace、24 证据；未收 `18036.00` |
| CLI `demo --variant v_oct_rent_corrected` | ✅ 未收 `17280.00` |
| CLI `demo --budget-tool-calls 1` | ✅ 退出码 2，`BUDGET_EXHAUSTED` 可见 |
| pytest | ⚠️ 环境未安装（本任务禁止安装），测试以 unittest 执行且可被 pytest 收集 |
| 依赖 | ✅ 仅声明 pydantic / PyYAML；未安装任何新依赖 |
| `git diff --check` | ⚠️ 仅既有 `database_design.md:1661` EOF 空行（Task 005 遗留，本任务不改该文件） |

### 建议 Commit Message（验收通过且用户确认后）

`feat: add offline agent runtime with controlled read-only tools`

### 回滚边界

未提交，无 hash 可回退。若需撤销本次实现，按上表删除新增文件、还原修改文件到执行前内容；执行前 96 个文件的 SHA-256 已记入会话基线。不恢复、不删除整个工作区，不影响此前未提交变更。

---

## [2026-11-06] 任务 006 / Prompt 1-R2 - Codex 复验通过（未提交）

- **开发阶段**：阶段 0' - Agent-first 基线与评测规格验收
- **对应任务**：006 - Prompt 1（R1/R2 返修后的独立复验）
- **Git 分支**：`main`；**HEAD**：`7ed2665bb9201568a8d74a12af37bf0a502378f1`
- **Commit Hash**：`Pending`（未提交、未推送）
- **结论**：Task 006 已验收；Prompt 2 / Task 007 可进入实施。
- **复验报告**：[`docs/reviews/2026-11-06_task006_r2_review.md`](../reviews/2026-11-06_task006_r2_review.md)
- **证据**：场景选择器 `62/62`；审批回归 `30/30`；真实 JSON/JSONL 与审批重放语义核验通过；R2 hash 比对确认仅 8 个授权文档变化，backend 62 文件及 database_design 未变。
- **边界**：只验收规格与 fixture；不代表 Runtime、模型调用或数据库已实现。`git diff --check` 唯一告警为 Task 005 遗留 `database_design.md:1661` EOF 空行。
- **Git 工作区**：沿用此前广泛未提交变更；本记录不暂存或提交任何内容。

---

## [2026-11-06] 任务 006 返修 - Prompt 1-R2（返修完成，已由 Codex 复验通过，未提交）

- **开发阶段**：阶段 0' - Agent-first 基线与评测规格（第二轮窄范围返修）
- **对应任务**：006 - Prompt 1-R2（不是任务 007）
- **Git 分支**：`main`；**现有 HEAD**：`7ed2665bb9201568a8d74a12af37bf0a502378f1`（既有提交，非本次）
- **本任务 Commit Hash**：`Pending`（未提交、未推送）
- **当前状态**：返修完成，待 Codex 复验

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `docs/evaluation/fixtures/agent_first_v1.json` | 修改（`scenario_protocol` r2、`approval_replay` 去 `replayed` + `delivery`、`spec_revision` r2） |
| `docs/evaluation/cases/smoke_v1.jsonl` | 修改（C06/C08 协议版本、`scenario_resolution`、probe 证据策略） |
| `docs/evaluation/evaluation_plan.md` | 修改（§2.3 运行项/双端匹配/错误码、§5、§7、§9 S7–S9） |
| `docs/architecture/agent_runtime_contracts.md` | 修改（§9.2、§12.6 重放投递语义） |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 修改（§15 与 §5/§6/§7/§9） |
| `docs/README.md` | 修改（006 状态为 R1/R2 返修完成、待复验） |
| `docs/development_logs/development_log.md` | 修改 |
| `docs/checkpoints/git_history.md` | 修改（本记录） |

**无代码变更**：`backend/` 62 个文件逐文件 SHA-256 一致；`docs/architecture/database_design.md` hash 未变；未安装依赖、未建库、未调用模型 API。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 执行前基线 | 94 个文件逐文件 SHA-256 |
| JSON / JSONL | ✅ 8 行；fixture 与 JSONL 协议版本 r2 |
| 运行项展开 | ✅ 14 项（C06=2、C08=6、其余各 1） |
| 选择器解析 | ✅ C06 两路径、C08 六路径、普通 case 均按 `scenario_id` 命中 fixture 事件与证据 |
| 错误注入 | ✅ 10 个反例、8 类错误码全部按预期抛出 |
| 同 ID 同内容幂等 | ✅ 逐字段相同、无 `replayed`、ignored=1、预算增量 0 |
| 同 ID 异内容冲突 | ✅ `EVENT_ID_CONFLICT` |
| 证据 / Decimal / 链接 | ✅ 全命中；`18036.00`、`756.00`、更正后 `17280.00`；0 断链 |
| 程序化检查合计 | ✅ `PASS=62 / FAIL=0` |
| 文件级 hash 比对 | ✅ 0 新增 / 0 删除；8 个文件变化（授权范围）；`backend/` 与 `database_design.md` 未变 |
| `git diff --check` | ⚠️ 仅 `database_design.md:1661` 任务 005 遗留告警 |

### 建议 Commit Message（待复验通过且用户确认后）

`docs: make scenario selection executable and replay content-identical`

### 回滚边界

未提交，无 hash 可回退。若需撤销本次修正，仅回退上述 8 个文件到执行前内容（执行前 SHA-256 已记录在会话基线中），不恢复、不删除整个工作区，不影响接手前的未提交变更。

---

## [2026-11-06] 任务 006 返修 - Prompt 1-R1（返修完成，待复验，未提交）

- **开发阶段**：阶段 0' - Agent-first 基线与评测规格（返修）
- **对应任务**：006 - Agent-first 基线、契约与首批评测样例（Prompt 1-R1，不是任务 007）
- **Git 分支**：`main`
- **现有 HEAD**：`7ed2665bb9201568a8d74a12af37bf0a502378f1`（任务 001/002 的既有提交，**不是**本次提交）
- **本任务 Commit Hash**：`Pending`（未提交、未推送）
- **当前状态**：返修完成，待 Codex 复验

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `docs/evaluation/fixtures/agent_first_v1.json` | 修改（R1、R3 场景协议与审批主体） |
| `docs/evaluation/cases/smoke_v1.jsonl` | 修改（R1、R2、R3，8 行全部重写） |
| `docs/evaluation/evaluation_plan.md` | 修改（R1、R2、R6） |
| `docs/architecture/agent_runtime_contracts.md` | 修改（R4、R5、R6） |
| `docs/architecture/agent_architecture.md` | 修改（K6→N1 的交叉引用更正） |
| `docs/product/mvp_scope_v2.md` | 修改（R6） |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 修改（§1/§4/§5–§9 + 新增 §14） |
| `docs/README.md` | 修改（006 状态） |
| `docs/development_logs/development_log.md` | 修改 |
| `docs/checkpoints/git_history.md` | 修改（本记录） |

**无代码变更**：`backend/` 全部文件逐文件 SHA-256 一致；`docs/architecture/database_design.md` hash 未变；未安装依赖、未建库、未迁移、未调用模型 API。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 执行前基线 | 93 个文件、1,080,865 字节，逐文件 SHA-256 记录 |
| JSON/JSONL | ✅ fixture 可解析；8 行、case_id 唯一；场景引用全部可解析 |
| 证据 ID / 负例 | ✅ 顶层与场景级 required 全命中；负例语义正确 |
| Decimal 金额 | ✅ 未收 `18036.00`；超额 `756.00`；更正后未收 `17280.00` |
| R1–R6 语义检查（S1–S6） | ✅ 全部通过（失败路径不要求证据、probe 成功才要求、A/B/C 共同质量、审批授权、重放不重复计账、verify 全覆盖） |
| Markdown 相对链接 | ✅ 0 断链 |
| 程序化检查合计 | ✅ `PASS=178 / FAIL=0` |
| 文件级 hash 比对 | ✅ 0 新增 / 0 删除；10 个文件变化（均为授权范围）；`backend/` 与 `database_design.md` 未变 |
| `git diff --check` | ⚠️ 仍仅有 `database_design.md:1661` 任务 005 遗留告警 |

### 建议 Commit Message（待复验通过且用户确认后）

`docs: fix task 006 spec conflicts for timeout, baselines and approval`

### 回滚边界

未提交，无 hash 可回退。若需撤销本次返修，仅回退上述 10 个文件到执行前内容（执行前 SHA-256 已记录在会话基线文件中），不恢复、不删除整个工作区，不影响接手前的未提交变更。

---

## [2026-11-04] 总路线图文 PDF 派生交付（未提交）

- **关联任务**：006 总路线的阅读批注版；不占用下一个正式开发任务编号。
- **Commit Hash**：`Pending`。
- **新增产物**：`output/pdf/commercial_property_agent_first_roadmap_notability.pdf`。
- **同步文档**：Docs README、006 归档第 13 节、开发日志及本记录。
- **验证**：16 页、16 项书签、中文文本可提取、全页渲染与视觉检查通过。
- **进度边界**：不改变 006 待修正状态，不修改业务源码或原 Conda 环境，无提交或推送。
- **建议提交信息**：`docs: add illustrated roadmap PDF for Notability`。

---

## [2026-11-03] 任务 006 首轮 Review 与总路线（待修正，未提交）

- **分支/现有 HEAD**：`main` / `7ed2665bb9201568a8d74a12af37bf0a502378f1`
- **本任务 Commit Hash**：`Pending`
- **当前结论**：DeepSeek 初稿已交付；Codex 首轮待修正；Prompt 1-R1 已准备。
- **新增**：`docs/reviews/2026-11-03_task006_review.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`。
- **同步**：006 归档、Docs README、开发日志、Issue 和本检查点。
- **验证**：数据解析、引用、变体和关键 Decimal 金额通过；旧 smoke 57 项通过；规格层仍有 6 组待修正问题。
- **进度口径**：10 次正式 Prompt；当前已发送 1 次，待一次返修，后续正式任务 9 次；不以文档交付计算工程完成百分比。
- **建议提交信息（最终验收后）**：`docs: establish agent-first MVP scope and evaluation baseline`
- **回滚边界**：未提交，不执行全工作区恢复；后续仅针对经核实的本任务变更处理，保留既有未提交文件。

---

## [2026-11-03] Agent-first Prompt 1 准备 - 任务 006（待执行）

- **开发阶段**：Agent-first 基线准备
- **对应任务**：006 - 基线、契约与首批评测样例
- **Git 分支**：`main`
- **准备时 HEAD**：`7ed2665bb9201568a8d74a12af37bf0a502378f1`（已有提交，不是本任务提交）
- **Commit Hash**：`Pending`
- **当前状态**：Codex 已准备 Prompt；DeepSeek 未执行；Codex 未验收。

### 本次变更

- 新增 `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md`。
- 更新 `docs/README.md`、`docs/development_logs/development_log.md` 与本文件。
- 既有代码、数据库设计及未提交变更保留，不归入本任务准备阶段成果。

### 验证结果

- 已核实当前 Git 分支、HEAD 及未提交状态。
- 准备阶段不修改业务代码、不安装依赖、不建库、不执行提交或推送。
- 任务交付及验收结果待补充；不能以此记录证明任务 006 已完成。

### 建议 Commit Message（完成并验收后）

`docs: establish agent-first MVP scope and evaluation baseline`

### 回滚边界

本阶段无提交可回滚。任何后续撤销仅限审查确认的本任务变更，不恢复或删除整个工作区，不影响接手前未提交内容。实际提交后才补充真实 hash 与对应撤销方案。

---

## [2026-11-06] 里程碑 6：Task 015 交付材料与版本候选（待提交）

- **开发阶段**：阶段 7' 交付与验收
- **对应任务**：015（Prompt 10）
- **Git 分支**：`main`
- **Commit Hash**：`b25d1b1`（父提交 `48c5b84`）
- **推送状态**：✅ `main -> origin/main`（`48c5b84..b25d1b1`）
- **版本动作**：**未打 Tag、未发布、未部署**（需项目所有者确认）

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `README.md`、`.env.example`、`docs/demo/demo_script.md` | 新增 |
| `backend/README.md` | 重写 |
| `docs/evaluation/reports/*` | 更新为最终两批（dev、heldout v2） |

### 验证结果

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 192 tests ... OK` |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| `python -m pip install --dry-run -e .` | 依赖可解析 |
| `python -m app.cli evaluate --split heldout` | A 0.5556 / B 0.5926 / C 0.8519 |

### 回滚参考命令

```bash
git revert <hash>
```

---

## [2026-11-06] 里程碑 5：Task 014 FastAPI 与演示页（已提交并推送）

- **开发阶段**：阶段 6' 演示与交互
- **对应任务**：014（Prompt 9）
- **Git 分支**：`main`
- **Commit Hash**：`48c5b84`（父提交 `3573e0c`）
- **推送状态**：✅ `main -> origin/main`（`3573e0c..48c5b84`）

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/app/api/*`（`__init__` / `app` / `service` / `static/index.html`） | 新增 |
| `backend/tests/test_api.py` | 新增（13 项） |
| `backend/pyproject.toml`、`backend/tests/test_runtime.py` | 修改 |

### 验证结果

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 192 tests ... OK` |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| uvicorn 实测（`/api/meta`、`/`、`POST /api/runs`） | 200 / 200 / 201 |

### 回滚参考命令

```bash
git revert <hash>
```

---

## [2026-11-06] 里程碑 4：Task 013 三基线与 40 题评测（已提交并推送）

- **开发阶段**：阶段 5' 评测与量化
- **对应任务**：013（Prompt 8）
- **Git 分支**：`main`
- **Commit Hash**：`3573e0c`（父提交 `dd517b4`）
- **推送状态**：✅ `main -> origin/main`（`dd517b4..3573e0c`）

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `docs/evaluation/scoring_v1.md`、`cases/heldout_v1.jsonl`、`cases/heldout_v2.jsonl`、`reports/*` | 新增 |
| `backend/app/evaluation/*`、`backend/scripts/generate_heldout_cases.py` | 新增 |
| `backend/tests/test_evaluation.py` | 新增（23 项） |
| `backend/app/cli.py`、`paths.py` | 修改 |

### 验证结果

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 179 tests ... OK` |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| `python -m app.cli evaluate --split heldout` | A 0.5556 / B 0.5926 / C 0.8519（27 计分题，离线） |

### 回滚参考命令

```bash
git revert <hash>
```

---

## [2026-11-06] 里程碑 3：Task 012 持久检查点与人工审批（已提交并推送）

- **开发阶段**：阶段 4' 可靠性与人机协同
- **对应任务**：012（Prompt 7）
- **Git 分支**：`main`
- **Commit Hash**：`dd517b4`（父提交 `87027e6`）
- **推送状态**：✅ `main -> origin/main`（`87027e6..dd517b4`）

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/app/orchestration/{approval,checkpointing}.py`、`backend/app/control_plane.py` | 新增 |
| `backend/tests/test_approval.py` | 新增（21 项） |
| `backend/app/orchestration/investigation.py` | 修改：审批节点、`resume()`、thread 标识 |
| `backend/app/{investigation_demo,cli,paths}.py`、`db/bootstrap.py` | 修改 |
| `backend/pyproject.toml`、`.gitignore` | 修改 |
| `docs/prompts/04_agents/2026-11-06_012_*.md` | 新增 |

### 验证结果

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 156 tests ... OK` |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| 四进程审批链（investigate → approve×2 → 重复 approve） | 全部退出码 0，状态依次正确 |
| 版本不匹配恢复 | 退出码 3，图保持暂停 |

### 回滚参考命令

```bash
git revert <hash>
```

---

## [2026-11-06] 里程碑 2：Task 010 只读数据层 + Task 011 合同 RAG（已提交并推送）

- **开发阶段**：阶段 2' 数据底座 + 阶段 3' 知识与证据层
- **对应任务**：010（Prompt 5）、011（Prompt 6）
- **Git 分支**：`main`
- **Commit Hash**：Task 010 = `3c10317`；Task 011 = `87027e6`
- **推送状态**：✅ `main -> origin/main`（`3c10317..87027e6`）

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/app/db/{models,session,seed,repository,bootstrap}.py`、`backend/migrations/` | 新增（Task 010） |
| `backend/app/rag/{pdf_builder,chunker,bm25,service,library,__init__}.py` | 新增（Task 011） |
| `backend/app/tools/knowledge_tools.py` | 新增（Task 011） |
| `docs/evaluation/documents/*.pdf` | 新增（合成文档产物） |
| `backend/app/agents/lease/agent.py`、`config/agents/lease.yaml` | 修改 |
| `backend/app/orchestration/investigation.py`、`investigation_demo.py` | 修改 |
| `backend/app/{cli,paths}.py`、`fixtures/repository.py` | 修改 |
| `backend/pyproject.toml` | 修改：`SQLAlchemy` / `alembic` / `pypdf` / `reportlab` |
| `backend/tests/{test_database_layer,test_rag,test_graph_workflow}.py` | 新增 / 修改 |
| `docs/prompts/02_database/2026-11-06_010_*.md`、`docs/prompts/03_rag/2026-11-06_011_*.md` | 新增 |

### 验证结果

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | `Ran 135 tests ... OK` |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| CLI `tools` / `check` / `demo` / `ask` / `investigate` / `search` | 全部退出码 0 |
| Alembic `upgrade head` / `downgrade`（SQLite） | 通过 |
| PostgreSQL 真库验证 | **未验证**（本机无 PostgreSQL 服务） |

### 回填记录

- Task 010：`3c10317`（已推送）
- Task 011：`87027e6`（已推送，父提交 `3c10317`）

### 回滚参考命令

```bash
# 查看该提交内容
git show <hash> --stat

# 撤销该提交（保留改动到工作区）
git revert <hash>
```

---

## [2026-11-06] 里程碑 1：Task 007 自检 + Task 008 + Task 009（已提交并推送）

- **Commit**：`7b87ef2`（父提交 `fe95ba5`）
- **推送状态**：✅ `main -> origin/main`（`fe95ba5..7b87ef2`）
- **提交原因说明**：三项任务的改动在同一工作树中累积（共享 `test_runtime.py` 与 `pyproject.toml`），
  逐项拆分会产生"中间提交单测失败"的状态，因此作为一个**已验证**里程碑提交；
  三项均有独立 Prompt 归档与验证记录。
- **验证**：57 项契约自检、94 项 unittest、6 个 CLI 命令全部退出码 0。

## [2026-11-06] Task 007 自检修复（待提交）

- **开发阶段**：阶段 1' - Runtime 与受控工具执行（自检收尾）
- **对应任务**：007（正式 Prompt 2）
- **Git 分支**：`main`
- **Commit Hash**：`Pending`
- **Commit Message**：见下方

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/app/fixtures/repository.py` | 修改（已收/未收按本租约核销金额） |
| `backend/tests/test_runtime.py` | 修改（新增拆分付款回归测试） |
| `docs/reviews/2026-11-06_task007_deepseek_selfcheck.md` | 新增 |
| `docs/prompts/04_agents/2026-11-06_007_agent_runtime_controlled_tools.md` | 修改 |
| `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | 修改 |
| `docs/development_logs/development_log.md` | 修改 |

### 验证结果

| 验证项 | 结果 |
|---|---|
| 57 项 smoke | ✅ 退出码 0 |
| unittest | ✅ `Ran 52 tests ... OK` |
| CLI（5 条命令） | ✅ 全部退出码 0（预算耗尽 2） |
| 租约隔离独立脚本 | ✅ 13/13 |
| Trace 隔离独立脚本 | ✅ 12/12 |

### 建议 Commit Message

```text
fix(billing): count statement paid amount by allocations to the lease

- `FixtureRepository.statement()` summed whole payment amounts, so a
  payment split across leases of the same project overstated paid_total
  and understated outstanding_total (reproduced: 35060.00 vs 34760.00)
- Derive paid_total from allocations whose invoice belongs to the lease
- Derive outstanding_total from per-invoice outstanding
- Add regression covering a 500.00 payment split 200/300 across A-301
  and A-302, asserting both leases stay correct
- Record DeepSeek self-check for Task 007 and update roadmap/logs

Verified: 57 smoke checks, 52 unittests, 5 CLI commands, budget-exhaustion
exit code 2, plus standalone lease-isolation (13/13) and trace-isolation
(12/12) probes.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

---

## [2026-11-03] 阶段 0' - Agent-first 基线与评测规格（待提交）

- **开发阶段**：阶段 0' - 方向重定与规格化
- **对应任务**：006 - Agent-first 基线、契约与首批评测样例（用户侧称 Prompt 1）
- **Git 分支**：`main`
- **Commit Hash**：`Pending`（等待 Codex 审查 + 用户确认；**未提交、未推送**）
- **Commit Message**：见下方「建议 Commit Message」

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `docs/decisions/ADR-005-agent-first-refocus.md` | 新增 |
| `docs/product/mvp_scope_v2.md` | 新增 |
| `docs/architecture/agent_runtime_contracts.md` | 新增 |
| `docs/evaluation/evaluation_plan.md` | 新增 |
| `docs/evaluation/fixtures/agent_first_v1.json` | 新增 |
| `docs/evaluation/cases/smoke_v1.jsonl` | 新增（8 行） |
| `docs/architecture/agent_architecture.md` | 修改 |
| `docs/architecture/system_design.md` | 修改 |
| `docs/README.md` | 修改 |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 修改（追加执行阶段） |
| `docs/development_logs/development_log.md` | 修改 |
| `docs/checkpoints/git_history.md` | 修改 |

**无代码变更**：`backend/` 全部文件前后一致；未安装依赖、未建库、未迁移、未调用模型 API。

### 验证结果

| 验证项 | 结果 |
|---|---|
| fixture / JSONL 结构与唯一性 | ✅ 44 实体；8 行；case_id 唯一有序 |
| 变体与证据 ID | ✅ 8/8 变体；required 全命中；负例语义正确 |
| Decimal 金额核对 | ✅ 未收合计 18036.00；冲销分配已排除（对照验证通过） |
| 数据变体 overlay | ✅ 更正后合计 17280.00，基线未被就地修改 |
| Markdown 相对链接 | ✅ 55 条，0 断链 |
| `backend/` 一致性 | ✅ 一致 |
| `git diff --check` | ⚠️ 1 条任务 005 遗留告警（本轮不改该文件，未处理） |
| 程序化断言 | ✅ 164/164 |

### 建议 Commit Message

```text
docs: establish agent-first MVP scope, runtime contracts and eval baseline

- Record the refocus decision in ADR-005, separating user-confirmed
  items from recommendations and defining conflict precedence
- Define the P0 scope with a verifiable completion matrix; keep P1 and
  paused items explicit; leave the P0 table count open pending review
- Add coding-level runtime contracts: contract versioning path,
  Evidence/Finding/Verification/Approval structures, Decimal money
  semantics, trusted-context permissions, tool executor gate order,
  state merge keys, budget ownership, resume and approval binding
- Add synthetic shared fixture (2 projects, 3 leases, 3 invoices,
  3 payments, 4 work orders, 4 documents) with self-consistent amounts
  and an explicit variant/overlay/event resolution protocol
- Add 8 machine-readable smoke cases C01-C08 covering deterministic
  lookup, single-agent retrieval, full investigation, conflicting
  evidence, missing documents, tool timeout, cross-project denial and
  the approval deny/grant/replay matrix
- List verified skeleton defects K1-K6 as task 007 fixes; do not change
  backend code in this task
- Correct system-design statements that no longer match reality and
  link them to ADR-005

Docs only: no code, no dependencies, no database, no model calls.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

**提交前检查清单**：

- [ ] Codex 审查通过
- [ ] 项目所有者确认
- [ ] `git status` 确认不包含接手前的无关变更误打包
- [ ] 确认无 `.env` / 密钥

### 回滚参考命令

```bash
# 仅回滚本任务新增文档（保留其他未提交改动）
git clean -fd docs/decisions docs/product docs/evaluation
git checkout -- docs/architecture/system_design.md docs/README.md

# 提交后、推送前
git reset --soft HEAD~1
```

---

## [2026-11-03] 阶段 2 复核 - 数据库设计 v2（待提交）

- **开发阶段**：阶段 2 - 数据层设计复核
- **对应任务**：005 - 数据库设计复核与 MVP 决策补充（用户侧标注 Task 003 Review）
- **Git 分支**：`main`
- **Commit Hash**：`Pending`（等待审核）
- **Commit Message**：见下方「建议 Commit Message」

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `docs/architecture/database_design.md` | 修改（v1 → v2，修复 12 项缺陷、新增 §14/§15） |
| `docs/prompts/02_database/2026-11-03_005_database_design_review.md` | 新增 |
| `docs/README.md` | 修改（编号登记表） |
| `docs/development_logs/development_log.md` | 修改 |
| `docs/checkpoints/git_history.md` | 修改 |
| `docs/lessons_learned/knowledge_notes.md` | 修改 |

**无代码变更**：未创建 `.sql`、未写模型、未写迁移、未安装 PostgreSQL、未执行任何 DDL。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 唯一约束 18 → 15 | ✅ 删除 3 条被蕴含的约束 |
| 索引 21 → 18 | ✅ 删除 2 条完全重复 + 1 条被 GiST 覆盖 |
| 排他约束可执行性 | ✅ 生成列 + 双触发器方案，附 11 场景验证表 |
| 核销并发方案 | ✅ 行锁 + 固定加锁顺序 + 10 测试用例 |
| Mermaid / 围栏 / 章节号 | ✅ 全部通过 |
| 未提交 Git | ✅ 按用户要求 |

### 建议 Commit Message

```text
docs(db): revise schema to v2 after design review

Fix 12 findings from the design review, two of them severe:

- occupied_to was nullable and became 'infinity' in the exclusion
  constraint, permanently locking a unit; make interval endpoints
  NOT NULL and materialize them from the lease
- blocks_occupancy had no initializer trigger, so inserting an
  occupancy row after an active lease silently bypassed the
  exclusion constraint; add BEFORE INSERT and AFTER propagation
  triggers so contract dates and occupancy can never diverge
- replace daterange(...) expressions inside EXCLUDE with STORED
  generated columns
- add reversed_at to payment_allocations and make its unique index
  partial, so payment reversal keeps audit history and correct balance
- add composite FKs from documents to leases/units for project
  consistency; make units.chargeable_area_sqm NOT NULL
- drop 3 redundant unique constraints and 3 redundant indexes,
  including indexes implicit in the exclusion constraints
- record DEC-001..003: deposits outside receivables, no meter
  readings, pending_signature does not occupy a unit
- document executable DDL, trigger set, 11 constraint scenarios,
  row-lock allocation protocol and tiered-rent rounding rules
- give default answers for the remaining 5 open questions

Docs only: no SQL files, no ORM models, no migrations, no database.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

**提交前检查清单**：

- [ ] 项目所有者已评审 §13.3 剩余 5 项
- [ ] 确认 `docs/` 下无临时文件
- [ ] 由项目所有者确认后才执行 `git add` / `git commit`

### 回滚参考命令

```bash
git checkout -- docs/architecture/database_design.md   # 提交前
git reset --soft HEAD~1                               # 提交后、推送前
git revert <hash>                                     # 已推送
```

---

## [2026-11-03] 阶段 2 - 数据库架构设计（待提交）

- **开发阶段**：阶段 2 - 数据层设计
- **对应任务**：004 - PostgreSQL 数据库架构设计（用户侧标注 Task 003）
- **Git 分支**：`main`
- **Commit Hash**：`Pending`（等待项目所有者审核设计后确认）
- **Commit Message**：见下方「建议 Commit Message」

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `docs/architecture/database_design.md` | 修改（骨架 → 完整设计，约 46000 字符） |
| `docs/prompts/02_database/2026-11-03_004_postgresql_database_design.md` | 新增 |
| `docs/prompts/02_database/.gitkeep` | 删除 |
| `docs/README.md` | 修改（编号登记表） |
| `docs/development_logs/development_log.md` | 修改 |
| `docs/checkpoints/git_history.md` | 修改 |
| `docs/lessons_learned/knowledge_notes.md` | 修改 |
| `docs/architecture/system_design.md` | 修改（待定问题 #9 已决策） |
| `docs/architecture/agent_development_guide.md` | 修改（新增数据访问规则） |

**无代码变更**：未创建 `.sql`、未写 SQLAlchemy 模型、未写 Alembic 迁移、未安装 PostgreSQL。
**不纳入版本控制**：`.vscode/`、`.env`、`__pycache__/`。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 文档章节完整（14 章） | ✅ 覆盖用户要求全部 10 项交付内容 |
| 14 张表逐表字段设计 | ✅ 6.1~6.14，含类型 / Nullable / 默认值 / 说明 |
| Mermaid ER 语法 | ✅ 14 实体 / 25 关系 / 属性行全部合法 |
| 代码围栏闭合 | ✅ 40 个围栏，偶数 |
| 约束与索引 | ✅ 17 唯一 / 2 排他 / 21 索引，均注明服务场景 |
| 状态机 | ✅ 5 组（租约/账单/收款/工单/Agent 运行） |
| 未创建真实数据库 | ✅ 未执行任何安装或连接 |
| 未提交 Git | ✅ 按用户要求 |

### 建议 Commit Message

```text
docs(db): design PostgreSQL schema for MVP (14 tables)

- Evaluate the initial 13-table proposal; no tables dropped or merged
- Add `lease_units` to support multi-unit leases later without a
  breaking migration (MVP limited by UNIQUE(lease_id))
- Enforce non-overlapping occupancy and charge-rule periods with
  PostgreSQL EXCLUDE constraints (btree_gist)
- Keep invoice totals, tenant, paid amount and overdue state derived
  via view v_invoice_outstanding instead of stored columns
- Model tiered rent and rent-free periods as dated charge-rule
  segments for reproducible historical billing
- Make documents immutable with version chain and checksum; drop
  updated_at
- Store Agent payloads as jsonb audit data, promote queryable fields
  (latency/tokens/error) to columns
- Add project_id isolation keys with composite FKs so denormalized
  columns cannot diverge
- Define TEXT + CHECK for enums and partial unique indexes for
  soft-delete-safe business numbers
- Document Agent -> Tool -> Service -> Repository -> Model boundary

Docs only: no SQL files, no ORM models, no migrations, no database.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

**提交前检查清单**：

- [ ] 项目所有者已评审 `database_design.md` 第 13.2 节的 8 项待确认问题
- [ ] 确认 `docs/` 下无临时文件
- [ ] 确认无 `.env` / 密钥
- [ ] 由项目所有者确认后才执行 `git add` / `git commit`

### 回滚参考命令

```bash
# 提交前放弃本次文档改动
git checkout -- docs/architecture/database_design.md

# 提交后、推送前撤销提交但保留改动
git reset --soft HEAD~1

# 已推送时使用可追溯撤销
git revert <hash>
```

---

## [2026-11-03] 阶段 0.5 - Agent 架构骨架（待提交）

- **开发阶段**：阶段 0 - 架构约束与接口骨架
- **对应任务**：003 - 模块化多 Agent 架构约束
- **Git 分支**：`main`
- **Commit Hash**：`Pending`（等待项目所有者确认后执行）
- **Commit Message**：见下方「建议 Commit Message」

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `backend/app/paths.py` | 新增 |
| `backend/app/agents/base/contracts.py` | 新增 |
| `backend/app/agents/base/protocol.py` | 新增 |
| `backend/app/agents/base/base_agent.py` | 新增 |
| `backend/app/agents/base/registry.py` | 新增 |
| `backend/app/agents/base/errors.py` | 新增 |
| `backend/app/agents/base/__init__.py` | 新增 |
| `backend/app/agents/factory.py` | 新增 |
| `backend/app/agents/lease/{__init__.py,agent.py,prompts/system.md}` | 新增 |
| `backend/app/agents/billing/{__init__.py,agent.py,prompts/system.md}` | 新增 |
| `backend/app/agents/compliance/{__init__.py,agent.py,prompts/system.md}` | 新增 |
| `backend/app/config/schema.py` | 新增 |
| `backend/app/config/loader.py` | 新增 |
| `backend/app/config/agents/{lease,billing,compliance}.yaml` | 新增 |
| `backend/app/llm/adapter.py` | 新增 |
| `backend/app/tools/base.py` | 新增 |
| `backend/app/orchestration/state.py` | 新增 |
| `backend/app/orchestration/coordinator.py` | 新增 |
| `backend/tests/smoke_agent_contracts.py` | 新增 |
| `docs/architecture/agent_architecture.md` | 新增 |
| `docs/architecture/agent_development_guide.md` | 新增 |
| `docs/prompts/04_agents/2026-11-03_003_modular_multi_agent_architecture.md` | 新增 |
| `.gitignore` | 修改（`env/` → `/env/`） |
| `docs/README.md` | 修改（编号登记表） |
| `docs/architecture/system_design.md` | 修改（引用 + ADR） |
| `docs/development_logs/development_log.md` | 修改 |
| `docs/lessons_learned/knowledge_notes.md` | 修改 |
| `docs/prompts/04_agents/.gitkeep` | 删除 |

**不纳入版本控制**：`.vscode/settings.json`、`.env`、`DEEPSEEK_API_KEY` 等全部密钥。

### 验证结果

| 验证项 | 结果 |
|---|---|
| 架构骨架自检 | ✅ 57 项全部通过，退出码 0 |
| 配置 Schema 拒绝非法输入 | ✅ 7 类非法配置全部被拒 |
| 禁用能力与缺失能力可区分 | ✅ `AgentDisabledError` / `CapabilityUnavailableError` |
| Prompt 隔离 | ✅ lease 与 billing 互不影响 |
| 模型参数裁剪 | ✅ `temperature: null` 时不下发 |
| 白名单防任意导入 | ✅ 白名单外 name 抛 `AgentNotRegisteredError` |
| 依赖范围 | ✅ 仅 pydantic / pyyaml 及传递依赖，无 AI 框架 |
| 无敏感信息 | ✅ YAML 中无密钥，密钥仅经 `api_key_env` 引用 |

### 建议 Commit Message

```text
feat(agents): establish modular multi-agent architecture skeleton

- Add AgentProtocol / BaseAgent with unified AgentRequest, AgentContext,
  AgentResult contracts (Pydantic, frozen, extra=forbid)
- Add AgentRegistry with capability discovery, enable/disable state,
  duplicate and capability-conflict rejection
- Add per-agent YAML config with schema validation that structurally
  rejects secret fields; API keys resolved from environment only
- Add model adapter layer to trim unsupported params per provider
- Add tool contract with allowlist plus permission checks
- Define LangGraph shared state reducers and coordinator degrade policy
- Register lease/billing/compliance skeleton agents via static allowlist
  (no dynamic import from config strings)
- Add architecture docs and agent development guide
- Anchor .gitignore `env/` to repo root to avoid ignoring nested packages

Verified: python backend/tests/smoke_agent_contracts.py -> 57/57 pass

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

**提交前检查清单**：

- [ ] `git status` 只包含预期文件
- [ ] `.vscode/` 与 `.env` 未出现在待提交列表
- [ ] 全仓搜索确认无 `sk-` 开头的密钥、无数据库密码
- [ ] 由项目所有者确认后才执行 `git add` / `git commit`

### 回滚参考命令

```bash
# 提交前放弃改动（谨慎：会丢弃未提交文件）
git restore --staged . && git checkout -- .

# 提交后、推送前撤销提交但保留改动
git reset --soft HEAD~1

# 已推送时使用可追溯撤销
git revert <hash>
```

---

## [2026-11-03] 阶段 0 - 工程基建（已提交）

- **开发阶段**：阶段 0 - 环境与工程规范搭建
- **对应任务**：001 - Conda 独立环境配置；002 - 项目文档与 Prompt 归档系统
- **Git 分支**：`main`
- **Commit Hash**：`7ed2665`
- **Commit Message**：`环境配置和prompt记录`

### 本次变更

| 文件 | 变更类型 |
|---|---|
| `.gitignore` | 新增 |
| `docs/README.md` | 新增 |
| `docs/architecture/system_design.md` | 新增 |
| `docs/architecture/database_design.md` | 新增 |
| `docs/prompts/01_environment/2026-11-03_001_conda_environment.md` | 新增 |
| `docs/prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md` | 新增 |
| `docs/prompts/02_database/.gitkeep` | 新增 |
| `docs/prompts/03_rag/.gitkeep` | 新增 |
| `docs/prompts/04_agents/.gitkeep` | 新增 |
| `docs/prompts/05_frontend/.gitkeep` | 新增 |
| `docs/prompts/06_testing/.gitkeep` | 新增 |
| `docs/development_logs/development_log.md` | 新增 |
| `docs/issues/issue_log.md` | 新增 |
| `docs/lessons_learned/knowledge_notes.md` | 新增 |
| `docs/checkpoints/git_history.md` | 新增 |

**不纳入版本控制**：`.vscode/settings.json`（个人机器配置，含解释器绝对路径，已被 `.gitignore` 忽略）。

### 验证结果

| 验证项 | 结果 |
|---|---|
| Conda 环境可用 | ✅ `commercial-agent`，Python 3.11.18，路径 `D:\anacada\envs\commercial-agent` |
| Python / pip 来源 | ✅ 均来自该环境（`sys.executable`、`python -m pip --version` 一致） |
| 环境隔离 | ✅ `sys.path` 无 base 环境路径泄漏 |
| 项目依赖 | ✅ 未安装（仅 pip / setuptools / wheel / packaging） |
| VS Code 解释器 | ✅ conda / 3.11.18 |
| 其他 Conda 环境 | ✅ `aiagent`、`z5581485` 未被修改或删除 |
| `docs/` 未被忽略 | ✅ `git check-ignore -v` 7 个路径全部 `NOT IGN` |
| 敏感信息 | ✅ 无 `.env`、密钥、密码被纳入（`.env` 已在 `.gitignore` 中） |

### 建议 Commit Message

```text
chore: bootstrap project docs system and Python environment config

- Add .gitignore covering secrets, Python caches, tool caches,
  vector store data and per-machine VS Code settings
- Add docs/ structure: architecture, prompt archive, development log,
  issue log, knowledge notes and git checkpoints
- Archive task 001 (Conda env setup) and task 002 (docs system) prompts
- Document conda compatibility issues and encoding pitfalls

Environment: conda env `commercial-agent`, Python 3.11.18

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

**提交前检查清单**：

- [x] `git status` 确认只包含预期文件
- [x] 确认 `.vscode/` 与 `.env` 未出现在待提交列表
- [x] 确认 `docs/` 下无临时文件、无乱码
- [x] 由项目所有者确认后执行 `git add` / `git commit`

> 实际提交时项目所有者使用了更简短的 message：`环境配置和prompt记录`（commit `7ed2665`）。上面的建议原文保留以备追溯。

### 回滚参考命令

本次为首个提交，无父提交可回退。若提交有误且**尚未推送**，可撤销提交但保留文件：

```bash
git reset --soft HEAD~1
```

若已推送，使用可追溯的撤销方式（不重写历史）：

```bash
git revert <hash>
```

---

## 后续阶段占位

> 2026-11-03 起按 ADR-005 的 Agent-first 路线重排；历史阶段划分保留在下表"历史"列。

| 阶段 | 内容 | 状态 | 历史对应 |
|---|---|---|---|
| 阶段 0' | 方向重定、运行时契约、评测规格与 8 题样例（任务 006） | 🔶 执行完成，待审查 | 原"阶段 0 文档/架构" |
| 阶段 1' | Agent Runtime 与受控 Tool Calling；修复 K1–K5（任务 007） | 未开始 | 原"阶段 1 项目骨架" |
| 阶段 2' | 最小数据底座 + Deterministic 基线 + fixture loader | 未开始 | 原"阶段 2 数据层" |
| 阶段 3' | LangGraph 编排、Verifier、故障恢复、审批节点 | 未开始 | 原"阶段 4 Agent 编排" |
| 阶段 4' | 三基线对照 + 30–50 题评测 + 演示与 README | 未开始 | 原"阶段 6 测试与部署" |
| — | 完整计费/押金/能耗/核销写引擎、招商、BI、完整前端 | **暂停** | 原"阶段 3 RAG 全量/阶段 5 API" |
