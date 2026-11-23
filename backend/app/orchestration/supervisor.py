"""LLM Supervisor 规划器与混合规划（Task 034）。

为什么不是"用模型替换规则"：规则规划可复现、零成本，简单问题上没有理由花钱；
但它只认词表，用户换一种说法（“这家店上个月的钱交齐了吗？”）就命不中。
本模块让模型只做**规划决策**（派哪几个领域 / 是否回问），其余全部由代码约束：

| 环节 | 谁决定 |
|---|---|
| 选哪些领域 | 模型（只能从领域枚举里选，最多 `max_domains` 个） |
| 能力名 | `DOMAIN_CAPABILITIES` 映射，模型无法给出 |
| 调查目标（lease_id / unit_id） | 只取自可信 payload；模型输出中的目标标识一律剥离并告警 |
| 子任务 payload | 与规则规划共用 `build_domain_subtasks`，同样的领域选择得到同样的子任务 |
| 预算 | 规划调用计入共享 `Budget`（模型调用次数与 token） |
| 失败 / 超时 / 非法输出 / 超预算 | 回退：规则有结果用规则结果，否则用规则的回问；原因写进 `planning.fallback_reason` |

输出方式选 **唯一的 `submit_plan` 工具**，而不是 JSON 文本模式：

- 参数 schema 直接由 `SupervisorPlan`（Pydantic，`extra="forbid"`）生成；
- 复用现有工具调用链路：参数不是合法 JSON 时 `invalid_tool_calls` / `parse_error`
  已经有统一处理，不必再写一套文本 JSON 解析；
- 脚本客户端（`FakeChatModelClient`）可以直接构造 `ModelTurn.tool_calls`，回退场景好测；
- 模型只给文本、调了别的工具、或调了多次 `submit_plan`，一律判为 `invalid_output`。

混合规划的"是否需要模型"由**确定性**规则判定（`ambiguity_signals`），不用模型判断
“是否需要模型”。规则口径见 `docs/architecture/planner_vocabulary.md`。
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..agents.base.errors import AgentError
from ..llm.model_client import (
    ChatMessage,
    ChatModelClient,
    ModelTurn,
    ToolSpec,
    describe_served_models,
    served_models_of,
)
from .investigation import (
    CLARIFICATION_QUESTION,
    PlanDetail,
    Planner,
    RuleBasedPlanner,
    build_clarification_request,
    build_domain_subtasks,
    rule_planning_record,
)
from .vocabulary import DOMAIN_LABELS, DOMAINS, matched_domains

__all__ = [
    "FALLBACK_REASONS",
    "HybridPlanner",
    "LLMSupervisorPlanner",
    "PLANNER_MODES",
    "SUBMIT_PLAN_TOOL",
    "SupervisorPlan",
    "ambiguity_signals",
    "build_planner",
    "load_supervisor_prompt",
    "submit_plan_tool_spec",
]

PLANNER_MODES: tuple[str, ...] = ("rule", "llm", "hybrid")
SUBMIT_PLAN_TOOL = "submit_plan"

#: 回退原因的全部取值（报告与评测按此枚举统计）
FALLBACK_REASONS: tuple[str, ...] = (
    "model_unavailable",
    "model_error",
    "timeout",
    "invalid_output",
    "budget_exhausted",
)

#: 模型输出里一旦出现这些键，视为"试图指定调查目标"：剥离并告警，绝不进入子任务
_TARGET_KEYS = frozenset(
    {
        "lease_id",
        "lease_ids",
        "unit_id",
        "unit_code",
        "tenant_id",
        "project_id",
        "principal_id",
        "target",
        "lease",
        "unit",
    }
)

#: 铺位号（A-301 / A301 / a 301）；两侧不能紧挨字母数字，避免把 "B1" "5 号" 当成铺位
_UNIT_CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z])\s?-?\s?(\d{2,4})(?![0-9])")
_LEASE_ID_RE = re.compile(r"lease_[a-z0-9_]+", re.IGNORECASE)

SUPERVISOR_CLARIFICATION_MESSAGE = (
    "规划模型判断需要补充信息后才能调查，因此本次没有执行调查，也没有调用任何工具。"
)

_REQUEST_SEQ = itertools.count(1)


# --------------------------------------------------------------------------- #
# 结构化计划
# --------------------------------------------------------------------------- #


class SupervisorPlan(BaseModel):
    """模型必须产出的受约束计划（`submit_plan` 的参数）。

    `max_domains` 依配置而定，由规划器在校验后再检查（不写死在 schema 里）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["dispatch", "clarify"]
    domains: list[Literal["lease", "billing", "property"]] = Field(
        default_factory=list, max_length=3
    )
    reasons: dict[str, str] = Field(default_factory=dict)
    clarification_question: str | None = None
    confidence: Literal["high", "medium", "low"]

    @field_validator("domains")
    @classmethod
    def _unique_domains(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError(f"domains 不允许重复: {value}")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "SupervisorPlan":
        if self.decision == "dispatch" and not self.domains:
            raise ValueError("decision=dispatch 时 domains 不能为空")
        if self.decision == "clarify" and self.domains:
            raise ValueError("decision=clarify 时 domains 必须为空")
        unknown = sorted(set(self.reasons) - set(self.domains))
        if unknown:
            raise ValueError(f"reasons 只能为已选领域给出理由，多出: {unknown}")
        for domain, text in self.reasons.items():
            if not str(text).strip() or len(str(text)) > 200:
                raise ValueError(f"领域 {domain} 的理由必须非空且不超过 200 字")
        return self


def submit_plan_tool_spec() -> ToolSpec:
    """唯一暴露给规划模型的工具。参数 schema 由 `SupervisorPlan` 生成。"""

    return ToolSpec(
        name=SUBMIT_PLAN_TOOL,
        description=(
            "提交调查计划：选择需要调查的业务领域（lease/billing/property），"
            "或判断必须先回问用户。必须且只能调用一次。"
        ),
        parameters=SupervisorPlan.model_json_schema(),
    )


def load_supervisor_prompt(prompt_path: str | None = None) -> str:
    from ..paths import BACKEND_ROOT

    relative = prompt_path or "app/orchestration/prompts/supervisor_system.md"
    return (BACKEND_ROOT / relative).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 歧义信号（确定性，决定 hybrid 是否交给模型）
# --------------------------------------------------------------------------- #

#: 否定词：出现在某个命中词之前 6 个字以内即视为“否定了这个领域”
NEGATION_WORDS: tuple[str, ...] = ("不是", "并非", "不用", "不要", "除了", "无关", "别查", "别管")
#: 指代别家商户的说法（问题可能不是在问可信目标）
TARGET_REFERENCE_WORDS: tuple[str, ...] = (
    "隔壁",
    "那家",
    "另一家",
    "另外一家",
    "对面",
    "别家",
    "其他店",
)
#: 去掉铺位号与标点后少于这么多字，视为“过短”
MIN_QUESTION_CHARS = 4

_NEGATION_WINDOW = 6


def normalize_unit_code(letter: str, digits: str) -> str:
    return f"{letter.upper()}-{digits}"


def unit_codes_in(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for letter, digits in _UNIT_CODE_RE.findall(text or ""):
        seen.setdefault(normalize_unit_code(letter, digits), None)
    return list(seen)


def ambiguity_signals(
    text: str,
    *,
    matched: dict[str, tuple[str, ...]] | None = None,
    trusted_unit_codes: frozenset[str] | set[str] = frozenset(),
) -> list[str]:
    """确定性的歧义信号（Task 034 / 2.2）。任一信号成立，hybrid 即交给模型。

    | 信号 | 规则 |
    |---|---|
    | `negation` | 否定词出现在某个命中词之前 6 个字以内（“不是租金的问题”） |
    | `target_reference` | 出现指代别家商户的说法（隔壁/那家/另一家/对面/别家/其他店） |
    | `unit_code_mismatch` | 问题中的铺位号与可信目标的铺位号不同 |
    | `too_short` | 去掉铺位号、空白与标点后少于 4 个字 |
    | `weak_hint_only` | 命中的词全部是单字（例如只命中“欠”） |
    """

    content = "" if text is None else str(text)
    hits = matched if matched is not None else matched_domains(content)
    signals: list[str] = []

    words = {word for domain_words in hits.values() for word in domain_words}
    for word in words:
        start = 0
        while True:
            position = content.find(word, start)
            if position < 0:
                break
            window = content[max(0, position - _NEGATION_WINDOW) : position]
            if any(negation in window for negation in NEGATION_WORDS):
                signals.append("negation")
                break
            start = position + 1
        if "negation" in signals:
            break

    if any(word in content for word in TARGET_REFERENCE_WORDS):
        signals.append("target_reference")

    codes = set(unit_codes_in(content))
    if codes and trusted_unit_codes and not codes <= set(trusted_unit_codes):
        signals.append("unit_code_mismatch")

    stripped = _UNIT_CODE_RE.sub("", content)
    stripped = re.sub(r"[\W_]+", "", stripped)
    if len(stripped) < MIN_QUESTION_CHARS:
        signals.append("too_short")

    if words and all(len(word) == 1 for word in words):
        signals.append("weak_hint_only")

    return signals


# --------------------------------------------------------------------------- #
# LLM Supervisor
# --------------------------------------------------------------------------- #


@dataclass
class _Fallback(Exception):
    reason: str
    detail: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class _CallMeta:
    model_calls: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    served: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
        }


class LLMSupervisorPlanner(Planner):
    """由模型做规划决策的 Planner（`plan_detailed` 的异步实现见 `aplan_detailed`）。"""

    def __init__(
        self,
        *,
        model_client: ChatModelClient | None,
        budget: Any = None,
        system_prompt: str | None = None,
        max_domains: int = 3,
        timeout_seconds: float = 20.0,
        max_clarification_chars: int = 120,
        unit_code_of: Callable[[str], str | None] | None = None,
        planner_mode: str = "llm",
    ) -> None:
        self._client = model_client
        self._budget = budget
        self._system_prompt = system_prompt or load_supervisor_prompt()
        self._max_domains = max_domains
        self._timeout = timeout_seconds
        self._max_clarification_chars = max_clarification_chars
        self._unit_code_of = unit_code_of
        self._mode = planner_mode
        self._rule = RuleBasedPlanner()

    @property
    def model_client(self) -> ChatModelClient | None:
        return self._client

    # 同步入口只给非图调用方（脚本 / 单测）使用；图节点走 aplan_detailed
    def plan(self, question: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        detail = self.plan_detailed(question, payload)
        return detail.subtasks, detail.route

    def plan_detailed(self, question: str, payload: dict[str, Any]) -> PlanDetail:
        return _run_sync(self.aplan_detailed(question, payload))

    async def aplan_detailed(self, question: str, payload: dict[str, Any]) -> PlanDetail:
        text = "" if question is None else str(question)
        rule_detail = self._rule.plan_detailed(text, payload)
        matched = matched_domains(text)
        signals = ambiguity_signals(
            text, matched=matched, trusted_unit_codes=self.trusted_unit_codes(payload)
        )
        return await self.supervise(
            text,
            payload,
            rule_detail=rule_detail,
            rule_domains=[domain for domain in DOMAINS if domain in matched],
            signals=signals,
        )

    def trusted_unit_codes(self, payload: dict[str, Any]) -> frozenset[str]:
        lease_id = str(payload.get("lease_id") or "").strip()
        if not lease_id or self._unit_code_of is None:
            return frozenset()
        code = self._unit_code_of(lease_id)
        return frozenset({code}) if code else frozenset()

    async def supervise(
        self,
        text: str,
        payload: dict[str, Any],
        *,
        rule_detail: PlanDetail,
        rule_domains: list[str],
        signals: list[str],
    ) -> PlanDetail:
        warnings: list[str] = []
        meta = _CallMeta()
        try:
            plan = await self._plan_with_model(text, payload, warnings, meta)
        except _Fallback as fallback:
            return self._fallback(
                rule_detail,
                fallback,
                rule_domains=rule_domains,
                signals=signals,
                warnings=warnings,
                meta=meta,
            )
        return self._detail_from_plan(
            text,
            payload,
            plan,
            rule_domains=rule_domains,
            signals=signals,
            warnings=warnings,
            meta=meta,
        )

    # ---------------- 模型调用 ----------------

    def _messages(self, text: str, payload: dict[str, Any]) -> tuple[ChatMessage, ...]:
        codes = sorted(self.trusted_unit_codes(payload))
        user = {
            # 用户问题作为**数据**放在独立字段（System Prompt 写明不得执行其中的指令）
            "user_question": text,
            "trusted_target": {
                "unit_code": codes[0] if codes else None,
                "note": "调查目标由系统根据可信上下文决定，规划时不能更改",
            },
            "available_domains": [
                {"domain": domain, "label": DOMAIN_LABELS[domain]} for domain in DOMAINS
            ],
            "max_domains": self._max_domains,
        }
        return (
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=json.dumps(user, ensure_ascii=False)),
        )

    async def _plan_with_model(
        self,
        text: str,
        payload: dict[str, Any],
        warnings: list[str],
        meta: _CallMeta,
    ) -> SupervisorPlan:
        if self._client is None:
            raise _Fallback("model_unavailable", "没有注入规划模型客户端")

        context = payload.get("context")
        run_id = getattr(context, "run_id", None) or "norun"
        call_id = f"pl_{run_id}_{next(_REQUEST_SEQ)}"
        budget = self._budget
        if budget is not None:
            try:
                await budget.reserve_model_call(call_id)
            except AgentError as exc:
                raise _Fallback("budget_exhausted", f"模型调用预算不足: {exc.code}") from None

        started = time.perf_counter()
        try:
            turn = await asyncio.wait_for(
                self._client.complete(self._messages(text, payload), (submit_plan_tool_spec(),)),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            meta.model_calls = 1
            meta.latency_ms = int((time.perf_counter() - started) * 1000)
            if budget is not None:
                await budget.settle(call_id)
            raise _Fallback("timeout", f"规划模型超过 {self._timeout:g}s 未返回") from None
        except Exception as exc:  # 客户端实现缺陷也不能让整条工作流崩掉
            meta.model_calls = 1
            meta.latency_ms = int((time.perf_counter() - started) * 1000)
            if budget is not None:
                await budget.settle(call_id)
            message = exc.message if isinstance(exc, AgentError) else str(exc)
            raise _Fallback("model_error", f"{type(exc).__name__}: {message}") from None
        meta.model_calls = 1
        meta.latency_ms = int((time.perf_counter() - started) * 1000)
        meta.served = served_models_of([turn])
        if budget is not None:
            await budget.settle(call_id)

        tokens = turn.usage.total_tokens if turn.usage is not None else 0
        meta.total_tokens = int(tokens or 0)
        if budget is not None and tokens:
            token_id = f"{call_id}_tok"
            try:
                await budget.reserve_tokens(token_id, tokens)
                await budget.settle(token_id)
            except AgentError:
                # 响应已真实产生 token：如实记账，再按超预算回退（不使用超预算后的计划）
                await budget.record_unbudgeted_tokens(tokens)
                raise _Fallback("budget_exhausted", "token 预算已耗尽") from None

        return self._parse_plan(turn, payload, warnings)

    def _parse_plan(
        self, turn: ModelTurn, payload: dict[str, Any], warnings: list[str]
    ) -> SupervisorPlan:
        if turn.invalid_tool_calls:
            raise _Fallback(
                "invalid_output",
                "模型返回了无法解析的工具调用: "
                + "; ".join(item.error for item in turn.invalid_tool_calls),
            )
        calls = list(turn.tool_calls)
        if len(calls) != 1:
            raise _Fallback(
                "invalid_output",
                f"必须且只能调用一次 {SUBMIT_PLAN_TOOL}，实际调用 {len(calls)} 次"
                + ("（只给了文本）" if not calls and turn.text else ""),
            )
        call = calls[0]
        if call.name != SUBMIT_PLAN_TOOL:
            raise _Fallback("invalid_output", f"调用了未授权的工具 {call.name!r}")
        if call.parse_error:
            raise _Fallback("invalid_output", f"submit_plan 参数无法解析: {call.parse_error}")

        arguments = dict(call.arguments or {})
        trusted_lease = str(payload.get("lease_id") or "").strip()
        trusted_unit = str(payload.get("unit_id") or "").strip()
        for key in sorted(set(arguments) & _TARGET_KEYS):
            value = arguments.pop(key)
            differs = str(value) not in {trusted_lease, trusted_unit} or not str(value)
            warnings.append(
                f"规划模型输出了目标标识 {key}={value!r}，已忽略；子任务目标只取自可信上下文"
                + ("（与可信目标不一致）" if differs else "")
            )
        try:
            plan = SupervisorPlan.model_validate(arguments)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
                for err in exc.errors()
            )
            raise _Fallback("invalid_output", f"计划校验失败: {details}") from None
        if len(plan.domains) > self._max_domains:
            raise _Fallback(
                "invalid_output",
                f"选择了 {len(plan.domains)} 个领域，超过上限 {self._max_domains}",
            )

        trusted_codes = self.trusted_unit_codes(payload)
        mentioned = " ".join([*plan.reasons.values(), plan.clarification_question or ""])
        foreign_codes = [code for code in unit_codes_in(mentioned) if code not in trusted_codes]
        foreign_leases = [
            lease for lease in _LEASE_ID_RE.findall(mentioned) if lease != trusted_lease
        ]
        if foreign_codes or foreign_leases:
            warnings.append(
                "规划模型的理由/回问中提到了与可信目标不同的目标 "
                f"{foreign_codes + foreign_leases}，已忽略；子任务目标只取自可信上下文"
            )
        return plan

    # ---------------- 计划 → PlanDetail ----------------

    def _planner_model(self, meta: _CallMeta) -> dict[str, Any] | None:
        if self._client is None:
            return None
        configured = getattr(self._client, "model_name", None)
        return {
            "provider": getattr(self._client, "provider", None),
            "model_name": configured,
            **describe_served_models(configured, meta.served),
        }

    def _record(
        self,
        *,
        plan_source: str,
        rule_domains: list[str],
        signals: list[str],
        warnings: list[str],
        meta: _CallMeta,
        plan: SupervisorPlan | None = None,
        planned_domains: list[str] | None = None,
        fallback: _Fallback | None = None,
    ) -> dict[str, Any]:
        record = rule_planning_record(rule_domains=rule_domains, planner_mode=self._mode)
        record.update(
            {
                "plan_source": plan_source,
                "fallback_reason": fallback.reason if fallback else None,
                "fallback_detail": fallback.detail if fallback else None,
                "planner_model": self._planner_model(meta),
                # 只记录**校验后**的计划，不记录 System Prompt
                "supervisor_plan": plan.model_dump(mode="json") if plan is not None else None,
                "ambiguity_signals": list(signals),
                "escalated_to_model": True,
                "rule_domains_not_planned": [
                    domain
                    for domain in rule_domains
                    if planned_domains is not None and domain not in planned_domains
                ],
                "warnings": list(warnings),
                **meta.as_dict(),
            }
        )
        return record

    def _detail_from_plan(
        self,
        text: str,
        payload: dict[str, Any],
        plan: SupervisorPlan,
        *,
        rule_domains: list[str],
        signals: list[str],
        warnings: list[str],
        meta: _CallMeta,
    ) -> PlanDetail:
        if plan.decision == "clarify":
            question = (plan.clarification_question or "").strip()
            if not self._acceptable_question(question):
                warnings.append(
                    "规划模型给出的回问为空、过长或含链接/标识，已改用默认回问"
                )
                question = CLARIFICATION_QUESTION
            return PlanDetail(
                subtasks=[],
                route="clarification",
                routing_reason=[],
                clarification=build_clarification_request(
                    text,
                    reason="supervisor_clarify",
                    message=SUPERVISOR_CLARIFICATION_MESSAGE,
                    question=question,
                ),
                planning=self._record(
                    plan_source="llm",
                    rule_domains=rule_domains,
                    signals=signals,
                    warnings=warnings,
                    meta=meta,
                    plan=plan,
                    planned_domains=[],
                ),
            )

        # 子任务编号与规则规划一致：按领域固定顺序，而不是模型给出的顺序
        ordered = [domain for domain in DOMAINS if domain in plan.domains]
        rule_hits = matched_domains(text)

        def _llm_reason(domain: str, _subtask_id: str) -> dict[str, Any]:
            return {
                "source": "llm",
                "reason": plan.reasons.get(domain, ""),
                "matched": [],
                "rule_matched": list(rule_hits.get(domain, ())),
            }

        subtasks, routing_reason = build_domain_subtasks(
            ordered, text, payload, reason_for=_llm_reason
        )
        return PlanDetail(
            subtasks=subtasks,
            route="deterministic" if len(subtasks) == 1 else "fanout",
            routing_reason=routing_reason,
            planning=self._record(
                plan_source="llm",
                rule_domains=rule_domains,
                signals=signals,
                warnings=warnings,
                meta=meta,
                plan=plan,
                planned_domains=ordered,
            ),
        )

    def _acceptable_question(self, question: str) -> bool:
        if not question or len(question) > self._max_clarification_chars:
            return False
        lowered = question.lower()
        if "http://" in lowered or "https://" in lowered or "lease_" in lowered:
            return False
        if SUBMIT_PLAN_TOOL in lowered:
            return False
        return True

    def _fallback(
        self,
        rule_detail: PlanDetail,
        fallback: _Fallback,
        *,
        rule_domains: list[str],
        signals: list[str],
        warnings: list[str],
        meta: _CallMeta,
    ) -> PlanDetail:
        if rule_detail.subtasks:
            source = "fallback_rule"
            warnings.append(
                f"规划模型不可用（{fallback.reason}：{fallback.detail}），已回退到规则规划结果"
            )
            planned = [item["domain"] for item in rule_detail.routing_reason]
        else:
            source = "fallback_clarification"
            warnings.append(
                f"规划模型不可用（{fallback.reason}：{fallback.detail}），规则也无法判断领域，改为回问"
            )
            planned = []
        return PlanDetail(
            subtasks=rule_detail.subtasks,
            route=rule_detail.route,
            routing_reason=rule_detail.routing_reason,
            clarification=rule_detail.clarification,
            planning=self._record(
                plan_source=source,
                rule_domains=rule_domains,
                signals=signals,
                warnings=warnings,
                meta=meta,
                planned_domains=planned,
                fallback=fallback,
            ),
        )


# --------------------------------------------------------------------------- #
# 混合规划
# --------------------------------------------------------------------------- #


class HybridPlanner(Planner):
    """规则能确定就用规则（零模型调用），否则交给 Supervisor（失败同样回退）。

    ```text
    规则命中恰好 1 个领域，且没有歧义信号        → 规则结果
    规则命中多个领域，无歧义信号，multi=rule     → 规则结果
    其余（0 个领域 / 多领域且 multi=llm / 有歧义） → Supervisor
    ```
    """

    def __init__(
        self,
        supervisor: LLMSupervisorPlanner,
        *,
        hybrid_multi_domain: str = "llm",
    ) -> None:
        if hybrid_multi_domain not in ("rule", "llm"):
            raise ValueError(f"hybrid_multi_domain 只能是 rule / llm，收到 {hybrid_multi_domain!r}")
        self._supervisor = supervisor
        self._multi = hybrid_multi_domain
        self._rule = RuleBasedPlanner()

    @property
    def supervisor(self) -> LLMSupervisorPlanner:
        return self._supervisor

    def plan(self, question: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        detail = self.plan_detailed(question, payload)
        return detail.subtasks, detail.route

    def plan_detailed(self, question: str, payload: dict[str, Any]) -> PlanDetail:
        return _run_sync(self.aplan_detailed(question, payload))

    def escalation(self, text: str, payload: dict[str, Any]) -> tuple[str | None, list[str], list[str]]:
        """返回 `(交给模型的原因 | None, 规则命中领域, 歧义信号)`。纯确定性，可单测。"""

        matched = matched_domains(text)
        rule_domains = [domain for domain in DOMAINS if domain in matched]
        signals = ambiguity_signals(
            text,
            matched=matched,
            trusted_unit_codes=self._supervisor.trusted_unit_codes(payload),
        )
        if signals:
            return "ambiguity_signal", rule_domains, signals
        if not rule_domains:
            return "no_domain_matched", rule_domains, signals
        if len(rule_domains) > 1 and self._multi == "llm":
            return "multi_domain", rule_domains, signals
        return None, rule_domains, signals

    async def aplan_detailed(self, question: str, payload: dict[str, Any]) -> PlanDetail:
        text = "" if question is None else str(question)
        rule_detail = self._rule.plan_detailed(text, payload)
        reason, rule_domains, signals = self.escalation(text, payload)
        if reason is None:
            planning = rule_planning_record(rule_domains=rule_domains, planner_mode="hybrid")
            planning["hybrid_multi_domain"] = self._multi
            return PlanDetail(
                subtasks=rule_detail.subtasks,
                route=rule_detail.route,
                routing_reason=rule_detail.routing_reason,
                clarification=rule_detail.clarification,
                planning=planning,
            )
        detail = await self._supervisor.supervise(
            text,
            payload,
            rule_detail=rule_detail,
            rule_domains=rule_domains,
            signals=signals,
        )
        detail.planning["escalation_reason"] = reason
        detail.planning["hybrid_multi_domain"] = self._multi
        return detail


# --------------------------------------------------------------------------- #
# 装配
# --------------------------------------------------------------------------- #


def build_planner(
    mode: str,
    *,
    config: Any = None,
    model_client: ChatModelClient | None = None,
    budget: Any = None,
    unit_code_of: Callable[[str], str | None] | None = None,
    hybrid_multi_domain: str | None = None,
) -> Planner:
    """按模式构造规划器。`rule` 不需要模型；`llm` / `hybrid` 需要 `model_client`。"""

    if mode not in PLANNER_MODES:
        raise ValueError(f"未知规划模式 {mode!r}（可选 {list(PLANNER_MODES)}）")
    if mode == "rule":
        return RuleBasedPlanner()
    if model_client is None:
        raise ValueError(f"规划模式 {mode!r} 需要规划模型客户端")

    supervisor = LLMSupervisorPlanner(
        model_client=model_client,
        budget=budget,
        system_prompt=load_supervisor_prompt(getattr(config, "prompt_path", None)),
        max_domains=int(getattr(config, "max_domains", 3)),
        timeout_seconds=float(getattr(config, "timeout_seconds", 20.0)),
        max_clarification_chars=int(getattr(config, "max_clarification_chars", 120)),
        unit_code_of=unit_code_of,
        planner_mode=mode,
    )
    if mode == "llm":
        return supervisor
    return HybridPlanner(
        supervisor,
        hybrid_multi_domain=hybrid_multi_domain
        or str(getattr(config, "hybrid_multi_domain", "llm")),
    )


def _run_sync(coroutine: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    coroutine.close()
    raise RuntimeError("事件循环内请调用 aplan_detailed（规划需要异步模型调用）")


def default_prompt_path() -> Path:
    from ..paths import BACKEND_ROOT

    return BACKEND_ROOT / "app" / "orchestration" / "prompts" / "supervisor_system.md"
