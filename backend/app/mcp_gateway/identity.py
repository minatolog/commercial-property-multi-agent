"""MCP 会话身份（Task 033A，开发模式）。

本版本只有 **stdio + 开发主体**：主体来自客户端档案的 `principal_id`，
环境变量 `DEMO_PRINCIPAL_ID` 非空时覆盖它，并且 `SessionIdentity.source`
如实记录主体来自哪里（`profile` / `env:DEMO_PRINCIPAL_ID`）。

安全边界：
- `AgentContext` 只能由 `resolve_context(session)` 从会话身份构造，
  **绝不从 tools/call 的调用参数读取**；
- 本版本没有令牌校验，也不会假装有——启动时应向 stderr 打印
  `DEV_MODE_WARNING`，让使用者清楚这不是生产身份。

下一版（Streamable HTTP + OAuth）要替换的是 `create_session` 里
"信任档案/环境变量"这一步：从**已验证的 OAuth 令牌**解析主体声明，
映射到 fixture 的主体记录，再构造 `SessionIdentity`。`resolve_context`
本身不需要改：它只消费"已经过认证的会话身份"。
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from ..agents.base.contracts import AgentContext
from ..fixtures.repository import FixtureRepository
from ..runtime.types import TrustedContext

if TYPE_CHECKING:  # 仅类型标注，避免身份模块反向依赖档案加载
    from .profiles import ClientProfile

__all__ = [
    "DEMO_PRINCIPAL_ENV",
    "DEV_MODE_WARNING",
    "SOURCE_PROFILE",
    "SessionIdentity",
    "create_session",
    "resolve_context",
]

#: 覆盖开发主体的环境变量名。
DEMO_PRINCIPAL_ENV = "DEMO_PRINCIPAL_ID"

#: 主体来源：来自客户端档案。
SOURCE_PROFILE = "profile"

#: 开发模式警示（Task 033B 在启动时打印到 stderr）。
DEV_MODE_WARNING = "开发模式：固定主体，不可用于生产"


class SessionIdentity(BaseModel):
    """一次 MCP 会话的身份快照（不含任何令牌材料）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    #: 主体来源，如实记录：`profile` 或 `env:DEMO_PRINCIPAL_ID`
    source: str = Field(min_length=1)


def create_session(
    profile: "ClientProfile",
    *,
    environ: Mapping[str, str] | None = None,
) -> SessionIdentity:
    """为一次 MCP 会话生成身份。

    `environ` 默认取 `os.environ`；测试可显式传入以隔离进程环境。
    空白的 `DEMO_PRINCIPAL_ID` 视为未设置（不覆盖档案主体）。
    """

    environment = os.environ if environ is None else environ
    override = (environment.get(DEMO_PRINCIPAL_ENV) or "").strip()
    if override:
        principal_id = override
        source = f"env:{DEMO_PRINCIPAL_ENV}"
    else:
        principal_id = profile.principal_id
        source = SOURCE_PROFILE

    return SessionIdentity(
        session_id=f"mcp_{profile.name}_{uuid.uuid4().hex[:12]}",
        client_name=profile.name,
        principal_id=principal_id,
        source=source,
    )


def resolve_context(
    session: SessionIdentity,
    *,
    repository: FixtureRepository | None = None,
) -> AgentContext:
    """会话身份 → 可信 `AgentContext`。

    只读取会话身份与**服务端**主体记录：

    - `project_ids` / `permissions` 来自 fixture 主体记录，不来自任何调用参数；
    - `run_id` 记为 MCP 会话 ID，便于在 Trace 中把同会话的调用归到一起；
    - `trace_id` 每次调用重新生成，保证单次调用可独立追踪。

    `repository` 仅用于测试注入；生产路径从 fixture 装载。
    """

    repo = FixtureRepository.load() if repository is None else repository
    principal = repo.principal(session.principal_id)
    trusted = TrustedContext.from_principal(
        principal,
        trace_id=f"trace_{session.session_id}_{uuid.uuid4().hex[:8]}",
    )
    return trusted.to_agent_context(run_id=session.session_id)
