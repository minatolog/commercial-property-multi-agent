"""MCP 客户端档案（Task 033A）。

档案回答三个问题：**谁**（开发模式下的固定主体）、**能调哪些只读工具**、
**一个会话最多调几次**。安全边界如下：

- `extra="forbid"`：档案里多写一个字段（例如 `api_key`）在加载期直接失败，
  不会留下"看起来生效、实际被忽略"的配置；
- **只读白名单**：本版本只允许 `READ_ONLY_TOOLS` 中的 5 个只读工具。
  即使将来注册了写工具，档案列出它也会被拒绝——防止"注册写工具时顺手暴露"；
- 白名单只收紧、不放宽：`to_agent_config` 原样搬运 `allowed_tools`，不追加任何工具。

档案的职责只是**选择**：真正执行白名单、权限、预算与校验的是既有 `ToolExecutor`。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..agents.base.errors import AgentConfigError
from ..config.schema import AgentConfig
from ..paths import BACKEND_ROOT
from ..tools.registry import ToolRegistry

__all__ = [
    "MCP_CLIENTS_DIR",
    "READ_ONLY_TOOLS",
    "ClientProfile",
    "SessionBudget",
    "load_profile",
    "to_agent_config",
]

#: 客户端档案目录（相对路径解析统一以 `backend/` 为基准，见 `app.paths`）。
MCP_CLIENTS_DIR: Path = BACKEND_ROOT / "app" / "config" / "mcp_clients"

#: **本版本唯一允许开放的工具集合**：全部只读。
#: 与注册表无关——注册表里出现写工具时，档案列出它仍会被拒绝。
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "lease.lookup",
        "billing.statement.read",
        "billing.arrears.calculate",
        "property.work_orders.read",
        "document.search",
    }
)

#: 档案名同时用作文件名，因此只接受小写字母、数字与下划线（与 `AgentConfig.name` 一致）。
_PROFILE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

#: 网关不运行 LLM Agent，这些字段对执行器没有意义；用固定占位值，
#: 保证任何人误把档案配置当模型配置使用时也不会真的去构造模型客户端。
_PLACEHOLDER_VERSION = "1.0.0"
_PLACEHOLDER_CAPABILITY = "mcp.gateway"
_PLACEHOLDER_MODEL_PROVIDER = "offline"
_PLACEHOLDER_MODEL_NAME = "none"
_PLACEHOLDER_PROMPT_PATH = "app/agents/single/prompts/system.md"


class SessionBudget(BaseModel):
    """单个 MCP 会话的工具调用额度。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tool_calls_per_session: int = Field(gt=0)


class ClientProfile(BaseModel):
    """一个 MCP 客户端档案的强类型表示。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)
    enabled: bool
    principal_id: str = Field(min_length=1)
    allowed_tools: tuple[str, ...] = Field(min_length=1)
    budget: SessionBudget

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError("allowed_tools 不允许空字符串")
        if len(set(value)) != len(value):
            duplicates = sorted({item for item in value if value.count(item) > 1})
            raise ValueError(f"allowed_tools 存在重复项: {duplicates}")
        return value


def load_profile(
    name: str,
    *,
    registry: ToolRegistry,
    config_dir: str | Path | None = None,
) -> ClientProfile:
    """读取并校验客户端档案；任何一项不合法都在启动期失败。

    校验顺序：文件名/档案名 → YAML 结构 → 字段 Schema → 是否启用 →
    工具是否已注册 → 工具是否只读。错误信息一律带上档案名与具体项，
    避免"启动失败但不知道是哪个档案的哪一行"。
    """

    if len(name) > 32 or not _PROFILE_NAME_PATTERN.match(name):
        raise AgentConfigError(
            f"客户端档案名非法: {name!r}"
            "（只允许小写字母、数字和下划线，以字母开头，最长 32 个字符）"
        )

    directory = Path(config_dir) if config_dir is not None else MCP_CLIENTS_DIR
    path = directory / f"{name}.yaml"
    if not path.is_file():
        raise AgentConfigError(f"客户端档案不存在: {name!r}（期望文件 {path}）")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentConfigError(f"客户端档案 {name!r} 的 YAML 解析失败: {path}: {exc}") from exc

    if raw is None:
        raise AgentConfigError(f"客户端档案 {name!r} 为空: {path}")
    if not isinstance(raw, dict):
        raise AgentConfigError(f"客户端档案 {name!r} 顶层必须是 mapping: {path}")

    try:
        profile = ClientProfile.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise AgentConfigError(f"客户端档案 {name!r} 校验失败: {details}") from exc

    if profile.name != name:
        raise AgentConfigError(
            f"客户端档案文件名与 name 不一致: {path.name} 的 name 为 {profile.name!r}"
        )
    if not profile.enabled:
        raise AgentConfigError(f"客户端档案 {name!r} 已被禁用（enabled: false）")

    registered = set(registry.names())
    unregistered = [item for item in profile.allowed_tools if item not in registered]
    if unregistered:
        raise AgentConfigError(
            f"客户端档案 {name!r} 列出未注册的工具: {unregistered}；"
            f"当前已注册: {sorted(registered)}"
        )

    non_read_only = [item for item in profile.allowed_tools if item not in READ_ONLY_TOOLS]
    if non_read_only:
        raise AgentConfigError(
            f"客户端档案 {name!r} 试图开放非只读工具: {non_read_only}；"
            f"本版本只允许 {sorted(READ_ONLY_TOOLS)}"
        )

    return profile


def to_agent_config(profile: ClientProfile) -> AgentConfig:
    """档案 → 执行器需要的 `AgentConfig`。

    只做转换：`allowed_tools` 原样搬运，**不追加、不放宽**。
    `capabilities` / 模型字段对网关没有意义（网关不运行 Agent、不调用模型），
    但 `AgentConfig` 要求它们必填，因此填固定占位值；执行器只读取白名单与名称。
    """

    return AgentConfig(
        name=profile.name,
        version=_PLACEHOLDER_VERSION,
        description=f"MCP client profile {profile.name}",
        capabilities=(_PLACEHOLDER_CAPABILITY,),
        model_provider=_PLACEHOLDER_MODEL_PROVIDER,
        model_name=_PLACEHOLDER_MODEL_NAME,
        prompt_path=_PLACEHOLDER_PROMPT_PATH,
        allowed_tools=profile.allowed_tools,
    )
