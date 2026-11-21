"""单 Agent + Tools 演示装配（Task 008 / Task 031 目标装配）。

把"配置 → 模型客户端 → 工具 → Agent → Runtime"的接线集中在一处：

- `provider="fake"`：固定脚本的 Fake 模型，零网络（历史测试与离线演示）；
- `provider="scripted"`：`ScriptedToolModel`，按问题涉及领域自动生成"先调工具、再总结"
  的两轮脚本（`ask` 的默认来源；只证明装配接好了，不代表模型质量）；
- `provider="deepseek"`：真实 LangChain/DeepSeek 客户端，需要 `DEEPSEEK_API_KEY`。

**Task 031 / Z1：`ask` 必须携带可信目标。** 目标（租约/商铺）由本模块的
`resolve_ask_target()` 从可信来源解析，并注入 `AgentRequest.payload`；`SingleToolAgent`
再通过 `TaskScope` 在工具调用边界强制执行，因此模型既不能更换目标、也不能省略目标。
解析结果与来源记录在 `SingleBundle.target` 中，供报告审计（不是模型说了算）。

**这不是模型质量证据。** Fake/scripted 路径不产生任何模型结论；deepseek 路径是否
成功必须看实际调用结果。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from .agents.base import AgentRequest
from .agents.base.errors import AgentError, ErrorCode
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
    "AskTarget",
    "SINGLE_CAPABILITY",
    "SingleBundle",
    "TargetResolutionError",
    "build_fake_script",
    "build_single_bundle",
    "resolve_ask_target",
    "run_single",
]

SINGLE_CAPABILITY = "single.investigate"

#: 从自然语言里识别商铺编号：`A-301` / `A301` / `a 301`。只认"字母 + 三位数字"，
#: 因此日期（2026-11-07）、条款号（5.2.1）与评测题号（H01）不会被误认为商铺。
_UNIT_CODE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z])\s*[-－]?\s*(\d{3})(?![0-9])")

#: 从问题领域推断的脚本化工具计划：领域 → 一次只读取数。
#: 参数留空，由 `TaskScope` 注入本次可信目标（省略目标也算注入，不是"不限"）。
_SCRIPTED_PLAN: dict[str, tuple[str, dict[str, Any]]] = {
    "lease": ("lease.lookup", {}),
    "billing": ("billing.statement.read", {}),
    "property": ("property.work_orders.read", {}),
}


class TargetResolutionError(AgentError):
    """`ask` 无法确定可信目标（属于用法错误，CLI 退出码 2）。"""

    default_code = ErrorCode.INVALID_REQUEST


@dataclass(frozen=True)
class AskTarget:
    """一次 `ask` 的可信目标解析结果（只由装配层产生，模型无法修改）。"""

    lease_id: str | None = None
    unit_id: str | None = None
    unit_code: str | None = None
    #: `cli_flag`（显式 --lease/--unit）| `question_parse`（问题文本里的商铺编号）| `none`
    source: str = "none"
    #: 问题是否表达了业务取数意图（词表命中的领域）；用于"不能无声落到 explain"
    business_domains: tuple[str, ...] = ()
    matched_words: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def targeted(self) -> bool:
        return bool(self.lease_id or self.unit_id)

    def describe(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "unit_id": self.unit_id,
            "unit_code": self.unit_code,
            "source": self.source,
            "mode": "targeted" if self.targeted else "explain",
            "business_domains": list(self.business_domains),
            "matched_words": {
                domain: list(words) for domain, words in self.matched_words.items()
            },
        }


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
    #: Task 031 / Z1：本次可信目标与来源（审计用，不是模型输出）
    target: dict[str, Any] = field(default_factory=dict)
    #: 身份来源：`cli_flag`（命令行自报）| `env:DEMO_PRINCIPAL_ID` | `demo_default`
    identity_source: str = "demo_default"


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
    lease_id: str | None = None,
    unit_id: str | None = None,
    resolve_target: bool = False,
    identity_source: str = "demo_default",
) -> SingleBundle:
    """装配单 Agent 问答。

    `resolve_target=True` 是 `ask` CLI 的入口语义（Task 031 / Z1）：

    - 显式 `--lease` / `--unit` 优先，并做权限范围校验；
    - 否则从问题文本里的商铺编号解析（`A-301` / `A301`）；
    - 有业务取数意图却没有任何可信目标 → 直接失败（用法错误），
      **不能**把业务问题静默降级成纯说明；
    - 纯说明问题（没有业务领域词）允许无目标执行（`explain` 形态）。

    默认 `resolve_target=False` 保持旧调用方的语义（测试/演示直接构造 bundle）。
    """

    repository = FixtureRepository.load(None, variant=variant)
    principal = repository.principal(principal_id)

    target: AskTarget
    if resolve_target:
        target = resolve_ask_target(
            repository,
            principal,
            question=question,
            lease_id=lease_id,
            unit_id=unit_id,
        )
    else:
        target = AskTarget(
            lease_id=lease_id,
            unit_id=unit_id,
            unit_code=None,
            source="explicit" if (lease_id or unit_id) else "none",
        )

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

    model_client = _build_model_client(
        provider,
        config,
        fake_script,
        scripted_calls=_scripted_plan(question) if provider == "scripted" else (),
    )

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
    trusted = TrustedContext.from_principal(
        principal, trace_id=f"trace_{uuid.uuid4().hex[:12]}"
    )
    payload: dict[str, Any] = {"question": question}
    # 目标只从这里（可信装配层）进入 payload；模型输出永远不会回写目标。
    if target.lease_id:
        payload["lease_id"] = target.lease_id
    if target.unit_id:
        payload["unit_id"] = target.unit_id
    request = AgentRequest(
        task_id="task-single",
        capability=SINGLE_CAPABILITY,
        payload=payload,
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
        target=target.describe(),
        identity_source=identity_source,
    )


async def run_single(bundle: SingleBundle) -> Any:
    return await bundle.runtime.run(bundle.request, bundle.trusted)


# ---------------------------------------------------------------- 可信目标解析（Z1）


def resolve_ask_target(
    repository: FixtureRepository,
    principal: dict[str, Any],
    *,
    question: str,
    lease_id: str | None = None,
    unit_id: str | None = None,
) -> AskTarget:
    """解析 `ask` 的可信目标，返回 (租约, 商铺, 来源)。

    只从"命令行显式参数"和"问题文本里的商铺编号"两个确定来源取值；
    两者都经过 fixture 的**项目范围校验**，越权/不存在一律明确失败。
    """

    project_ids = frozenset(principal.get("project_ids") or ())
    question = str(question or "")

    explicit = _explicit_target(repository, project_ids, lease_id=lease_id, unit_id=unit_id)
    parsed, unresolved = _question_target(repository, project_ids, question)
    if len(parsed) > 1:
        raise TargetResolutionError(
            "问题中出现多个可访问的商铺编号 "
            f"{[item['unit_code'] for item in parsed.values()]}；请用 --lease/--unit 明确目标"
        )

    question_target = next(iter(parsed.values())) if parsed else None
    if explicit is not None and question_target is not None:
        if explicit["lease_id"] != question_target["lease_id"]:
            raise TargetResolutionError(
                "命令行目标与问题文本不一致："
                f"--lease/--unit 指向 {explicit['lease_id']}，"
                f"问题里写的是 {question_target['unit_code']}（{question_target['lease_id']}）；"
                "请确认后再执行"
            )
    if explicit is None and question_target is None and unresolved and not parsed:
        raise TargetResolutionError(
            "问题中的商铺编号无法解析为可访问的租约: "
            f"{unresolved}；请检查编号，或用 --lease/--unit 指定可信目标"
        )

    chosen = explicit or question_target
    source = "cli_flag" if explicit is not None else ("question_parse" if chosen else "none")

    domains = _business_domains(question)
    if chosen is None and domains:
        raise TargetResolutionError(
            "这是有业务目标的问题，但没有可信目标：请用 --lease <租约ID> 或 "
            "--unit <商铺编号> 指定；不能把业务问题当成纯说明处理"
        )
    return AskTarget(
        lease_id=chosen["lease_id"] if chosen else None,
        unit_id=chosen["unit_id"] if chosen else None,
        unit_code=chosen["unit_code"] if chosen else None,
        source=source,
        business_domains=tuple(domains),
        matched_words={domain: tuple(words) for domain, words in domains.items()},
    )


def _explicit_target(
    repository: FixtureRepository,
    project_ids: frozenset[str],
    *,
    lease_id: str | None,
    unit_id: str | None,
) -> dict[str, Any] | None:
    """校验显式 --lease/--unit 并归一到 (lease_id, unit_id, unit_code)。"""

    if not lease_id and not unit_id:
        return None
    try:
        if lease_id:
            facts = repository.lease_facts(project_ids=project_ids, lease_id=lease_id)
        else:
            raw_unit = str(unit_id).strip()
            unit = repository.record(raw_unit)
            # `--unit` 接受商铺 ID 或商铺编号（A-301）：两者都交给仓库做范围校验
            if unit is not None and unit.get("code"):
                facts = repository.lease_facts(
                    project_ids=project_ids, unit_code=str(unit["code"])
                )
            else:
                facts = repository.lease_facts(
                    project_ids=project_ids, unit_code=raw_unit
                )
    except TargetResolutionError:
        raise
    except AgentError as exc:
        raise TargetResolutionError(
            f"命令行给出的目标不可用: {exc.message}",
            details={"lease_id": lease_id, "unit_id": unit_id},
        ) from exc

    lease = facts["lease"]
    unit = facts.get("unit") or {}
    resolved_unit_id = unit.get("id")
    resolved_unit_code = unit.get("code")
    if unit_id and str(unit_id) not in {
        str(resolved_unit_id or ""),
        str(resolved_unit_code or ""),
    }:
        raise TargetResolutionError(
            f"--lease 与 --unit 指向不同目标: --unit={unit_id!r} 属于租约 {lease['id']!r} 的商铺 {resolved_unit_id!r}"
        )
    return {
        "lease_id": str(lease["id"]),
        "unit_id": str(resolved_unit_id) if resolved_unit_id else None,
        "unit_code": str(resolved_unit_code) if resolved_unit_code else None,
    }


def _question_target(
    repository: FixtureRepository,
    project_ids: frozenset[str],
    question: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """从问题文本解析商铺编号；返回 (可访问目标, 无法解析的编号)。"""

    targets: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []
    for code in _unit_codes_in(question):
        if code in targets or code in unresolved:
            continue
        try:
            facts = repository.lease_facts(project_ids=project_ids, unit_code=code)
        except AgentError:
            unresolved.append(code)
            continue
        lease = facts["lease"]
        unit = facts.get("unit") or {}
        targets[code] = {
            "lease_id": str(lease["id"]),
            "unit_id": str(unit.get("id")) if unit.get("id") else None,
            "unit_code": code,
        }
    return targets, unresolved


def _unit_codes_in(text: str) -> list[str]:
    codes: list[str] = []
    for match in _UNIT_CODE.finditer(text or ""):
        code = f"{match.group(1).upper()}-{match.group(2)}"
        if code not in codes:
            codes.append(code)
    return codes


def _business_domains(question: str) -> dict[str, tuple[str, ...]]:
    """问题命中的业务领域（与 RuleBasedPlanner 共用同一份词表）。"""

    from .orchestration.vocabulary import matched_domains

    return matched_domains(question)


def _scripted_plan(question: str) -> list[tuple[str, dict[str, Any]]]:
    """脚本化模型的两轮计划：按问题领域各取一次数；目标由 scope 注入。"""

    domains = _business_domains(question)
    plan: list[tuple[str, dict[str, Any]]] = []
    for domain in ("lease", "billing", "property"):
        if domain in domains:
            plan.append(_SCRIPTED_PLAN[domain])
    return plan


def _build_model_client(
    provider: str,
    config: Any,
    fake_script: Iterable[ModelTurn] | None,
    *,
    scripted_calls: Iterable[tuple[str, dict[str, Any]]] = (),
) -> ChatModelClient:
    if provider == "fake":
        script = tuple(fake_script) if fake_script is not None else build_fake_script()
        return FakeChatModelClient(script)
    if provider == "scripted":
        from .llm.scripted import scripted_client_for_tools

        return scripted_client_for_tools(
            list(scripted_calls),
            summary="已按受控工具结果核对；金额与日期均取自工具输出。",
        )
    if provider == "deepseek":
        from .llm.factory import build_model_client_for_config

        # Task 031 / 2.5：按 single.yaml 自己的模型声明构造并校验客户端
        # （缺 api_key_env / 未知 provider / 参数越界都在启动期失败）。
        client = build_model_client_for_config(config)
        assert client is not None
        return client
    raise ValueError(
        f"未知 provider: {provider!r}（可选 fake / scripted / deepseek）"
    )
