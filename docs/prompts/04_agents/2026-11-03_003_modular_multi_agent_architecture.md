# 2026-11-03_003_模块化多 Agent 架构约束

## 1. 基本信息

- **日期**：2026-11-03
- **任务编号**：003
- **模块**：04_agents（架构约束，跨模块生效）
- **关联任务**：001（环境）、002（文档体系）
- **Git Commit**：`Pending`

## 2. 任务目标和背景

项目需要长期支持「随时增删改换 Agent」，且单个 Agent 的模型、Prompt、工具、推理参数、性能可独立优化而不影响其他 Agent。

这要求把架构约束前置到项目初始化阶段确定下来，否则后续业务代码写进一个巨型文件后，重构成本会指数上升。

本次交付范围：架构设计 + 目录规划 + 配置示例 + 接口规范。**不实现完整六 Agent 系统，不安装不必要依赖。**

## 3. 原始用户 Prompt

````
# 项目新增架构要求：模块化、可扩展、低耦合 Multi-Agent 系统
我们的项目 `commercial-property-multi-agent` 增加一项长期、强制性的架构要求。

我希望这个项目未来能够方便地增加、禁用、删除或替换 Agent，并能够单独优化某个 Agent 的模型、Prompt、工具、推理参数和运行性能，而不影响其他 Agent 的正常运行。

请将以下要求作为整个项目后续开发的架构约束。

## 1. 核心架构原则
采用：

**Modular Monolith + Agent Registry + LangGraph Orchestration + Configuration-Driven Design**

遵循以下原则：

- Single Responsibility：每个 Agent 只负责明确的业务职责。
- Loose Coupling：Agent 之间不直接依赖彼此的具体实现。
- High Cohesion：同一个 Agent 的代码、Prompt、配置和测试集中管理。
- Dependency Injection：通过依赖注入获取模型、工具和服务。
- Interface Standardization：所有 Agent 遵守统一接口。
- Configuration Isolation：每个 Agent 的配置相互独立。
- Testability：每个 Agent 可以独立测试，不必启动完整系统。
禁止将所有 Agent 的业务逻辑写进一个巨大的 Python 文件。

## 2. 统一 Agent 接口
请在架构设计中定义统一的 AgentProtocol 或 BaseAgent。

至少包含：

- Agent 标识与能力描述。
- 标准输入 AgentRequest。
- 标准输出 AgentResult。
- 执行上下文 AgentContext。
- 错误处理约定。
- 可观测性与执行元数据。
输入输出使用 Pydantic 或明确的类型契约。

所有 Agent 通过标准接口交互，不能直接依赖其他 Agent 的内部方法。

## 3. Agent Registry
设计一个 Agent Registry，用于：

- 注册和查找 Agent。
- 根据能力发现可用 Agent。
- 判断 Agent 是否启用。
- 拒绝重复名称或不兼容接口。
- 在需要时为 LangGraph 构建流程提供可用 Agent 清单。
新增 Agent 不应要求修改所有现有 Agent 文件。

禁止根据不可信的配置字符串任意导入 Python 模块或执行代码。只允许注册项目中明确授权的 Agent 实现。

## 4. 独立 Agent 配置
每个 Agent 使用独立 YAML 配置，例如：

`backend/app/config/agents/lease.yaml`

独立配置至少支持：

- enabled
- model_provider
- model_name
- temperature（模型支持时）
- timeout
- max_retries
- prompt_path
- allowed_tools
- retrieval_settings（适用时）
配置加载时进行 Schema 校验。

模型参数应通过统一模型适配层转换，不要假设所有模型都支持完全相同的参数。

API Key 等敏感配置必须通过环境变量或安全的密钥管理方式读取，不能写入 YAML 或 Git 仓库。

## 5. 工作流解耦
使用 LangGraph 编排 Agent，但不要将每个 Agent 的具体实现硬编码在 Coordinator 中。

Coordinator 负责：

- 理解和拆解任务。
- 选择当前可用的能力。
- 分配子任务。
- 合并执行结果。
- 处理任务失败或部分完成。
对于被禁用或缺失的能力，必须提供明确的错误处理、降级或人工转交机制，不允许悄悄忽略重要任务。

共享 State 只保存跨节点需要的信息，Agent 内部临时状态尽量保持私有。并发更新要有明确的数据合并策略。

## 6. 业务工具与 Agent 分离
数据库访问、收费计算、合同查询、风险规则、RAG 检索等功能，应当封装为独立工具或业务服务。

Agent 负责决策和调用。

确定性计算由普通 Python 代码执行，不依赖 LLM 自由生成结果。

每个 Agent 只能访问明确授权的工具，并受到业务数据权限限制。

## 7. 独立性能优化
未来需要能够单独调整以下内容：

- 单个 Agent 使用的 LLM。
- 单个 Agent 的 System Prompt。
- 单个 Agent 的工具列表。
- 单个 Agent 的超时和重试策略。
- 单个 Agent 的 RAG 检索参数。
- 单个 Agent 的日志级别与运行指标。
优化某个 Agent 后，需要能够单独运行它的测试和评测，并运行相关跨 Agent 回归测试。

日志中记录 agent_name、agent_version、model、latency、token_usage（可获得时）、error、trace_id 等信息。

## 8. 测试与兼容性要求
未来至少需要验证：

1. 新增 Agent 后，原有 Agent 功能正常。
2. 禁用非核心 Agent 后，系统能正常处理其他业务。
3. 禁用核心能力后，系统能明确报告能力不可用。
4. 修改 Lease Agent 的 Prompt 不影响 Billing Agent 的独立测试。
5. 替换模型后，仍符合统一输入输出契约。
6. 单个 Agent 故障不会无控制地导致整个流程崩溃。
7. 新版本 Agent 能兼容现有工作流的标准接口。
注意：模块化不代表完全不存在依赖。接口、数据库 Schema、共享状态发生变化时，仍然必须进行兼容性检查和回归测试。

## 9. 文档归档要求
请在现有 docs 体系中增加：

`docs/architecture/agent_architecture.md`

记录：

- Agent 模块设计。
- 接口契约。
- Agent Registry。
- 配置机制。
- 工作流编排。
- 依赖关系。
- 错误处理和降级策略。
- 如何添加、禁用或替换 Agent。
同时新增：

`docs/architecture/agent_development_guide.md`

作为未来开发 Agent 的标准指导文档。

本次架构决策也需要记录到开发日志，并保留原始 Prompt。

## 10. 当前阶段的任务边界
注意：我们目前仍处于项目初始化阶段。

本次先完成架构设计、目录规划、配置示例和必要的接口规范，不要提前实现完整的六 Agent 系统，不要安装不必要的依赖。

如果现有项目已经包含文件，请先检查，再进行兼容性修改，不要覆盖已有代码。

请先向我展示建议的目录结构、模块职责、接口设计和可能的风险，然后按照当前开发阶段完成必要的初始化工作。

最后报告修改了哪些文件、采用这些设计的原因，以及未来如何新增或关闭一个 Agent。
````

## 4. AI 实际执行的主要步骤

### 4.1 前置检查（未做任何修改）

1. `git ls-files` + 全量文件枚举：确认任务 002 的成果已被提交为 `7ed2665`（已推送 `origin/main`），仓库中**只有 `docs/` 与 `.gitignore`，没有任何业务代码**，因此不存在需要兼容或覆盖的既有实现。
2. 预判性地对计划创建的路径做 `git check-ignore` 检查，发现** `.gitignore` 中的 `env/` 规则会忽略任意层级的 `env/` 目录**。这会对未来可能出现的 `backend/app/env/` 包造成隐性丢失，因此将规则锚定为 `/env/`。
3. 确认 `pydantic` 未安装、`py_compile` 可用。

### 4.2 依赖决策

只安装 `pydantic>=2.7` 与 `pyyaml>=6.0`。理由：本次交付物包含「配置 Schema 校验」与「Pydantic 类型契约」，没有这两个包，交付的接口规范无法被执行验证。**未安装** LangGraph / LangChain / FastAPI / PyTorch / Chroma 等。

### 4.3 目录与代码骨架

按 `backend/app/` 布局建立骨架，实现以下模块：

| 模块 | 文件 | 说明 |
|---|---|---|
| 路径解析 | `app/paths.py` | 以 `backend/` 为基准，禁止绝对路径与越界 |
| 契约 | `app/agents/base/contracts.py` | Request / Context / Result / Descriptor / Output / Metadata |
| 接口 | `app/agents/base/protocol.py` | `AgentProtocol`（runtime_checkable） |
| 基类 | `app/agents/base/base_agent.py` | 超时、重试、错误映射、日志、Prompt 惰性加载 |
| 注册表 | `app/agents/base/registry.py` | 注册/查找/发现/启用判定/冲突拒绝 |
| 错误 | `app/agents/base/errors.py` | `ErrorCode` 枚举 + 异常体系 + 可重试集合 |
| 配置 Schema | `app/config/schema.py` | `AgentConfig` + `RetrievalSettings`，拒绝敏感字段 |
| 配置加载 | `app/config/loader.py` | YAML → 校验 → 强类型对象 |
| 工厂 | `app/agents/factory.py` | **静态白名单**，配置 → 实例 |
| 模型适配 | `app/llm/adapter.py` | 参数裁剪 + 密钥来源 + provider 白名单 |
| 工具契约 | `app/tools/base.py` | `ToolProtocol` + 工具授权 + 业务权限校验 |
| 编排 State | `app/orchestration/state.py` | `WorkflowState` + reducer 与合并策略 |
| 编排契约 | `app/orchestration/coordinator.py` | 降级策略 + 能力可行性检查 + 结果聚合 |

**不导入 langgraph**：`state.py` 只用 `Annotated` 声明 reducer 语义，因此可在依赖安装前导入与测试。

### 4.4 示例 Agent 与配置

按「骨架 + 无业务逻辑」原则实现 3 个 Agent 包（`lease`、`billing`、`compliance`），每个 `_execute()` 直接抛 `NOT_IMPLEMENTED`。三者用于覆盖不同状态组合：

| Agent | 状态 | 用途 |
|---|---|---|
| `lease` | enabled + 有检索配置 | 主示例 |
| `billing` | enabled + `temperature: null` + 无检索 | 验证模型参数裁剪与配置隔离 |
| `compliance` | `enabled: false` | 验证能力禁用后的明确报告 |

每个 Agent 配独立 `prompts/system.md`，验证 Prompt 隔离。

### 4.5 自检脚本

编写 `backend/tests/smoke_agent_contracts.py`（纯 Python，不依赖 pytest），覆盖 7 个分组共 57 项检查。

### 4.6 迭代修复

首次运行发现真实缺陷（详见第 7 节），修复后 57 项全绿、退出码 0。

### 4.7 文档

新增 `agent_architecture.md`、`agent_development_guide.md`，并回填开发日志、Git 检查点、编号登记表与知识笔记。

## 5. 新增和修改的文件

### 新增

| 文件 | 说明 |
|---|---|
| `backend/app/__init__.py`、`backend/app/agents/__init__.py`、`backend/app/config/__init__.py`、`backend/app/llm/__init__.py`、`backend/app/orchestration/__init__.py`、`backend/app/tools/__init__.py`、`backend/tests/__init__.py` | 包声明（空） |
| `backend/app/paths.py` | 路径解析 |
| `backend/app/agents/base/__init__.py` | 契约统一导出 |
| `backend/app/agents/base/contracts.py` | 输入输出契约 |
| `backend/app/agents/base/protocol.py` | AgentProtocol |
| `backend/app/agents/base/base_agent.py` | BaseAgent |
| `backend/app/agents/base/registry.py` | AgentRegistry |
| `backend/app/agents/base/errors.py` | 错误码与异常 |
| `backend/app/agents/factory.py` | 静态白名单工厂 |
| `backend/app/agents/lease/{__init__.py,agent.py,prompts/system.md}` | Lease Agent 骨架 |
| `backend/app/agents/billing/{__init__.py,agent.py,prompts/system.md}` | Billing Agent 骨架 |
| `backend/app/agents/compliance/{__init__.py,agent.py,prompts/system.md}` | Compliance Agent 骨架（默认禁用） |
| `backend/app/config/schema.py` | 配置 Schema |
| `backend/app/config/loader.py` | 配置加载器 |
| `backend/app/config/agents/lease.yaml` | 配置示例 |
| `backend/app/config/agents/billing.yaml` | 配置示例 |
| `backend/app/config/agents/compliance.yaml` | 配置示例（禁用） |
| `backend/app/llm/adapter.py` | 模型适配层 |
| `backend/app/tools/base.py` | 工具契约与授权 |
| `backend/app/orchestration/state.py` | 共享 State |
| `backend/app/orchestration/coordinator.py` | 编排契约 |
| `backend/tests/smoke_agent_contracts.py` | 阶段 0 自检 |
| `docs/architecture/agent_architecture.md` | 架构设计文档 |
| `docs/architecture/agent_development_guide.md` | Agent 开发指南 |
| `docs/prompts/04_agents/2026-11-03_003_modular_multi_agent_architecture.md` | 本归档 |

### 修改

| 文件 | 变更 |
|---|---|
| `.gitignore` | `env/` → `/env/`（避免忽略任意层级的 `env` 包） |
| `docs/development_logs/development_log.md` | 追加任务 003 记录 |
| `docs/checkpoints/git_history.md` | 回填 7ed2665，新增本次待提交记录 |
| `docs/README.md` | 编号登记表补 003 |
| `docs/architecture/system_design.md` | 引用新文档，补充 ADR |
| `docs/lessons_learned/knowledge_notes.md` | 新增两篇笔记 |

### 删除

| 文件 | 原因 |
|---|---|
| `docs/prompts/04_agents/.gitkeep` | 该目录已有实际文件，占位文件不再需要 |

## 6. 执行结果和验证方式

运行 `python backend/tests/smoke_agent_contracts.py`，结果：**57 项全部通过，退出码 0**。

| 分组 | 覆盖内容 | 结果 |
|---|---|---|
| 1. 配置加载与 Schema 校验 | 3 个配置加载、7 类非法配置被拒、无实现配置的跳过与 strict 报错、文件名与 name 不一致 | 16 项通过 |
| 2. Registry | 注册、能力发现、禁用能力可查、`AgentDisabledError` 与 `CapabilityUnavailableError` 区分、重名、能力冲突、接口不兼容 | 10 项通过 |
| 3. Agent 执行与错误约定 | `NOT_IMPLEMENTED`、`CAPABILITY_NOT_DECLARED`、`AGENT_NOT_ENABLED`、元数据含 name/version/trace/latency | 8 项通过 |
| 4. Prompt 与工具授权隔离 | 各 Agent 加载自己的 Prompt 且互不影响、未授权工具被拒、缺权限被拒 | 7 项通过 |
| 5. 模型适配层 | temperature 为 null 时不下发、max_tokens 下发、未登记 provider 被拒、缺少 API Key 报错 | 7 项通过 |
| 6. 计划可行性与聚合 | available / disabled / missing 三类区分、`feasible` 判定、部分成功聚合 | 7 项通过 |
| 7. 工厂白名单 | 三个 Agent 已登记、白名单外 name 无法实例化 | 2 项通过 |

补充验证：

| 验证项 | 结果 |
|---|---|
| `git check-ignore` 对 `backend/` 下 6 个代表路径 | 全部可跟踪（`env/` 锚定后不再误伤） |
| 环境依赖 | 仅 pydantic 2.14.2 / pydantic-core / pyyaml / typing-* / annotated-types，无 AI 框架 |
| 未覆盖既有代码 | 仓库此前无业务代码，本次全部为新增 |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `AgentError` 子类以 message 作为首个位置参数时报 `AttributeError: 'str' object has no attribute 'value'` | 基类签名是 `__init__(code, message)`，而 `default_code` 风格的子类（如 `ToolNotAllowedError`）习惯以 message 开头 | 把签名改为 `__init__(message, *, code=None, ...)`，`code` 默认取 `self.default_code`；同步修正全部调用点 |
| 自检断言 `report.registered == ("lease","billing","compliance")` 失败 | 配置按文件名排序加载，注册顺序为 `billing, compliance, lease` | 断言改为集合比较，并补充「无配置被跳过」的显式检查 |
| 自检脚本输出在 PowerShell 中显示为乱码且退出码被误判为 1 | Agent 的 warning 日志写入 stderr；控制台代码页为 GBK | 自检脚本把 logging 输出定向到 stdout；运行前设 `$env:PYTHONIOENCODING='utf-8'` |
| `Registry` 首次实现里为了类型注解导入了 `AgentConfig` | 多余依赖，且可能引入 `agents ↔ config` 的首轮循环 | 确认 `Registry` 不需要该类型，直接删除导入 |
| `.gitignore` 中 `env/` 会忽略任意层级同名目录 | gitignore 目录模式按路径段匹配 | 锚定为 `/env/`，并在自检中验证 |

## 8. 对应 Git Commit Hash

- **状态**：`Pending`
- **原因**：按约定不自动创建 Commit，等待确认。
- **建议 Commit Message**：见 `docs/checkpoints/git_history.md`。

## 9. 后续待办事项

- [ ] 确认后提交本次架构骨架
- [ ] 阶段 1：`pyproject.toml`、FastAPI 入口、`python-dotenv` 或 Pydantic Settings 配置层
- [ ] 阶段 1：把 `smoke_agent_contracts.py` 迁移为 pytest 正式测试
- [ ] 阶段 2：确定多租户字段（`tenant_id` 落库），否则后续无法后补
- [ ] 阶段 3：实现 RAG 检索工具，接入 `retrieval_settings`
- [ ] 阶段 4：引入 LangGraph，实现 Coordinator 的 `build_plan` / `run`，并补并发写入测试
- [ ] 阶段 4：确定 checkpointer 版本迁移策略
- [ ] 补充跨 Agent 回归测试矩阵（对应本次需求第 8 节 7 条）
