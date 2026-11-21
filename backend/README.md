# backend/ — Agent 工作流、受控只读工具、知识检索、审批控制面与评测

离线优先：默认不联网、不调用真实模型；单 Agent ask 默认用脚本化模型（scripted），调查默认用确定性 Agent。业务数据默认来自 fixture，checkpoint/审批按模式可写本地 SQLite 控制面。
业务数据来自 `../docs/evaluation/fixtures/agent_first_v1.json`（合成数据，只读）。

> 当前指导关系见 [当前基线](../docs/architecture/CURRENT_BASELINE.md)。真实 DeepSeek 已有 dev/单题证据；真实 heldout/重复测量与 PostgreSQL 实机未完成。Task 031 已完成 Z1–Z3、CLI 契约、逐 Agent 模型配置、配置真实性与路由兜底的实施与自检（**待独立复查**），见 [Task 031](../docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)。

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
python -m app.cli check                     # Agent 配置 / 模型配置 / 检索配置 / 工具注册表
python tests/smoke_agent_contracts.py       # 契约自检（70 项）

# 单 Agent 路径：默认 scripted（离线脚本化模型），目标必须可信
python -m app.cli ask "A-301 现在还有多少钱没交？"      # 目标从问题中的商铺编号解析
python -m app.cli ask "现在还欠多少钱？" --lease lease_xh_a301_2025
python -m app.cli ask "..." --model-provider deepseek   # 需 DEEPSEEK_API_KEY，按 single.yaml 建客户端
# 旧参数 --provider fake|deepseek 仍可用，但属于弃用别名（fake→scripted，stderr 会提示）

# 多 Agent 图（规则规划 → 并发子 Agent → 确定性核验；未命中领域会回问）
python -m app.cli investigate
python -m app.cli investigate --backend sqlite      # 用只读数据库后端（本机 SQLite）
python -m app.cli investigate --model-provider scripted   # 领域 Agent 改由模型选工具（离线脚本化）
python -m app.cli investigate --model-provider deepseek   # 真实模型（需 DEEPSEEK_API_KEY；每 Agent 按各自 YAML）

# 合同条款检索（真实 PDF、真实页码）
python -m app.cli search "租金递增比例" --verify-claim "自第二个租赁年度起租金递增百分之五"

# 审批（持久 checkpoint + 独立审批台账）
# 注意：一条 thread_id 只能承载一次运行，重复演示请换新 id 或换 --control-dir
python -m app.cli investigate --with-approval --thread-id thread_demo_01
python -m app.cli pending
python -m app.cli approve <request_id> --dry-run --principal principal_property_manager_xinghui --draft-version 2   # 只校验，不写台账、不恢复图
python -m app.cli approve <request_id> --principal principal_property_manager_xinghui --draft-version 2 --reason "核对合同 5.1.1 后同意减免"
python -m app.cli approve <request_id> --principal principal_finance_xinghui --draft-version 2 --reason "财务复核通过"

# 评测（三基线）
python -m app.cli evaluate --split dev
python -m app.cli evaluate --split heldout
python -m app.cli evaluate --split heldout --baseline C_multi_agent --model-provider deepseek  # 需密钥

# 演示 API + 工作台页面（http://127.0.0.1:8000/）
# 页面资源全部在 app/api/static/ 下本地提供（Tabler 1.7.4），运行期不访问 CDN
python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000

# 回归测试
python -m unittest discover -s tests -p "test_*.py"
```

### 退出码（Task 031）

| 码 | 含义 |
|---|---|
| `0` | 成功（含"有明确警告的部分完成"的 `partial`） |
| `1` | 业务结果失败，例如有目标但零事实、调查没有任何子任务结果、路由要求澄清 |
| `2` | 用法或配置错误（未知参数、非法配置、无法确定可信目标等） |
| `3` | 审批错误（请求不存在、版本不匹配、越权、过期等） |

### 身份来源（Task 031）

`--principal` 默认读取与 API 相同的 `DEMO_PRINCIPAL_ID`（未设置时回退 `principal_ops_xinghui`，审批命令回退默认审批人）。显式传入 `--principal` 时属于**开发模式自报身份**：向 stderr 打印提示，并在报告元数据记录 `identity_source=cli_flag`。这不是认证，也不构成生产身份来源。

## 3. 模块职责

| 路径 | 职责 |
|---|---|
| `app/agents/base/` | Agent 契约（`AgentRequest/Context/Output`）、Registry、`BaseAgent`、`ToolBackedAgent`（确定性）、`LLMToolAgent`（模型驱动）、共享事实映射 `facts.py`、可信任务范围 `scope.py`（领域 Agent 与单 Agent 共用）、能力最低结果契约 `evidence.py`、叙述一致性 `narrative.py`、结构化资金结论 `conclusions.py` |
| `app/agents/factory.py` | 配置 → 实例的**静态白名单**（确定性表 + LLM 表）；K2 配置/实现一致性校验；按签名依赖注入 |
| `app/agents/{lease,billing,property}/` | 领域 Agent：确定性实现 + `llm_agent.py`（模型选工具、事实取自工具输出） |
| `app/agents/single/` | 单 Agent + Tools 基线（`single.investigate`） |
| `app/agents/base/` | Agent 契约（`AgentRequest/Context/Output`）、Registry、`BaseAgent`、`ToolBackedAgent`（确定性）、`LLMToolAgent`（模型驱动）、共享事实映射 `facts.py`、可信任务范围 `scope.py`（领域 Agent 与单 Agent 共用）、能力最低结果契约与取证口径 `evidence.py`（Task 031：成功且属于目标才算取证）、叙述一致性 `narrative.py`、结构化资金结论 `conclusions.py` |
| `app/agents/factory.py` | 配置 → 实例的**静态白名单**（确定性表 + LLM 表）；K2 配置/实现一致性校验；按签名依赖注入；Task 031 起 llm 引擎按 Agent 名注入各自模型客户端 |
| `app/agents/{lease,billing,property}/` | 领域 Agent：确定性实现 + `llm_agent.py`（模型选工具、事实取自工具输出） |
| `app/agents/single/` | 单 Agent + Tools 基线（`single.investigate`）；失败/越界调用只作审计（Task 031 / Z2） |
| `app/config/` | 每个 Agent 独立 YAML + Schema（拒绝密钥字段）；`retrieval_settings` 只接受真实能力（`enabled`/`top_k`） |
| `app/fixtures/repository.py` | fixture 只读仓库：项目范围、`Decimal` 金额、变体 overlay |
| `app/llm/` | 厂商无关消息类型、`Fake` 客户端、脚本化模型（`scripted`，仅验证装配）、模型工厂（按配置校验/构造/缓存，`offline/scripted/deepseek`）、DeepSeek（OpenAI 兼容）适配、参数裁剪 |
| `app/runtime/` | `TrustedContext`/`Evidence`/`Trace`、共享预算、有限轮次循环、Runtime 边界 |
| `app/tools/` | 工具白名单、统一受控执行器、fixture 只读工具、`document.search` |
| `app/orchestration/investigation.py` | LangGraph：规划 → 并发扇出 → 合流核验 → 限次补查 → 报告 → 审批门；未命中领域返回 `needs_clarification`，报告写 `routing_reason` |
| `app/orchestration/vocabulary.py` | 领域词表（唯一来源；逐词来源见 [planner_vocabulary](../docs/architecture/planner_vocabulary.md)） |
| `app/orchestration/approval.py` | 审批规则、审计台账、校验链、幂等与并发（独立 SQLite）；`preview_decision` 在副本上做纯校验 |
| `app/orchestration/checkpointing.py` | `AsyncSqliteSaver` 装配与 serde 白名单 |
| `app/rag/` | 合成 PDF 生成、逐页条款分块、BM25、两级引用验证、fixture↔PDF 对齐校验、`DocumentCatalog` 目录契约（按租约限定文档版本） |
| `app/db/` + `migrations/` | SQLAlchemy 2.0 只读模型、Alembic 迁移、只读连接闸门（装配期 `PRAGMA query_only=1`；本机用 SQLite 验证） |
| `app/evaluation/` | 用例装载（`expected_outcome`/`scorable`）、三基线（统一结局推导）、字段绑定的确定性评分（`scoring-v3.3`：工具事实 / 资金结论 / 金额接地分开判定）、报告绑定与逐 Agent `models_by_agent` |
| `app/api/` | FastAPI 适配层 + 同源工作台页面（`static/` 由受限 `/static` 挂载提供；**可整体删除**，CLI/评测不依赖它） |
| `app/cli.py` | 命令行入口（tools/check/demo/ask/investigate/search/approve/pending/evaluate）；退出码 0/1/2/3、身份来源与匹配展示 |

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
| 正式真实模型实验 | 已实测 `ask` / `investigate` / `evaluate --split dev` 与有界单题；heldout 真实对照与重复测量**未做**，成本未换算。历史真实的模型名是 `deepseek-chat`（官方 2026-07-24 下线），当前配置为 `deepseek-flash` |
| PostgreSQL | 本机无服务；迁移与查询仅在 SQLite 上验证，`EXCLUDE`/RLS/NUMERIC 未实测 |
| 向量检索 / Embedding / Reranker | 只有 BM25；长问题召回不足是已知短板（见评测 H18–H20）。`retrieval_settings` 只接受 `enabled`/`top_k`，声明未实现字段即加载失败；`top_k` 为声明值 |
| 外部副作用 | 没有调账/派单实现；接入前需先定义幂等键与补偿策略 |
| 演示鉴权 | `DEMO_PRINCIPAL_ID` + 白名单仅为演示，非真实认证；CLI `--principal` 是开发模式自报身份并会提示、记录 `identity_source=cli_flag` |
| 人工量表 | 评测 rubric 仍为人工待评队列；保留集 H25/H26 显式声明为人工评定（`scorable=false`） |
| 开发集自动计分 | `smoke_v1.jsonl` 是自然语言断言、面向人工量表；离线三基线在它上面都是 0/7，不能用它评价实现质量 |
| 分布式语义 | checkpoint 与审批台账是本机 SQLite；多实例并发与"恰好一次"未验证 |
| 线索复用 | 一条 `thread_id` 只允许一次运行（新增运行会因 `invalid_context` 被拒），恢复请走 `resume`/`approve` |
| Z1–Z3 等修复状态 | Task 031 已实现 `ask` 可信目标、失败调用不计取证、默认输出可信资金结论，并有前后反例与回归；**待独立复查**，不以自检替代验收，见 [Task 031](../docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md) |
| 每 Agent 独立模型 | 已实现：客户端按各 Agent YAML 创建（同参数缓存共享），非法配置启动期失败；`agent_models`/`models_by_agent` 逐 Agent 报告实际模型。仍待独立复查 |
| 路由与澄清 | 未命中领域返回 `needs_clarification`（`route=clarification`、零工具、不审批），不再静默落 billing；API 层对澄清 run 的状态语义（当前仍记 `completed`）属 Task 032 |
| 独立 Business Service 层 | 部分只读聚合在 Repository 内；保留现有实现，目标 Service/Repository 职责差距见 [系统架构](../docs/architecture/system_design.md) |
