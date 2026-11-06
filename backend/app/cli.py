"""命令行入口（离线、无网络、无模型）。

用法（在 `backend/` 下）：

    python -m app.cli --help
    python -m app.cli tools
    python -m app.cli check
    python -m app.cli demo --principal principal_ops_xinghui --lease lease_xh_a301_2025

`demo` 使用 ScriptedToolAgent（Fake Agent）跑通 Runtime → ToolExecutor → fixture，
只证明边界、权限、预算与 Trace，不代表已接入真实模型。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .agents.base.errors import AgentError, ConfigError
from .agents.factory import build_registry
from .demo import DEFAULT_SCRIPT, build_demo_bundle, run_demo
from .fixtures.repository import FixtureRepository
from .runtime.types import RuntimeResult
from .tools.fixture_tools import build_fixture_tools
from .tools.registry import ToolRegistry

__all__ = ["build_parser", "main"]


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _print_json(payload: Any) -> None:
    print(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="commercial-property-multi-agent 的离线 Runtime CLI（无模型、无数据库、无网络）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="列出已注册的只读工具及其权限/超时/重试上限")

    sub.add_parser("check", help="加载 3 个 Agent 配置并校验工厂白名单与工具注册表")

    demo = sub.add_parser("demo", help="运行 fixture 只读演示（ScriptedToolAgent，无模型调用）")
    demo.add_argument(
        "--principal",
        default="principal_ops_xinghui",
        help="可信主体 ID（来自 fixture，模拟服务端会话）",
    )
    demo.add_argument(
        "--variant",
        default=None,
        help="应用 fixture 中的数据变体，例如 v_oct_rent_corrected",
    )
    demo.add_argument(
        "--budget-tool-calls",
        type=int,
        default=10,
        help="本次演示允许的最大工具调用次数（默认 10）",
    )
    demo.add_argument(
        "--fixture",
        default=None,
        help="fixture 路径（默认 docs/evaluation/fixtures/agent_first_v1.json）",
    )
    demo.add_argument(
        "--full",
        action="store_true",
        help="输出完整 RuntimeResult（默认只输出摘要）",
    )
    return parser


def _cmd_tools() -> int:
    repository = FixtureRepository.load()
    registry = ToolRegistry()
    for tool in build_fixture_tools(repository):
        registry.register(tool)
    payload = {
        "dataset_version": repository.dataset_version,
        "as_of_date": repository.as_of_date.isoformat(),
        "tools": list(registry.descriptors()),
    }
    _print_json(payload)
    return 0


def _cmd_check() -> int:
    report = build_registry()
    repository = FixtureRepository.load()
    tools = ToolRegistry()
    for tool in build_fixture_tools(repository):
        tools.register(tool)
    declared = sorted(
        {tool for config in _load_configs() for tool in config.allowed_tools}
    )
    payload = {
        "agents": list(report.registered),
        "skipped": list(report.skipped),
        "capabilities": sorted(report.registry.available_capabilities()),
        "disabled_capabilities": sorted(report.registry.disabled_capabilities()),
        "registered_tools": list(tools.names()),
        "declared_allowed_tools": declared,
        "unimplemented_allowed_tools": sorted(set(declared) - set(tools.names())),
    }
    _print_json(payload)
    return 0


def _load_configs():
    from .config.loader import load_all_agent_configs
    from .paths import CONFIG_DIR

    return load_all_agent_configs(CONFIG_DIR).values()


def _summarize(result: RuntimeResult) -> dict[str, Any]:
    output = result.output or {}
    tool_results = output.get("tool_results", []) or []
    summary: dict[str, Any] = {
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "status": result.status.value,
        "budget": result.budget,
        "tool_calls": [
            {"tool": item["tool"], "call_id": item["call_id"], "attempts": item["attempts"]}
            for item in tool_results
        ],
        "tool_trace_count": len(result.tool_traces),
        "evidence_count": len(result.evidence),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "entity": item.entity,
                "project_id": item.project_id,
                "tool": item.source_tool,
                "call_id": item.tool_call_id,
            }
            for item in result.evidence
        ],
        "warnings": list(result.warnings),
        "error": result.error,
    }
    for item in tool_results:
        tool = item["tool"]
        if tool == "billing.arrears.calculate":
            summary["arrears"] = item["data"]
        elif tool == "lease.lookup":
            summary["lease"] = item["data"]
        elif tool == "property.work_orders.read":
            summary["work_orders"] = item["data"]
        elif tool == "billing.statement.read":
            summary["statement"] = item["data"]
    return summary


def _cmd_demo(args: argparse.Namespace) -> int:
    bundle = build_demo_bundle(
        principal_id=args.principal,
        variant=args.variant,
        max_tool_calls=args.budget_tool_calls,
        fixture_path=args.fixture,
    )
    result = asyncio.run(run_demo(bundle))
    _print_json(result if args.full else _summarize(result))
    return 0 if result.ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "tools":
            return _cmd_tools()
        if args.command == "check":
            return _cmd_check()
        if args.command == "demo":
            return _cmd_demo(args)
    except (ConfigError, AgentError, FileNotFoundError, ValueError) as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
