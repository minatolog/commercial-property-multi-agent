# 2026-11-07 - 019 - 让 `.env` 真正生效（密钥填写路径可用性修复）

- **日期**：2026-11-07
- **任务编号**：019
- **模块**：01_environment
- **关联任务**：018（模型驱动装配，提供 `--model-provider deepseek` 入口）

---

## 1. 任务目标和背景

用户问"在哪里填写 key"。核对后发现一个**真实的可用性缺陷**：

- `.env.example` 写着"复制为 `.env` 或直接 export"；
- 但代码只读 `os.environ`，**没有任何 `.env` 加载逻辑**，也没有 `python-dotenv` 依赖。

也就是说：用户按模板复制 `.env` 并填入密钥后，程序**读不到**，表现为
"填了 key 还是报未设置"或"模型没调用"。配置项存在、模板存在、文档说可以用，
但这条路径从来没有被打通。

本任务把这条路径补通，并保持"不引入新依赖、密钥不落盘到仓库"的约束。

## 2. 原始任务 Prompt（逐字保存）

> 在哪里填写key

（附带的 IDE 上下文为浏览器标签页 `商业地产多 Agent 工作流演示 http://127.0.0.1:8011/`，与本任务无关。）

## 3. AI 实际执行的主要步骤

1. 核实事实：`backend/app/llm/adapter.py` 用 `os.environ.get(env_name)`；全仓库无 `dotenv` 引用；`.env` 未被跟踪也未加载。
2. 新增 `backend/app/env.py`：无依赖的 `.env` 解析与加载（`parse_env_text` / `load_env_file` / `load_project_env`）。
3. 接入两个真实入口：
   - `app/cli.py::main()` 开头 `load_project_env()`（所有子命令生效）；
   - `app/api/app.py` 模块导入时加载（`uvicorn app.api.app:app` 不经过 CLI）。
4. 明确优先级：**已存在的环境变量优先**，`.env` 只补空缺；`.env` 里的空值不会覆盖已导出的真值。
5. 更新 `.env.example` 头部说明（自动加载、优先级、填法）。
6. 更新根 `README.md`（新增"在哪里填 Key"两条路径与验证命令）与 `backend/README.md`（配置段落）。
7. 新增 `backend/tests/test_env.py`（15 项）。

## 4. 新增和修改的文件

| 文件 | 变更 |
|---|---|
| `backend/app/env.py` | 新增：`.env` 解析与加载（无第三方依赖） |
| `backend/app/cli.py` | `main()` 先加载项目 `.env` |
| `backend/app/api/app.py` | 模块导入即加载（覆盖 uvicorn 启动方式） |
| `backend/tests/test_env.py` | 新增 15 项 |
| `.env.example` | 说明自动加载、优先级与填法 |
| `README.md` | 新增"在哪里填 Key"小节（两种方式 + 验证命令） |
| `backend/README.md` | 环境段新增配置说明 |

## 5. 执行结果和验证方式

```powershell
cd D:\commercial-property-multi-agent\backend
D:\anacada\envs\commercial-agent\python.exe -m unittest discover -s tests -p "test_*.py"
# Ran 299 tests ... OK

D:\anacada\envs\commercial-agent\python.exe tests\smoke_agent_contracts.py
# 全部通过：57 项检查
```

端到端验证（不打印密钥内容）：

| 步骤 | 结果 |
|---|---|
| `Copy-Item .env.example .env`，在 `DEEPSEEK_API_KEY=` 后填入占位值 | — |
| `git check-ignore -v .env` | `.gitignore:4:.env` → **不入库** |
| `load_project_env()` | `applied_keys=('DEEPSEEK_API_KEY', 'DEMO_PRINCIPAL_ID', ...)` |
| `build_model_client("deepseek")` | `LangChainChatModelClient`（provider=deepseek, model=deepseek-chat）——说明填了就真的被用上 |
| `.env` 里留空 | `--model-provider deepseek` → `EXIT=2` + `MissingApiKeyError`（不静默降级） |

## 6. 执行结果：仍受凭据限制的部分

本任务**没有**调用真实 DeepSeek API：本机没有可用密钥，验证止于"客户端被正确构造"。
真实调用（以及由此产生的 token/成本与质量结论）仍需项目所有者填入自己的 Key 后执行。

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| 模板说"复制为 .env"，代码却只读环境变量 | 缺 `.env` 加载层 | 新增 `app/env.py` 并接入 CLI / API 两个入口 |
| `uvicorn app.api.app:app` 不走 CLI，加载会漏 | 入口不同 | 在 `app/api/app.py` 模块级加载 |
| `.env` 里的空值可能覆盖已导出的真值 | 简单赋值 | 只在"环境变量不存在或为空"时填充 |
| 单测误把 FastAPI 实例当模块取源码 | `from app.api import app` 拿的是对象 | 改用 `importlib.import_module("app.api.app")` |

## 8. 对应 Git Commit Hash

- 上一轮基线：`9054993`
- 本轮：见 `docs/checkpoints/git_history.md`（提交后回填）

## 9. 后续待办事项

- [ ] 项目所有者填入真实 `DEEPSEEK_API_KEY` 后跑一次 `investigate --model-provider deepseek` 并归档 trace
- [ ] 真实模型下重复 3 次 B/C 测量，另立报告版本
- [ ] PostgreSQL 实机、人工量表、部署验证（同 Task 017/018 的剩余项）
