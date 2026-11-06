# Agent 开发指南

> **状态**：生效（阶段 0 起强制执行）
> **最后更新**：2026-11-03
> **关联任务**：003
> **配套文档**：[agent_architecture.md](./agent_architecture.md)

本文档是新增、修改、禁用 Agent 的唯一标准流程。**与本指南冲突的写法一律不合并。**

---

## 0. 十条硬规则

1. 业务 Agent **不得** import 其他 Agent 的实现模块。
2. Coordinator **不得** import 任何具体 Agent。
3. 只有 `app/agents/factory.py` 可以 import 具体 Agent。
4. Agent **不得**自己构造 `AgentResult`，只返回 `AgentOutput`。
5. Agent **不得**读取 `os.environ` 取密钥，必须经由模型适配层。
6. Agent **不得**自行调用未在 `allowed_tools` 中声明的工具。
7. 确定性计算（金额、账期、规则判定）写在 `app/tools/`，**不得**交给 LLM 生成。
8. Prompt 必须放在 `agents/<name>/prompts/`，**不得**内联在 Python 字符串里。
9. 禁止 `importlib.import_module(config.name)` 之类的动态导入。
10. 修改 `agents/base/contracts.py` 视为破坏性变更，必须同步回归全部 Agent。

---

## 1. 新增一个 Agent

以新增 `risk`（风险评估）为例，共 4 步。

### 步骤 1：声明模块目录

```text
backend/app/agents/risk/
├── __init__.py
├── agent.py
└── prompts/
    └── system.md
```

### 步骤 2：实现 Agent

```python
from __future__ import annotations

from ..base import AgentContext, AgentOutput, AgentRequest, BaseAgent
from ..base.errors import AgentError, ErrorCode


class RiskAgent(BaseAgent):
    name = "risk"
    version = "0.1.0"
    description = "租约风险评估"
    capabilities = frozenset({"risk.assess"})

    async def _execute(
        self, request: AgentRequest, context: AgentContext
    ) -> AgentOutput:
        # 1) 需要业务数据时，调用 tools（先确认 allowed_tools 已授权）
        # 2) 需要检索时，使用 config.retrieval_settings 的参数
        # 3) 需要 Prompt 时，读取 self.prompt_text
        # 4) 需要模型时，通过适配层拿到参数后调用
        return AgentOutput(data={"risk_level": "low"}, warnings=())
```

注意：

- 类属性 `name` / `version` / `capabilities` / `description` 必填（`name` 与 `capabilities` 缺失会在实例化时抛 `IncompatibleAgentError`）。
- `capability` 必须是 `<domain>.<action>`，全小写。
- **不要**写 `try/except` 包裹全部逻辑然后返回空结果。抛 `AgentError` 即可，`BaseAgent` 会统一转换成 `FAILED` 结果并记录日志。

### 步骤 3：写配置

`backend/app/config/agents/risk.yaml`（文件名必须等于 `name`）：

```yaml
name: risk
version: 0.1.0
enabled: true
description: 租约风险评估

capabilities:
  - risk.assess

model_provider: deepseek
model_name: deepseek-chat
temperature: 0.1
max_tokens: 2048
api_key_env: DEEPSEEK_API_KEY

timeout_seconds: 30
max_retries: 1
prompt_path: app/agents/risk/prompts/system.md

allowed_tools:
  - lease.lookup

retrieval_settings:
  enabled: true
  top_k: 5
  rerank_top_n: 3

log_level: INFO
```

### 步骤 4：登记白名单

`backend/app/agents/factory.py`：

```python
from .risk.agent import RiskAgent

AGENT_IMPLEMENTATIONS: Final[dict[str, type[BaseAgent]]] = {
    "lease": LeaseAgent,
    "billing": BillingAgent,
    "compliance": ComplianceAgent,
    "risk": RiskAgent,          # ← 新增这一行
}
```

**这一步不可省略。** 忘记登记时，`build_registry()` 会跳过该配置并计入 `skipped`；使用 `build_registry(strict=True)` 可直接报错，建议在正式启动流程中启用 strict。

### 步骤 5：验证

```powershell
python backend/tests/smoke_agent_contracts.py
```

再确认三件事：

- `registry.available_capabilities()` 中出现新能力。
- `check_plan_feasibility()` 对新能力返回 `available`。
- 原有 Agent 的自检全部仍通过。

---

## 2. 禁用 / 启用一个 Agent

**只改 YAML，不改代码。**

```yaml
enabled: false
```

效果：

- `available_capabilities()` 不再包含它的能力。
- `disabled_capabilities()` 会列出这些能力。
- 直接调用 `agent.handle()` 返回 `FAILED` + `AGENT_NOT_ENABLED`。
- `registry.require_capability()` 抛 `AgentDisabledError`（与「能力不存在」可区分）。
- Registry 中仍保留该 Agent，因此上面两条能给出**明确原因**而不是含糊的「能力不存在」。

---

## 3. 删除一个 Agent

1. 删除 `backend/app/agents/<name>/`。
2. 删除 `backend/app/config/agents/<name>.yaml`。
3. 删除 `factory.py` 中对应的一行。
4. 全仓搜索该能力的引用，确认没有 SubTask/文档依赖它。

> 若该能力仍被某个工作流使用，`check_plan_feasibility()` 会把它归入 `missing`，任务会按 `CoordinatorPolicy` 降级或失败。这属于预期行为，不是 bug。

---

## 4. 替换一个 Agent 的实现

保持 `name`、`capabilities`、`version` 语义不变的前提下：

```python
AGENT_IMPLEMENTATIONS = {
    "lease": LeaseAgentV2,   # 指向新实现
}
```

要求：

- 新实现必须满足 `AgentProtocol`（`descriptor` / `supports` / `handle`）。
- 输入输出必须仍是 `AgentRequest` / `AgentContext` → `AgentResult`。
- **升级 `version`**，否则日志和结果元数据无法区分新旧实现。
- 跑该 Agent 的独立测试 + 相关跨 Agent 回归测试。

如果不满足接口，Registry 会抛 `IncompatibleAgentError`，启动即失败。

---

## 5. 调整单个 Agent 的性能与成本

全部通过 YAML，无需改代码：

| 目标 | 改哪个字段 |
|---|---|
| 换 LLM | `model_provider` + `model_name` |
| 换 Prompt | `prompt_path`（或直接改 Prompt 文件） |
| 增减工具 | `allowed_tools` |
| 调超时 / 重试 | `timeout_seconds` / `max_retries` |
| 调 RAG 检索 | `retrieval_settings`（`top_k` / `rerank_top_n` / 权重） |
| 降日志噪音 | `log_level` |

**改完必须做的两件事**：

1. 只跑该 Agent 的独立测试（不需要启动完整系统）。
2. 跑涉及该 Agent 的跨 Agent 回归测试。

---

## 6. 编写测试

### 6.1 独立测试（不需要完整系统）

```python
from app.agents.factory import build_agent
from app.config.loader import load_agent_config

def test_risk_agent_returns_level():
    config = load_agent_config("app/config/agents/risk.yaml")
    agent = build_agent(config)
    assert agent.supports("risk.assess")
```

### 6.2 契约测试（每个 Agent 必做）

| 检查 | 期望 |
|---|---|
| 调用未声明能力 | `CAPABILITY_NOT_DECLARED` |
| `enabled: false` 时调用 | `AGENT_NOT_ENABLED` |
| 返回结果含 `metadata.agent_name` / `agent_version` | 是 |
| 返回结果含 `metadata.trace_id` | 是 |
| 内部抛异常 | 转换为 `FAILED`，不向上抛 |
| `prompt_text` 可加载 | 是 |

### 6.3 阶段 0 自检脚本

```powershell
python backend/tests/smoke_agent_contracts.py
```

覆盖配置校验、Registry、错误约定、Prompt 隔离、工具授权、模型参数裁剪、计划可行性、工厂白名单，共 57 项。**任何改动后必须保持全绿。**

---

## 7. 编写 Prompt

位置：`agents/<name>/prompts/system.md`。

必须写清四段：

1. **职责范围** —— 这个 Agent 负责什么。
2. **边界** —— 不做什么，什么必须转人工。
3. **数据来源** —— 金额/日期必须来自工具，不得自行推算。
4. **输出格式** —— 结论优先，依据在后。

禁止事项：

- 不要在 Prompt 里写死具体金额、具体租户等业务数据。
- 不要在 Prompt 中要求模型「自行计算」合计、利息、滞纳金。
- 不要把多个 Agent 的职责塞进同一个 Prompt。

---

## 8. 编写工具

位置：`backend/app/tools/`。

```python
from typing import Any, ClassVar
from ..agents.base.contracts import AgentContext

class LeaseLookupTool:
    name: ClassVar[str] = "lease.lookup"
    description: ClassVar[str] = "按租约编号查询租约条款"
    required_permissions: ClassVar[frozenset[str]] = frozenset({"lease.read"})

    async def invoke(self, payload: dict[str, Any], context: AgentContext) -> dict[str, Any]:
        ...
```

要求：

- 纯确定性逻辑，**不调用 LLM**。
- 声明 `required_permissions`，由 `assert_tool_invocable()` 统一校验工具授权 + 业务权限。
- 工具名带上领域前缀（`lease.` / `billing.`），与 capability 命名风格一致。

调用前必须先过校验：

```python
assert_tool_invocable(self.config, tool, context)
result = await tool.invoke(payload, context)
```

---

## 9. 共享 State 的使用规范

- 只往 `WorkflowState` 放**跨节点**需要的数据。
- Agent 内部中间变量一律局部，不进 State。
- 新增可并发更新的字段时，必须配 `Annotated[..., reducer]`，否则并发写入会抛冲突（这是保护，不是缺陷）。
- `results` 存 `AgentResult.model_dump(mode="json")`，不存对象。
- 同一 `subtask_id` 的去重必须在聚合节点显式实现，不要指望 reducer。

---

## 10. 数据访问规则（任务 004 起强制）

Agent **不得**直接访问数据库。数据访问必须经四层，依赖方向单向向下：

```text
Agent  →  Tool  →  Service  →  Repository  →  SQLAlchemy Model
```

| 层 | 职责 | 禁止 |
|---|---|---|
| Tool | 单个确定性业务操作，校验 `allowed_tools` + `permissions` | 含复杂事务、跨多表聚合 |
| Service | 事务边界、业务规则、跨表聚合、DTO 转换 | 被 Agent 绕过 |
| Repository | 单表读写、查询构造 | `commit()`、业务判断 |
| Model | 表映射 | 被 Agent / Tool 直接 import |

**五条硬规则**（补入第 0 节）：

11. Agent **不得** import `app.db.models` 或 `app.db.repositories`。
12. Agent **不得**持有 `Session`，不得写 SQL。
13. Tool 返回 **Pydantic DTO**，不返回 ORM 实例。
14. Service 是事务边界的唯一所有者；Repository 不 `commit()`。
15. 跨表聚合（余额、逾期、占用状态）只在 Service 或数据库视图中实现。

**为什么不能直接拿 ORM 实例**：ORM 实例带懒加载关系（如 `lease.lease_units[0].unit.code`），一旦加载策略或表结构变化，Agent 会静默崩坏。DTO 把对外形状变成显式契约，改动必然触发评审。

参考：[database_design.md](./database_design.md) 第 11 章。

---

## 11. 提交前检查清单

- [ ] `name` 与 YAML 文件名一致
- [ ] `capabilities` 符合 `<domain>.<action>`
- [ ] 已在 `AGENT_IMPLEMENTATIONS` 登记
- [ ] Prompt 放在 `prompts/` 且 `prompt_path` 正确
- [ ] `allowed_tools` 最小授权（不要图省事全给）
- [ ] YAML 中没有 `api_key` / `password` / `token` 等字段
- [ ] 密钥只通过 `api_key_env` 引用环境变量
- [ ] 没有 import 其他 Agent 的实现
- [ ] 没有 import `app.db.models` / `app.db.repositories`，没有写 SQL
- [ ] 数据访问经 Tool → Service，且 Tool 返回 DTO 而非 ORM 实例
- [ ] 没有自己构造 `AgentResult`
- [ ] `python backend/tests/smoke_agent_contracts.py` 全绿
- [ ] 已在 `docs/prompts/<模块>/` 归档本次任务 Prompt
- [ ] 已更新 `development_log.md`

---

## 12. 常见错误速查

| 报错 | 原因 | 处理 |
|---|---|---|
| `IncompatibleAgentError` | 缺 `name` / `capabilities`，或对象不是 `BaseAgent` | 补齐类属性 |
| `DuplicateAgentError` | 同名重复注册 | 检查是否重复构造；确需覆盖用 `replace=True` |
| `CapabilityConflictError` | 两个 Agent 声明同一能力 | 合并职责或改用不同 capability |
| `AgentNotRegisteredError` | 忘记登记白名单，或 `strict=True` 下配置无实现 | 在 `AGENT_IMPLEMENTATIONS` 补一行 |
| `AgentConfigError` + `Extra inputs are not permitted` | YAML 写了未定义字段（常见于写 `api_key`） | 改用 `api_key_env` |
| `AgentConfigError` + 文件名与 name 不一致 | 复制配置后忘改 `name` | 让两者一致 |
| `PromptPathError` | `prompt_path` 指向不存在的文件 | 校对相对 `backend/` 的路径 |
| `ToolNotAllowedError` | 调了未在 `allowed_tools` 中的工具 | 补进 YAML 或改用已授权工具 |
| `PermissionDeniedError` | 调用方 `context.permissions` 不足 | 由上游注入正确权限，不要在工具内部绕过 |
| `MissingApiKeyError` | 环境变量未设置 | 设置 `DEEPSEEK_API_KEY`，不要写进 YAML |
