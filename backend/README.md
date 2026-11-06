# backend/ — Agent 工作流、受控只读工具、知识检索、审批控制面与评测

离线优先：**默认不联网、不调用模型、不连数据库**。
业务数据来自 `../docs/evaluation/fixtures/agent_first_v1.json`（合成数据，只读）。

> 本文只描述**已经实现并验证**的能力。未安装/未验证的部分（真实 DeepSeek 调用、PostgreSQL、
> 向量检索）在「已知限制」中明确列出，不当作已完成。

## 1. 环境

- Python 3.11（推荐 Conda 环境 `commercial-agent`）
- 依赖见 `pyproject.toml`：pydantic、PyYAML、langchain-core、langchain-openai、langgraph、
  langgraph-checkpoint-sqlite、SQLAlchemy、alembic、pypdf、reportlab、fastapi、uvicorn
- 测试以标准库 `unittest` 编写（`Test*` / `test_*` 命名，可被 pytest 直接收集）

```bash
conda activate commercial-agent
cd backend
python -m pip install -e .          # 仅首次
```

### 配置真实模型的 Key

`DEEPSEEK_API_KEY` 只从环境变量或仓库根 `.env` 读取（**不**写在 YAML/代码里）：

```powershell
cd D:\commercial-property-multi-agent
Copy-Item .env.example .env     # 仅首次；.env 已被 .gitignore 忽略
notepad .env                    # 填 DEEPSEEK_API_KEY=sk-...
```

CLI 与 `uvicorn` 启动时都会自动读取 `.env`；已存在的环境变量优先，`.env` 只补空缺。
未配置时 `--model-provider deepseek` 会明确抛 `MissingApiKeyError`，不会静默降级成离线。

## 2. 常用命令（在 `backend/` 目录下）

```bash
# 自检与清单
python -m app.cli --help
python -m app.cli tools                    # 已注册只读工具（含 document.search）
python -m app.cli check                     # Agent 配置 vs 白名单 vs 工具注册表
python tests/smoke_agent_contracts.py       # 契约自检（57 项）

# 单 Agent 路径（Fake 模型，可切换真实模型）
python -m app.cli ask "A-301 现在还有多少钱没交？"
python -m app.cli ask "..." --provider deepseek     # 需 DEEPSEEK_API_KEY

# 多 Agent 图（规则规划 → 并发子 Agent → 确定性核验）
python -m app.cli investigate
python -m app.cli investigate --backend sqlite      # 用只读数据库后端（本机 SQLite）
python -m app.cli investigate --model-provider scripted   # 领域 Agent 改由模型选工具（离线脚本化）
python -m app.cli investigate --model-provider deepseek   # 真实模型（需 DEEPSEEK_API_KEY）

# 合同条款检索（真实 PDF、真实页码）
python -m app.cli search "租金递增比例" --verify-claim "自第二个租赁年度起租金递增百分之五"

# 审批（持久 checkpoint + 独立审批台账）
# 注意：一条 thread_id 只能承载一次运行，重复演示请换新 id 或换 --control-dir
python -m app.cli investigate --with-approval --thread-id thread_demo_01
python -m app.cli pending
python -m app.cli approve <request_id> --principal principal_property_manager_xinghui --draft-version 2 --reason "核对合同 5.1.1 后同意减免"
python -m app.cli approve <request_id> --principal principal_finance_xinghui --draft-version 2 --reason "财务复核通过"

# 评测（三基线）
python -m app.cli evaluate --split dev
python -m app.cli evaluate --split heldout
python -m app.cli evaluate --split heldout --baseline C_multi_agent --model-provider deepseek  # 需密钥

# 演示 API + 页面
python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000

# 回归测试
python -m unittest discover -s tests -p "test_*.py"
```

## 3. 模块职责

| 路径 | 职责 |
|---|---|
| `app/agents/base/` | Agent 契约（`AgentRequest/Context/Output`）、Registry、`BaseAgent`、`ToolBackedAgent`（确定性）、`LLMToolAgent`（模型驱动）、共享事实映射 `facts.py`、可信任务范围 `scope.py`（领域 Agent 与单 Agent 共用）、能力最低结果契约 `evidence.py`、叙述一致性 `narrative.py`、结构化资金结论 `conclusions.py` |
| `app/agents/factory.py` | 配置 → 实例的**静态白名单**（确定性表 + LLM 表）；K2 配置/实现一致性校验；按签名依赖注入 |
| `app/agents/{lease,billing,property}/` | 领域 Agent：确定性实现 + `llm_agent.py`（模型选工具、事实取自工具输出） |
| `app/agents/single/` | 单 Agent + Tools 基线（`single.investigate`） |
| `app/config/` | 每个 Agent 独立 YAML + Schema（拒绝密钥字段） |
| `app/fixtures/repository.py` | fixture 只读仓库：项目范围、`Decimal` 金额、变体 overlay |
| `app/llm/` | 厂商无关消息类型、`Fake` 客户端、脚本化模型（`scripted`，仅验证装配）、模型工厂（`offline/scripted/deepseek`）、DeepSeek（OpenAI 兼容）适配、参数裁剪 |
| `app/runtime/` | `TrustedContext`/`Evidence`/`Trace`、共享预算、有限轮次循环、Runtime 边界 |
| `app/tools/` | 工具白名单、六道闸执行器、fixture 只读工具、`document.search` |
| `app/orchestration/investigation.py` | LangGraph：规划 → 并发扇出 → 合流核验 → 限次补查 → 报告 → 审批门 |
| `app/orchestration/approval.py` | 审批规则、审计台账、校验链、幂等与并发（独立 SQLite） |
| `app/orchestration/checkpointing.py` | `AsyncSqliteSaver` 装配与 serde 白名单 |
| `app/rag/` | 合成 PDF 生成、逐页条款分块、BM25、两级引用验证、fixture↔PDF 对齐校验、`DocumentCatalog` 目录契约（按租约限定文档版本） |
| `app/db/` + `migrations/` | SQLAlchemy 2.0 只读模型、Alembic 迁移、只读连接闸门（装配期 `PRAGMA query_only=1`；本机用 SQLite 验证） |
| `app/evaluation/` | 用例装载（`expected_outcome`/`scorable`）、三基线（统一结局推导）、字段绑定的确定性评分（`scoring-v3.3`：工具事实 / 资金结论 / 金额接地分开判定）、报告绑定 |
| `app/api/` | FastAPI 适配层 + 同源演示页（**可整体删除**，CLI/评测不依赖它） |
| `app/cli.py` | 命令行入口（tools/check/demo/ask/investigate/search/approve/pending/evaluate） |

## 4. 安全边界

- 权限与项目范围只来自 `TrustedContext`；payload 出现 `permissions` / `project_ids` / `principal_id` 等保留键直接拒绝
- 工具无法伪造证据来源：`Evidence.source_tool` / `tool_call_id` 由执行器写入
- 不提供任意 SQL / Python / Shell / 文件系统 / 网络工具
- 文档正文是**不可信数据**：条款检索只把它当返回值，不改变工具策略或权限
- 审批只产出 `approved_draft`（`executed_side_effects=[]`），**不执行**调账/派单
- API 请求不能自报身份；审批人只能从服务端白名单选择（`X-Actor-Id` 只是选择，不是认证）

## 5. 已知限制（不夸大）

| 未完成/未验证 | 说明 |
|---|---|
| 真实 DeepSeek 调用 | 已实测 `ask` / `investigate` / `evaluate --split dev`；heldout 真实对照与重复测量**未做**，成本未换算 |
| PostgreSQL | 本机无服务；迁移与查询仅在 SQLite 上验证，`EXCLUDE`/RLS/NUMERIC 未实测 |
| 向量检索 / Embedding / Reranker | 只有 BM25；长问题召回不足是已知短板（见评测 H18–H20） |
| 外部副作用 | 没有调账/派单实现；接入前需先定义幂等键与补偿策略 |
| 演示鉴权 | `DEMO_PRINCIPAL_ID` + 白名单仅为演示，非真实认证 |
| 人工量表 | 评测 rubric 仍为人工待评队列；保留集 H25/H26 显式声明为人工评定（`scorable=false`） |
| 开发集自动计分 | `smoke_v1.jsonl` 是自然语言断言、面向人工量表；离线三基线在它上面都是 0/7，不能用它评价实现质量 |
| 分布式语义 | checkpoint 与审批台账是本机 SQLite；多实例并发与"恰好一次"未验证 |
| 线索复用 | 一条 `thread_id` 只允许一次运行（新增运行会因 `invalid_context` 被拒），恢复请走 `resume`/`approve` |
