"""单 Agent + Tools 演示装配（Task 008）。

把"配置 → 模型客户端 → 工具 → Agent → Runtime"的接线集中在一处：

- `provider="fake"`：脚本化模型，零网络，用于测试与离线演示；
- `provider="deepseek"`：真实 LangChain/DeepSeek 客户端，需要 `DEEPSEEK_API_KEY`。

**这只证明工具调用闭环接通了**。Fake 路径不产生任何模型质量结论；
真实路径是否成功必须以实际调用结果为准。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from .agents.base import AgentRequest
from .agents.base.registry import AgentRegistry
from .agents.single.agent import SingleToolAgent
from .config.loader import load_agent_config
from .fixtures.repository import FixtureRepository
from .llm.model_client import ChatModelClient, FakeChatModelClient, ModelToolCall, ModelTurn
from .paths import CONFIG_DIR
from .runtime.agent_runtime import AgentRuntime
from .runtime.budget import Budget
from .runtime.types import TraceLog, TrustedContext
from .tools.fixture_tools import build_fixture_tools
from .tools.registry import ToolRegistry

__all__ = [
    "SINGLE_CAPABILITY",
    "SingleBundle",
    "build_fake_script",
    "build_single_bundle",
    "run_single",
]

SINGLE_CAPABILITY = "single.investigate"


def build_fake_script(lease_id: str = "lease_xh_a301_2025") -> tuple[ModelTurn, ...]:
    """默认离线脚本：先查欠费，再基于工具结果作答。

    刻意让"最终答案"包含工具返回值中的关键金额，用来断言工具结果确实回传给了模型。
    """

    return (
        ModelTurn(
            text="",
            tool_calls=(
                ModelToolCall(
                    call_id="call_fake_1",
                    name="billing.arrears.calculate",
                    arguments={"lease_id": lease_id},
                    arguments_json=json.dumps({"lease_id": lease_id}),
                ),
            ),
        ),
        ModelTurn(
            text="根据账务工具结果，该租约未收金额见 outstanding_total。",
        ),
    )


@dataclass
class SingleBundle:
    repository: FixtureRepository
    tool_registry: ToolRegistry
    budget: Budget
    trace_log: TraceLog
    registry: AgentRegistry
    agent: SingleToolAgent
    runtime: AgentRuntime
    trusted: TrustedContext
    request: AgentRequest
    model_client: ChatModelClient


def build_single_bundle(
    *,
    question: str,
    principal_id: str = "principal_ops_xinghui",
    variant: str | None = None,
    provider: str = "fake",
    fake_script: Iterable[ModelTurn] | None = None,
    max_tool_calls: int = 8,
    max_model_calls: int = 6,
    max_total_tokens: int = 20000,
    config_path: str | None = None,
) -> SingleBundle:
    repository = FixtureRepository.load(None, variant=variant)

    tool_registry = ToolRegistry()
    for tool in build_fixture_tools(repository):
        tool_registry.register(tool)

    budget = Budget(
        max_tool_calls=max_tool_calls,
        max_model_calls=max_model_calls,
        max_total_tokens=max_total_tokens,
    )
    trace_log = TraceLog()

    config_file = config_path or (CONFIG_DIR / "single.yaml")
    config = load_agent_config(config_file)

    model_client = _build_model_client(provider, config, fake_script)

    agent = SingleToolAgent(
        config,
        model_client=model_client,
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
    )
    registry = AgentRegistry()
    registry.register(agent)

    runtime = AgentRuntime(registry, budget, trace_log=trace_log)
    principal = repository.principal(principal_id)
    trusted = TrustedContext.from_principal(
        principal, trace_id=f"trace_{uuid.uuid4().hex[:12]}"
    )
    request = AgentRequest(
        task_id="task-single",
        capability=SINGLE_CAPABILITY,
        payload={"question": question},
    )
    return SingleBundle(
        repository=repository,
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
        registry=registry,
        agent=agent,
        runtime=runtime,
        trusted=trusted,
        request=request,
        model_client=model_client,
    )


async def run_single(bundle: SingleBundle) -> Any:
    return await bundle.runtime.run(bundle.request, bundle.trusted)


def _build_model_client(
    provider: str,
    config: Any,
    fake_script: Iterable[ModelTurn] | None,
) -> ChatModelClient:
    if provider == "fake":
        script = tuple(fake_script) if fake_script is not None else build_fake_script()
        return FakeChatModelClient(script)
    if provider == "deepseek":
        from .llm.langchain_client import build_chat_client

        return build_chat_client(config)
    raise ValueError(f"未知 provider: {provider!r}（可选 fake / deepseek）")
