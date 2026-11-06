# 2026-11-06_016_release_candidate_review

## 1. 基本信息

- 日期：2026-11-06
- 任务编号：016
- 模块：06_testing
- 关联任务：007–015
- 执行者：Codex（按用户临时请求审查，不恢复逐任务复核流程）
- 被审查 Commit：`041b2c5`
- 本轮文档 Commit：`Pending`

## 2. 任务目标和背景

DeepSeek 已交付 Agent-First 版本候选。核实实际进度，检查实现、现有测试和关键边界，寻找可复现的设计/实现问题，给出后续修正顺序。

## 3. 原始用户 Prompt

```text
deepseek 已完成 帮我检查一下 项目进度 找找毛病
```

## 4. AI 实际执行的主要步骤

1. 检查 Git 状态与提交记录，读取最高需求基线、路线图、README 和实际模块。
2. 运行现有 192 项 unittest、57 项契约检查；重跑三个离线保留集评测，未覆盖历史报告。
3. 在临时目录/内存库构造金额字段交换、权限题、一次失败后恢复、审批恢复、非法模型工具响应、同项目其他合同、共享索引主体切换、数据库只读及 API 参数反例。
4. 将位置、复现结果、影响、修正验收标准归档至完整审查报告，并更新本轮文档索引、日志、问题记录和检查点。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| docs/reviews/2026-11-06_release_candidate_review.md | 新增 | 完整进度与缺陷报告 |
| 本文件 | 新增 | 本轮 Prompt 与执行归档 |
| docs/README.md | 修改 | 登记 016 |
| docs/product/PROJECT_DEVELOPMENT_ROADMAP.md | 修改 | 增加当前审查提示，保留历史自检记录 |
| docs/development_logs/development_log.md | 修改 | 本轮审查日志 |
| docs/issues/issue_log.md | 修改 | 版本候选待修正问题入口 |
| docs/checkpoints/git_history.md | 修改 | 审查基线与待提交文档状态 |

## 6. 执行结果和验证方式

- 192 项 unittest、57 项契约检查通过。
- 重现保留集原有计分结果：A 15/27、B 16/27、C 23/27；评分存在 F1/F2 缺陷，不能据此认定质量提升。
- 复现 8 项优先问题、4 项其他问题；另静态发现审批意见未转发。
- 完整证据和复现条件见 [审查报告](../../reviews/2026-11-06_release_candidate_review.md)。
- 未修改业务代码，未访问外部模型/PG，未执行 Git 提交、推送、发布或部署。

## 7. 遇到的问题及解决方法

测试全部通过仍存在跨模块装配、状态归并和评分错误。本轮通过真实入口和反例复现定位；问题尚未修复，不能将“报告已生成”记为“问题已解决”。

## 8. 对应 Git Commit Hash

- 审查基线：`041b2c5`。
- 本轮文档：`Pending`，本轮仅审查与归档。

## 9. 后续待办事项

- [ ] 按报告第一批修正正确性、评分与隔离。
- [ ] 按报告第二批修正数据库/图/审批/模型异常集成。
- [ ] 完成真实模型、PostgreSQL、严谨评测和独立环境复现。

---

## 10. 实施记录（本文件 §1–§9 为 Codex 审查原文，未改动）

用户在本任务之后的指令要求：按审查报告修复项目，先核对代码并复现问题再修改；第一批 F1/F2/F7/F8，第二批 F3/F4/F5/F6/S1–S4 并顺带修复审批意见未持久化；评分逻辑变更必须升版本、生成新报告并保留历史报告；缺少凭据时明确记录未完成的真实验证。

### 10.1 复现（改代码之前）

| 项 | 复现方式 | 修复前实测 |
|---|---|---|
| F1 | 把三个金额期望值互换后评分 | `passed=True`，7/7 全过 |
| F2 | 对 H06/H11（预期拒绝）评分 | `1/2` 失败（断言 `Hxx-P` 不成立） |
| F3 | `python -m app.cli investigate --backend sqlite` | `AttributeError: 'DatabaseRepository' object has no attribute 'snapshot'` |
| F4 | 构造"首次失败、补查成功"的变体 | 补查成功后仍 `insufficient` / `partial` |
| F5 | `investigate --with-approval` 后比对返回 ID 与台账 ID | 两个 ID 不同 |

### 10.2 实际修改

第一批：`evaluation/scoring.py`（`scoring-v2`）、`evaluation/cases.py`、`evaluation/baselines.py`、`scripts/generate_heldout_cases.py`、`docs/evaluation/cases/heldout_v3.jsonl`、`docs/evaluation/scoring_v2.md`、`rag/catalog.py`、`rag/library.py`、`rag/service.py`、`tools/knowledge_tools.py`、`agents/lease/agent.py`、`api/service.py`。

第二批：`orchestration/investigation.py`、`orchestration/approval.py`、`runtime/tool_loop.py`、`llm/model_client.py`、`llm/langchain_client.py`、`db/session.py`、`db/bootstrap.py`、`db/repository.py`、`api/app.py`、`api/service.py`、`investigation_demo.py`、`cli.py`。

回归测试：`test_evaluation.py`（F1/F2 + 契约缺口语义）、`test_rag.py`（F7）、`test_api.py`（F8 所有权、S3 校验、S4 运行身份）、`test_database_layer.py`（F3、S2）、`test_graph_workflow.py`（F4）、`test_approval.py`（F5/S1/reason）、`test_llm_tool_loop.py`（F6）。

### 10.3 验证命令与结果

```powershell
cd D:\commercial-property-multi-agent\backend
D:\anacada\envs\commercial-agent\python.exe -m unittest discover -s tests -p "test_*.py"
# Ran 238 tests ... OK

D:\anacada\envs\commercial-agent\python.exe tests\smoke_agent_contracts.py
# 全部通过：57 项检查

D:\anacada\envs\commercial-agent\python.exe -m app.cli investigate --backend sqlite
# 退出码 0（修复前崩溃）

D:\anacada\envs\commercial-agent\python.exe -m app.cli investigate --with-approval --thread-id thread_cli_demo
D:\anacada\envs\commercial-agent\python.exe -m app.cli approve apr_xxxxxxxx --draft-version 2 --reason "核对合同5.1.1后同意减免"
# 台账 stages[0].reason == 该意见；approval_status=pending_next_stage

D:\anacada\envs\commercial-agent\python.exe -m app.cli evaluate --split heldout --quiet
D:\anacada\envs\commercial-agent\python.exe -m app.cli evaluate --split dev --quiet
```

评分报告（`scoring-v2`，绑定提交 `43b48ef`）：

| 切分 | A_deterministic | B_single_agent | C_multi_agent |
|---|---|---|---|
| heldout（30 题可自动计分） | 20/30 | 21/30 | 23/30 |
| dev（人工量表题） | 0/7 | 0/7 | 0/7 |

dev 全 0 与 v1 一致，原因是开发集为自然语言断言、离线基线不解析自然语言；**不能**把 heldout 的百分比读成"多 Agent 提升"，因为三基线都未调用真实模型。

### 10.4 评分规则升级说明

`scoring-v1` 的全部规则与报告保留不动；v2 另立 `docs/evaluation/scoring_v2.md`。v2 与 v1 的差异（字段绑定、结局断言、契约缺口转人工）使两者不可做通过率对比。

### 10.5 Git

- `a9c6355` fix(runtime): repair scoring, ownership isolation and failure recovery
- `43b48ef` fix(eval): treat contract gaps as manual review, not as wrong answers
- `97b4e9f` docs: record the release candidate review and the fixes that closed it
- `9da7189` chore(repo): stop tracking the local SQLite migration fallback

### 10.6 第三批：真实服务与独立环境（本轮实际执行范围）

**已完成（有真实命令与输出）**

| 项 | 做法 | 结果 |
|---|---|---|
| 独立环境复现 | `python -m venv`（base = conda `commercial-agent`）建全新空 venv；确认隔离（`import pydantic` 失败、`sys.prefix` 指向 venv）；`pip install -e .` 安装声明的全部依赖；再跑全量验证 | 安装 `EXIT=0`；`unittest discover` **238 项通过**；契约自检 **57 项通过**；`app.cli check` `EXIT=0`；`investigate --backend sqlite` `EXIT=0` |
| 浏览器视觉验收 | 本地 `uvicorn` 起 `127.0.0.1:8011`，用浏览器打开演示页并提交一次调查 | 页面完整渲染：运行/线程 ID、结论与完成度、预算、6 条发现（含证据 ID）、冲突、缺失信息、审批请求（草案 v2、有效期、两级阶段）、4 条工具 Trace；`awaiting_approval` 状态正确 |
| 运行态文件治理 | 确认 `backend/commercial_agent_migrate.db` 的唯一用途是 `migrations/env.py` 在未配置数据库 URL 时的 SQLite 回退；`git rm --cached` 并加入 `.gitignore`；再跑 `alembic upgrade head` 验证可重建 | 迁移 `EXIT=0`（`Running upgrade -> 0001`），文件被正确重新生成且不再被跟踪 |

**未完成（缺外部条件，不得用离线结果替代）**

- [ ] 至少一次真实 DeepSeek 工具调用闭环与真实 B/C 评测装配 —— 本机 `DEEPSEEK_API_KEY` 未设置（已检查，值为空）。
- [ ] 可连接的 PostgreSQL 实例、迁移执行与 fixture 等价性验证 —— 本机无 PostgreSQL 服务，`127.0.0.1:5432` 不可达，`DATABASE_URL` 未设置。
- [ ] 5 道人工量表题的评分（H25/H26 已声明 `scorable=false`，需人工；H22/H27/H30 已补自动断言）。
- [ ] 真实服务鉴权、部署或外部副作用验证。

**结论**：真实模型与 PostgreSQL 两项**不能**用离线测试代替，当前状态仍是"版本候选"，不得宣称 MVP 已验收。
