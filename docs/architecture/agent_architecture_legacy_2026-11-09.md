> **历史快照（2026-11-09 归档）**：下文保留 Task 026 整理前的原文，仅供追溯；其中的“当前”、待办、示例和优先级不作为现行指导。现行内容见 [agent_architecture.md](./agent_architecture.md)。

# Agent 架构设计

> **状态**：概念设计（阶段 0 骨架，57 项自检通过）· **已被 ADR-005 限定适用范围**
> **最后更新**：2026-11-03（任务 006 增量更新）
> **关联任务**：003（初版）、006（方向收敛与契约细化）
> **配套文档**：[agent_development_guide.md](./agent_development_guide.md)、[agent_runtime_contracts.md](./agent_runtime_contracts.md)
>
> **2026-11-03 增量说明（任务 006）**：
> 1. 项目已转向 Agent-first 基线，**P0 范围与优先级以 [ADR-005](../decisions/ADR-005-agent-first-refocus.md) 和 [mvp_scope_v2.md](../product/mvp_scope_v2.md) 为准**。本文档保留为 Agent 层的**概念设计依据**（分层、Registry、配置、错误与降级），不再单独定义 P0 范围。
> 2. **字段级契约、State 归并规则、预算与重试归属、审批与恢复语义**，一律以 [agent_runtime_contracts.md](./agent_runtime_contracts.md) 为准；本文档不重复定义，避免两处漂移。
> 3. 本文档 §10 列出的风险中，**"能力字符串无编译期校验""工厂白名单是唯一登记点"仍然有效**；新增的骨架缺陷 **K1–K5** 见运行时契约 §13，列为任务 007 修复项。原 K6（数据库 `UNIQUE(lease_id)` 未在代码层表达）已按 Prompt 1-R1 改记为**未来数据库映射注意事项 N1**，不属于已复现的运行时缺陷。

---

## 1. 架构定位

采用 **Modular Monolith + Agent Registry + LangGraph Orchestration + Configuration-Driven Design**。

选择 Modular Monolith 而非微服务的原因：

- 当前是单人/小团队项目，微服务的部署与运维成本远高于收益。
- Agent 之间需要频繁共享上下文（租约 + 账单 + 合规），跨进程调用会显著增加延迟与失败面。
- 模块边界靠**接口契约**而非网络边界保证，仍然可以做到「独立开发、独立测试、独立替换」。
- 未来若某个 Agent 需要独立扩容，可沿现有接口边界抽成服务，不需要重写业务逻辑。

核心约束一句话：**Agent 之间只通过 `AgentProtocol` 交互，任何 Agent 不得 import 另一个 Agent 的实现模块。**

---

## 2. 目录结构

```text
backend/
├── app/
│   ├── paths.py                        # 统一路径解析（基准 = backend/）
│   ├── agents/
│   │   ├── base/                       # 唯一的 Agent 契约实现，业务 Agent 只依赖这里
│   │   │   ├── contracts.py            # AgentRequest / AgentResult / AgentContext / ...
│   │   │   ├── protocol.py             # AgentProtocol
│   │   │   ├── base_agent.py           # BaseAgent（超时/重试/错误映射/日志）
│   │   │   ├── registry.py             # AgentRegistry
│   │   │   └── errors.py               # ErrorCode + 异常体系
│   │   ├── factory.py                  # 配置 -> 实例，静态白名单
│   │   ├── lease/                      # 每个 Agent 一个包：代码 + prompts 同居
│   │   │   ├── agent.py
│   │   │   └── prompts/system.md
│   │   ├── billing/
│   │   └── compliance/                 # 默认禁用示例
│   ├── config/
│   │   ├── schema.py                   # AgentConfig（Pydantic，拒绝敏感字段）
│   │   ├── loader.py                   # YAML 加载 + Schema 校验
│   │   └── agents/                     # 数据：每个 Agent 一个 YAML
│   │       ├── lease.yaml
│   │       ├── billing.yaml
│   │       └── compliance.yaml
│   ├── llm/adapter.py                  # 模型适配层（参数裁剪 + 密钥来源）
│   ├── tools/base.py                   # 工具契约 + 工具授权校验
│   └── orchestration/
│       ├── state.py                    # LangGraph 共享 State 与合并策略
│       └── coordinator.py              # 编排契约 + 能力可行性检查
└── tests/
    └── smoke_agent_contracts.py        # 阶段 0 自检（57 项）
```

**High Cohesion 的体现**：一个 Agent 的代码、Prompt、配置、测试放在同一命名空间下（`agents/<name>/` + `config/agents/<name>.yaml`），修改时不需要在仓库里到处找文件。

---

## 3. 接口契约

### 3.1 三类数据结构

| 类型 | 作用 | 关键字段 |
|---|---|---|
| `AgentRequest` | 标准输入 | `request_id`、`task_id`、`capability`、`payload` |
| `AgentContext` | 执行上下文（横切关注点） | `trace_id`、`tenant_id`、`user_id`、`permissions`、`deadline_at` |
| `AgentResult` | 标准输出 | `status`、`output`、`error`、`warnings`、`metadata` |
| `AgentDescriptor` | 自我描述（发现用） | `name`、`version`、`description`、`capabilities`、`enabled` |

设计取舍：

- **payload 与 context 分离**。业务数据放 `payload`，权限/租户/超时放 `context`。这样 Agent 只关心业务，横切关注点由上层统一注入，也避免业务代码被权限判断污染。
- **Agent 只返回业务数据**。子类实现的 `_execute()` 返回 `AgentOutput`，`AgentResult` 由 `BaseAgent` 构造。因此延迟、模型名、trace_id、重试次数这些元数据**在所有 Agent 上天然一致**，不会出现某个 Agent 忘了记日志。
- **全部 `frozen=True` + `extra="forbid"`**。契约对象不可变，禁止悄悄塞入额外字段。

### 3.2 能力命名

`capability` 采用 `<domain>.<action>` 格式，由正则强制校验：

```text
lease.query
lease.renewal_evaluation
billing.statement
billing.arrears_check
compliance.check
```

**刻意不设全局能力枚举表**。若把所有能力集中在一个 enum 里，每新增一个 Agent 都要改这个公共文件，违背「新增 Agent 不应修改已有文件」。能力由各 Agent 在 `ClassVar capabilities` 与自己的 YAML 中声明，Registry 在运行时汇总。

### 3.3 执行流程

```text
调用方
  └─> BaseAgent.handle()
        ├─ 1. 检查 config.enabled          → 否则 AGENT_NOT_ENABLED
        ├─ 2. 检查 capability 是否声明      → 否则 CAPABILITY_NOT_DECLARED
        ├─ 3. 检查 context.deadline_at      → 否则 DEADLINE_EXCEEDED
        ├─ 4. asyncio.wait_for(_execute())  → 超时则 TIMEOUT（可重试）
        ├─ 5. 失败且 retryable 且未超过 max_retries → 重试
        └─ 6. 任何未捕获异常 → INTERNAL_ERROR，转成失败结果，不向上抛
```

第 6 步是关键：**单个 Agent 崩溃不会让整条工作流连带崩溃**，只会产生一个 `FAILED` 的 `AgentResult`。

---

## 4. Agent Registry

### 4.1 职责

| 能力 | 接口 | 说明 |
|---|---|---|
| 注册 | `register(agent, replace=False)` | 拒绝重名、拒绝能力冲突、拒绝接口不兼容 |
| 查找 | `get(name)` | 按名称取实例 |
| 按能力发现 | `agent_for_capability(cap)` / `require_capability(cap)` | 后者区分「缺失」与「禁用」 |
| 启用状态 | `available_capabilities()` / `disabled_capabilities()` | 供 Coordinator 生成可用清单 |
| 清单输出 | `descriptors(enabled_only=True)` | 供 LangGraph 构建节点集 |

### 4.2 冲突处理

- **同名**：抛 `DuplicateAgentError`。覆盖必须显式传 `replace=True`，避免手滑。
- **同能力**：两个 Agent 声明同一个 capability 时抛 `CapabilityConflictError`。多 Agent 声称能处理同一件事会破坏「按能力选 Agent」的确定性，因此宁可启动失败。
- **接口不兼容**：`descriptor` 不是 `AgentDescriptor` 或缺少 `handle`/`supports` 时抛 `IncompatibleAgentError`。

### 4.3 安全边界（重要）

Registry **只接受已构造好的对象，绝不接受字符串**。

配置字符串到实现的映射在 `app/agents/factory.py`，是一张代码内的静态白名单：

```python
AGENT_IMPLEMENTATIONS: Final[dict[str, type[BaseAgent]]] = {
    "lease": LeaseAgent,
    "billing": BillingAgent,
    "compliance": ComplianceAgent,
}
```

因此 YAML 里的 `name` 只能命中这三个键。即使配置文件被篡改写成 `os.system` 或任意模块路径，也只会在字典查找时得到 `None` 并抛 `AgentNotRegisteredError`，**不存在 `importlib.import_module(config_name)` 这类任意导入路径**。

自检已覆盖：白名单外的 `name` 无法实例化。

---

## 5. 配置机制

### 5.1 文件位置与独立性

一个 Agent 一个文件：`backend/app/config/agents/<name>.yaml`。文件名必须与 `name` 字段一致（加载器强制校验），防止复制粘贴后改配置改错对象。

### 5.2 字段

| 字段 | 作用 | 约束 |
|---|---|---|
| `name` / `version` | 标识 | `name` 与文件名一致 |
| `enabled` | 启用开关 | 禁用后能力从可用清单消失 |
| `capabilities` | 能力声明 | `<domain>.<action>`，不可重复 |
| `model_provider` / `model_name` | 模型 | 必须命中适配层白名单 |
| `temperature` / `max_tokens` | 生成参数 | `null` 表示不下发该参数 |
| `api_key_env` | **变量名**，不是密钥 | 必须是大写下划线形式 |
| `timeout_seconds` / `max_retries` | 稳定性 | 0 < timeout ≤ 600，0 ≤ retries ≤ 5 |
| `prompt_path` | Prompt 路径 | 相对 `backend/`，禁止绝对路径与 `..` |
| `allowed_tools` | 工具白名单 | Agent 只能调用列出的工具 |
| `retrieval_settings` | RAG 参数 | `rerank_top_n ≤ top_k` |
| `log_level` | 日志级别 | 白名单校验 |

### 5.3 校验

全部在 Pydantic Schema 中，加载即校验，失败抛 `AgentConfigError` 并带出文件路径与具体字段。

### 5.4 密钥

**三层防护**：

1. Schema 里 `extra="forbid"`，未知字段直接报错。
2. `_reject_secret_fields` 显式拒绝 `api_key` / `password` / `token` / `secret` 等键名，报错信息提示改用 `api_key_env`。
3. 运行时密钥由 `ModelAdapter.resolve_api_key()` 从 `os.environ` 读取，缺失时抛 `MissingApiKeyError`，**且从不回显密钥值**。

### 5.5 模型参数裁剪

Agent 只声明意图，适配层决定实际下发什么：

```python
{"model": config.model_name}
+ temperature  仅在非 None 且 provider 支持时加入
+ max_tokens   仅在非 None 且 provider 支持时加入
```

因此 `billing.yaml` 写 `temperature: null` 时，该参数不会出现在请求中——这对不支持 temperature 的模型是必须的。替换模型时只改 YAML，不改任何 Agent 代码。

---

## 6. 工作流编排

### 6.1 分工

```text
Coordinator（编排层）
  ├─ 拆解：request → list[SubTask]
  ├─ 选择：按 capability 从 Registry 取 Agent（不 import 任何具体 Agent）
  ├─ 执行：并发调度 SubTask，收集 AgentResult
  ├─ 聚合：summarize_results() 判定 SUCCESS / PARTIAL / FAILED
  └─ 降级：按 CoordinatorPolicy 处理能力缺口
```

### 6.2 共享 State

`app/orchestration/state.py` 定义 `WorkflowState`，并规定合并策略：

| 字段 | Reducer | 理由 |
|---|---|---|
| `results` / `warnings` / `failures` | `operator.add`（追加） | 并发节点只追加，天然无冲突 |
| `plan` / `final_output` | 无 reducer（单点写入） | 并发写入应直接报错，属于有意的保护 |

**State 只放跨节点信息**。Agent 内部的临时变量必须是局部变量，不进 State——否则 checkpointer 体积会迅速膨胀，且字段语义会变得难以维护。

State 中的 `results` 存 `AgentResult.model_dump(mode="json")` 而非对象本身，保证可被 checkpointer 序列化。

### 6.3 能力缺口处理

`check_plan_feasibility()` 在执行前扫描整个计划，输出三类结果：

| 分类 | 含义 | 来源 |
|---|---|---|
| `available` | 能力可用，返回提供者 | `require_capability` 成功 |
| `disabled` | 有 Agent 声明但被配置禁用 | `AgentDisabledError` |
| `missing` | 没有任何 Agent 声明 | `CapabilityUnavailableError` |

**禁止静默跳过**。缺口必须三选一处理：

| 策略 | 行为 | 适用场景 |
|---|---|---|
| `FAIL_FAST` | 整个任务失败，返回明确错误 | 关键业务链路 |
| `DEGRADE` | 用可用能力完成任务，结果标 `PARTIAL` 并写明缺什么 | 非关键增强能力（默认） |
| `ESCALATE_TO_HUMAN` | 转人工，保留已完成部分 | 涉及金额、法律判断 |

---

## 7. 依赖关系

```text
agents/*/agent.py ──> agents/base（契约）
        │
        └──X 禁止 ──> 其他 agent 的实现模块

agents/factory.py ──> agents/*（唯一允许引用具体实现的地方）
                  ──> config/loader

orchestration/coordinator.py ──> agents/base（契约）+ registry
                             ──X 禁止 ──> 具体 Agent 实现

config/schema.py ──> agents/base/contracts（仅复用 capability 正则）
llm/adapter.py   ──> config/schema
tools/base.py    ──> config/schema + agents/base/contracts
```

三条硬规则：

1. 业务 Agent **不得** import 其他 Agent 的实现。
2. Coordinator **不得** import 具体 Agent。
3. 只有 `factory.py` 可以 import 具体 Agent（它是白名单的唯一登记处）。

**循环依赖的处理**：`agents/base/base_agent.py` 通过 `TYPE_CHECKING` 导入 `AgentConfig`，运行时为零依赖，因此 `agents ↔ config` 不构成循环。

---

## 8. 错误处理与降级

### 8.1 错误码

| 错误码 | 可重试 | 典型场景 |
|---|---|---|
| `INVALID_REQUEST` | 否 | 请求结构不合法 |
| `CAPABILITY_NOT_DECLARED` | 否 | 调用了 Agent 未声明的能力 |
| `CAPABILITY_UNAVAILABLE` | 否 | 没有 Agent 提供该能力 |
| `AGENT_NOT_ENABLED` | 否 | Agent 被配置禁用 |
| `AGENT_NOT_REGISTERED` | 否 | 名称不在白名单 |
| `TOOL_NOT_ALLOWED` | 否 | 调用了未授权工具 |
| `PERMISSION_DENIED` | 否 | 调用方缺少业务数据权限 |
| `DEADLINE_EXCEEDED` | 否 | 上游给定的时限已过 |
| `TIMEOUT` | **是** | 单次执行超时 |
| `MODEL_ERROR` | **是** | 模型调用失败 |
| `UPSTREAM_ERROR` | **是** | 外部依赖失败 |
| `NOT_IMPLEMENTED` | 否 | 骨架阶段占位 |
| `INTERNAL_ERROR` | 否 | 未捕获异常 |

### 8.2 分层兜底

```text
Agent 内部异常
  └─ BaseAgent 捕获 → FAILED + ErrorDetail（工作流继续）
       └─ Coordinator 汇总 → PARTIAL / FAILED
            └─ API 层 → 明确的 HTTP 错误 + trace_id
```

任何一层都不允许「吞掉错误继续假装成功」。

### 8.3 可观测性字段

每条日志固定包含：`agent_name`、`agent_version`、`model_provider`、`model_name`、`trace_id`、`tenant_id`、`attempt`、`latency_ms`，失败时额外带 `error_code`。`AgentResult.metadata` 中另有 `token_usage`（模型返回时）与 `started_at` / `finished_at`。

---

## 9. 如何新增 / 禁用 / 替换 Agent

详细步骤见 [agent_development_guide.md](./agent_development_guide.md)，此处给出结论：

| 操作 | 需要改什么 | 不需要改什么 |
|---|---|---|
| **新增 Agent** | ① 新建 `agents/<name>/agent.py` + `prompts/`；② 新建 `config/agents/<name>.yaml`；③ 在 `factory.AGENT_IMPLEMENTATIONS` 加一行 | 其他 Agent、Coordinator、Registry、契约 |
| **禁用 Agent** | 仅改 YAML：`enabled: false` | 任何代码 |
| **删除 Agent** | 删 `agents/<name>/`、删 YAML、删白名单一行 | 其他 Agent、Coordinator |
| **替换实现** | 改白名单指向新类 | 其他 Agent、配置、Coordinator |
| **换模型** | 仅改 YAML 的 `model_provider` / `model_name` / `temperature` | 任何代码 |
| **改 Prompt** | 仅改 `prompts/system.md` | 任何代码、其他 Agent |
| **改工具权限** | 仅改 YAML 的 `allowed_tools` | 任何代码 |

---

## 10. 已知风险与未决问题

| # | 风险 | 影响 | 当前缓解 | 待办 |
|---|---|---|---|---|
| 1 | 能力字符串无编译期校验 | 拼错 capability 只会在运行时报错 | 正则格式校验 + 自检覆盖 | 阶段 4 引入配置级静态检查 |
| 2 | `factory` 白名单是新 Agent 的唯一登记点 | 忘记登记时配置被静默跳过 | `build_registry(strict=True)` 可强制报错 | 启动时使用 `strict=True` |
| 3 | 同能力冲突采用「宁可失败」策略 | 多 Agent 协作场景可能需要路由 | 显式 `replace=True` 可覆盖 | 阶段 4 评估是否需要 `capability → 多 Agent` 路由 |
| 4 | 未接入 LangGraph | State 的 reducer 目前只是类型声明 | 已按 LangGraph 语义定义 | 阶段 4 引入后补集成测试 |
| 5 | 版本兼容性目前只有字段级约束 | 跨版本 State 变更可能破坏在途流程 | `agent_version` 已进日志与结果元数据 | 阶段 4 设计 checkpointer 版本迁移策略 |
| 6 | 并发合并策略未经过真实并发验证 | 追加式 reducer 的理论正确性未实测 | 策略已文档化 | 阶段 4 补并发写入测试 |
| 7 | 多租户字段尚未落到数据库 | `tenant_id` 已在 context 中传递 | 契约已预留 | 阶段 2 建表前必须定 |

---

## 11. 变更历史

| 日期 | 任务 | 变更 |
|---|---|---|
| 2026-11-03 | 003 | 初版：确立四层架构、接口契约、Registry、配置机制、编排分工与降级策略 |
