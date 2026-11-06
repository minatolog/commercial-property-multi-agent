# 项目文档与 Prompt 归档系统

本目录用于记录 `commercial-property-multi-agent`（商业地产租约与物业运营多 Agent 协作系统）的开发过程、技术决策与 AI 协作历史。

目标：任何一次开发任务都能被**追溯、复现和回滚**。文档不是代码快照，真正的代码回滚依赖 Git 提交记录。

---

## 一、目录结构与用途

| 路径 | 用途 |
|---|---|
| `docs/README.md` | 本文件。说明目录约定、命名规范与文档更新流程 |
| `docs/decisions/` | **架构决策记录（ADR）**：ADR-005 起的新方向决策与取舍 |
| `docs/product/` | **产品范围**：MVP 范围（P0/P1/暂停）、场景与完成标准 |
| `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | **项目总路线与进度表**：10 次正式 Prompt、每步产物/验收及当前进度 |
| [项目路线图文 PDF](../output/pdf/commercial_property_agent_first_roadmap_notability.pdf) | **Notability 阅读批注版**：16 页，含流程图、十步导航、验收页及手写进度表；2026-11-04 导出，状态快照截至 2026-11-03 |
| `docs/reviews/` | **Codex 验收报告**：实际验证、待修正项及同任务返修 Prompt |
| `docs/evaluation/` | **评测**：评测计划、共享 fixture、评测用例（JSON/JSONL） |
| `docs/handoffs/` | **交接文档**：跨工具（Codex / DeepSeek）的方向基线与交接记录 |
| `docs/architecture/system_design.md` | 系统架构设计：模块划分、Agent 编排、数据流、技术选型理由 |
| `docs/architecture/agent_architecture.md` | Agent 层概念设计：契约、Registry、配置、编排、错误与降级 |
| `docs/architecture/agent_runtime_contracts.md` | **Agent Runtime 契约与 Graph 规格**（编码级，P0 规格，尚未实现） |
| `docs/architecture/agent_development_guide.md` | 新增/禁用/替换 Agent 的标准流程与硬规则 |
| `docs/architecture/database_design.md` | 数据库设计：表结构、字段定义、索引、关系与演进记录（**P0 长期参考，非建表清单**） |
| `docs/prompts/01_environment/` | 环境配置相关任务的 Prompt 归档（Conda、依赖、工具链） |
| `docs/prompts/02_database/` | 数据库相关任务的 Prompt 归档（建表、迁移、SQLAlchemy 模型） |
| `docs/prompts/03_rag/` | RAG 相关任务的 Prompt 归档（Chroma、BGE Embedding、BM25、Reranker） |
| `docs/prompts/04_agents/` | 多 Agent 与 LangGraph 相关任务的 Prompt 归档 |
| `docs/prompts/05_frontend/` | 前端 / API 交互层相关任务的 Prompt 归档 |
| `docs/prompts/06_testing/` | 测试、调试、质量保障相关任务的 Prompt 归档 |
| `docs/development_logs/development_log.md` | 开发日志：按任务追加，记录完成内容、技术决策、验证结果 |
| `docs/issues/issue_log.md` | 问题记录：现象、错误信息、根因、解决方案、预防措施 |
| `docs/lessons_learned/knowledge_notes.md` | 知识沉淀：技术原理与选型原因，而非命令清单 |
| `docs/checkpoints/git_history.md` | Git 开发检查点：阶段、任务、分支、Commit、回滚命令 |

空目录使用 `.gitkeep` 占位，因为 Git 不跟踪空文件夹。

---

## 二、文件命名规范

### 2.1 Prompt 归档

命名规则：

```
YYYY-MM-DD_编号_任务名称.md
```

- `YYYY-MM-DD`：任务开始日期。
- `编号`：三位数字，**全局递增**（跨模块不重置），例如 `001`、`002`。
- `任务名称`：小写英文 + 下划线，简洁描述任务主题。

示例：

```
docs/prompts/01_environment/2026-11-03_001_conda_environment.md
docs/prompts/02_database/2026-11-05_003_postgresql_schema.md
```

### 2.2 编号分配

编号记录在本文件下方的「编号登记表」中，新增任务时先查表取下一个可用编号。

| 编号 | 日期 | 模块 | 任务 | 文件 |
|---|---|---|---|---|
| 001 | 2026-11-03 | 01_environment | Conda 独立环境配置 | [2026-11-03_001_conda_environment.md](./prompts/01_environment/2026-11-03_001_conda_environment.md) |
| 002 | 2026-11-03 | 01_environment | 项目文档与 Prompt 归档系统 | [2026-11-03_002_docs_prompt_archive_system.md](./prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md) |
| 003 | 2026-11-03 | 04_agents | 模块化多 Agent 架构约束 | [2026-11-03_003_modular_multi_agent_architecture.md](./prompts/04_agents/2026-11-03_003_modular_multi_agent_architecture.md) |
| 004 | 2026-11-03 | 02_database | PostgreSQL 数据库架构设计（用户侧标注为 Task 003） | [2026-11-03_004_postgresql_database_design.md](./prompts/02_database/2026-11-03_004_postgresql_database_design.md) |
| 005 | 2026-11-03 | 02_database | 数据库设计复核与 MVP 决策补充（用户侧标注为 Task 003 Review） | [2026-11-03_005_database_design_review.md](./prompts/02_database/2026-11-03_005_database_design_review.md) |
| 006 | 2026-11-03 | 04_agents | Agent-first 基线、契约与首批评测样例（Prompt 1 已验收；进入 Prompt 2 / Task 007） | [2026-11-03_006_agent_first_baseline.md](./prompts/04_agents/2026-11-03_006_agent_first_baseline.md) |
| 007 | 2026-11-06 | 04_agents | Agent Runtime 与受控工具执行（Prompt 2；DeepSeek 自检通过） | [2026-11-06_007_agent_runtime_controlled_tools.md](./prompts/04_agents/2026-11-06_007_agent_runtime_controlled_tools.md) |
| 008 | 2026-11-06 | 04_agents | LangChain、DeepSeek 适配与真实工具调用闭环（Prompt 3；DeepSeek 自检通过，真实调用受凭据限制） | [2026-11-06_008_langchain_deepseek_tool_calling.md](./prompts/04_agents/2026-11-06_008_langchain_deepseek_tool_calling.md) |
| 009 | 2026-11-06 | 04_agents | LangGraph 多 Agent 工作流与条件路由（Prompt 4；DeepSeek 自检通过） | [2026-11-06_009_langgraph_multi_agent_workflow.md](./prompts/04_agents/2026-11-06_009_langgraph_multi_agent_workflow.md) |
| 010 | 2026-11-06 | 02_database | PostgreSQL 只读业务工具与数据访问边界（Prompt 5；SQLite 验证通过，PostgreSQL 未验证） | [2026-11-06_010_postgresql_readonly_tools.md](./prompts/02_database/2026-11-06_010_postgresql_readonly_tools.md) |
| 011 | 2026-11-06 | 03_rag | 合同 PDF 导入、BM25 条款检索与可追溯证据（Prompt 6；离线验证通过，向量检索属 P1） | [2026-11-06_011_contract_pdf_rag.md](./prompts/03_rag/2026-11-06_011_contract_pdf_rag.md) |
| 012 | 2026-11-06 | 04_agents | 持久检查点、人工审批与暂停恢复（Prompt 7；本地 SQLite 控制面验证通过） | [2026-11-06_012_durable_checkpoint_and_approval.md](./prompts/04_agents/2026-11-06_012_durable_checkpoint_and_approval.md) |
| 013 | 2026-11-06 | 06_testing | 三基线与 40 题正式评测（Prompt 8；离线三基线完成，真实模型测量受凭据限制） | [2026-11-06_013_three_baselines_evaluation.md](./prompts/06_testing/2026-11-06_013_three_baselines_evaluation.md) |
| 014 | 2026-11-06 | 05_frontend | FastAPI 与轻量演示页（Prompt 9；本地 uvicorn 实测通过） | [2026-11-06_014_fastapi_demo_api.md](./prompts/05_frontend/2026-11-06_014_fastapi_demo_api.md) |
| 015 | 2026-11-06 | 01_environment | 最终验收与项目展示材料（Prompt 10；版本候选，未打 Tag/发布） | [2026-11-06_015_release_candidate.md](./prompts/01_environment/2026-11-06_015_release_candidate.md) |
| 016 | 2026-11-06 | 06_testing | 版本候选独立审查与缺陷修复（F1–F8、S1–S4 已修复并有回归测试；真实模型/PG 验证待补） | [2026-11-06_016_release_candidate_review.md](./prompts/06_testing/2026-11-06_016_release_candidate_review.md) |
| 017 | 2026-11-07 | 06_testing | 修复复查与 R1–R7 修复（261 项测试通过；真实模型/PG 仍待外部条件） | [2026-11-07_017_release_candidate_recheck.md](./prompts/06_testing/2026-11-07_017_release_candidate_recheck.md) |

---

## 三、Prompt 归档文档模板

每个归档文件必须包含以下 9 个部分：

````markdown
# YYYY-MM-DD_编号_任务名称

## 1. 基本信息

- **日期**：YYYY-MM-DD
- **任务编号**：NNN
- **模块**：01_environment / 02_database / 03_rag / 04_agents / 05_frontend / 06_testing
- **Git Commit**：`<hash>`（未提交则写 `Pending`）

## 2. 任务目标和背景

说明为什么做这件事、要解决什么问题、有哪些前置条件。

## 3. 原始用户 Prompt

> 逐字保存，不擅自改写、不提炼、不补全。

```
（原始 Prompt 原文）
```

## 4. AI 实际执行的主要步骤

按执行顺序列出真实做过的动作，包括检查、决策、修改。没做过的不要写。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `path/to/file` | 新增 / 修改 / 删除 | 变更内容概要 |

## 6. 执行结果和验证方式

写清楚「怎么验证的」，包括实际执行的命令与真实输出结论。

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|

若无问题，写「本次任务未遇到阻塞性问题」。

## 8. 对应 Git Commit Hash

- Commit：`Pending` / `<hash>`
- 若为 Pending，说明尚未提交的原因。

## 9. 后续待办事项

- [ ] 待办 1
- [ ] 待办 2
````

---

## 四、每次开发任务的文档更新流程

任务开始时：

1. 判断任务所属模块，查「编号登记表」取下一个编号。
2. 在对应 `docs/prompts/<模块>/` 下新建归档文件，先填「原始用户 Prompt」与「任务目标和背景」。

任务进行中：

3. 遇到技术问题 → 追加到 `docs/issues/issue_log.md`。
4. 产生值得沉淀的技术认知 → 追加到 `docs/lessons_learned/knowledge_notes.md`。

任务结束时，逐项自检：

| 检查项 | 判定标准 |
|---|---|
| Prompt 归档 | 本次任务有对应文件，9 个部分齐全，原始 Prompt 逐字保存 |
| Development Log | `development_log.md` 追加一条本次记录 |
| Issue Log | 本次有技术问题则追加；无则不动 |
| Lessons Learned | 本次有可复用的技术认知则追加；无则不动 |
| Git Checkpoints | 有提交则登记 commit；未提交则记录为待提交状态 |
| 编号登记表 | 本次新任务的编号已登记 |

---

## 五、记录原则

1. **不编造**。没有发生过的工作不写执行记录；无法获取的 Prompt 原文标注「原文缺失，待补充」，由人工补齐，不自行生成。
2. **不覆盖**。旧 Prompt 归档只读不改。同一任务的后续修改作为新编号新增，并在新文件顶部注明「关联任务：NNN」。
3. **文档用于追溯，不是备份**。不要把代码全文粘贴进文档当快照，代码回滚一律使用 Git。
4. **敏感信息零记录**。文档中不得出现 API Key、密码、Token、连接串中的凭据。涉及时统一写 `<REDACTED>`。
5. **语言**：正文使用中文，专业技术术语保留英文（如 Embedding、Reranker、Checkpoint）。

---

## 六、Git 操作约定

- 未经确认，不执行 `git reset`、`git rebase`、`git push --force` 等破坏历史记录的操作。
- 不自动删除或覆盖已有代码。
- 不自动创建 Commit。每个功能完成后提交建议的 Commit Message，由项目所有者确认后执行。
- 提交前必须检查变更内容，确认不包含 `.env`、密钥、密码等敏感信息。

---

## 七、文档模板索引

| 模板 | 位置 |
|---|---|
| Prompt 归档模板 | 本文件 第三节 |
| 开发日志模板 | [development_log.md](./development_logs/development_log.md) 文件头部 |
| 问题记录模板 | [issue_log.md](./issues/issue_log.md) 文件头部 |
| 知识笔记模板 | [knowledge_notes.md](./lessons_learned/knowledge_notes.md) 文件头部 |
| Git 检查点模板 | [git_history.md](./checkpoints/git_history.md) 文件头部 |
