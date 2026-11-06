"""三基线实现（Task 013）。

三条基线共用：同一 fixture、同一套只读工具、同一份全任务预算（工具调用总数）。

| 基线 | 架构 | 会不会做的事 | 明确不会做的事 |
|---|---|---|---|
| `A_deterministic` | 意图表 → **单次**只读工具调用 | 取数、按固定模板陈述事实 | 不拆任务、不交叉核验、不发起审批 |
| `B_single_agent` | 一个 Agent 收集**全部适用**工具结果后汇总 | 多工具汇总、单一答案 | 不做角色分解、不做证据矛盾核验、不发起审批 |
| `C_multi_agent` | LangGraph：规划 → 并发子 Agent → 确定性核验 → 审批门 | 分解、并发、核验、缺失标注、可选审批 | 不执行任何业务写操作 |

**关于模型**：本机没有 `DEEPSEEK_API_KEY`，因此 B/C 都在**离线**模式下运行
（B 不调用模型，C 用确定性 Planner + 确定性工具）。报告里 `model.provider` 会明确写
`offline_deterministic`，`total_tokens=0`，`cost=null`——不得把这些数字当成真实模型的成本或质量。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..agents.base.contracts import AgentContext, AgentRequest
from ..agents.factory import build_registry
from ..fixtures.repository import FixtureRepository
from ..investigation_demo import build_investigation_bundle
from ..rag.library import build_knowledge_library
from ..runtime.budget import Budget
from ..runtime.types import TraceLog, TrustedContext
from ..tools.fixture_tools import build_fixture_tools
from ..tools.knowledge_tools import DocumentSearchTool
from ..tools.registry import ToolRegistry

__all__ = [
    "BASELINES",
    "BaselineResult",
    "DeterministicBaseline",
    "MultiAgentBaseline",
    "SingleAgentBaseline",
    "build_baseline",
]

BASELINES: tuple[str, ...] = ("A_deterministic", "B_single_agent", "C_multi_agent")

#: 全任务工具调用预算：三条基线一致，避免"多 Agent 因为多做事而被判作弊/占便宜"。
DEFAULT_MAX_TOOL_CALLS = 12


@dataclass
class BaselineResult:
    baseline: str
    case_id: str
    status: str  # ok | failed | denied
    answer: str
    facts: dict[str, str] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    route: str = ""
    latency_ms: int = 0
    tool_calls: int = 0
    model_calls: int = 0
    total_tokens: int = 0
    errors: list[str] = field(default_factory=list)
    approval_status: str | None = None
    approval_draft_version: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline,
            "case_id": self.case_id,
            "status": self.status,
            "answer": self.answer,
            "facts": self.facts,
            "evidence_ids": list(self.evidence_ids),
            "route": self.route,
            "latency_ms": self.latency_ms,
            "tool_calls": self.tool_calls,
            "model_calls": self.model_calls,
            "total_tokens": self.total_tokens,
            "errors": list(self.errors),
            "approval_status": self.approval_status,
            "approval_draft_version": self.approval_draft_version,
        }


# ---------------------------------------------------------------- 意图识别


_ARREARS_HINTS = (
    "欠",
    "未交",
    "没交",
    "未收",
    "余额",
    "已收",
    "对账",
    "应收",
    "账单",
    "付款",
)
_LEASE_HINTS = ("合同", "租约", "租期", "递增", "租金标准", "条款", "免租", "续租", "押金")
_WORK_ORDER_HINTS = ("工单", "报修", "维修", "空调", "电梯", "故障", "漏水")
_CLAUSE_HINTS = ("条款", "第几页", "原文", "合同里", "如何约定", "怎么约定", "政策", "标准")


_SF: "re.Pattern[str] | None" = None


def resolve_lease(repository: FixtureRepository, principal: dict[str, Any], case: Any) -> str:
    """解析用例对应的租约。

    保留集显式带 `lease_id`；开发集只给问题文本（如 "A-301"），
    因此按单元编号从 fixture 反查，查不到就返回空串（后续会明确失败，而不是猜一个租约）。
    """

    if case.lease_id:
        return str(case.lease_id)
    global _SF
    if _SF is None:
        import re

        _SF = re.compile(r"[A-Za-z]-\d{3}")
    match = _SF.search(case.user_input)
    if not match:
        return ""
    try:
        facts = repository.lease_facts(
            project_ids=frozenset(principal.get("project_ids") or []),
            unit_code=match.group(0).upper(),
        )
    except Exception:  # noqa: BLE001 - 越权或不存在都按"无法解析"处理
        return ""
    lease = facts.get("lease") or {}
    return str(lease.get("id") or lease.get("lease_id") or "")


def detect_intents(question: str) -> list[str]:
    """确定性意图识别。三条基线共用，保证比较的是**架构**而不是提示词运气。"""

    intents: list[str] = []
    if any(hint in question for hint in _ARREARS_HINTS):
        intents.append("arrears")
    if any(hint in question for hint in _LEASE_HINTS):
        intents.append("lease")
    if any(hint in question for hint in _WORK_ORDER_HINTS):
        intents.append("work_orders")
    if any(hint in question for hint in _CLAUSE_HINTS):
        intents.append("clauses")
    return intents


def _compose_answer(facts: dict[str, str], intents: Iterable[str]) -> str:
    parts: list[str] = []
    if "arrears" in intents and "outstanding_total" in facts:
        parts.append(
            f"应收 {facts.get('invoiced_total', '-')}、已收 {facts.get('paid_total', '-')}、"
            f"未收 {facts.get('outstanding_total', '-')}"
        )
    if "lease" in intents and facts.get("lease_period"):
        parts.append(f"租期 {facts['lease_period']}，状态 {facts.get('lease_status', '-')}")
    if "work_orders" in intents and facts.get("work_order_count"):
        parts.append(
            f"相关工单 {facts['work_order_count']} 条，未关闭 {facts.get('open_count', '0')} 条"
        )
    if "clauses" in intents and facts.get("clause_ref"):
        parts.append(f"依据 {facts['clause_ref']}")
    if not parts:
        return "（本次没有取到可用事实）"
    return "；".join(parts) + "。"


# ---------------------------------------------------------------- 基线基类


class _Baseline:
    name: str = ""

    def __init__(self, *, max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS) -> None:
        self.max_tool_calls = max_tool_calls
        self._knowledge = None

    # 三条基线共享的只读工具集合（含合同条款检索）
    def _tools(self, repository: FixtureRepository) -> ToolRegistry:
        registry = ToolRegistry()
        for tool in build_fixture_tools(repository):
            registry.register(tool)
        if self._knowledge is None:
            self._knowledge = build_knowledge_library(repository)
        if self._knowledge.indexed:
            registry.register(DocumentSearchTool(self._knowledge.service))
        return registry

    def _config(self, registry: ToolRegistry) -> Any:
        """基线也要走工具的六道闸：构造一份显式声明全部工具的白名单配置。

        为什么不给 `ToolExecutor` 传 `agent_config=None` 就放行：
        那会绕过"Agent 只能调用自己 YAML 中允许的工具"这条约束，
        评测就会在比生产更宽松的权限下跑，结论不可用。
        """

        from ..config.schema import AgentConfig

        return AgentConfig.model_validate(
            {
                "name": self.name.lower().replace("_", "-")[:32].replace("-", "_"),
                "version": "1.0.0",
                "description": f"evaluation baseline {self.name}",
                "capabilities": ("evaluation.baseline",),
                "model_provider": "offline",
                "model_name": "none",
                "prompt_path": "app/agents/single/prompts/system.md",
                "allowed_tools": tuple(sorted(registry.names())),
                "timeout_seconds": 30,
                "max_retries": 0,
            }
        )

    @staticmethod
    def _context(principal: dict[str, Any], run_id: str) -> AgentContext:
        trusted = TrustedContext.from_principal(principal, trace_id=f"trace_{run_id}")
        return trusted.to_agent_context(run_id=run_id)

    async def run(self, *, case: Any) -> BaselineResult:  # pragma: no cover - 抽象
        raise NotImplementedError


# ---------------------------------------------------------------- A：确定性单工具


class DeterministicBaseline(_Baseline):
    """无 Agent、无模型：意图表 → 一次只读工具调用 → 固定模板陈述。"""

    name = "A_deterministic"

    async def run(self, *, case: Any) -> BaselineResult:
        from ..tools.executor import ToolExecutor

        started = time.perf_counter()
        repository = FixtureRepository.load(variant=None if case.variant == "v_base" else case.variant)
        principal = repository.principal(case.principal_id)
        context = self._context(principal, f"run_{case.case_id}_A")
        registry = self._tools(repository)
        budget = Budget(max_tool_calls=self.max_tool_calls)
        config = self._config(registry)
        executor = ToolExecutor(registry, budget, trace_log=TraceLog())

        intents = detect_intents(case.user_input)
        result = BaselineResult(
            baseline=self.name, case_id=case.case_id, status="ok", answer="", route="deterministic"
        )
        if not intents:
            result.status = "failed"
            result.errors.append("未能识别意图（确定性基线不做猜测）")
            result.latency_ms = int((time.perf_counter() - started) * 1000)
            return result

        primary = intents[0]
        lease_id = resolve_lease(repository, principal, case)
        tool, payload = _single_call(primary, case, repository, lease_id)
        execution = await executor.execute(
            tool, payload, context=context, agent_config=config
        )
        result.tool_calls = 1
        if not execution.ok:
            error = execution.error
            result.status = "denied" if error and error.code.value in {
                "permission_denied",
                "project_scope_denied",
            } else "failed"
            result.errors.append(f"{error.code.value}: {error.message}" if error else "工具失败")
            result.approval_status = None
            result.latency_ms = int((time.perf_counter() - started) * 1000)
            return result

        result.facts = _facts_from_tool(tool, execution.data or {}, repository, case)
        result.evidence_ids = [item.evidence_id for item in execution.evidence]
        result.answer = _compose_answer(result.facts, [primary])
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result


# ---------------------------------------------------------------- B：单 Agent 多工具


class SingleAgentBaseline(_Baseline):
    """一个 Agent 把**所有适用**工具结果汇总成一个答案，不做角色分解与核验。"""

    name = "B_single_agent"

    async def run(self, *, case: Any) -> BaselineResult:
        from ..tools.executor import ToolExecutor

        started = time.perf_counter()
        repository = FixtureRepository.load(variant=None if case.variant == "v_base" else case.variant)
        principal = repository.principal(case.principal_id)
        context = self._context(principal, f"run_{case.case_id}_B")
        registry = self._tools(repository)
        budget = Budget(max_tool_calls=self.max_tool_calls)
        config = self._config(registry)
        executor = ToolExecutor(registry, budget, trace_log=TraceLog())

        intents = detect_intents(case.user_input)
        result = BaselineResult(
            baseline=self.name, case_id=case.case_id, status="ok", answer="", route="single_agent"
        )
        if not intents:
            intents = ["arrears"]

        facts: dict[str, str] = {}
        evidence: list[str] = []
        errors: list[str] = []
        calls = 0
        denied = False
        lease_id = resolve_lease(repository, principal, case)
        for intent in intents:
            for tool, payload in _calls_for(intent, case, repository, lease_id):
                if calls >= self.max_tool_calls:
                    errors.append("工具预算耗尽")
                    break
                calls += 1
                execution = await executor.execute(
                    tool, payload, context=context, agent_config=config
                )
                if not execution.ok:
                    error = execution.error
                    code = error.code.value if error else "tool_error"
                    errors.append(f"{tool}: {code}")
                    if code in {"permission_denied", "project_scope_denied"}:
                        denied = True
                    continue
                facts.update(_facts_from_tool(tool, execution.data or {}, repository, case))
                evidence.extend(item.evidence_id for item in execution.evidence)

        result.tool_calls = calls
        result.facts = facts
        result.evidence_ids = list(dict.fromkeys(evidence))
        result.answer = _compose_answer(facts, intents)
        result.errors = errors
        if not facts:
            result.status = "denied" if denied else "failed"
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result


# ---------------------------------------------------------------- C：多 Agent 图


class MultiAgentBaseline(_Baseline):
    """LangGraph 图：规则规划 → 并发子 Agent → 确定性核验 → 审批门。"""

    name = "C_multi_agent"

    async def run(self, *, case: Any) -> BaselineResult:
        started = time.perf_counter()
        bundle = build_investigation_bundle(
            principal_id=case.principal_id,
            variant=None if case.variant == "v_base" else case.variant,
            max_tool_calls=self.max_tool_calls,
        )
        result = BaselineResult(
            baseline=self.name, case_id=case.case_id, status="ok", answer="", route=""
        )
        investigation = await bundle.investigator.investigate(
            question=case.user_input,
            lease_id=resolve_lease(bundle.repository, bundle.repository.principal(case.principal_id), case),
            context=bundle.context,
            thread_id=f"thread_{case.case_id}_C",
        )
        result.route = investigation.route
        result.approval_status = investigation.approval_status or None
        draft = (investigation.report or {}).get("proposed_draft") or {}
        result.approval_draft_version = draft.get("draft_version")

        facts: dict[str, str] = {}
        evidence: list[str] = []
        for item in investigation.results:
            output = item.get("output") or {}
            capability = item.get("capability")
            evidence.extend(_evidence_ids(output))
            if capability == "billing.statement":
                facts.update(
                    {
                        "invoiced_total": str(output.get("invoiced_total")),
                        "paid_total": str(output.get("paid_total")),
                        "outstanding_total": str(output.get("outstanding_total")),
                    }
                )
            elif capability == "lease.query":
                lease = output.get("lease") or {}
                facts["lease_period"] = f"{lease.get('start_date')} 至 {lease.get('end_date')}"
                facts["lease_status"] = str(lease.get("status"))
                for clause in output.get("clauses") or []:
                    facts.setdefault(
                        "clause_ref",
                        f"合同第 {clause.get('page')} 页 {clause.get('clause_id')} 条",
                    )
            elif capability == "property.work_orders":
                facts["work_order_count"] = str(output.get("work_order_count", 0))
                facts["open_count"] = str(output.get("open_count", 0))

        result.facts = facts
        result.evidence_ids = list(dict.fromkeys(evidence))
        result.answer = _compose_answer(
            facts, detect_intents(case.user_input) or ["arrears"]
        )
        result.errors = [
            f"{item.get('subtask_id')}: {item.get('error_code')}"
            for item in investigation.failures
        ]
        snapshot = bundle.budget.snapshot()
        result.tool_calls = snapshot.used_tool_calls
        result.model_calls = snapshot.used_model_calls
        result.total_tokens = snapshot.used_total_tokens
        if investigation.failures and not investigation.results:
            result.status = "failed"
        elif not investigation.results:
            result.status = "failed"
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result


# ---------------------------------------------------------------- 工具选择


def _single_call(intent: str, case: Any, repository: FixtureRepository, lease_id: str = ""):
    calls = _calls_for(intent, case, repository, lease_id)
    return calls[0]


def _calls_for(intent: str, case: Any, repository: FixtureRepository, lease_id: str = "") -> list[tuple[str, dict]]:
    if intent == "arrears":
        return [("billing.statement.read", {"lease_id": lease_id})]
    if intent == "lease":
        return [("lease.lookup", {"lease_id": lease_id})]
    if intent == "work_orders":
        return [("property.work_orders.read", {"lease_id": lease_id})]
    if intent == "clauses":
        return [("document.search", {"query": case.user_input, "top_k": 3})]
    return [("lease.lookup", {"lease_id": lease_id})]


def _facts_from_tool(
    tool: str, data: dict[str, Any], repository: FixtureRepository, case: Any
) -> dict[str, str]:
    if tool == "billing.statement.read":
        return {
            "invoiced_total": str(data.get("invoiced_total")),
            "paid_total": str(data.get("paid_total")),
            "outstanding_total": str(data.get("outstanding_total")),
        }
    if tool == "lease.lookup":
        return {
            "lease_period": f"{data.get('start_date')} 至 {data.get('end_date')}",
            "lease_status": str(data.get("status")),
        }
    if tool == "property.work_orders.read":
        return {
            "work_order_count": str(data.get("work_order_count", 0)),
            "open_count": str(data.get("open_count", 0)),
        }
    if tool == "document.search":
        results = data.get("results") or []
        if not results:
            return {"clause_ref": "未检索到匹配条款"}
        top = results[0]
        return {"clause_ref": f"合同第 {top.get('page')} 页 {top.get('clause_id')} 条"}
    return {}


def _evidence_ids(output: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("evidence", "clause_evidence"):
        for item in output.get(key, []) or []:
            if isinstance(item, dict) and item.get("evidence_id"):
                ids.append(str(item["evidence_id"]))
    return ids


def build_baseline(name: str, *, max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS) -> _Baseline:
    mapping = {
        "A_deterministic": DeterministicBaseline,
        "B_single_agent": SingleAgentBaseline,
        "C_multi_agent": MultiAgentBaseline,
    }
    if name not in mapping:
        raise ValueError(f"未知基线: {name!r}（可选 {BASELINES}）")
    return mapping[name](max_tool_calls=max_tool_calls)
