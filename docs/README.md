# 项目文档与 Prompt 归档系统

本目录用于记录 `commercial-property-multi-agent`（商业地产租约与物业运营多 Agent 协作系统）的开发过程、技术决策与 AI 协作历史。

目标：任何一次开发任务都能被**追溯、复现和回滚**。文档不是代码快照，真正的代码回滚依赖 Git 提交记录。

---

## 一、目录结构与用途

| 路径 | 用途 |
|---|---|
| `docs/README.md` | 本文件。说明目录约定、命名规范与文档更新流程 |
| `docs/architecture/system_design.md` | 系统架构设计：模块划分、Agent 编排、数据流、技术选型理由 |
| `docs/architecture/database_design.md` | 数据库设计：表结构、字段定义、索引、关系与演进记录 |
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
