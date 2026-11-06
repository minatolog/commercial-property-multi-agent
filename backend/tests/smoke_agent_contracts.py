"""阶段 0 架构骨架自检脚本。

用途：在不安装 LangGraph / FastAPI 的前提下，验证接口契约、配置校验、
Registry、工厂白名单与降级逻辑确实成立。

运行：python backend/tests/smoke_agent_contracts.py
正式 pytest 测试待阶段 1 引入 pytest 后迁移。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Agent 的告警日志统一走 stdout，避免 PowerShell 把 stderr 误判为命令失败
logging.basicConfig(
    level=logging.WARNING,
    format="  [LOG] %(name)s %(message)s",
    stream=sys.stdout,
)

from pydantic import ValidationError

from app.agents.base import (
    AgentContext,
    AgentOutput,
    AgentRequest,
    AgentResult,
    BaseAgent,
    ErrorCode,
    TaskStatus,
)
from app.agents.base.errors import (
    AgentConfigError,
    AgentDisabledError,
    AgentError,
    AgentNotRegisteredError,
    CapabilityConflictError,
    CapabilityUnavailableError,
    DuplicateAgentError,
    IncompatibleAgentError,
    MissingApiKeyError,
    PermissionDeniedError,
    ToolNotAllowedError,
    UnsupportedProviderError,
)
from app.agents.base.registry import AgentRegistry
from app.agents.factory import AGENT_IMPLEMENTATIONS, build_agent, build_registry
from app.config.loader import load_all_agent_configs
from app.config.schema import AgentConfig
from app.llm.adapter import get_adapter
from app.orchestration.coordinator import check_plan_feasibility, summarize_results
from app.tools.base import assert_tool_allowed, assert_tool_invocable

_passed = 0


def check(label: str, condition: bool) -> None:
    global _passed
    if not condition:
        raise AssertionError(f"失败: {label}")
    _passed += 1
    print(f"  [PASS] {label}")


def expect_error(label: str, exc_type: type[BaseException], fn) -> BaseException:
    global _passed
    try:
        fn()
    except exc_type as exc:
        _passed += 1
        print(f"  [PASS] {label} -> {type(exc).__name__}")
        return exc
    except Exception as exc:
        raise AssertionError(
            f"失败: {label} 期望 {exc_type.__name__}，实际 {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"失败: {label} 未抛出 {exc_type.__name__}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


def run_agent(agent: BaseAgent, capability: str) -> AgentResult:
    context = AgentContext(trace_id="trace-smoke", tenant_id="tenant-001")
    request = AgentRequest(task_id="task-smoke", capability=capability, payload={})
    return asyncio.run(agent.handle(request, context))


class _ShadowAgent(BaseAgent):
    """仅用于验证能力冲突检测的最小 Agent。"""

    name = "shadow"
    version = "0.0.1"
    description = "test-only"
    capabilities = frozenset({"lease.query"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        return AgentOutput()


class _VoidAgent(BaseAgent):
    """永远返回 NOT_IMPLEMENTED 的契约测试替身。"""

    name = "void"
    version = "0.1.0"
    description = "test-only"
    capabilities = frozenset({"void.noop"})

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        raise AgentError(
            "test-only not implemented",
            code=ErrorCode.NOT_IMPLEMENTED,
            retryable=False,
        )


class _FakeTool:
    name = "billing.arrears.calculate"
    description = "test-only"
    required_permissions = frozenset({"billing.read"})

    async def invoke(self, payload, context):
        return {}


def main() -> int:
    section("1. 配置加载与 Schema 校验")
    configs = load_all_agent_configs(Path(__file__).resolve().parents[1] / "app" / "config" / "agents")
    check("加载到 5 个 Agent 配置", set(configs) == {"lease", "billing", "compliance", "property", "single"})
    check("lease 启用", configs["lease"].enabled is True)
    check("compliance 默认禁用", configs["compliance"].enabled is False)
    check(
        "billing.temperature 为 null（用于验证参数裁剪）",
        configs["billing"].temperature is None,
    )
    check(
        "每个 Agent 的 prompt_path 互不相同",
        len({c.prompt_path for c in configs.values()}) == len(configs),
    )

    bad_cases = [
        ("拒绝在 YAML 中写入 api_key", {"api_key": "sk-should-not-be-here"}),
        ("拒绝绝对路径 prompt_path", {"prompt_path": "D:/tmp/system.md"}),
        ("拒绝路径穿越 prompt_path", {"prompt_path": "../secret.md"}),
        ("拒绝非法 capability 格式", {"capabilities": ["leasequery"]}),
        ("拒绝 rerank_top_n > top_k", {"retrieval_settings": {"top_k": 2, "rerank_top_n": 5}}),
        ("拒绝未知字段", {"unexpected_field": 1}),
        ("拒绝非法 api_key_env 命名", {"api_key_env": "deepseek-key"}),
    ]
    base = configs["lease"].model_dump(mode="json")
    for label, override in bad_cases:
        expect_error(
            label,
            ValidationError,
            lambda o=override: AgentConfig.model_validate({**base, **o}),
        )

    with tempfile.TemporaryDirectory() as tmp:
        ghost = Path(tmp) / "ghost.yaml"
        ghost.write_text(
            "name: ghost\nversion: 0.1.0\ncapabilities: [ghost.check]\n"
            "model_provider: deepseek\nmodel_name: deepseek-chat\n"
            "prompt_path: app/agents/lease/prompts/system.md\n",
            encoding="utf-8",
        )
        report = build_registry(tmp)
        check("无实现的白名单外配置被跳过而非报错", report.skipped == ("ghost",))
        check("跳过项不进入 Registry", len(report.registry) == 0)
        expect_error(
            "strict 模式拒绝无实现的配置",
            AgentNotRegisteredError,
            lambda: build_registry(tmp, strict=True),
        )

        mismatch = Path(tmp) / "lease.yaml"
        mismatch.write_text(
            "name: wrong_name\nversion: 0.1.0\ncapabilities: [x.y]\n"
            "model_provider: deepseek\nmodel_name: deepseek-chat\n"
            "prompt_path: app/agents/lease/prompts/system.md\n",
            encoding="utf-8",
        )
        expect_error(
            "文件名与 name 不一致时报错",
            AgentConfigError,
            lambda: load_all_agent_configs(tmp),
        )

    section("2. Registry：注册、发现、禁用、冲突")
    report = build_registry()
    registry = report.registry
    check(
        "全部 5 个 Agent 已注册",
        set(report.registered) == {"lease", "billing", "compliance", "property", "single"},
    )
    check("无配置被跳过", report.skipped == ())
    check(
        "可用能力不含被禁用的 compliance.check",
        registry.available_capabilities()
        == frozenset(
            {
                "lease.query",
                "lease.renewal_evaluation",
                "billing.statement",
                "billing.arrears_check",
                "property.work_orders",
                "single.investigate",
            }
        ),
    )
    check("禁用能力可被单独查询", registry.disabled_capabilities() == frozenset({"compliance.check"}))
    check(
        "按能力发现 Agent",
        registry.require_capability("lease.query").descriptor.name == "lease",
    )
    expect_error(
        "能力被禁用时抛 AgentDisabledError",
        AgentDisabledError,
        lambda: registry.require_capability("compliance.check"),
    )
    expect_error(
        "能力不存在时抛 CapabilityUnavailableError",
        CapabilityUnavailableError,
        lambda: registry.require_capability("unknown.capability"),
    )
    expect_error(
        "重复注册同名 Agent 被拒绝",
        DuplicateAgentError,
        lambda: registry.register(build_agent(configs["lease"])),
    )

    shadow_cfg = AgentConfig.model_validate(
        {
            "name": "shadow",
            "version": "0.0.1",
            "capabilities": ["lease.query"],
            "model_provider": "deepseek",
            "model_name": "deepseek-chat",
            "prompt_path": "app/agents/lease/prompts/system.md",
        }
    )
    expect_error(
        "能力已被占用时拒绝注册",
        CapabilityConflictError,
        lambda: registry.register(_ShadowAgent(shadow_cfg)),
    )
    expect_error(
        "接口不兼容的对象被拒绝",
        IncompatibleAgentError,
        lambda: AgentRegistry().register(object()),  # type: ignore[arg-type]
    )

    section("3. Agent 执行与错误约定")
    # 契约层检查不依赖具体业务 Agent 是否已实现：用专门的最小 stub 验证
    # "AgentError -> FAILED 结果"的转换语义。
    stub = _VoidAgent(configs["lease"].model_copy(update={"name": "void"}))
    lease = stub
    result = run_agent(stub, "void.noop")
    check("未实现的 Agent 返回 FAILED 而非抛异常", result.status is TaskStatus.FAILED)
    check("错误码为 NOT_IMPLEMENTED", result.error is not None and result.error.code == ErrorCode.NOT_IMPLEMENTED)
    check("错误可重试标记为 False", result.error is not None and result.error.retryable is False)
    check("结果携带 agent_name / version", result.metadata.agent_name == "void" and result.metadata.agent_version == "0.1.0")
    check("结果携带 trace_id", result.metadata.trace_id == "trace-smoke")
    check("结果记录 latency_ms", result.metadata.latency_ms >= 0)

    undeclared = run_agent(lease, "billing.statement")
    check(
        "调用未声明能力返回 CAPABILITY_NOT_DECLARED",
        undeclared.error is not None
        and undeclared.error.code == ErrorCode.CAPABILITY_NOT_DECLARED,
    )

    compliance = build_agent(configs["compliance"])
    disabled_result = run_agent(compliance, "compliance.check")
    check(
        "被禁用的 Agent 直接调用返回 AGENT_NOT_ENABLED",
        disabled_result.error is not None
        and disabled_result.error.code == ErrorCode.AGENT_NOT_ENABLED,
    )

    section("4. Prompt 与工具授权隔离")
    check("lease 能加载自己的 Prompt", "商业地产租约专员" in lease.prompt_text)
    billing = build_agent(configs["billing"])
    check("billing 能加载自己的 Prompt", "物业费用专员" in billing.prompt_text)
    check(
        "两个 Agent 的 Prompt 内容互不影响",
        "物业费用专员" not in lease.prompt_text and "商业地产租约专员" not in billing.prompt_text,
    )

    assert_tool_allowed(configs["lease"], "lease.lookup")
    check("授权工具调用通过", True)
    expect_error(
        "未授权工具被拒绝",
        ToolNotAllowedError,
        lambda: assert_tool_allowed(configs["lease"], "billing.arrears.calculate"),
    )
    context = AgentContext(trace_id="trace-tool", permissions=frozenset())
    expect_error(
        "缺少业务权限时被拒绝",
        PermissionDeniedError,
        lambda: assert_tool_invocable(configs["billing"], _FakeTool(), context),
    )
    granted = AgentContext(trace_id="trace-tool", permissions=frozenset({"billing.read"}))
    assert_tool_invocable(configs["billing"], _FakeTool(), granted)
    check("具备权限且工具已授权时通过", True)

    section("5. 模型适配层参数裁剪与密钥来源")
    adapter = get_adapter("deepseek")
    lease_params = adapter.build_request_params(configs["lease"])
    billing_params = adapter.build_request_params(configs["billing"])
    check("lease 传递 temperature", lease_params["temperature"] == 0.1)
    check("temperature 为 null 时不下发该参数", "temperature" not in billing_params)
    check("max_tokens 正常下发", billing_params["max_tokens"] == 1024)
    check("model 名称来自配置", lease_params["model"] == "deepseek-chat")
    expect_error(
        "未登记厂商被拒绝",
        UnsupportedProviderError,
        lambda: get_adapter("openai"),
    )

    saved = os.environ.pop("DEEPSEEK_API_KEY", None)
    try:
        expect_error(
            "缺少 API Key 环境变量时报错",
            MissingApiKeyError,
            lambda: adapter.resolve_api_key(configs["lease"]),
        )
        os.environ["DEEPSEEK_API_KEY"] = "smoke-test-placeholder"
        check("API Key 从环境变量读取", adapter.resolve_api_key(configs["lease"]) == "smoke-test-placeholder")
    finally:
        os.environ.pop("DEEPSEEK_API_KEY", None)
        if saved is not None:
            os.environ["DEEPSEEK_API_KEY"] = saved

    section("6. 计划可行性检查与部分成功聚合")
    plan = [
        {"subtask_id": "s1", "capability": "lease.query", "payload": {}, "depends_on": []},
        {"subtask_id": "s2", "capability": "compliance.check", "payload": {}, "depends_on": []},
        {"subtask_id": "s3", "capability": "unknown.capability", "payload": {}, "depends_on": []},
    ]
    feasibility = check_plan_feasibility(registry, plan)
    check("可用能力被正确解析", feasibility.available == {"lease.query": "lease"})
    check("禁用能力被单独标出", feasibility.disabled == {"compliance.check": "compliance"})
    check("缺失能力被单独标出", feasibility.missing == ("unknown.capability",))
    check("存在缺口时计划不可行", feasibility.feasible is False)

    results = [result, disabled_result]
    check(
        "全部失败时聚合为 FAILED",
        summarize_results(results, allow_partial=True) is TaskStatus.FAILED,
    )
    check(
        "禁止部分成功时聚合为 FAILED",
        summarize_results(results, allow_partial=False) is TaskStatus.FAILED,
    )
    check("空结果聚合为 FAILED", summarize_results([], allow_partial=True) is TaskStatus.FAILED)

    section("7. 工厂白名单")
    check("白名单包含五个 Agent", set(AGENT_IMPLEMENTATIONS) == {"lease", "billing", "compliance", "property", "single"})
    non_whitelisted = configs["lease"].model_copy(update={"name": "not_whitelisted"})
    expect_error(
        "白名单外的 name 无法实例化（不触发动态导入）",
        AgentNotRegisteredError,
        lambda: build_agent(non_whitelisted),
    )

    print(f"\n全部通过：{_passed} 项检查")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
