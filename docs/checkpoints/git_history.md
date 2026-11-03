# Git 开发检查点

记录每个开发阶段对应的 Git 提交，用于追溯与回滚。

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

## [2026-11-03] 阶段 0 - 工程基建（待提交）

- **开发阶段**：阶段 0 - 环境与工程规范搭建
- **对应任务**：001 - Conda 独立环境配置；002 - 项目文档与 Prompt 归档系统
- **Git 分支**：`main`
- **Commit Hash**：`Pending`（等待项目所有者确认后执行）
- **Commit Message**：见下方「建议 Commit Message」

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

- [ ] `git status` 确认只包含预期文件
- [ ] 确认 `.vscode/` 与 `.env` 未出现在待提交列表
- [ ] 确认 `docs/` 下无临时文件、无乱码
- [ ] 由项目所有者确认后才执行 `git add` / `git commit`

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

| 阶段 | 内容 | 状态 |
|---|---|---|
| 阶段 1 | 项目骨架与依赖声明（`pyproject.toml`） | 未开始 |
| 阶段 2 | 数据层：PostgreSQL + SQLAlchemy 模型 | 未开始 |
| 阶段 3 | RAG：Chroma + BGE Embedding + BM25 / Reranker | 未开始 |
| 阶段 4 | Agent 编排：LangGraph 状态图与工具调用 | 未开始 |
| 阶段 5 | API 层：FastAPI 路由与鉴权 | 未开始 |
| 阶段 6 | 测试与部署 | 未开始 |
