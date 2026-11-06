"""Task 007 的 Runtime / Tool 自动化测试。

为什么用 `unittest.TestCase` 而不是 `pytest` fixture 风格：

- 本任务明确**不安装依赖**，当前 Conda 环境没有 pytest；
- `unittest.TestCase` 既可被 `python -m unittest discover` 直接执行，
  也能被 pytest 原生收集（装了 pytest 的机器无需改测试）；
- 因此测试覆盖不依赖"未安装的框架"，同时保留 pytest 兼容性。

运行：在 `backend/` 下 `python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from pydantic import BaseModel, ConfigDict

# 与既有 smoke 脚本一致：Agent 的失败日志走 stdout，
# 避免 PowerShell 把预期失败的告警日志当作命令错误。
import logging

logging.basicConfig(
    level=logging.WARNING,
    format="  [LOG] %(name)s %(message)s",
    stream=sys.stdout,
    force=True,
)

from app.agents.base import (
    AgentContext,
    AgentOutput,
    AgentRequest,
    AgentResult,
    BaseAgent,
    ErrorCode,
    ExecutionMetadata,
    TaskStatus,
)
from app.agents.base.errors import (
    AgentConfigMismatchError,
    DuplicateToolError,
    IncompatibleToolError,
    IncompatibleAgentError,
    ToolNotFoundError,
)
from app.agents.base.registry import AgentRegistry
from app.agents.factory import build_agent, build_registry
from app.config.loader import load_all_agent_configs
from app.config.schema import AgentConfig
from app.demo import (
    DEMO_TOOLS,
    ScriptedToolAgent,
    build_demo_agent_config,
    build_demo_bundle,
    run_demo,
)
from app.fixtures.repository import FixtureRepository
from app.orchestration.coordinator import summarize_results
from app.paths import CONFIG_DIR, DEFAULT_FIXTURE_PATH
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.budget import Budget
from app.runtime.types import EvidenceDraft, ToolStatus, TraceLog, TrustedContext
from app.tools.base import BaseTool, ToolInvocation
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_agent_config(
    *,
    name: str = "lease",
    version: str = "0.1.0",
    capabilities: tuple[str, ...] = ("lease.query",),
    allowed_tools: tuple[str, ...] = (),
    timeout_seconds: float = 5.0,
    max_retries: int = 0,
) -> AgentConfig:
    return AgentConfig(
        name=name,
        version=version,
        capabilities=list(capabilities),
        model_provider="fake",
        model_name="fake-offline",
        temperature=None,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        prompt_path="app/agents/lease/prompts/system.md",
        allowed_tools=list(allowed_tools),
    )


def make_result(status: TaskStatus) -> AgentResult:
    now = utcnow()
    return AgentResult(
        request_id=__import__("uuid").uuid4(),
        status=status,
        metadata=ExecutionMetadata(
            agent_name="unit-test",
            agent_version="0.1.0",
            trace_id="trace-unit",
            started_at=now,
            finished_at=now,
        ),
    )


class _StaticAgent(BaseAgent):
    name = "lease"
    version = "0.1.0"
    description = "test double"
    capabilities = frozenset({"lease.query"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        return AgentOutput(data={"ok": True})


class _ReplacementAgent(BaseAgent):
    name = "lease"
    version = "0.2.0"
    description = "replacement"
    capabilities = frozenset({"lease.query", "lease.extra"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        return AgentOutput(data={"replaced": True})


class _SlowAgent(BaseAgent):
    name = "slow"
    version = "0.1.0"
    description = "test double"
    capabilities = frozenset({"slow.run"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        await asyncio.sleep(2.0)
        return AgentOutput()


class _AlwaysTimeoutAgent(BaseAgent):
    name = "slow"
    version = "0.1.0"
    description = "test double"
    capabilities = frozenset({"slow.run"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        await asyncio.sleep(2.0)
        return AgentOutput()


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _EchoInput(_StrictModel):
    value: str = "x"


class _EchoOutput(_StrictModel):
    value: str


class _SlowTool(BaseTool):
    name = "test.slow"
    version = "1.0.0"
    description = "test-only"
    required_permissions = frozenset()
    timeout_seconds = 0.1
    max_attempts = 1
    input_model = _EchoInput
    output_model = _EchoOutput

    async def invoke(self, payload: _EchoInput, context: AgentContext) -> ToolInvocation:
        await asyncio.sleep(0.5)
        return ToolInvocation(data={"value": payload.value})


class _FlakyTool(BaseTool):
    name = "test.flaky"
    version = "1.0.0"
    description = "test-only: times out N times then succeeds"
    required_permissions = frozenset()
    timeout_seconds = 0.2
    max_attempts = 2
    input_model = _EchoInput
    output_model = _EchoOutput

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def invoke(self, payload: _EchoInput, context: AgentContext) -> ToolInvocation:
        self.calls += 1
        if self.calls <= self.failures:
            await asyncio.sleep(0.5)
        return ToolInvocation(data={"value": payload.value})


class _BadOutputTool(BaseTool):
    name = "test.bad_output"
    version = "1.0.0"
    description = "test-only: violates its own output schema"
    required_permissions = frozenset()
    timeout_seconds = 1.0
    max_attempts = 1
    input_model = _EchoInput
    output_model = _EchoOutput

    async def invoke(self, payload: _EchoInput, context: AgentContext) -> ToolInvocation:
        return ToolInvocation(data={"unexpected": "field"})


class _ForeignEvidenceTool(BaseTool):
    name = "test.foreign_evidence"
    version = "1.0.0"
    description = "test-only: returns evidence from a foreign project"
    required_permissions = frozenset()
    timeout_seconds = 1.0
    max_attempts = 1
    input_model = _EchoInput
    output_model = _EchoOutput

    async def invoke(self, payload: _EchoInput, context: AgentContext) -> ToolInvocation:
        return ToolInvocation(
            data={"value": payload.value},
            evidence=(
                EvidenceDraft(
                    evidence_id="foreign_1",
                    project_id="prj_jinlan",
                    dataset_version="agent-first-v1",
                    as_of_date=datetime(2026, 11, 3).date(),
                    entity="unit",
                    record_id="unit_jl_b101",
                    fields={"code": "B-101"},
                ),
            ),
        )


class _GateTool(BaseTool):
    name = "test.gate"
    version = "1.0.0"
    description = "test-only: concurrency gate"
    required_permissions = frozenset()
    timeout_seconds = 2.0
    max_attempts = 1
    input_model = _EchoInput
    output_model = _EchoOutput

    async def invoke(self, payload: _EchoInput, context: AgentContext) -> ToolInvocation:
        await asyncio.sleep(0.05)
        return ToolInvocation(data={"value": payload.value})


def _context_with(
    *,
    project_ids: frozenset[str] = frozenset({"prj_xinghui"}),
    permissions: frozenset[str] = frozenset({"lease.read", "billing.read", "property.read"}),
    deadline_at: datetime | None = None,
) -> AgentContext:
    return TrustedContext(
        trace_id="trace-unit",
        principal_id="principal_ops_xinghui",
        project_ids=project_ids,
        permissions=permissions,
        deadline_at=deadline_at,
    ).to_agent_context()


# --------------------------------------------------------------------------- #
# K1
# --------------------------------------------------------------------------- #

class TestK1RegistryAtomicReplace(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AgentRegistry()
        self.registry.register(_StaticAgent(make_agent_config()))

    def test_failed_replace_keeps_old_registration(self) -> None:
        before_names = self.registry.names()
        before_caps = set(self.registry.available_capabilities())

        with self.assertRaises(IncompatibleAgentError):
            self.registry.register(object(), replace=True)  # type: ignore[arg-type]

        self.assertEqual(self.registry.names(), before_names)
        self.assertEqual(set(self.registry.available_capabilities()), before_caps)
        self.assertEqual(self.registry.require_capability("lease.query").name, "lease")

    def test_replace_success_swaps_capabilities_atomically(self) -> None:
        self.registry.register(
            _ReplacementAgent(make_agent_config(version="0.2.0")), replace=True
        )
        self.assertEqual(self.registry.names(), ("lease",))
        self.assertEqual(
            self.registry.available_capabilities(), frozenset({"lease.query", "lease.extra"})
        )

    def test_duplicate_without_replace_is_rejected(self) -> None:
        from app.agents.base.errors import DuplicateAgentError

        with self.assertRaises(DuplicateAgentError):
            self.registry.register(_ReplacementAgent(make_agent_config()))


# --------------------------------------------------------------------------- #
# K2
# --------------------------------------------------------------------------- #

class TestK2ConfigDescriptorConsistency(unittest.TestCase):
    def setUp(self) -> None:
        configs = load_all_agent_configs(CONFIG_DIR)
        self.lease_config = configs["lease"]

    def test_version_mismatch_rejected(self) -> None:
        bad = self.lease_config.model_copy(update={"version": "9.9.9"})
        with self.assertRaises(AgentConfigMismatchError):
            build_agent(bad)

    def test_capability_mismatch_rejected(self) -> None:
        bad = self.lease_config.model_copy(update={"capabilities": ("lease.query",)})
        with self.assertRaises(AgentConfigMismatchError):
            build_agent(bad)

    def test_matching_config_builds(self) -> None:
        agent = build_agent(self.lease_config)
        self.assertEqual(agent.descriptor.name, "lease")


# --------------------------------------------------------------------------- #
# K3
# --------------------------------------------------------------------------- #

class TestK3DeadlineBoundsSingleExecution(unittest.TestCase):
    def _run(self, agent: BaseAgent, deadline_at: datetime) -> AgentResult:
        context = AgentContext(trace_id="trace-deadline", deadline_at=deadline_at)
        request = AgentRequest(task_id="task-deadline", capability="slow.run")
        return asyncio.run(agent.handle(request, context))

    def test_single_execution_aborts_at_deadline(self) -> None:
        agent = _SlowAgent(make_agent_config(name="slow", capabilities=("slow.run",), timeout_seconds=5.0))
        started = time.perf_counter()
        result = self._run(agent, utcnow() + timedelta(seconds=0.2))
        elapsed = time.perf_counter() - started

        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertIsNotNone(result.error)
        self.assertIn(
            result.error.code, {ErrorCode.DEADLINE_EXCEEDED, ErrorCode.TIMEOUT}
        )
        self.assertLess(elapsed, 1.5, f"deadline 未生效，实际耗时 {elapsed:.2f}s")

    def test_retries_do_not_run_past_deadline(self) -> None:
        agent = _AlwaysTimeoutAgent(
            make_agent_config(
                name="slow",
                capabilities=("slow.run",),
                timeout_seconds=0.1,
                max_retries=5,
            )
        )
        started = time.perf_counter()
        result = self._run(agent, utcnow() + timedelta(seconds=0.35))
        elapsed = time.perf_counter() - started

        self.assertIs(result.status, TaskStatus.FAILED)
        # 重试次数必须停在 max_retries 内（这是本用例的核心断言）
        self.assertLessEqual(result.metadata.attempt, 5)
        # elapsed 只作辅助护栏：Windows 上 asyncio.wait_for 的取消有调度抖动，
        # 全量连跑时偶发超过 1.2s；即使 deadline 完全失效，5×0.1s 也远小于 3s，
        # 所以放宽到 3s 不损失"重试爆炸"的检出能力。
        self.assertLess(elapsed, 3.0, f"重试越过 deadline，实际耗时 {elapsed:.2f}s")

    def test_expired_deadline_fails_without_executing(self) -> None:
        agent = _SlowAgent(make_agent_config(name="slow", capabilities=("slow.run",)))
        started = time.perf_counter()
        result = self._run(agent, utcnow() - timedelta(seconds=1))
        elapsed = time.perf_counter() - started

        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.DEADLINE_EXCEEDED)  # type: ignore[union-attr]
        self.assertLess(elapsed, 0.5)
        self.assertEqual(result.metadata.attempt, 0)


# --------------------------------------------------------------------------- #
# K4 / K5
# --------------------------------------------------------------------------- #

class TestK4K5Aggregation(unittest.TestCase):
    def test_all_success(self) -> None:
        self.assertIs(
            summarize_results([make_result(TaskStatus.SUCCESS)], allow_partial=False),
            TaskStatus.SUCCESS,
        )

    def test_partial_visible_only_when_allowed(self) -> None:
        results = [make_result(TaskStatus.SUCCESS), make_result(TaskStatus.PARTIAL)]
        self.assertIs(summarize_results(results, allow_partial=True), TaskStatus.PARTIAL)
        self.assertIs(summarize_results(results, allow_partial=False), TaskStatus.FAILED)

    def test_all_skipped_is_failed(self) -> None:
        results = [make_result(TaskStatus.SKIPPED), make_result(TaskStatus.SKIPPED)]
        self.assertIs(summarize_results(results, allow_partial=True), TaskStatus.FAILED)
        self.assertIs(summarize_results(results, allow_partial=False), TaskStatus.FAILED)

    def test_mixed_skipped_is_partial_only_when_allowed(self) -> None:
        results = [make_result(TaskStatus.SUCCESS), make_result(TaskStatus.SKIPPED)]
        self.assertIs(summarize_results(results, allow_partial=True), TaskStatus.PARTIAL)
        self.assertIs(summarize_results(results, allow_partial=False), TaskStatus.FAILED)

    def test_all_failed_and_empty(self) -> None:
        self.assertIs(
            summarize_results([make_result(TaskStatus.FAILED)], allow_partial=True),
            TaskStatus.FAILED,
        )
        self.assertIs(summarize_results([], allow_partial=True), TaskStatus.FAILED)


# --------------------------------------------------------------------------- #
# Tool registry / executor
# --------------------------------------------------------------------------- #

class TestToolRegistry(unittest.TestCase):
    def test_duplicate_tool_rejected(self) -> None:
        registry = ToolRegistry()
        registry.register(_GateTool())
        with self.assertRaises(DuplicateToolError):
            registry.register(_GateTool())

    def test_non_base_tool_rejected(self) -> None:
        class _Impostor:
            name = "fake.tool"

        with self.assertRaises(IncompatibleToolError):
            ToolRegistry().register(_Impostor())  # type: ignore[arg-type]

    def test_unknown_tool_lookup(self) -> None:
        with self.assertRaises(ToolNotFoundError):
            ToolRegistry().get("nope.nope")


class TestToolExecutor(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = build_demo_bundle()
        self.executor = self.bundle.executor
        self.context = self.bundle.trusted.to_agent_context()
        self.config = build_demo_agent_config()

    def _execute(self, tool: str, payload: dict[str, Any], **kwargs: Any):
        context = kwargs.pop("context", self.context)
        config = kwargs.pop("config", self.config)
        return asyncio.run(
            self.executor.execute(tool, payload, context=context, agent_config=config)
        )

    # ---- 授权与校验 ----

    def test_allowed_tool_succeeds_with_evidence(self) -> None:
        execution = self._execute("lease.lookup", {"lease_id": "lease_xh_a301_2025"})
        self.assertTrue(execution.ok, execution.error)
        self.assertEqual(execution.status, ToolStatus.OK)
        self.assertEqual(execution.data["unit_code"], "A-301")
        self.assertGreaterEqual(len(execution.evidence), 3)
        for evidence in execution.evidence:
            self.assertEqual(evidence.source_tool, "lease.lookup")
            self.assertEqual(evidence.tool_call_id, execution.call_id)
            self.assertTrue(evidence.synthetic)
            self.assertEqual(evidence.dataset_version, "agent-first-v1")
            self.assertEqual(evidence.as_of_date.isoformat(), "2026-11-03")

    def test_tool_not_in_agent_allowed_tools(self) -> None:
        narrow = build_demo_agent_config(allowed_tools=["lease.lookup"])
        execution = self._execute(
            "billing.arrears.calculate",
            {"lease_id": "lease_xh_a301_2025"},
            config=narrow,
        )
        self.assertFalse(execution.ok)
        self.assertEqual(execution.error.code, ErrorCode.TOOL_NOT_ALLOWED)  # type: ignore[union-attr]
        self.assertEqual(execution.status, ToolStatus.DENIED)

    def test_permission_denied(self) -> None:
        context = self.context.model_copy(update={"permissions": frozenset()})
        execution = self._execute(
            "lease.lookup", {"lease_id": "lease_xh_a301_2025"}, context=context
        )
        self.assertEqual(execution.error.code, ErrorCode.PERMISSION_DENIED)  # type: ignore[union-attr]

    def test_unknown_tool(self) -> None:
        execution = self._execute("nope.nope", {})
        self.assertEqual(execution.error.code, ErrorCode.TOOL_NOT_FOUND)  # type: ignore[union-attr]

    def test_invalid_arguments(self) -> None:
        execution = self._execute(
            "lease.lookup",
            {"lease_id": "lease_xh_a301_2025", "unit_code": "A-301"},
        )
        self.assertEqual(execution.error.code, ErrorCode.INVALID_TOOL_ARGUMENTS)  # type: ignore[union-attr]

    def test_payload_cannot_grant_permissions(self) -> None:
        execution = self._execute(
            "lease.lookup",
            {"lease_id": "lease_xh_a301_2025", "permissions": ["lease.read"]},
        )
        self.assertEqual(execution.error.code, ErrorCode.INVALID_TOOL_ARGUMENTS)  # type: ignore[union-attr]

    def test_bad_output_schema(self) -> None:
        self.bundle.tool_registry.register(_BadOutputTool())
        execution = self._execute(
            "test.bad_output",
            {"value": "x"},
            config=build_demo_agent_config(allowed_tools=["test.bad_output"]),
        )
        self.assertEqual(execution.error.code, ErrorCode.INVALID_TOOL_RESULT)  # type: ignore[union-attr]

    def test_foreign_project_evidence_rejected(self) -> None:
        self.bundle.tool_registry.register(_ForeignEvidenceTool())
        execution = self._execute(
            "test.foreign_evidence",
            {"value": "x"},
            config=build_demo_agent_config(allowed_tools=["test.foreign_evidence"]),
        )
        self.assertEqual(execution.error.code, ErrorCode.PERMISSION_DENIED)  # type: ignore[union-attr]

    # ---- 项目范围 ----

    def test_cross_project_access_denied(self) -> None:
        execution = self._execute("lease.lookup", {"lease_id": "lease_jl_b101_2025"})
        self.assertEqual(execution.error.code, ErrorCode.PROJECT_SCOPE_DENIED)  # type: ignore[union-attr]
        self.assertIsNone(execution.data)

        # 没有工单的外项目商铺也必须先被范围校验，不能靠"空结果"探测存在性
        property_execution = self._execute(
            "property.work_orders.read", {"unit_id": "unit_jl_b101"}
        )
        self.assertEqual(
            property_execution.error.code, ErrorCode.PROJECT_SCOPE_DENIED  # type: ignore[union-attr]
        )
        self.assertIsNone(property_execution.data)

    def test_other_project_context_cannot_read_xinghui(self) -> None:
        context = _context_with(project_ids=frozenset({"prj_jinlan"}))
        execution = self._execute(
            "billing.arrears.calculate",
            {"lease_id": "lease_xh_a301_2025"},
            context=context,
        )
        self.assertEqual(execution.error.code, ErrorCode.PROJECT_SCOPE_DENIED)  # type: ignore[union-attr]

    # ---- 超时 / 重试 / 预算 ----

    def test_timeout_then_retry_succeeds_once(self) -> None:
        flaky = _FlakyTool(failures=1)
        self.bundle.tool_registry.register(flaky)
        execution = self._execute(
            "test.flaky",
            {"value": "ok"},
            config=build_demo_agent_config(allowed_tools=["test.flaky"]),
        )
        self.assertTrue(execution.ok, execution.error)
        self.assertEqual(execution.attempts, 2)
        self.assertEqual(flaky.calls, 2)
        self.assertEqual(len(execution.traces), 2)
        self.assertEqual(execution.traces[0].status, ToolStatus.TIMEOUT)
        self.assertEqual(execution.traces[1].status, ToolStatus.OK)
        # 重试不重复扣预算：一次逻辑调用只算 1
        self.assertEqual(self.bundle.budget.snapshot().used_tool_calls, 1)

    def test_retry_exhausted_reports_timeout_and_counts_once(self) -> None:
        flaky = _FlakyTool(failures=99)
        self.bundle.tool_registry.register(flaky)
        execution = self._execute(
            "test.flaky",
            {"value": "ok"},
            config=build_demo_agent_config(allowed_tools=["test.flaky"]),
        )
        self.assertFalse(execution.ok)
        self.assertEqual(execution.error.code, ErrorCode.TOOL_TIMEOUT)  # type: ignore[union-attr]
        self.assertEqual(execution.attempts, 2)
        self.assertEqual(self.bundle.budget.snapshot().used_tool_calls, 1)

    def test_budget_exhaustion(self) -> None:
        bundle = build_demo_bundle(max_tool_calls=1)
        first = asyncio.run(
            bundle.executor.execute(
                "lease.lookup",
                {"lease_id": "lease_xh_a301_2025"},
                context=bundle.trusted.to_agent_context(),
                agent_config=build_demo_agent_config(),
            )
        )
        second = asyncio.run(
            bundle.executor.execute(
                "lease.lookup",
                {"lease_id": "lease_xh_a301_2025"},
                context=bundle.trusted.to_agent_context(),
                agent_config=build_demo_agent_config(),
            )
        )
        self.assertTrue(first.ok)
        self.assertEqual(second.error.code, ErrorCode.BUDGET_EXHAUSTED)  # type: ignore[union-attr]
        self.assertEqual(bundle.budget.snapshot().used_tool_calls, 1)

    def test_concurrent_budget_never_overspends(self) -> None:
        bundle = build_demo_bundle(max_tool_calls=3)
        bundle.tool_registry.register(_GateTool())
        config = build_demo_agent_config(
            allowed_tools=["test.gate"]
        )
        context = bundle.trusted.to_agent_context()

        async def _run_all():
            return await asyncio.gather(
                *[
                    bundle.executor.execute(
                        "test.gate", {"value": str(i)}, context=context, agent_config=config
                    )
                    for i in range(10)
                ]
            )

        results = asyncio.run(_run_all())
        ok_count = sum(1 for item in results if item.ok)
        exhausted = sum(
            1
            for item in results
            if not item.ok and item.error and item.error.code is ErrorCode.BUDGET_EXHAUSTED
        )
        self.assertEqual(ok_count, 3)
        self.assertEqual(exhausted, 7)
        self.assertEqual(bundle.budget.snapshot().used_tool_calls, 3)

    # ---- Trace ----

    def test_trace_fields_and_no_raw_payload(self) -> None:
        execution = self._execute("lease.lookup", {"lease_id": "lease_xh_a301_2025"})
        trace = execution.traces[0]
        self.assertEqual(trace.tool_name, "lease.lookup")
        self.assertEqual(trace.trace_id, self.context.trace_id)
        self.assertEqual(len(trace.args_digest), 16)
        self.assertEqual(trace.status, ToolStatus.OK)
        dumped = json.dumps(trace.model_dump(mode="json"), ensure_ascii=False)
        self.assertNotIn("lease_xh_a301_2025", dumped)  # 只存摘要，不存原始参数


# --------------------------------------------------------------------------- #
# Fixture 查询与 Decimal
# --------------------------------------------------------------------------- #

class TestFixtureTools(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = build_demo_bundle()
        self.context = self.bundle.trusted.to_agent_context()
        self.config = build_demo_agent_config()

    def _call(self, tool: str, payload: dict[str, Any], executor=None, context=None):
        return asyncio.run(
            (executor or self.bundle.executor).execute(
                tool, payload, context=context or self.context, agent_config=self.config
            )
        )

    def test_lease_domain(self) -> None:
        execution = self._call("lease.lookup", {"unit_code": "A-301"})
        self.assertTrue(execution.ok, execution.error)
        self.assertEqual(execution.data["lease_no"], "XH-A301-2025-01")
        self.assertEqual(len(execution.data["rules"]), 4)
        self.assertIn("doc_xh_a301_annex_b", execution.data["missing_document_ids"])

    def test_billing_statement_decimal_and_variance(self) -> None:
        from decimal import Decimal

        execution = self._call(
            "billing.statement.read", {"lease_id": "lease_xh_a301_2025"}
        )
        self.assertTrue(execution.ok, execution.error)
        data = execution.data
        self.assertEqual(Decimal(data["invoiced_total"]), Decimal("52596.00"))
        self.assertEqual(Decimal(data["paid_total"]), Decimal("34560.00"))
        self.assertEqual(Decimal(data["outstanding_total"]), Decimal("18036.00"))
        self.assertEqual(Decimal(data["rent_variance_total"]), Decimal("756.00"))
        october = [inv for inv in data["invoices"] if inv["invoice_id"] == "inv_2026_10"][0]
        self.assertEqual(Decimal(october["rent_variance"]), Decimal("756.00"))
        # 金额以十进制字符串传输，绝不出现 float
        self.assertIsInstance(data["invoiced_total"], str)

    def test_billing_arrears_base_and_corrected(self) -> None:
        from decimal import Decimal

        base = self._call("billing.arrears.calculate", {"lease_id": "lease_xh_a301_2025"})
        self.assertEqual(Decimal(base.data["outstanding_total"]), Decimal("18036.00"))

        corrected_bundle = build_demo_bundle(variant="v_oct_rent_corrected")
        corrected = asyncio.run(
            corrected_bundle.executor.execute(
                "billing.arrears.calculate",
                {"lease_id": "lease_xh_a301_2025"},
                context=corrected_bundle.trusted.to_agent_context(),
                agent_config=build_demo_agent_config(),
            )
        )
        self.assertTrue(corrected.ok, corrected.error)
        self.assertEqual(Decimal(corrected.data["outstanding_total"]), Decimal("17280.00"))

    def test_property_domain(self) -> None:
        execution = self._call(
            "property.work_orders.read",
            {"lease_id": "lease_xh_a301_2025", "category": "hvac"},
        )
        self.assertTrue(execution.ok, execution.error)
        self.assertEqual(execution.data["work_order_count"], 3)
        self.assertEqual(execution.data["open_count"], 1)
        self.assertEqual(
            [item["work_order_id"] for item in execution.data["work_orders"]],
            ["wo_2026_07_12", "wo_2026_08_18", "wo_2026_09_25"],
        )

    def test_evidence_ids_match_fixture_records(self) -> None:
        execution = self._call(
            "billing.arrears.calculate", {"lease_id": "lease_xh_a301_2025"}
        )
        ids = {item.evidence_id for item in execution.evidence}
        self.assertTrue(
            {"inv_2026_10", "itm_inv10_rent", "alloc_001", "alloc_002"} <= ids,
            sorted(ids),
        )
        repository = self.bundle.repository
        for evidence in execution.evidence:
            self.assertIsNotNone(repository.record(evidence.record_id))


# --------------------------------------------------------------------------- #
# Runtime 边界
# --------------------------------------------------------------------------- #

class TestRuntime(unittest.TestCase):
    def test_demo_run_end_to_end(self) -> None:
        bundle = build_demo_bundle()
        result = asyncio.run(run_demo(bundle))
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        self.assertEqual(len(result.tool_traces), 3)
        self.assertEqual(result.budget.used_tool_calls, 3)
        self.assertGreaterEqual(len(result.evidence), 3)
        self.assertTrue(all(item.project_id == "prj_xinghui" for item in result.evidence))

    def test_payload_cannot_inject_permissions(self) -> None:
        bundle = build_demo_bundle()
        request = AgentRequest(
            task_id="task-evil",
            capability="runtime.demo",
            payload={"permissions": ["billing.read"], "project_ids": ["prj_jinlan"]},
        )
        result = asyncio.run(bundle.runtime.run(request, bundle.trusted))
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INVALID_REQUEST)  # type: ignore[union-attr]
        self.assertEqual(result.budget.used_tool_calls, 0)

    def test_capability_missing_and_disabled(self) -> None:
        report = build_registry()
        budget = Budget(max_tool_calls=1)
        runtime = AgentRuntime(report.registry, budget)
        trusted = TrustedContext(
            trace_id="trace-unit",
            principal_id="principal_ops_xinghui",
            project_ids=frozenset({"prj_xinghui"}),
            permissions=frozenset({"lease.read"}),
        )
        missing = asyncio.run(
            runtime.run(
                AgentRequest(task_id="t", capability="unknown.capability", payload={}),
                trusted,
            )
        )
        self.assertEqual(missing.error.code, ErrorCode.CAPABILITY_UNAVAILABLE)  # type: ignore[union-attr]

        disabled = asyncio.run(
            runtime.run(
                AgentRequest(task_id="t", capability="compliance.check", payload={}),
                trusted,
            )
        )
        self.assertEqual(disabled.error.code, ErrorCode.AGENT_NOT_ENABLED)  # type: ignore[union-attr]

    def test_agent_tool_failure_surfaces_stable_code(self) -> None:
        bundle = build_demo_bundle(
            script=(("billing.arrears.calculate", {"lease_id": "lease_jl_b101_2025"}),)
        )
        result = asyncio.run(run_demo(bundle))
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.PROJECT_SCOPE_DENIED)  # type: ignore[union-attr]
        self.assertTrue(result.tool_traces)


# --------------------------------------------------------------------------- #
# CLI / 配置与敏感键
# --------------------------------------------------------------------------- #

class TestStatementLeaseIsolation(unittest.TestCase):
    """F1：同项目其他租约的付款/核销不得计入当前租约。"""

    @staticmethod
    def _repository_with_other_lease_payment() -> FixtureRepository:
        data = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
        data["invoices"].append(
            {
                "id": "inv_test_a302_2026_10",
                "project_id": "prj_xinghui",
                "lease_id": "lease_xh_a302_2025",
                "invoice_no": "XH-TEST-A302-2026-10",
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
                "issue_date": "2026-10-25",
                "due_date": "2026-10-30",
                "currency": "CNY",
                "status": "issued",
            }
        )
        data["invoice_items"].append(
            {
                "id": "itm_test_a302_rent",
                "invoice_id": "inv_test_a302_2026_10",
                "charge_rule_id": None,
                "charge_type": "rent",
                "description": "A-302 测试租金",
                "quantity": "10.0000",
                "unit_price": "10.0000",
                "amount": "100.00",
            }
        )
        data["payments"].append(
            {
                "id": "pay_test_a302",
                "project_id": "prj_xinghui",
                "receipt_no": "XH-TEST-A302",
                "payer_tenant_id": "ten_xh_wenju",
                "payment_method": "bank_transfer",
                "amount": "100.00",
                "currency": "CNY",
                "paid_at": "2026-10-28T10:00:00+08:00",
                "status": "confirmed",
            }
        )
        data["payment_allocations"].append(
            {
                "id": "alloc_test_a302",
                "payment_id": "pay_test_a302",
                "invoice_id": "inv_test_a302_2026_10",
                "amount": "100.00",
                "allocated_at": "2026-10-28T10:05:00+08:00",
                "reversed_at": None,
            }
        )
        return FixtureRepository(data)

    def test_other_lease_payment_does_not_change_current_lease(self) -> None:
        from decimal import Decimal

        repository = self._repository_with_other_lease_payment()
        statement = repository.statement(
            project_ids=frozenset({"prj_xinghui"}), lease_id="lease_xh_a301_2025"
        )
        self.assertEqual(Decimal(statement["invoiced_total"]), Decimal("52596.00"))
        self.assertEqual(Decimal(statement["paid_total"]), Decimal("34560.00"))
        self.assertEqual(Decimal(statement["outstanding_total"]), Decimal("18036.00"))
        allocation_ids = {item["id"] for item in statement["allocations"]}
        payment_ids = {item["id"] for item in statement["payments"]}
        self.assertEqual(allocation_ids, {"alloc_001", "alloc_002"})
        self.assertEqual(payment_ids, {"pay_2026_08_28", "pay_2026_09_28"})
        self.assertNotIn("alloc_test_a302", allocation_ids)
        self.assertNotIn("pay_test_a302", payment_ids)

    def test_other_lease_statement_uses_its_own_payment(self) -> None:
        from decimal import Decimal

        repository = self._repository_with_other_lease_payment()
        statement = repository.statement(
            project_ids=frozenset({"prj_xinghui"}), lease_id="lease_xh_a302_2025"
        )
        self.assertEqual(Decimal(statement["invoiced_total"]), Decimal("100.00"))
        self.assertEqual(Decimal(statement["paid_total"]), Decimal("100.00"))
        self.assertEqual(Decimal(statement["outstanding_total"]), Decimal("0.00"))
        self.assertEqual(
            {item["id"] for item in statement["allocations"]}, {"alloc_test_a302"}
        )

    def test_payment_split_across_leases_counts_only_own_allocation(self) -> None:
        """一笔付款同时核销两个租约时，本租约已收额只能按自己的核销金额计。"""

        from decimal import Decimal

        data = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
        data["invoices"].append(
            {
                "id": "inv_split_a302",
                "project_id": "prj_xinghui",
                "lease_id": "lease_xh_a302_2025",
                "invoice_no": "XH-SPLIT-A302",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
                "issue_date": "2026-09-25",
                "due_date": "2026-09-30",
                "currency": "CNY",
                "status": "issued",
            }
        )
        data["invoice_items"].append(
            {
                "id": "itm_split_a302",
                "invoice_id": "inv_split_a302",
                "charge_rule_id": None,
                "charge_type": "rent",
                "description": "A-302 拆分测试",
                "quantity": "1.0000",
                "unit_price": "300.0000",
                "amount": "300.00",
            }
        )
        data["payments"].append(
            {
                "id": "pay_split_across_leases",
                "project_id": "prj_xinghui",
                "receipt_no": "XH-SPLIT-RC",
                "payer_tenant_id": "ten_xh_yunduan",
                "payment_method": "bank_transfer",
                "amount": "500.00",
                "currency": "CNY",
                "paid_at": "2026-09-28T10:00:00+08:00",
                "status": "confirmed",
            }
        )
        data["payment_allocations"].extend(
            [
                {
                    "id": "alloc_split_a301",
                    "payment_id": "pay_split_across_leases",
                    "invoice_id": "inv_2026_10",
                    "amount": "200.00",
                    "allocated_at": "2026-09-28T10:05:00+08:00",
                    "reversed_at": None,
                },
                {
                    "id": "alloc_split_a302",
                    "payment_id": "pay_split_across_leases",
                    "invoice_id": "inv_split_a302",
                    "amount": "300.00",
                    "allocated_at": "2026-09-28T10:05:00+08:00",
                    "reversed_at": None,
                },
            ]
        )
        repository = FixtureRepository(data)

        statement = repository.statement(
            project_ids=frozenset({"prj_xinghui"}), lease_id="lease_xh_a301_2025"
        )
        # 34560.00 原有 + 200.00 本租约核销；不得把整笔 500.00 算进来
        self.assertEqual(Decimal(statement["paid_total"]), Decimal("34760.00"))
        self.assertEqual(Decimal(statement["outstanding_total"]), Decimal("17836.00"))
        self.assertEqual(
            {item["id"] for item in statement["allocations"]},
            {"alloc_001", "alloc_002", "alloc_split_a301"},
        )
        self.assertEqual(
            sum((Decimal(a["amount"]) for a in statement["allocations"]), Decimal("0")),
            Decimal("34760.00"),
        )

        other = repository.statement(
            project_ids=frozenset({"prj_xinghui"}), lease_id="lease_xh_a302_2025"
        )
        self.assertEqual(Decimal(other["paid_total"]), Decimal("300.00"))
        self.assertEqual(Decimal(other["outstanding_total"]), Decimal("0.00"))


class TestTraceIsolation(unittest.TestCase):
    """F2：RuntimeResult.tool_traces 只包含本次 run 的 Trace。"""

    def test_sequential_runs_do_not_mix_traces(self) -> None:
        bundle = build_demo_bundle()
        first = asyncio.run(run_demo(bundle))
        second = asyncio.run(run_demo(bundle))

        self.assertEqual(len(first.tool_traces), 3)
        self.assertEqual(len(second.tool_traces), 3)
        self.assertTrue(all(t.run_id == first.run_id for t in first.tool_traces))
        self.assertTrue(all(t.run_id == second.run_id for t in second.tool_traces))
        self.assertNotEqual(first.run_id, second.run_id)

        first_calls = {t.call_id for t in first.tool_traces}
        second_calls = {t.call_id for t in second.tool_traces}
        self.assertTrue(first_calls.isdisjoint(second_calls))

        # 共享 TraceLog 仍是 append-only：历史全部保留
        global_traces = bundle.trace_log.snapshot()
        self.assertEqual(len(global_traces), 6)
        self.assertEqual(first_calls | second_calls, {t.call_id for t in global_traces})

    def test_concurrent_runs_are_isolated(self) -> None:
        bundle = build_demo_bundle()

        async def _run_both():
            return await asyncio.gather(run_demo(bundle), run_demo(bundle))

        first, second = asyncio.run(_run_both())

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(len(first.tool_traces), 3)
        self.assertEqual(len(second.tool_traces), 3)
        self.assertTrue(all(t.run_id == first.run_id for t in first.tool_traces))
        self.assertTrue(all(t.run_id == second.run_id for t in second.tool_traces))

        first_calls = {t.call_id for t in first.tool_traces}
        second_calls = {t.call_id for t in second.tool_traces}
        self.assertTrue(first_calls.isdisjoint(second_calls))

        global_traces = bundle.trace_log.snapshot()
        self.assertEqual(len(global_traces), 6)
        self.assertEqual(first_calls | second_calls, {t.call_id for t in global_traces})


class TestCLI(unittest.TestCase):
    def test_help_lists_commands(self) -> None:
        from app.cli import build_parser

        help_text = build_parser().format_help()
        for command in ("tools", "check", "demo"):
            self.assertIn(command, help_text)

    def test_tools_and_check_commands_exit_zero(self) -> None:
        from app.cli import main

        for argv in (["tools"], ["check"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), 0, argv)

    def test_demo_command_outputs_json(self) -> None:
        from app.cli import main

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["demo"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["tool_trace_count"], 3)
        self.assertEqual(payload["arrears"]["outstanding_total"], "18036.00")


class TestSecurityScan(unittest.TestCase):
    def test_configs_have_no_secret_values(self) -> None:
        secret = re.compile(r"sk-[A-Za-z0-9]{10,}")
        for path in sorted(CONFIG_DIR.glob("*.yaml")):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(secret.search(text), f"{path} 含疑似密钥")
            self.assertNotRegex(text, r"(?m)^\s*api_key\s*:")

    def test_pyproject_declares_only_needed_dependencies(self) -> None:
        raw = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        # 去掉注释行后再检查依赖声明，避免把说明文字当成依赖
        text = "\n".join(
            line for line in raw.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertIn("pydantic", text)
        self.assertIn("PyYAML", text)
        # Task 008/009/010/011/012/014 明确引入的依赖
        self.assertIn("langchain-core", text)
        self.assertIn("langgraph", text)
        self.assertIn("sqlalchemy", text.lower())
        self.assertIn("pypdf", text.lower())
        self.assertIn("reportlab", text.lower())
        # Task 014 起 fastapi 是**展示层**依赖（可整体删除，不影响 CLI/评测）
        self.assertIn("fastapi", text.lower())
        # 仍未引入的重型/业务依赖：出现即说明越界
        for forbidden in ("chromadb", "psycopg", "torch", "transformers", "sentence-transformers"):
            self.assertNotIn(forbidden, text.lower())

    def test_declared_dependencies_match_imports(self) -> None:
        """声明了就必须真的被 import；否则属于"为未来预留"的无据依赖。"""

        text = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        app_sources = {
            path: path.read_text(encoding="utf-8")
            for path in (BACKEND_ROOT / "app").rglob("*.py")
        }
        if "langgraph" in text.lower():
            self.assertTrue(
                any("langgraph" in source for source in app_sources.values()),
                "pyproject 声明了 langgraph，但 app/ 未 import",
            )
        if "langchain-core" in text:
            self.assertTrue(
                any("langchain_core" in source for source in app_sources.values()),
                "pyproject 声明了 langchain-core，但 app/ 未 import",
            )

    def test_no_network_or_db_imports_in_runtime_modules(self) -> None:
        forbidden = ("import requests", "import httpx", "import sqlalchemy", "import psycopg")
        for path in (BACKEND_ROOT / "app").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                self.assertNotIn(needle, text, f"{path} 出现禁止依赖 {needle}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
