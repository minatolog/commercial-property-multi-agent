# 开发日志

按时间追加，最新记录在最上方。每条记录对应一次开发任务。

---

## 模板

```markdown
## [YYYY-MM-DD] 任务 NNN - 任务标题

- **日期**：YYYY-MM-DD
- **开发阶段**：环境搭建 / 数据层 / RAG / Agent 编排 / API 层 / 测试
- **对应 Prompt 归档**：`docs/prompts/<模块>/YYYY-MM-DD_NNN_任务名称.md`

### 本次完成的功能

- 功能点 1
- 功能点 2

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|

### 修改的文件

| 文件 | 变更 |
|---|---|

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|

### 当前项目状态

一句话说明当前可运行到什么程度、有哪些已知缺口。

### 下一步开发计划

- [ ] 计划 1
- [ ] 计划 2
```

---

## [2026-11-03] 任务 002 - 项目文档与 Prompt 归档系统

- **日期**：2026-11-03
- **开发阶段**：环境搭建 / 工程规范
- **对应 Prompt 归档**：`docs/prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md`

### 本次完成的功能

- 建立 `docs/` 完整目录结构（architecture / prompts / development_logs / issues / lessons_learned / checkpoints）。
- 建立 Prompt 归档机制，包含 9 段式归档模板与全局递增编号规则。
- 归档任务 001（Conda 环境配置）与任务 002（文档系统）两条历史 Prompt。
- 建立开发日志、问题记录、知识笔记、Git 检查点四类文档及各自模板。
- 编写 `docs/README.md` 作为统一规范入口，含目录说明、命名规范、更新流程、记录原则与 Git 约定。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 空目录占位 | `.gitkeep` | Git 不跟踪空文件夹，需要占位文件才能把目录结构提交进仓库 |
| 模板存放位置 | 嵌入各文档文件头部的「模板」小节 | 严格遵循用户指定的目录结构，不额外引入 `templates/` 目录，同时保证模板触手可及 |
| Prompt 原文保存方式 | 4 个反引号围栏的代码块 | 原始 Prompt 内部含 3 个反引号的代码块（如 `conda create ...`），用 4 反引号包裹可避免围栏提前闭合 |
| 编号规则 | 三位数全局递增，跨模块不重置 | 保证任一编号在项目内唯一，便于跨模块按序检索 |
| 归档范围 | 仅保存真实发生过的任务 | 遵守「不为没做过的工作编造记录」原则 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `.vscode/settings.json` | 新增（本地文件，已被 .gitignore 忽略） |
| `docs/README.md` | 新增 |
| `docs/architecture/system_design.md` | 新增（骨架） |
| `docs/architecture/database_design.md` | 新增（骨架） |
| `docs/prompts/01_environment/2026-11-03_001_conda_environment.md` | 新增 |
| `docs/prompts/01_environment/2026-11-03_002_docs_prompt_archive_system.md` | 新增 |
| `docs/prompts/02_database/.gitkeep` 等 5 个 | 新增（占位） |
| `docs/development_logs/development_log.md` | 新增 |
| `docs/issues/issue_log.md` | 新增 |
| `docs/lessons_learned/knowledge_notes.md` | 新增 |
| `docs/checkpoints/git_history.md` | 新增 |

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 目录结构完整 | `Get-ChildItem docs -Recurse -Directory` | 12 个目录全部就位 |
| `docs/` 未被忽略 | `git check-ignore -v docs/...`（7 个代表路径） | 全部 `NOT IGN`，未被排除 |
| 空目录可入库 | 各空目录生成 `.gitkeep` | 5 个 `.gitkeep` 已生成 |
| Git 变更可见 | `git status --short --ignored` | `docs/` 与 `.gitignore` 为未跟踪状态，`.vscode/` 已忽略 |

### 当前项目状态

Conda 环境 `commercial-agent` 可用，文档与归档体系已建立，仓库尚无任何提交。项目代码为空，等待进入数据层与 Agent 骨架开发。

### 下一步开发计划

- [ ] 确认并执行首次 Git 提交（`.gitignore` + `docs/`）
- [ ] 建立 `pyproject.toml` 与项目最小目录骨架（`app/`、`agents/`、`tests/`）
- [ ] 设计 PostgreSQL 表结构，输出 `docs/architecture/database_design.md` 正式版本

---

## [2026-11-03] 任务 001 - Conda 独立环境配置

- **日期**：2026-11-03
- **开发阶段**：环境搭建
- **对应 Prompt 归档**：`docs/prompts/01_environment/2026-11-03_001_conda_environment.md`

### 本次完成的功能

- 确认项目根目录为 `D:\commercial-property-multi-agent`，Git 仓库已初始化且绑定远端 `minatolog/commercial-property-multi-agent`。
- 定位 Anaconda 安装位置 `D:\anacada`（Anaconda3 2025.12-2，conda 26.1.1），并确认其未加入系统 PATH。
- 盘点已有环境（`base` / `aiagent` / `z5581485`），确认 `commercial-agent` 无命名冲突。
- 创建独立环境 `commercial-agent`（Python 3.11.18 + pip 26.2.2），路径 `D:\anacada\envs\commercial-agent`。
- 将 VS Code Python Interpreter 指向该环境，并写入 `.vscode/settings.json` 兜底。
- 创建 `.gitignore`，覆盖密钥、Python 缓存、工具缓存、向量库数据与 VS Code 个人配置。
- 未安装任何项目依赖（仅 pip / setuptools / wheel / packaging）。

### 主要技术决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 环境管理方式 | Conda 独立命名环境，不使用 venv | 项目后续需要 BGE Embedding、向量检索等可能含原生扩展的依赖，Conda 在 Windows 上处理二进制依赖更稳 |
| Python 版本 | 3.11 | LangGraph / LangChain 生态与 3.11 兼容性最成熟，3.12+ 部分依赖轮子尚不齐全 |
| 环境存放位置 | 默认 `D:\anacada\envs\`，不放进项目目录 | 环境体积大且含绝对路径，放入项目会污染仓库并拖慢 Git 操作 |
| `.vscode` 忽略策略 | 忽略全部 + 白名单 `extensions.json` / `launch.json` / `tasks.json` | 个人机器配置（含解释器绝对路径、终端设置）不进仓库，团队可共享的调试配置保留 |
| 项目依赖 | 本次一律不装 | 遵循「仅完成环境准备」的要求，避免在架构未定时锁定版本 |

### 修改的文件

| 文件 | 变更 |
|---|---|
| `.gitignore` | 新增 |
| `.vscode/settings.json` | 新增（本地文件，已被 .gitignore 忽略） |

### 测试和验证结果

| 验证项 | 命令 / 方式 | 结果 |
|---|---|---|
| 环境创建成功 | `conda env list` | 列表中存在 `commercial-agent` → `D:\anacada\envs\commercial-agent` |
| Python 版本 | `python --version` | `Python 3.11.18` |
| Python 来源 | `sys.executable` | `D:\anacada\envs\commercial-agent\python.exe` |
| pip 来源 | `python -m pip --version` | pip 26.2.2 from `...\commercial-agent\Lib\site-packages` |
| 环境隔离 | 打印 `sys.path` | 仅含 `commercial-agent` 路径，无 base 环境泄漏 |
| 依赖干净 | `pip list` | 仅 packaging / pip / setuptools / wheel |
| 其他环境未受影响 | 对比 `envs` 目录时间戳 | `aiagent`、`z5581485` 时间戳不变 |
| `.gitignore` 生效 | `git check-ignore -v`（双向用例） | 该忽略的已忽略，源码路径均未被忽略 |
| VS Code 解释器 | Python 扩展环境信息 | Environment Type: conda，Version: 3.11.18 |
| 激活可用性 | `conda activate commercial-agent` | `CONDA_PREFIX` 正确，`where python` 首选该环境，`conda deactivate` 正常回退 |

### 当前项目状态

开发环境就绪，仓库无代码。`.gitignore` 与 `.vscode/settings.json` 已建立但尚未提交。

### 下一步开发计划

- [ ] 提交 `.gitignore`
- [ ] 建立 `pyproject.toml`
- [ ] 规划 PostgreSQL 表结构与 Agent 模块划分
