# 2026-11-03_002_项目文档与 Prompt 归档系统

## 1. 基本信息

- **日期**：2026-11-03
- **任务编号**：002
- **模块**：01_environment（工程规范类，归入环境与工程基建）
- **关联任务**：001（Conda 独立环境配置）
- **Git Commit**：`Pending`（仓库尚无任何提交）

## 2. 任务目标和背景

任务 001 完成了环境准备，但项目缺少可追溯的开发记录体系。随着后续引入 PostgreSQL、RAG 检索、LangGraph 多 Agent 编排，问题排查和决策复盘的成本会快速上升。

需要建立一套长期规范：

1. **Prompt 归档**：每一次开发任务的需求原文必须留档，避免需求在口头迭代中丢失。
2. **开发日志**：按阶段记录完成内容、技术决策与验证结果。
3. **问题与经验**：技术问题记录根因与预防措施；技术认知沉淀为可复用的原理性笔记。
4. **Git 检查点**：把文档记录与真实的 Git 提交对应起来，保证可回滚。

核心原则：**文档用于追溯，不编造、不覆盖、不作为代码快照**。

## 3. 原始用户 Prompt

````
在刚才的 Conda 环境配置任务基础上，我需要增加一项长期开发规范：建立完整的项目文档和 AI Prompt 归档系统。

### 一、创建 docs 文件夹
请在 `commercial-property-multi-agent` 项目根目录创建如下结构：

```
docs/
├── README.md
├── architecture/
│   ├── system_design.md
│   └── database_design.md
├── prompts/
│   ├── 01_environment/
│   ├── 02_database/
│   ├── 03_rag/
│   ├── 04_agents/
│   ├── 05_frontend/
│   └── 06_testing/
├── development_logs/
│   └── development_log.md
├── issues/
│   └── issue_log.md
├── lessons_learned/
│   └── knowledge_notes.md
└── checkpoints/
    └── git_history.md
```
由于 Git 不跟踪空文件夹，可以使用 `.gitkeep` 保留暂时没有内容的目录。

### 二、建立 Prompt 归档机制
从现在开始，我发送给你的每一条开发任务 Prompt，都需要根据所属模块保存到 `docs/prompts/` 对应目录。

命名规则：

`YYYY-MM-DD_编号_任务名称.md`

例如：

`2026-11-03_001_conda_environment.md`

每个 Prompt 文档需要包含：

1. 日期与任务编号。
2. 任务目标和背景。
3. 原始用户 Prompt（尽可能逐字保存，不擅自改写）。
4. AI 实际执行的主要步骤。
5. 新增和修改的文件。
6. 执行结果和验证方式。
7. 遇到的问题及解决方法。
8. 对应 Git Commit Hash（尚未提交则标记为 Pending）。
9. 后续待办事项。
注意：如果无法访问之前的 Prompt 原文，不要自行编造历史记录，可以让我补充。

### 三、建立开发日志规范
每完成一次开发任务，请更新：

`docs/development_logs/development_log.md`

记录以下信息：

- 日期
- 开发阶段
- 本次完成的功能
- 主要技术决策
- 修改的文件
- 测试和验证结果
- 当前项目状态
- 下一步开发计划

### 四、建立问题与经验总结机制
遇到技术问题时，更新：

`docs/issues/issue_log.md`

记录问题现象、错误信息、原因分析、解决方案以及如何避免再次出现。

当开发过程中产生值得学习的技术知识时，更新：

`docs/lessons_learned/knowledge_notes.md`

例如：

- Conda 环境隔离原理
- PostgreSQL 数据库设计
- LangGraph State 管理
- Agent Tool Calling 机制
- RAG 检索优化方法
这些总结应该解释技术原理和选择原因，而不只是记录运行了哪些命令。

### 五、建立 Git 开发检查点
在 `docs/checkpoints/git_history.md` 中记录：

- 开发阶段
- 对应任务
- Git 分支
- Commit Hash
- 本次变更
- 验证结果
- 回滚参考命令
注意：

1. 不要未经我同意执行 Git reset、rebase、force push 等可能破坏历史记录的操作。
2. 不要自动删除或覆盖已有代码。
3. 每个主要功能完成后，向我建议一个清晰的 Git Commit Message。
4. Git 提交前先检查修改内容，不要把 API Key、密码、`.env` 等敏感信息提交进去。
5. 文档用于追溯，真正的代码回滚依赖 Git 提交记录，不要把文档记录当作代码快照。
6. 不要自动创建 Commit，先让我确认。

### 六、建立统一规范
请在 `docs/README.md` 中说明上述目录用途、文件命名规范和每次开发任务的文档更新流程。

从现在起，每次开发任务结束时，请主动检查是否需要更新：

- 对应 Prompt 归档
- Development Log
- Issue Log
- Lessons Learned
- Git Checkpoints
不要为没有发生过的工作编造执行记录，也不要覆盖旧 Prompt。对于同一任务的后续修改，保留历史版本。

所有文档使用中文撰写，专业技术术语可以保留英文。

### 七、本次任务的验收要求

1. 完成 Conda 独立环境配置（如果此前尚未完成）。
2. 创建完整的 docs 文件夹。
3. 保存本次环境配置的 Prompt 和真实执行情况。
4. 建立文档模板和开发日志。
5. 确认 docs 文件夹没有被 `.gitignore` 排除。
6. 检查 Git 变更并给我建议的 Commit Message。
不要在本次任务中安装大量 AI 依赖、开发 Agent 或修改数据库。

完成后请向我汇报项目目录结构、文档创建情况、Conda 环境验证结果及下一步建议。
````

## 4. AI 实际执行的主要步骤

### 4.1 前置状态确认

1. `git status --short --ignored`：仅 `.gitignore` 未跟踪、`.vscode/` 已忽略，`docs/` 尚不存在。
2. 用 `git check-ignore -v` 预先验证 7 个代表性 `docs/` 路径，全部 `NOT IGN`，确认 `.gitignore` 中的 `logs/`、`*.log` 等规则**不会**误伤 `development_logs/`、`issue_log.md`。

### 4.2 创建目录结构

创建 12 个目录：`docs`、`architecture`、`prompts` 及 6 个模块子目录、`development_logs`、`issues`、`lessons_learned`、`checkpoints`。

对 5 个暂时无内容的模块目录（`02_database`、`03_rag`、`04_agents`、`05_frontend`、`06_testing`）各写入 `.gitkeep` 占位。

### 4.3 编写文档

| 文件 | 内容要点 |
|---|---|
| `docs/README.md` | 目录用途表、命名规范、编号登记表、9 段式 Prompt 模板、任务结束时自检清单、6 条记录原则、Git 操作约定、模板索引 |
| `docs/development_logs/development_log.md` | 文件头部模板 + 任务 002、任务 001 两条真实记录（倒序） |
| `docs/issues/issue_log.md` | 文件头部模板 + 4 条本次真实遇到的问题 |
| `docs/lessons_learned/knowledge_notes.md` | 文件头部模板 + 4 篇原理性笔记 |
| `docs/checkpoints/git_history.md` | 文件头部模板 + 待提交记录与建议 Commit Message |
| `docs/architecture/system_design.md` | 骨架：范围说明、规划中的模块划分、待定项（明确标注未实现） |
| `docs/architecture/database_design.md` | 骨架：范围说明、设计原则、待定实体清单（明确标注未实现） |
| `docs/prompts/01_environment/001` | 任务 001 的完整归档，含逐字 Prompt 与 8 个真实遇到的问题 |
| `docs/prompts/01_environment/002` | 本任务归档 |

### 4.4 验证

1. 递归列出 `docs` 目录，确认结构与要求一致。
2. 对 7 个代表路径执行 `git check-ignore -v`，确认未被忽略。
3. `git status` 确认 `docs/` 出现在未跟踪列表。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `docs/README.md` | 新增 | 统一规范入口 |
| `docs/architecture/system_design.md` | 新增 | 架构骨架（内容待后续任务填充） |
| `docs/architecture/database_design.md` | 新增 | 数据库设计骨架（内容待后续任务填充） |
| `docs/prompts/01_environment/2026-11-03_001_conda_environment.md` | 新增 | 任务 001 归档 |
| `docs/prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md` | 新增 | 本任务归档 |
| `docs/prompts/02_database/.gitkeep` | 新增 | 占位 |
| `docs/prompts/03_rag/.gitkeep` | 新增 | 占位 |
| `docs/prompts/04_agents/.gitkeep` | 新增 | 占位 |
| `docs/prompts/05_frontend/.gitkeep` | 新增 | 占位 |
| `docs/prompts/06_testing/.gitkeep` | 新增 | 占位 |
| `docs/development_logs/development_log.md` | 新增 | 开发日志 + 模板 |
| `docs/issues/issue_log.md` | 新增 | 问题记录 + 模板 |
| `docs/lessons_learned/knowledge_notes.md` | 新增 | 知识笔记 + 模板 |
| `docs/checkpoints/git_history.md` | 新增 | Git 检查点 + 模板 |

未修改任何已有代码文件。`.gitignore` 本次未改动（经验证无需新增规则）。

## 6. 执行结果和验证方式

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 目录结构完整 | `Get-ChildItem docs -Recurse -Directory` | 12 个目录全部存在，层级与要求一致 |
| 空目录占位 | 文件枚举 | 5 个 `.gitkeep` 已生成 |
| `docs/` 未被忽略 | `git check-ignore -v` × 7 | 全部 `NOT IGN` |
| `development_logs` 未被 `logs/` 误伤 | 针对 `docs/development_logs/development_log.md` 单独验证 | `NOT IGN`，确认 `logs/` 只匹配名为 `logs` 的目录 |
| Git 变更可见 | `git status --short --ignored` | `?? docs/`、`?? .gitignore`、`!! .vscode/` |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `logs/` 规则可能误伤 `development_logs/` | `.gitignore` 中的 `logs/` 若被理解为子串匹配会连带排除 `development_logs/` | 实测验证：gitignore 的目录模式按路径段完整匹配，`logs/` 只匹配名为 `logs` 的目录，`development_logs/` 不受影响，无需修改规则 |
| Prompt 原文含 3 个反引号代码块，直接放入 md 围栏会提前闭合 | 原始 Prompt 内部有 ```` ``` ```` 围栏 | 归档时使用 4 个反引号 ```` ```` ```` 作为外层围栏 |

（任务 001 中出现过的 PowerShell 执行策略、GBK 编码等问题已记录在 001 归档与 `issue_log.md`，本任务未重复遇到。）

## 8. 对应 Git Commit Hash

- **状态**：`Pending`
- **原因**：用户明确要求「不要自动创建 Commit，先让我确认」。仓库当前仍无任何提交。
- **建议 Commit Message**：见 `docs/checkpoints/git_history.md`。

## 9. 后续待办事项

- [ ] 用户确认后执行首次 Git 提交（`.gitignore` + `docs/`）
- [ ] 建立 `pyproject.toml`，确定项目包结构与依赖管理方式（pip-tools / uv / poetry）
- [ ] 填充 `docs/architecture/system_design.md`：确定 Agent 划分与 LangGraph 状态图
- [ ] 填充 `docs/architecture/database_design.md`：租约、物业、租户等核心实体建模
- [ ] 决定是否关闭 Conda `auto_activate_base`
- [ ] 每个模块开始开发时，在对应 `docs/prompts/<模块>/` 下建立归档
