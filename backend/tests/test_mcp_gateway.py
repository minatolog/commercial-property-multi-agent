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


# --------------------------------------------------------------------------- #
# Task 033B：端到端测试（内存客户端 + stdio 冒烟）
# --------------------------------------------------------------------------- #
#
# 下面只追加测试，不修改 033A 的用例。内存测试用 SDK 的 `Client(server,
# mode="legacy")` 连接 `server.py` 构建的 low-level `Server`（内部走
# `InMemoryTransport`，不起子进程）；最后一个用例用 SDK 的 stdio 客户端
# 以子进程方式启动真实 CLI。

import copy
import io
import sys
from contextlib import redirect_stderr, redirect_stdout

from mcp import Client, ClientSession, StdioServerParameters, stdio_client

from app import cli
from app.mcp_gateway.server import GatewayServer, alias_for, load_gateway


class _AliasCollisionTool(BaseTool):
    """测试专用：注册名与 `billing.statement.read` 折叠出同一个别名。"""

    name = "billing.statement_read"
    version = "1.0.0"
    description = "test-only alias collision"
    required_permissions = frozenset()
    timeout_seconds = 1.0
    max_attempts = 1
    input_model = _EmptyInput
    output_model = _EmptyOutput

    async def invoke(self, payload: _EmptyInput, context: AgentContext) -> ToolInvocation:
        raise AssertionError("别名冲突的测试工具不应被调用")


def _normalized_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """去掉每次调用必然不同的字段，便于比较别名与原名两次调用的等价性。"""

    cleaned = copy.deepcopy(payload)
    cleaned.pop("call_id", None)
    for item in cleaned.get("evidence") or ():
        item.pop("tool_call_id", None)
        item.pop("collected_at", None)
    return cleaned


class TestMcpGatewayEndToEnd(unittest.TestCase):
    """内存客户端端到端：协议外壳 → 执行器 → fixture 的完整链路。"""

    def _gateway(
        self,
        client_name: str = "local_dev",
        *,
        registry: ToolRegistry | None = None,
        config_dir: str | Path | None = None,
    ) -> GatewayServer:
        return load_gateway(
            client_name,
            registry=_registry() if registry is None else registry,
            config_dir=config_dir,
            environ={},  # 隔离进程环境：身份只来自档案
        )

    @staticmethod
    def _run(gateway: GatewayServer, action: Any) -> Any:
        async def scenario() -> Any:
            async with Client(gateway.server, mode="legacy") as client:
                return await action(client)

        return asyncio.run(scenario())

    # 1. tools/list：只列允许的工具、Schema 与 input_model 一致、别名正确
    def test_tools_list_only_allowed_with_aliases_and_schemas(self) -> None:
        local = self._gateway("local_dev")
        listing = self._run(local, lambda client: client.list_tools())

        expected_order = [
            alias_for(name) for name in local.profile.allowed_tools
        ]
        self.assertEqual([tool.name for tool in listing.tools], expected_order)
        self.assertEqual(
            {tool.name for tool in listing.tools},
            {alias_for(name) for name in READ_ONLY_TOOLS},
        )
        self.assertFalse(any("." in tool.name for tool in listing.tools))

        for advertised in listing.tools:
            original = {
                alias_for(name): name for name in local.profile.allowed_tools
            }[advertised.name]
            tool = local.registry.get(original)
            self.assertEqual(
                advertised.input_schema, tool.input_model.model_json_schema()
            )
            self.assertEqual(
                advertised.output_schema,
                envelope_output_schema(tool.output_model),
            )
            self.assertIn(tool.description, advertised.description)
            self.assertIn(f"原名: {original}", advertised.description)
            self.assertNotIn(original, {t.name for t in listing.tools})

        flowise = self._gateway("flowise")
        flowise_listing = self._run(flowise, lambda client: client.list_tools())
        flowise_names = {tool.name for tool in flowise_listing.tools}
        self.assertEqual(
            flowise_names,
            {
                "lease_lookup",
                "billing_statement_read",
                "property_work_orders_read",
                "document_search",
            },
        )
        self.assertNotIn("billing_arrears_calculate", flowise_names)
        self.assertNotIn(
            "billing.arrears.calculate",
            flowise.profile.allowed_tools,
        )

    # 2. 一定经过执行器：Trace 有记录，run_id 是会话 ID，工具名是原名
    def test_call_goes_through_executor_and_trace_records_session(self) -> None:
        gateway = self._gateway("local_dev")
        tool = gateway.registry.get("lease.lookup")
        original_invoke = tool.invoke
        seen_contexts: list[AgentContext] = []

        async def spy(payload: Any, context: AgentContext) -> ToolInvocation:
            seen_contexts.append(context)
            return await original_invoke(payload, context)

        with mock.patch.object(tool, "invoke", spy):
            result = self._run(
                gateway,
                lambda client: client.call_tool(
                    "lease_lookup", {"lease_id": LEASE}
                ),
            )

        self.assertFalse(result.is_error)
        self.assertEqual(len(seen_contexts), 1)
        self.assertEqual(len(gateway.sessions), 1)
        session = gateway.sessions[0]
        self.assertEqual(session.identity.client_name, "local_dev")
        self.assertEqual(seen_contexts[0].run_id, session.identity.session_id)

        traces = session.executor.trace_log.snapshot()
        self.assertEqual(len(traces), 1)
        trace = traces[0]
        self.assertEqual(trace.tool_name, "lease.lookup")  # Trace 记录原名
        self.assertEqual(trace.run_id, session.identity.session_id)
        self.assertTrue(trace.run_id.startswith("mcp_local_dev_"))
        self.assertEqual(trace.status, "ok")
        self.assertEqual(trace.call_id, result.structured_content["call_id"])

    # 3. 保留键：直接拒绝，不执行工具，也没有该工具的执行记录
    def test_reserved_keys_are_denied_without_execution(self) -> None:
        gateway = self._gateway("local_dev")
        tool = gateway.registry.get("lease.lookup")
        invoked = False

        async def spy(payload: Any, context: AgentContext) -> ToolInvocation:
            nonlocal invoked
            invoked = True
            raise AssertionError("保留键调用不应进入工具")

        malicious_arguments = [
            {"lease_id": LEASE, "principal_id": PRINCIPAL},
            {"lease_id": LEASE, "permissions": ["billing.read"]},
            {"lease_id": LEASE, "project_ids": ["prj_jinlan"]},
        ]
        with mock.patch.object(tool, "invoke", spy):
            for arguments in malicious_arguments:
                result = self._run(
                    gateway,
                    lambda client, args=arguments: client.call_tool(
                        "lease_lookup", args
                    ),
                )
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["status"], "denied")
                self.assertEqual(
                    result.structured_content["error"]["code"],
                    ErrorCode.PERMISSION_DENIED.value,
                )
                self.assertIsNone(result.structured_content["data"])

        self.assertFalse(invoked)
        session = gateway.sessions[0]
        self.assertEqual(session.executor.trace_log.snapshot(), ())

    # 4. 不在档案中的工具 → isError + TOOL_NOT_ALLOWED（原名与别名一致）
    def test_tool_not_in_profile_is_denied(self) -> None:
        gateway = self._gateway("flowise")

        original = self._run(
            gateway,
            lambda client: client.call_tool(
                "billing.arrears.calculate", {"lease_id": LEASE}
            ),
        )
        alias = self._run(
            gateway,
            lambda client: client.call_tool(
                "billing_arrears_calculate", {"lease_id": LEASE}
            ),
        )

        for result in (original, alias):
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["status"], "denied")
            self.assertEqual(
                result.structured_content["error"]["code"],
                ErrorCode.TOOL_NOT_ALLOWED.value,
            )

    # 5. 超出会话预算 → BUDGET_EXHAUSTED；新会话额度重新计算
    def test_session_budget_is_exhausted_and_reset_per_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "budget_one",
                budget={"max_tool_calls_per_session": 1},
            )
            gateway = self._gateway(
                "budget_one", config_dir=tmp
            )

        async def two_calls(client: Any) -> tuple[Any, Any]:
            first = await client.call_tool("lease_lookup", {"lease_id": LEASE})
            second = await client.call_tool("lease_lookup", {"lease_id": LEASE})
            return first, second

        first, second = self._run(gateway, two_calls)
        self.assertFalse(first.is_error)
        self.assertTrue(second.is_error)
        self.assertEqual(
            second.structured_content["status"], "budget_exhausted"
        )
        self.assertEqual(
            second.structured_content["error"]["code"],
            ErrorCode.BUDGET_EXHAUSTED.value,
        )

        # 新连接 = 新会话：同样的 Server，额度重新从档案计算
        third = self._run(
            gateway,
            lambda client: client.call_tool("lease_lookup", {"lease_id": LEASE}),
        )
        self.assertFalse(third.is_error)
        self.assertEqual(len(gateway.sessions), 2)
        first_session, second_session = gateway.sessions
        self.assertNotEqual(
            first_session.identity.session_id, second_session.identity.session_id
        )
        self.assertEqual(first_session.budget.snapshot().used_tool_calls, 1)
        self.assertEqual(second_session.budget.snapshot().used_tool_calls, 1)
        self.assertEqual(second_session.budget.snapshot().max_tool_calls, 1)

    # 6. 跨项目数据 → 范围拒绝
    def test_cross_project_query_is_denied(self) -> None:
        # 档案主体 principal_ops_xinghui 只有 prj_xinghui；租约属于 prj_jinlan
        gateway = self._gateway("local_dev")
        result = self._run(
            gateway,
            lambda client: client.call_tool(
                "billing_statement_read", {"lease_id": "lease_jl_b101_2025"}
            ),
        )

        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["status"], "denied")
        self.assertEqual(
            result.structured_content["error"]["code"],
            ErrorCode.PROJECT_SCOPE_DENIED.value,
        )
        self.assertIsNone(result.structured_content["data"])

    # 6b.（复查 P2-1）文档检索点名越权租约 / 文档 → 范围拒绝，不再是 ok + 0 条
    def test_document_search_cross_project_target_is_denied(self) -> None:
        # 用网关自己的真实注册表（含文档库与 PDF 索引）；`_registry()` 里的
        # `document.search` 只是占位，测不到真实的检索与范围判断。
        gateway = load_gateway("local_dev", environ={})
        cases = [
            {"query": "免租期", "lease_id": "lease_jl_b101_2025"},
            {"query": "免租期", "lease_id": LEASE, "document_ids": ["doc_jl_b101_contract"]},
            {"query": "免租期", "document_id": "doc_jl_b101_contract"},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self._run(
                    gateway,
                    lambda client, a=arguments: client.call_tool("document_search", a),
                )
                self.assertTrue(result.is_error)
                envelope = result.structured_content
                self.assertEqual(envelope["status"], "denied")
                self.assertEqual(envelope["error"]["code"], ErrorCode.PROJECT_SCOPE_DENIED.value)
                self.assertIsNone(envelope["data"])
                self.assertEqual(envelope["evidence"], [])

        # 本项目租约照常可检索，证据带出页码 / 条款号（复查 P3-5 的证据路径）
        ok = self._run(
            gateway,
            lambda client: client.call_tool(
                "document_search", {"query": "免租期", "lease_id": LEASE}
            ),
        )
        self.assertFalse(ok.is_error)
        data = ok.structured_content["data"]
        self.assertGreater(data["result_count"], 0)
        for item in data["results"]:
            self.assertEqual(item["project_id"], "prj_xinghui")
            self.assertIsInstance(item["page"], int)
            self.assertTrue(item["clause_id"])
        evidence = ok.structured_content["evidence"]
        self.assertEqual(len(evidence), data["result_count"])
        self.assertTrue(all("page" in e["fields"] and "clause_id" in e["fields"] for e in evidence))

    # 6c.（复查 P2-2）未知工具名：报错，且绝不能被路由到任何已允许的工具
    def test_unknown_tool_name_is_rejected_without_execution(self) -> None:
        gateway = self._gateway("local_dev")
        invoked: list[str] = []
        patches = []
        for name in gateway.profile.allowed_tools:
            tool = gateway.registry.get(name)

            async def spy(payload: Any, context: AgentContext, _n: str = name) -> ToolInvocation:
                invoked.append(_n)
                raise AssertionError(f"未知工具名不应执行 {_n}")

            patches.append(mock.patch.object(tool, "invoke", spy))
        for p in patches:
            p.start()
        try:
            for unknown in ("does_not_exist", "billing.statement.write", "Billing_Statement_Read"):
                with self.subTest(name=unknown):
                    result = self._run(
                        gateway,
                        lambda client, n=unknown: client.call_tool(n, {"lease_id": LEASE}),
                    )
                    self.assertTrue(result.is_error)
                    envelope = result.structured_content
                    self.assertNotEqual(envelope["status"], "ok")
                    self.assertIn(
                        envelope["error"]["code"],
                        {ErrorCode.TOOL_NOT_FOUND.value, ErrorCode.TOOL_NOT_ALLOWED.value},
                    )
                    self.assertIsNone(envelope["data"])
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(invoked, [])
        for session in gateway.sessions:
            self.assertTrue(
                all(t.status != "ok" for t in session.executor.trace_log.snapshot())
            )

    # 7. 工具执行失败 → isError: true 且 status 不是 ok
    def test_tool_failure_is_not_reported_as_success(self) -> None:
        gateway = self._gateway("local_dev")
        tool = gateway.registry.get("lease.lookup")

        async def boom(payload: Any, context: AgentContext) -> ToolInvocation:
            raise RuntimeError("fixture 工具内部异常")

        with mock.patch.object(tool, "invoke", boom):
            result = self._run(
                gateway,
                lambda client: client.call_tool(
                    "lease_lookup", {"lease_id": LEASE}
                ),
            )

        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["status"], "error")
        self.assertNotEqual(result.structured_content["status"], "ok")
        self.assertEqual(
            result.structured_content["error"]["code"],
            ErrorCode.INTERNAL_ERROR.value,
        )
        session = gateway.sessions[0]
        traces = session.executor.trace_log.snapshot()
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].status, "error")

    # 8. 金额在 structuredContent 中是精确到分的字符串
    def test_amounts_are_strings_to_the_cent(self) -> None:
        gateway = self._gateway("local_dev")
        result = self._run(
            gateway,
            lambda client: client.call_tool(
                "billing_statement_read", {"lease_id": LEASE}
            ),
        )

        self.assertFalse(result.is_error)
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

        text = result.content[0].text
        self.assertIn('"outstanding_total": "18036.00"', text)
        _assert_no_float(json.loads(text))
        _assert_no_float(result.structured_content)

    # 9. 别名与原名调用结果相同（只忽略每次调用必然不同的标识/时间）
    def test_alias_and_original_return_the_same_envelope(self) -> None:
        gateway = self._gateway("local_dev")

        async def both(client: Any) -> tuple[Any, Any]:
            by_alias = await client.call_tool(
                "lease_lookup", {"lease_id": LEASE}
            )
            by_original = await client.call_tool(
                "lease.lookup", {"lease_id": LEASE}
            )
            return by_alias, by_original

        by_alias, by_original = self._run(gateway, both)
        self.assertFalse(by_alias.is_error)
        self.assertFalse(by_original.is_error)
        self.assertEqual(
            _normalized_envelope(by_alias.structured_content),
            _normalized_envelope(by_original.structured_content),
        )
        traces = gateway.sessions[0].executor.trace_log.snapshot()
        self.assertEqual(
            [trace.tool_name for trace in traces],
            ["lease.lookup", "lease.lookup"],
        )

    # 10. 档案配置错误 → Server 构建失败 / CLI 非零退出
    def test_invalid_profile_fails_at_build_and_cli(self) -> None:
        with self.assertRaises(AgentConfigError):
            self._gateway("no_such_client")

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            code = cli.main(
                [
                    "mcp-serve",
                    "--transport",
                    "stdio",
                    "--client",
                    "no_such_client",
                ]
            )
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("no_such_client", buffer.getvalue())

        # 别名冲突同样在构建 Server 时失败
        registry = _registry()
        registry.register(_AliasCollisionTool())
        with self.assertRaises(AgentConfigError) as caught:
            load_gateway(
                "local_dev", registry=registry, environ={}
            )
        message = str(caught.exception)
        self.assertIn("billing.statement.read", message)
        self.assertIn("billing.statement_read", message)

    # 复查 P3-5：CLI 启动失败时 stdout 必须为空（stdout 只留给协议）
    def test_cli_startup_failure_keeps_stdout_empty(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["mcp-serve", "--transport", "stdio", "--client", "no_such_client"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("no_such_client", err.getvalue())

    # 复查 P3-4：主体不存在 → 启动期失败，而不是服务起来后每次调用都失败
    def test_unknown_principal_fails_at_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(Path(tmp), "ghost_owner", principal_id="principal_ghost")
            with self.assertRaises(AgentConfigError) as caught:
                load_gateway("ghost_owner", registry=_registry(), config_dir=tmp, environ={})
            self.assertIn("principal_ghost", str(caught.exception))
            self.assertIn("profile", str(caught.exception))
        with self.assertRaises(AgentConfigError) as caught:
            load_gateway(
                "local_dev", registry=_registry(), environ={"DEMO_PRINCIPAL_ID": "principal_ghost"}
            )
        self.assertIn("env:DEMO_PRINCIPAL_ID", str(caught.exception))

    # 复查 P3-1：启动身份如实暴露主体与来源（CLI 启动提示据此打印）
    def test_startup_identity_reports_principal_and_source(self) -> None:
        identity = self._gateway("local_dev").startup_identity
        self.assertEqual((identity.principal_id, identity.source), (PRINCIPAL, "profile"))
        overridden = load_gateway(
            "local_dev", registry=_registry(), environ={"DEMO_PRINCIPAL_ID": "principal_finance_xinghui"}
        ).startup_identity
        self.assertEqual(
            (overridden.principal_id, overridden.source),
            ("principal_finance_xinghui", "env:DEMO_PRINCIPAL_ID"),
        )

    # 复查 P3-5：大小写变体 / 嵌套的保留键同样不能执行（由 input_model 的 extra=forbid 挡住）
    def test_reserved_key_variants_are_rejected_without_execution(self) -> None:
        gateway = self._gateway("local_dev")
        tool = gateway.registry.get("lease.lookup")
        calls: list[Any] = []

        async def spy(payload: Any, context: AgentContext) -> ToolInvocation:
            calls.append(payload)
            raise AssertionError("不应执行")

        variants = [
            {"lease_id": LEASE, "Principal_ID": "principal_finance_jinlan"},
            {"lease_id": LEASE, "PROJECT_IDS": ["prj_jinlan"]},
            {"lease_id": LEASE, "filters": {"project_ids": ["prj_jinlan"]}},
            {"lease_id": LEASE, "metadata": {"principal_id": "principal_finance_jinlan"}},
        ]
        stderr = io.StringIO()
        with mock.patch.object(tool, "invoke", spy), redirect_stderr(stderr):
            for arguments in variants:
                with self.subTest(arguments=arguments):
                    result = self._run(
                        gateway,
                        lambda client, a=arguments: client.call_tool("lease_lookup", a),
                    )
                    self.assertTrue(result.is_error)
                    self.assertNotEqual(result.structured_content["status"], "ok")
                    self.assertIsNone(result.structured_content["data"])
        self.assertEqual(calls, [])

    # 复查 P3-3：顶层保留键的预拦截会在 stderr 留痕
    def test_reserved_key_denial_is_logged_to_stderr(self) -> None:
        gateway = self._gateway("local_dev")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self._run(
                gateway,
                lambda client: client.call_tool(
                    "lease_lookup", {"lease_id": LEASE, "permissions": ["billing.write"]}
                ),
            )
        log = stderr.getvalue()
        self.assertIn("拒绝", log)
        self.assertIn("permissions", log)
        self.assertIn(gateway.sessions[-1].identity.session_id, log)

    # 复查 P3-2：会话快照有上限，不随连接数无限增长
    def test_session_history_is_bounded(self) -> None:
        from app.mcp_gateway import server as server_module

        with mock.patch.object(server_module, "_SESSION_HISTORY", 3):
            gateway = self._gateway("local_dev")
        for _ in range(5):
            self._run(gateway, lambda client: client.list_tools())
        self.assertEqual(len(gateway.sessions), 3)


class TestMcpGatewayUnexpectedError(unittest.TestCase):
    """网关自身的未预期异常也不能变成成功（Claude Code 复核 033B 时补充）。

    第 7 点测的是执行器内部的工具失败；这里测执行器**之外**、网关处理器里
    抛出的异常：必须返回 `isError` 信封，且不把 Python 堆栈发给客户端。
    """

    # 复用端到端用例的连接辅助方法（不继承，避免父类用例被重复收集）
    _gateway = TestMcpGatewayEndToEnd._gateway
    _run = staticmethod(TestMcpGatewayEndToEnd._run)

    def test_gateway_exception_is_error_without_traceback(self) -> None:
        gateway = self._gateway("local_dev")

        async def boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("gateway-secret-detail")

        stderr = io.StringIO()
        with mock.patch.object(ToolExecutor, "execute", boom), redirect_stderr(stderr):
            result = self._run(
                gateway,
                lambda client: client.call_tool("lease_lookup", {"lease_id": LEASE}),
            )

        self.assertTrue(result.is_error)
        envelope = result.structured_content
        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["error"]["code"], ErrorCode.INTERNAL_ERROR.value)
        self.assertIsNone(envelope["data"])
        client_text = result.content[0].text
        self.assertNotIn("gateway-secret-detail", client_text)
        self.assertNotIn("Traceback", client_text)
        # 堆栈只写服务端 stderr
        self.assertIn("gateway-secret-detail", stderr.getvalue())


class TestMcpGatewayStdio(unittest.TestCase):
    """stdio 冒烟：真实 CLI 子进程 + SDK stdio 客户端。"""

    def test_stdio_cli_smoke(self) -> None:
        backend = Path(__file__).resolve().parents[1]
        errlog = tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", suffix=".log", delete=False
        )
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-m",
                    "app.cli",
                    "mcp-serve",
                    "--transport",
                    "stdio",
                    "--client",
                    "local_dev",
                ],
                cwd=str(backend),
                env={
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1",
                    "DEMO_PRINCIPAL_ID": "",
                },
            )

            async def scenario() -> tuple[Any, Any]:
                async with stdio_client(params, errlog=errlog) as (
                    read_stream,
                    write_stream,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        listing = await session.list_tools()
                        result = await session.call_tool(
                            "lease_lookup", {"lease_id": LEASE}
                        )
                        return listing, result

            listing, result = asyncio.run(
                asyncio.wait_for(scenario(), timeout=120)
            )
            errlog.seek(0)
            stderr = errlog.read()
        finally:
            errlog.close()
            Path(errlog.name).unlink(missing_ok=True)

        self.assertEqual(
            {tool.name for tool in listing.tools},
            {alias_for(name) for name in READ_ONLY_TOOLS},
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "ok")
        self.assertEqual(result.structured_content["data"]["lease_id"], LEASE)
        self.assertIn(DEV_MODE_WARNING, stderr)
        self.assertIn("开发模式", stderr)
        self.assertIn("不可用于生产", stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
