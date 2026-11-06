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
from .investigation_demo import run_investigation
from .orchestration.approval import ApprovalStore
from .rag.library import fixture_catalog
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

    ask = sub.add_parser(
        "ask",
        help="单 Agent + Tools 问答（--provider fake 离线；deepseek 需 DEEPSEEK_API_KEY）",
    )
    ask.add_argument("question", help="自然语言问题，例如“A-301 现在还有多少钱没交？”")
    ask.add_argument(
        "--provider",
        default="fake",
        choices=("fake", "deepseek"),
        help="模型来源：fake=脚本化离线（默认）；deepseek=真实 LangChain 调用",
    )
    ask.add_argument("--principal", default="principal_ops_xinghui", help="可信主体 ID")
    ask.add_argument("--variant", default=None, help="fixture 数据变体")
    ask.add_argument("--budget-tool-calls", type=int, default=8, help="工具调用预算（默认 8）")
    ask.add_argument("--budget-model-calls", type=int, default=6, help="模型调用预算（默认 6）")
    ask.add_argument("--budget-tokens", type=int, default=20000, help="token 总预算（默认 20000）")
    ask.add_argument(
        "--max-tool-rounds",
        type=int,
        default=None,
        help="覆盖配置中的 max_tool_rounds（默认取 YAML）",
    )
    ask.add_argument("--full", action="store_true", help="输出完整 RuntimeResult")

    investigate = sub.add_parser(
        "investigate",
        help="LangGraph 多 Agent 调查工作流（Lease + Billing + Property）",
    )
    investigate.add_argument(
        "question",
        nargs="?",
        default=(
            "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
            "并要求减免费用。请核对合同、账单、付款和工单，分析争议原因，"
            "指出证据与缺失信息，形成供人工审核的处理方案。"
        ),
        help="调查问题（默认使用 C03 争议调查场景）",
    )
    investigate.add_argument(
        "--lease", default="lease_xh_a301_2025", help="租约 ID（默认 A-301 租约）"
    )
    investigate.add_argument("--principal", default="principal_ops_xinghui", help="可信主体 ID")
    investigate.add_argument("--variant", default=None, help="fixture 数据变体")
    investigate.add_argument("--budget-tool-calls", type=int, default=12, help="工具调用预算")
    investigate.add_argument(
        "--budget-tokens",
        type=int,
        default=20000,
        help="token 总预算（默认 20000；仅 --model-provider 非 offline 时生效）",
    )
    investigate.add_argument("--max-revisions", type=int, default=1, help="补查上限（默认 1）")
    investigate.add_argument(
        "--backend",
        default="fixture",
        choices=("fixture", "sqlite"),
        help="数据来源：fixture=JSON（默认）；sqlite=SQLAlchemy 只读数据库（本机无 PostgreSQL）",
    )
    investigate.add_argument("--full", action="store_true", help="输出完整图状态报告")
    investigate.add_argument(
        "--thread-id",
        default=None,
        help="持久线索 ID（使用控制面时必填，用于跨进程恢复）",
    )
    investigate.add_argument(
        "--with-approval",
        action="store_true",
        help="启用控制面（持久 checkpoint + 审批台账），存在差额时暂停等待人工审批",
    )
    investigate.add_argument(
        "--control-dir",
        default=None,
        help="控制面数据目录（默认仓库 data/，已被 .gitignore 排除）",
    )
    investigate.add_argument(
        "--model-provider",
        default="offline",
        choices=("offline", "scripted", "deepseek"),
        help=(
            "领域 Agent 的引擎：offline=确定性（默认）；"
            "scripted=脚本化模型（离线验证模型驱动装配，不代表模型质量）；"
            "deepseek=真实模型（需 DEEPSEEK_API_KEY）"
        ),
    )

    search = sub.add_parser(
        "search",
        help="在已归档合同 PDF 中检索条款（离线 BM25，返回真实页码与原文摘录）",
    )
    search.add_argument("query", help="检索词，例如“租金递增比例”")
    search.add_argument("--document-id", default=None, help="限定文档 ID，例如 doc_xh_a301_contract")
    search.add_argument("--document-version", type=int, default=None, help="限定文档版本")
    search.add_argument("--top-k", type=int, default=3, help="返回条数（默认 3）")
    search.add_argument(
        "--principal", default="principal_ops_xinghui", help="可信主体 ID（决定可见项目范围）"
    )
    search.add_argument(
        "--verify-claim",
        default=None,
        help="附带 L1/L2 引用验证：判断返回的首条证据是否支持该结论",
    )
    search.add_argument(
        "--dir", default=None, help="文档目录（默认 docs/evaluation/documents）"
    )

    approve = sub.add_parser(
        "approve",
        help="按审批请求恢复被暂停的调查（批准只产生 approved_draft，不执行任何业务动作）",
    )
    approve.add_argument("request_id", help="审批请求 ID，例如 apr_xxxxxxxx")
    approve.add_argument(
        "--decision", default="approve", choices=("approve", "reject"), help="审批决定"
    )
    approve.add_argument(
        "--principal", default="principal_property_manager_xinghui", help="审批人（可信主体）"
    )
    approve.add_argument(
        "--draft-version", type=int, required=True, help="被审批的草案版本（必须与请求一致）"
    )
    approve.add_argument("--reason", default=None, help="审批意见")
    approve.add_argument("--thread-id", default=None, help="覆盖恢复所用的 thread_id")
    approve.add_argument("--control-dir", default=None, help="控制面数据目录")
    approve.add_argument(
        "--dry-run", action="store_true", help="只记录决定、不恢复图（用于验证校验逻辑）"
    )
    approve.add_argument("--full", action="store_true", help="输出完整结果")

    pending = sub.add_parser("pending", help="列出待审批请求与已记录的决定")
    pending.add_argument("--control-dir", default=None, help="控制面数据目录")

    evaluate_parser = sub.add_parser(
        "evaluate",
        help="三基线评测（A_deterministic / B_single_agent / C_multi_agent），输出逐题结果与汇总",
    )
    evaluate_parser.add_argument(
        "--baseline",
        default="all",
        choices=("all", "A_deterministic", "B_single_agent", "C_multi_agent"),
        help="要运行的基线（默认全部）",
    )
    evaluate_parser.add_argument(
        "--split",
        default="dev",
        choices=("dev", "heldout"),
        help="数据切分：dev=8 道开发题；heldout=32 道保留题",
    )
    evaluate_parser.add_argument(
        "--max-tool-calls", type=int, default=12, help="全任务工具调用预算（三基线一致）"
    )
    evaluate_parser.add_argument(
        "--out", default=None, help="报告输出目录（默认 docs/evaluation/reports）"
    )
    evaluate_parser.add_argument(
        "--quiet", action="store_true", help="只输出汇总表，不打印逐题 JSON"
    )
    evaluate_parser.add_argument(
        "--model-provider",
        default="offline",
        choices=("offline", "deepseek"),
        help=(
            "B/C 的引擎：offline=确定性规则（默认，历史结果口径）；"
            "deepseek=真实模型（需 DEEPSEEK_API_KEY；A 基线始终离线）"
        ),
    )
    return parser


def _tool_registry(repository: FixtureRepository) -> ToolRegistry:
    """与真实运行一致的只读工具集合（含可用的条款检索工具）。"""

    from .rag.library import build_knowledge_library, fixture_catalog
    from .tools.knowledge_tools import DocumentSearchTool

    registry = ToolRegistry()
    for tool in build_fixture_tools(repository):
        registry.register(tool)
    library = build_knowledge_library(
        fixture_catalog(repository), as_of_date=repository.as_of_date
    )
    if library.indexed:
        # CLI 的 `search` 是人工交互式检索（用户自己指定词），允许不限定租约；
        # Agent 调查路径由 `build_investigation_bundle` 装配，默认要求可信范围。
        registry.register(
            DocumentSearchTool(library.service, library=library, require_scope=False)
        )
    return registry


def _cmd_tools() -> int:
    repository = FixtureRepository.load()
    registry = _tool_registry(repository)
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
    tools = _tool_registry(repository)
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


def _cmd_ask(args: argparse.Namespace) -> int:
    from .single_demo import build_single_bundle, run_single

    bundle = build_single_bundle(
        question=args.question,
        principal_id=args.principal,
        variant=args.variant,
        provider=args.provider,
        max_tool_calls=args.budget_tool_calls,
        max_model_calls=args.budget_model_calls,
        max_total_tokens=args.budget_tokens,
    )
    if args.max_tool_rounds is not None:
        # 覆盖只影响本次运行，不改磁盘 YAML（配置仍是唯一事实源）
        bundle.agent._config = bundle.agent.config.model_copy(  # noqa: SLF001
            update={"max_tool_rounds": args.max_tool_rounds}
        )

    result = asyncio.run(run_single(bundle))
    _print_json(result if args.full else _summarize_single(result, bundle))
    return 0 if result.ok else 2


def _summarize_single(result: RuntimeResult, bundle: Any) -> dict[str, Any]:
    output = result.output or {}
    return {
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "status": result.status.value,
        "provider": bundle.model_client.provider,
        "model": bundle.model_client.model_name,
        "answer": output.get("answer"),
        "stop_reason": output.get("stop_reason"),
        "rounds": output.get("rounds"),
        "usage": output.get("usage"),
        "tool_calls": output.get("tool_calls", []),
        "evidence_count": len(result.evidence),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "entity": item.entity,
                "record_id": item.record_id,
                "tool": item.source_tool,
                "call_id": item.tool_call_id,
            }
            for item in result.evidence
        ],
        "tool_trace_count": len(result.tool_traces),
        "budget": result.budget,
        "warnings": list(result.warnings),
        "error": result.error,
    }


def _scripted_calls_for(args: argparse.Namespace) -> list[tuple[str, dict]]:
    """脚本化模型的工具计划：只覆盖本次问题涉及的领域，且只用本租约的数据。"""

    return [
        ("lease.lookup", {"lease_id": args.lease}),
        ("document.search", {"query": args.question, "top_k": 3}),
        ("billing.statement.read", {"lease_id": args.lease}),
        ("property.work_orders.read", {"lease_id": args.lease}),
    ]


def _model_client_for(args: argparse.Namespace) -> Any:
    from .llm.factory import build_model_client

    provider = getattr(args, "model_provider", "offline")
    calls = _scripted_calls_for(args) if provider == "scripted" else None
    return build_model_client(
        provider,
        scripted_calls=calls,
        summary="已按受控工具结果核对；金额与日期均取自工具输出。",
    )


def _cmd_investigate(args: argparse.Namespace) -> int:
    if args.with_approval:
        return asyncio.run(_investigate_with_control_plane(args))
    from .investigation_demo import build_investigation_bundle

    model_client = _model_client_for(args)
    bundle = build_investigation_bundle(
        principal_id=args.principal,
        variant=args.variant,
        max_tool_calls=args.budget_tool_calls,
        max_revisions=args.max_revisions,
        backend=args.backend,
        engine="llm" if model_client is not None else "deterministic",
        model_client=model_client,
        max_model_calls=0 if model_client is None else 32,
        # token 预算是"模型请求闸门"（Task 024 / Q1）：None = 未配置上限，
        # 0 = 一个 token 都不许用。模型引擎下必须给真实预算，否则连第一次请求
        # 都会被拒绝（这正是 Q1 要求的行为）。
        max_total_tokens=(
            getattr(args, "budget_tokens", 0) if model_client is not None else None
        ),
    )
    result = asyncio.run(
        run_investigation(
            bundle,
            question=args.question,
            lease_id=args.lease,
            thread_id=args.thread_id,
        )
    )
    _print_json(result.report if args.full else _investigation_payload(result, bundle, args))
    return 0


async def _investigate_with_control_plane(args: argparse.Namespace) -> int:
    from .control_plane import control_plane
    from .investigation_demo import build_investigation_bundle, run_investigation
    from .paths import CHECKPOINT_DB, CONTROL_DB

    base = Path(args.control_dir) if args.control_dir else None
    model_client = _model_client_for(args)
    async with control_plane(
        checkpoint_path=(base / "checkpoints" / "graph.sqlite") if base else CHECKPOINT_DB,
        approval_path=(base / "control" / "approval.sqlite") if base else CONTROL_DB,
    ) as plane:
        bundle = build_investigation_bundle(
            principal_id=args.principal,
            variant=args.variant,
            max_tool_calls=args.budget_tool_calls,
            max_revisions=args.max_revisions,
            backend=args.backend,
            control_plane=plane,
            engine="llm" if model_client is not None else "deterministic",
            model_client=model_client,
            max_model_calls=0 if model_client is None else 32,
            max_total_tokens=(
                getattr(args, "budget_tokens", 0) if model_client is not None else None
            ),
        )
        thread_id = args.thread_id or f"thread_{bundle.context.run_id}"
        result = await run_investigation(
            bundle,
            question=args.question,
            lease_id=args.lease,
            thread_id=thread_id,
        )
    _print_json(result.report if args.full else _investigation_payload(result, bundle, args))
    return 0


def _investigation_payload(
    result: Any, bundle: Any, args: argparse.Namespace
) -> dict[str, Any]:
    return {
        "verdict": result.verdict,
        "route": result.route,
        "revision": result.revision,
        "lease_id": args.lease,
        "thread_id": result.thread_id,
        "approval_status": result.approval_status,
        "approval_request": result.approval_request,
        "approved_draft": result.approved_draft,
        "agent_results": [
            {
                "subtask_id": item["subtask_id"],
                "capability": item["capability"],
                "agent": item["agent"],
                "status": item["status"],
            }
            for item in result.results
        ],
        "findings": result.report.get("findings", []),
        "conflicts": list(result.conflicts),
        "missing_information": list(result.missing),
        "failures": list(result.failures),
        "requires_human_review": result.report.get("requires_human_review"),
        "proposed_draft": result.report.get("proposed_draft"),
        "tool_traces": [
            {
                "subtask_id": trace.subtask_id,
                "tool": trace.tool_name,
                "status": trace.status,
                "attempt": trace.attempt,
                "duration_ms": trace.duration_ms,
            }
            for trace in bundle.trace_log.snapshot()
        ],
        "budget": bundle.budget.snapshot(),
        "warnings": list(result.warnings),
        "disclaimer": result.report.get("disclaimer"),
    }


def _cmd_approve(args: argparse.Namespace) -> int:
    return asyncio.run(_approve_async(args))


async def _approve_async(args: argparse.Namespace) -> int:
    from .control_plane import control_plane
    from .investigation_demo import build_investigation_bundle
    from .orchestration.approval import ApprovalError
    from .paths import CHECKPOINT_DB, CONTROL_DB

    base = Path(args.control_dir) if args.control_dir else None
    async with control_plane(
        checkpoint_path=(base / "checkpoints" / "graph.sqlite") if base else CHECKPOINT_DB,
        approval_path=(base / "control" / "approval.sqlite") if base else CONTROL_DB,
    ) as plane:
        bundle = build_investigation_bundle(control_plane=plane)
        try:
            if args.dry_run:
                principal = bundle.repository.principal(args.principal)
                outcome = plane.approval_store.decide(
                    args.request_id,
                    principal_id=args.principal,
                    decision=args.decision,
                    draft_version=args.draft_version,
                    principal=principal,
                    reason=args.reason,
                )
                _print_json(
                    {
                        "dry_run": True,
                        "request": outcome.request.as_dict(),
                        "decided_role": outcome.decided_role,
                        "idempotent": outcome.idempotent,
                    }
                )
                return 0
            result = await bundle.investigator.resume(
                request_id=args.request_id,
                decision=args.decision,
                draft_version=args.draft_version,
                principal_id=args.principal,
                reason=args.reason,
            )
        except ApprovalError as exc:
            print(f"[approval-error] {exc.code}: {exc.message}", file=sys.stderr)
            _print_json({"error": {"code": exc.code.value, "message": exc.message}})
            return 3

    _print_json(
        {
            "request_id": args.request_id,
            "decision": args.decision,
            "principal_id": args.principal,
            "thread_id": result.thread_id,
            "approval_status": result.approval_status,
            "verdict": result.verdict,
            "approval_request": result.approval_request,
            "approved_draft": result.approved_draft,
            "report": result.report,
            "warnings": list(result.warnings),
            "note": "批准只形成 approved_draft，不产生调账/派单等业务副作用",
        }
    )
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    from .control_plane import control_plane
    from .paths import CONTROL_DB

    approval_path = (
        Path(args.control_dir) / "control" / "approval.sqlite"
        if args.control_dir
        else CONTROL_DB
    )
    store = ApprovalStore(approval_path)
    requests = store.pending()
    payload = {
        "pending_count": len(requests),
        "requests": [
            {**item.as_dict(), "decisions": store.decisions(item.request_id)}
            for item in requests
        ],
        "approval_path": str(approval_path),
        "note": "checkpoint 只保存流程位置；审批结论以本台账为准",
    }
    _print_json(payload)
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from .evaluation import evaluate, render_markdown, write_report
    from .evaluation.baselines import BASELINES
    from .llm.factory import build_model_client
    from .paths import REPORT_DIR

    names = list(BASELINES) if args.baseline == "all" else [args.baseline]
    provider = getattr(args, "model_provider", "offline")
    if provider != "offline" and "A_deterministic" in names:
        # A 的定义是"无 Agent、无模型"：混进来会改变基线含义
        names = [name for name in names if name != "A_deterministic"]
        if not names:
            raise ValueError(
                "A_deterministic 不使用模型；请显式指定 B/C 基线或改用 --model-provider offline"
            )
    model_client = build_model_client(provider)
    reports = []
    written: list[str] = []
    for name in names:
        report = asyncio.run(
            evaluate(
                baseline=name,
                split=args.split,
                max_tool_calls=args.max_tool_calls,
                model_client=model_client,
            )
        )
        reports.append(report)
        path = write_report(report, out_dir=args.out)
        written.append(str(path))

    markdown = render_markdown(reports)
    stamp = reports[0].started_at.replace(":", "").replace("-", "")[:15]
    summary_dir = Path(args.out) if args.out else REPORT_DIR
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{stamp}_{args.split}_summary.md"
    summary_path.write_text(markdown, encoding="utf-8")
    written.append(str(summary_path))

    if not args.quiet:
        print(markdown)
    for path in written:
        print(f"[report] {path}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    from .rag.library import build_knowledge_library

    repository = FixtureRepository.load()
    library = build_knowledge_library(
        fixture_catalog(repository),
        as_of_date=repository.as_of_date,
        document_dir=args.dir,
    )
    principal = repository.principal(args.principal)
    project_ids = frozenset(principal.get("project_ids") or [])
    hits = library.service.search(
        args.query,
        document_id=args.document_id,
        document_version=args.document_version,
        project_ids=project_ids,
        top_k=args.top_k,
    )
    payload: dict[str, Any] = {
        "query": args.query,
        "principal_id": args.principal,
        "visible_project_ids": sorted(project_ids),
        "indexed_documents": sorted(library.indexed),
        "missing_documents": list(library.missing_documents),
        "result_count": len(hits),
        "results": [
            {
                "chunk_id": hit.chunk.chunk_id,
                "document_id": hit.chunk.document_id,
                "document_version": hit.chunk.document_version,
                "page": hit.chunk.page,
                "clause_id": hit.chunk.clause_id,
                "excerpt": hit.chunk.text,
                "score": hit.score,
                "project_id": library.service.project_of(
                    hit.chunk.document_id, hit.chunk.document_version
                ),
            }
            for hit in hits
        ],
    }
    if args.verify_claim is not None:
        if not hits:
            payload["citation_check"] = {
                "claim": args.verify_claim,
                "reference_exists": False,
                "note": "没有检索结果，无法验证引用",
            }
        else:
            check = library.service.verify_citation(
                chunk_id=hits[0].chunk.chunk_id, claim=args.verify_claim
            )
            payload["citation_check"] = {
                "claim": args.verify_claim,
                "chunk_id": check.chunk_id,
                "reference_exists": check.reference_exists,
                "supports_claim": check.supports_claim,
                "coverage": check.coverage,
                "method": check.method,
                "acceptable": check.acceptable,
            }
    _print_json(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    from .env import load_project_env

    # 先加载仓库根 / backend 下的 `.env`（不覆盖已导出的环境变量），
    # 否则用户按 .env.example 填好的密钥会静默失效。
    load_project_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "tools":
            return _cmd_tools()
        if args.command == "check":
            return _cmd_check()
        if args.command == "demo":
            return _cmd_demo(args)
        if args.command == "ask":
            return _cmd_ask(args)
        if args.command == "investigate":
            return _cmd_investigate(args)
        if args.command == "approve":
            return _cmd_approve(args)
        if args.command == "pending":
            return _cmd_pending(args)
        if args.command == "evaluate":
            return _cmd_evaluate(args)
        if args.command == "search":
            return _cmd_search(args)
    except (ConfigError, AgentError, FileNotFoundError, ValueError) as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
