"""Task 033A：MCP 网关基础（档案、身份、结果信封）单元测试。

范围与边界：

- 只测 033A 的三件基础，不启动 MCP Server、不走 stdio、不碰 CLI；
- 用临时目录写坏档案，不改仓库里的 `app/config/mcp_clients/*.yaml`；
- 金额测试走**真实执行器**（`billing.statement.read`，星汇 A-301 合同），
  断言 `structuredContent` 与 JSON 文本里金额都是精确到分的字符串；
- 档案里的 `document.search` 只验证注册名，不建 PDF 索引（本任务不测检索）。

运行：在 `backend/` 下 `python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import mock

import jsonschema
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.base.contracts import AgentContext, AgentErrorDetail
from app.agents.base.errors import AgentConfigError, ErrorCode
from app.config.schema import AgentConfig
from app.fixtures.repository import FixtureRepository
from app.mcp_gateway.identity import (
    DEV_MODE_WARNING,
    SessionIdentity,
    create_session,
    resolve_context,
)
from app.mcp_gateway.profiles import (
    READ_ONLY_TOOLS,
    ClientProfile,
    load_profile,
    to_agent_config,
)
from app.mcp_gateway.results import (
    envelope_output_schema,
    to_call_tool_result,
    to_envelope,
)
from app.rag.service import KnowledgeService
from app.runtime.budget import Budget
from app.runtime.types import ToolExecution, TraceLog, TrustedContext
from app.tools.base import BaseTool, ToolInvocation
from app.tools.executor import ToolExecutor
from app.tools.fixture_tools import StatementOutput, build_fixture_tools
from app.tools.knowledge_tools import DocumentSearchTool
from app.tools.registry import ToolRegistry

LEASE = "lease_xh_a301_2025"
PRINCIPAL = "principal_ops_xinghui"
PLACEHOLDER_PROMPT = "app/agents/single/prompts/system.md"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class _EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _EmptyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _WriteTool(BaseTool):
    """测试专用：一个已注册但**非只读**的工具（真实代码里不应存在）。"""

    name = "billing.statement.write"
    version = "1.0.0"
    description = "test-only write tool"
    required_permissions = frozenset()
    timeout_seconds = 1.0
    max_attempts = 1
    input_model = _EmptyInput
    output_model = _EmptyOutput

    async def invoke(self, payload: _EmptyInput, context: AgentContext) -> ToolInvocation:
        raise AssertionError("写工具不应被网关执行")


class _SlowTool(BaseTool):
    """测试专用：用于触发执行器的 TOOL_TIMEOUT。"""

    name = "lease.slow"
    version = "1.0.0"
    description = "test-only slow tool"
    required_permissions = frozenset()
    timeout_seconds = 0.01
    max_attempts = 1
    input_model = _EmptyInput
    output_model = _EmptyOutput

    async def invoke(self, payload: _EmptyInput, context: AgentContext) -> ToolInvocation:
        await asyncio.sleep(0.2)
        return ToolInvocation(data={})


def _registry(*extra: BaseTool) -> ToolRegistry:
    """真实只读工具 + 仅占位的 `document.search`（不建索引，避免依赖 PDF）。"""

    repository = FixtureRepository.load()
    registry = ToolRegistry()
    for tool in build_fixture_tools(repository):
        registry.register(tool)
    registry.register(DocumentSearchTool(KnowledgeService()))
    for tool in extra:
        registry.register(tool)
    return registry


def _config(*allowed: str) -> AgentConfig:
    return AgentConfig(
        name="mcp_test",
        version="1.0.0",
        capabilities=("mcp.gateway",),
        model_provider="offline",
        model_name="none",
        prompt_path=PLACEHOLDER_PROMPT,
        allowed_tools=tuple(allowed),
    )


def _agent_context(
    repository: FixtureRepository, principal_id: str = PRINCIPAL
) -> AgentContext:
    principal = repository.principal(principal_id)
    return TrustedContext.from_principal(
        principal, trace_id="trace_mcp_test"
    ).to_agent_context(run_id="mcp_test_session")


def _write_profile(directory: Path, file_stem: str, **overrides: Any) -> Path:
    payload: dict[str, Any] = {
        "name": file_stem,
        "enabled": True,
        "principal_id": PRINCIPAL,
        "allowed_tools": ["lease.lookup"],
        "budget": {"max_tool_calls_per_session": 20},
    }
    payload.update(overrides)
    path = directory / f"{file_stem}.yaml"
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _assert_no_float(node: Any, *, path: str = "$") -> None:
    """JSON 解析结果里不允许出现浮点数（金额必须全程是字符串）。"""

    if isinstance(node, float):
        raise AssertionError(f"{path} 出现浮点数: {node!r}")
    if isinstance(node, dict):
        for key, value in node.items():
            _assert_no_float(value, path=f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_no_float(value, path=f"{path}[{index}]")


# --------------------------------------------------------------------------- #
# 1. 客户端档案
# --------------------------------------------------------------------------- #

class TestClientProfiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()
        cls.repository = FixtureRepository.load()

    def test_repository_profiles_load(self) -> None:
        local = load_profile("local_dev", registry=self.registry)
        self.assertEqual(local.name, "local_dev")
        self.assertTrue(local.enabled)
        self.assertEqual(set(local.allowed_tools), set(READ_ONLY_TOOLS))
        self.assertEqual(len(local.allowed_tools), 5)
        self.assertEqual(local.budget.max_tool_calls_per_session, 20)

        flowise = load_profile("flowise", registry=self.registry)
        self.assertEqual(
            set(flowise.allowed_tools),
            {
                "lease.lookup",
                "billing.statement.read",
                "property.work_orders.read",
                "document.search",
            },
        )
        self.assertNotIn("billing.arrears.calculate", flowise.allowed_tools)

    def test_missing_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("no_such_client", registry=self.registry, config_dir=tmp)
        message = str(caught.exception)
        self.assertIn("no_such_client", message)
        self.assertIn("不存在", message)

    def test_disabled_profile_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(Path(tmp), "off_client", enabled=False)
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("off_client", registry=self.registry, config_dir=tmp)
        message = str(caught.exception)
        self.assertIn("off_client", message)
        self.assertIn("禁用", message)

    def test_unregistered_tool_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "bad_tool",
                allowed_tools=["lease.lookup", "billing.refund.create"],
            )
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("bad_tool", registry=self.registry, config_dir=tmp)
        message = str(caught.exception)
        self.assertIn("bad_tool", message)
        self.assertIn("billing.refund.create", message)
        self.assertIn("未注册", message)

    def test_registered_non_read_only_tool_fails(self) -> None:
        registry = _registry(_WriteTool())
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "writer_client",
                allowed_tools=["lease.lookup", "billing.statement.write"],
            )
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("writer_client", registry=registry, config_dir=tmp)
        message = str(caught.exception)
        self.assertIn("writer_client", message)
        self.assertIn("billing.statement.write", message)
        self.assertIn("非只读", message)

    def test_extra_field_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(Path(tmp), "extra_client", extra_field="not-allowed")
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("extra_client", registry=self.registry, config_dir=tmp)
        message = str(caught.exception)
        self.assertIn("extra_client", message)
        self.assertIn("extra_field", message)

    def test_name_must_match_file_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(Path(tmp), "file_client", name="other_name")
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("file_client", registry=self.registry, config_dir=tmp)
        message = str(caught.exception)
        self.assertIn("file_client", message)
        self.assertIn("other_name", message)

    def test_allowed_tools_must_be_non_empty_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(Path(tmp), "empty_tools", allowed_tools=[])
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("empty_tools", registry=self.registry, config_dir=tmp)
            self.assertIn("allowed_tools", str(caught.exception))

            _write_profile(
                Path(tmp), "dup_tools", allowed_tools=["lease.lookup", "lease.lookup"]
            )
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("dup_tools", registry=self.registry, config_dir=tmp)
            self.assertIn("重复", str(caught.exception))

    def test_budget_must_be_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "zero_budget",
                budget={"max_tool_calls_per_session": 0},
            )
            with self.assertRaises(AgentConfigError) as caught:
                load_profile("zero_budget", registry=self.registry, config_dir=tmp)
        self.assertIn("max_tool_calls_per_session", str(caught.exception))

    def test_to_agent_config_preserves_whitelist(self) -> None:
        profile = load_profile("flowise", registry=self.registry)
        config = to_agent_config(profile)
        self.assertEqual(config.name, profile.name)
        self.assertEqual(config.allowed_tools, profile.allowed_tools)
        self.assertEqual(config.model_provider, "offline")
        self.assertEqual(config.model_name, "none")

    def test_client_profile_rejects_extra_fields(self) -> None:
        # Schema 层同样拒绝未知字段（不只依赖 load_profile 的 YAML 路径）
        with self.assertRaises(ValidationError):
            ClientProfile.model_validate(
                {
                    "name": "x",
                    "enabled": True,
                    "principal_id": PRINCIPAL,
                    "allowed_tools": ["lease.lookup"],
                    "budget": {"max_tool_calls_per_session": 1},
                    "extra": True,
                }
            )


# --------------------------------------------------------------------------- #
# 2. 会话身份
# --------------------------------------------------------------------------- #

class TestSessionIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()
        cls.profile = load_profile("local_dev", registry=cls.registry)
        cls.repository = FixtureRepository.load()

    def test_default_principal_comes_from_profile(self) -> None:
        session = create_session(self.profile, environ={})
        self.assertTrue(session.session_id.startswith("mcp_local_dev_"))
        self.assertEqual(session.client_name, "local_dev")
        self.assertEqual(session.principal_id, PRINCIPAL)
        self.assertEqual(session.source, "profile")

    def test_env_principal_overrides_and_records_source(self) -> None:
        with mock.patch.dict(
            os.environ, {"DEMO_PRINCIPAL_ID": "principal_finance_jinlan"}
        ):
            session = create_session(self.profile)
        self.assertEqual(session.principal_id, "principal_finance_jinlan")
        self.assertEqual(session.source, "env:DEMO_PRINCIPAL_ID")

    def test_blank_env_is_treated_as_unset(self) -> None:
        with mock.patch.dict(os.environ, {"DEMO_PRINCIPAL_ID": "   "}):
            session = create_session(self.profile)
        self.assertEqual(session.principal_id, PRINCIPAL)
        self.assertEqual(session.source, "profile")

    def test_context_scope_comes_from_principal_record(self) -> None:
        session = create_session(self.profile, environ={})
        context = resolve_context(session, repository=self.repository)

        principal = self.repository.principal(PRINCIPAL)
        self.assertEqual(context.principal_id, PRINCIPAL)
        self.assertEqual(context.user_id, PRINCIPAL)
        self.assertEqual(context.project_ids, frozenset(principal["project_ids"]))
        self.assertEqual(context.permissions, frozenset(principal["permissions"]))
        self.assertEqual(context.run_id, session.session_id)

        # 换一个主体记录（另一个项目）→ 项目范围随之改变，无需任何调用参数
        other = create_session(self.profile, environ={"DEMO_PRINCIPAL_ID": "principal_finance_jinlan"})
        other_context = resolve_context(other, repository=self.repository)
        self.assertEqual(other_context.project_ids, frozenset({"prj_jinlan"}))

    def test_context_cannot_take_scope_from_call_arguments(self) -> None:
        session = create_session(self.profile, environ={})
        with self.assertRaises(TypeError):
            resolve_context(  # type: ignore[call-arg]
                session, {"project_ids": ["prj_jinlan"]}
            )

    def test_trace_id_unique_per_call_and_run_id_is_session(self) -> None:
        session = create_session(self.profile, environ={})
        first = resolve_context(session, repository=self.repository)
        second = resolve_context(session, repository=self.repository)
        self.assertNotEqual(first.trace_id, second.trace_id)
        self.assertEqual(first.run_id, session.session_id)
        self.assertEqual(second.run_id, session.session_id)

    def test_dev_mode_warning_text(self) -> None:
        self.assertIn("开发模式", DEV_MODE_WARNING)
        self.assertIn("不可用于生产", DEV_MODE_WARNING)

    def test_session_identity_rejects_empty_fields(self) -> None:
        with self.assertRaises(ValidationError):
            SessionIdentity(
                session_id="",
                client_name="local_dev",
                principal_id=PRINCIPAL,
                source="profile",
            )


# --------------------------------------------------------------------------- #
# 3. 结果信封
# --------------------------------------------------------------------------- #

class TestResultEnvelope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()
        cls.repository = FixtureRepository.load()
        cls.config = to_agent_config(load_profile("local_dev", registry=cls.registry))
        cls.flowise_config = to_agent_config(
            load_profile("flowise", registry=cls.registry)
        )
        cls.context = _agent_context(cls.repository)

    def _execute(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        config: AgentConfig | None = None,
        registry: ToolRegistry | None = None,
        max_tool_calls: int = 10,
    ) -> ToolExecution:
        tool_registry = registry if registry is not None else self.registry
        executor = ToolExecutor(
            tool_registry,
            Budget(max_tool_calls=max_tool_calls),
            trace_log=TraceLog(),
        )
        return asyncio.run(
            executor.execute(
                tool_name,
                payload,
                context=self.context,
                agent_config=config if config is not None else self.config,
            )
        )

    def test_success_envelope(self) -> None:
        execution = self._execute("billing.statement.read", {"lease_id": LEASE})
        self.assertTrue(execution.ok)

        envelope = to_envelope(execution)
        self.assertEqual(envelope.status, "ok")
        self.assertIsNone(envelope.error)
        self.assertEqual(envelope.call_id, execution.call_id)
        self.assertEqual(envelope.data["outstanding_total"], "18036.00")
        self.assertTrue(envelope.evidence)
        self.assertTrue(
            all(item["source_tool"] == "billing.statement.read" for item in envelope.evidence)
        )
        self.assertTrue(any("invoice_no" in item["fields"] for item in envelope.evidence))

        result = to_call_tool_result(execution)
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "ok")
        self.assertEqual(json.loads(result.content[0].text), result.structured_content)

    def test_denied_envelope_uses_executor_error_code(self) -> None:
        execution = self._execute(
            "billing.arrears.calculate",
            {"lease_id": LEASE},
            config=self.flowise_config,
        )
        self.assertFalse(execution.ok)
        self.assertEqual(execution.error.code, ErrorCode.TOOL_NOT_ALLOWED)

        envelope = to_envelope(execution)
        self.assertEqual(envelope.status, "denied")
        self.assertIsNone(envelope.data)
        self.assertEqual(envelope.error.code, "tool_not_allowed")
        self.assertTrue(to_call_tool_result(execution).is_error)

    def test_timeout_envelope(self) -> None:
        registry = _registry(_SlowTool())
        execution = self._execute(
            "lease.slow", {}, config=_config("lease.slow"), registry=registry
        )
        self.assertEqual(execution.error.code, ErrorCode.TOOL_TIMEOUT)

        envelope = to_envelope(execution)
        self.assertEqual(envelope.status, "timeout")
        self.assertIsNone(envelope.data)
        self.assertEqual(envelope.error.code, "tool_timeout")
        self.assertTrue(to_call_tool_result(execution).is_error)

    def test_budget_exhausted_envelope(self) -> None:
        execution = self._execute(
            "lease.lookup", {"lease_id": LEASE}, max_tool_calls=0
        )
        self.assertEqual(execution.error.code, ErrorCode.BUDGET_EXHAUSTED)

        envelope = to_envelope(execution)
        self.assertEqual(envelope.status, "budget_exhausted")
        self.assertEqual(envelope.error.code, "budget_exhausted")
        self.assertTrue(to_call_tool_result(execution).is_error)

    def test_other_error_envelope(self) -> None:
        execution = self._execute(
            "billing.statement.read", {"lease_id": "lease_does_not_exist"}
        )
        self.assertEqual(execution.error.code, ErrorCode.RECORD_NOT_FOUND)

        envelope = to_envelope(execution)
        self.assertEqual(envelope.status, "error")
        self.assertEqual(envelope.error.code, "record_not_found")
        self.assertTrue(to_call_tool_result(execution).is_error)

    def test_unknown_status_falls_back_to_error(self) -> None:
        execution = ToolExecution(
            call_id="tc_unknown", tool_name="lease.lookup", status="mystery"
        )
        envelope = to_envelope(execution)
        self.assertEqual(envelope.status, "error")
        self.assertEqual(envelope.error.code, "internal_error")
        self.assertIsNone(envelope.data)
        self.assertTrue(to_call_tool_result(execution).is_error)

    def test_ok_status_with_error_detail_is_not_success(self) -> None:
        contradictory = ToolExecution(
            call_id="tc_contradict",
            tool_name="lease.lookup",
            status="ok",
            error=AgentErrorDetail(
                code=ErrorCode.INTERNAL_ERROR, message="执行器报告了内部错误"
            ),
        )
        self.assertEqual(to_envelope(contradictory).status, "error")

    def test_amounts_are_strings_to_the_cent(self) -> None:
        execution = self._execute("billing.statement.read", {"lease_id": LEASE})
        result = to_call_tool_result(execution)
        data = result.structured_content["data"]

        expected = {
            "invoiced_total": "52596.00",
            "paid_total": "34560.00",
            "outstanding_total": "18036.00",
            "rent_variance_total": "756.00",
        }
        for key, value in expected.items():
            self.assertIsInstance(data[key], str)
            self.assertEqual(data[key], value)
            self.assertEqual(f"{Decimal(data[key]):.2f}", data[key])

        for invoice in data["invoices"]:
            for key in ("total", "outstanding"):
                self.assertIsInstance(invoice[key], str)
            for item in invoice["items"]:
                for key in ("quantity", "unit_price", "amount"):
                    self.assertIsInstance(item[key], str)
        for payment in data["payments"]:
            self.assertIsInstance(payment["amount"], str)

        text = result.content[0].text
        self.assertIn('"outstanding_total": "18036.00"', text)
        self.assertIsNone(re.search(r'"outstanding_total":\s*-?\d', text))
        self.assertIsNone(re.search(r'"paid_total":\s*-?\d', text))
        _assert_no_float(json.loads(text))

        self.assertEqual(
            f"{Decimal(result.structured_content['data']['outstanding_total']):.2f}",
            "18036.00",
        )

    def test_schema_validates_success_and_failure_envelopes(self) -> None:
        schema = envelope_output_schema(StatementOutput)

        success = to_call_tool_result(
            self._execute("billing.statement.read", {"lease_id": LEASE})
        ).structured_content
        jsonschema.validate(instance=success, schema=schema)

        failure = to_call_tool_result(
            self._execute(
                "billing.arrears.calculate",
                {"lease_id": LEASE},
                config=self.flowise_config,
            )
        ).structured_content
        self.assertIsNone(failure["data"])
        jsonschema.validate(instance=failure, schema=schema)

    def test_schema_declares_amounts_as_strings(self) -> None:
        schema = envelope_output_schema(StatementOutput)
        data_schema = schema["properties"]["data"]["anyOf"][0]

        self.assertEqual(data_schema["properties"]["outstanding_total"]["type"], "string")
        self.assertEqual(data_schema["properties"]["invoices"]["items"]["$ref"], "#/$defs/InvoiceOut")
        self.assertEqual(
            schema["$defs"]["InvoiceOut"]["properties"]["total"]["type"], "string"
        )
        self.assertEqual(
            schema["$defs"]["InvoiceOut"]["properties"]["expected_rent"]["anyOf"][0]["type"],
            "string",
        )
        self.assertIn({"type": "null"}, schema["properties"]["data"]["anyOf"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
