"""命令行入口（离线、无网络、无模型）。

用法（在 `backend/` 下）：

    python -m app.cli --help
    python -m app.cli tools
    python -m app.cli check
    python -m app.cli demo --principal principal_ops_xinghui --lease lease_xh_a301_2025
    python -m app.cli mcp-serve --transport stdio --client local_dev

`demo` 使用 ScriptedToolAgent（Fake Agent）跑通 Runtime → ToolExecutor → fixture，
只证明边界、权限、预算与 Trace，不代表已接入真实模型。

退出码（Task 031 / 2.4，`--help` 与 `backend/README.md` 同步说明）：

| 码 | 含义 |
|---|---|
| 0 | 成功（含"部分完成但有明确警告"的 partial） |
| 1 | 业务结果失败，例如有目标却零事实、调查没有任何子任务结果 |
| 2 | 用法或配置错误（未知参数、非法配置、无法确定可信目标等） |
| 3 | 审批错误（请求不存在、版本不匹配、越权、过期等） |
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .agents.base.contracts import TaskStatus
from .agents.base.errors import AgentError, ConfigError
from .agents.factory import build_registry
from .demo import build_demo_bundle, run_demo
from .fixtures.repository import FixtureRepository
from .investigation_demo import run_investigation
from .orchestration.approval import ApprovalStore
from .rag.library import fixture_catalog
from .runtime.types import RuntimeResult
from .tools.fixture_tools import build_fixture_tools
from .tools.registry import ToolRegistry

__all__ = [
    "EXIT_APPROVAL",
    "EXIT_BUSINESS_FAILURE",
    "EXIT_OK",
    "EXIT_USAGE",
    "build_parser",
    "main",
]

#: 退出码（Task 031 / 2.4）：分开语义，脚本与人工都能判断"失败在哪一层"
EXIT_OK = 0
EXIT_BUSINESS_FAILURE = 1
EXIT_USAGE = 2
EXIT_APPROVAL = 3

#: 与 API 相同的演示主体默认值（`DEMO_PRINCIPAL_ID` 未设置时使用）
DEFAULT_PRINCIPAL_FALLBACK = "principal_ops_xinghui"
#: 审批人默认值：approve 的主体必须是能签署的主体，不能复用运营只读主体
DEFAULT_APPROVER_FALLBACK = "principal_property_manager_xinghui"

_EXIT_EPILOG = (
    "退出码：0=成功；1=业务结果失败（例如有目标但零事实）；"
    "2=用法或配置错误；3=审批错误。"
)


class UsageError(Exception):
    """命令行用法错误（退出码 2）：与业务结果失败（退出码 1）明确区分。"""


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
        description=(
            "commercial-property-multi-agent 的 Runtime CLI（默认离线、无模型、无网络；"
            "investigate --backend postgresql 读取本地 PostgreSQL）"
        ),
        epilog=_EXIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="列出已注册的只读工具及其权限/超时/重试上限")

    sub.add_parser("check", help="加载 3 个 Agent 配置并校验工厂白名单、模型配置与工具注册表")

    demo = sub.add_parser(
        "demo",
        help="运行 fixture 只读演示（ScriptedToolAgent，无模型调用）",
        epilog=_EXIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    demo.add_argument(
        "--principal",
        default=None,
        help="可信主体 ID（默认读取 DEMO_PRINCIPAL_ID，否则 principal_ops_xinghui）",
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
        help="单 Agent + Tools 问答（默认 scripted 离线模型；deepseek 需 DEEPSEEK_API_KEY）",
        epilog=_EXIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ask.add_argument("question", help="自然语言问题，例如“A-301 现在还有多少钱没交？”")
    ask.add_argument(
        "--model-provider",
        default=None,
        choices=("offline", "scripted", "deepseek"),
        help=(
            "模型来源：scripted=脚本化模型（默认，离线，仅证明装配）；"
            "deepseek=真实 LangChain 调用（需 DEEPSEEK_API_KEY）；"
            "offline=无模型（ask 必须有模型，传入 offline 会以用法错误退出）"
        ),
    )
    ask.add_argument(
        "--provider",
        default=None,
        choices=("fake", "deepseek"),
        help="[已弃用] 旧参数：fake→scripted、deepseek→deepseek；请改用 --model-provider",
    )
    ask.add_argument(
        "--principal",
        default=None,
        help="可信主体 ID（默认读取 DEMO_PRINCIPAL_ID，否则 principal_ops_xinghui）",
    )
    ask.add_argument(
        "--lease",
        default=None,
        help=(
            "可信目标租约 ID（与 investigate 同名同语义）；省略时从问题文本中的"
            "商铺编号解析（如 A-301 / A301），解析不到且问题涉及业务取数时直接失败"
        ),
    )
    ask.add_argument(
        "--unit",
        default=None,
        help="可信目标商铺编号（如 A-301）或商铺 ID；与 --lease 同时给出时必须一致",
    )
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
        epilog=_EXIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    investigate.add_argument(
        "--principal",
        default=None,
        help="可信主体 ID（默认读取 DEMO_PRINCIPAL_ID，否则 principal_ops_xinghui）",
    )
    investigate.add_argument("--variant", default=None, help="fixture 数据变体")
    investigate.add_argument("--budget-tool-calls", type=int, default=12, help="工具调用预算")
    investigate.add_argument(
        "--budget-model-calls",
        type=int,
        default=32,
        help="模型调用预算（默认 32；仅 --model-provider 非 offline 时生效）",
    )
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
        choices=("fixture", "sqlite", "postgresql"),
        help=(
            "数据来源：fixture=JSON（默认）；sqlite=SQLAlchemy 只读数据库；"
            "postgresql=环境变量 COMMERCIAL_DB_URL 指向的已迁移库（只读，连接串不进命令行）"
        ),
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
            "deepseek=真实模型（需 DEEPSEEK_API_KEY，按各 Agent 自己的 YAML 建客户端）"
        ),
    )

    investigate.add_argument(
        "--planner",
        default=None,
        choices=("rule", "llm", "hybrid"),
        help=(
            "规划模式（默认读 app/config/planner.yaml，当前为 rule）："
            "rule=词表规则（零模型调用）；llm=LLM Supervisor；"
            "hybrid=规则能确定就用规则，否则交给 Supervisor"
        ),
    )
    investigate.add_argument(
        "--planner-provider",
        default=None,
        choices=("scripted", "deepseek"),
        help=(
            "规划模型来源（仅 llm/hybrid）：scripted=脚本化（离线，只证明链路）；"
            "deepseek=真实模型（planner.yaml 的参数）。省略时沿用 --model-provider"
        ),
    )
    investigate.add_argument(
        "--hybrid-multi-domain",
        default=None,
        choices=("rule", "llm"),
        help="hybrid 下规则命中多个领域时：llm=交给模型复核（默认）；rule=直接用规则",
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
        "--principal",
        default=None,
        help="可信主体 ID（默认读取 DEMO_PRINCIPAL_ID；决定可见项目范围）",
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
        epilog=(
            _EXIT_EPILOG
            + "\n--dry-run 只做校验：不写入审批台账、不恢复图；恢复使用的 thread_id "
            "一律取自台账中的审批请求，命令行不能覆盖。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    approve.add_argument("request_id", help="审批请求 ID，例如 apr_xxxxxxxx")
    approve.add_argument(
        "--decision", default="approve", choices=("approve", "reject"), help="审批决定"
    )
    approve.add_argument(
        "--principal",
        default=None,
        help="审批人（可信主体；默认读取 DEMO_PRINCIPAL_ID，无审批权限时退回默认审批人）",
    )
    approve.add_argument(
        "--draft-version", type=int, required=True, help="被审批的草案版本（必须与请求一致）"
    )
    approve.add_argument("--reason", default=None, help="审批意见")
    approve.add_argument("--control-dir", default=None, help="控制面数据目录")
    approve.add_argument(
        "--dry-run",
        action="store_true",
        help="只做校验：读取并校验审批请求，不写入台账、不恢复图（可安全预演）",
    )
    approve.add_argument("--full", action="store_true", help="输出完整结果")

    pending = sub.add_parser("pending", help="列出待审批请求与已记录的决定")
    pending.add_argument("--control-dir", default=None, help="控制面数据目录")

    mcp_serve = sub.add_parser(
        "mcp-serve",
        help="以 MCP stdio 服务开放只读工具（开发模式固定主体，不可用于生产）",
        epilog=_EXIT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mcp_serve.add_argument(
        "--transport",
        default="stdio",
        choices=("stdio",),
        help="传输方式（本版本只支持 stdio；stdout 只承载 MCP 协议）",
    )
    mcp_serve.add_argument(
        "--client",
        required=True,
        help="客户端档案名（app/config/mcp_clients/<name>.yaml，例如 local_dev / flowise）",
    )

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
    evaluate_parser.add_argument(
        "--suite",
        default="baselines",
        choices=("baselines", "planner"),
        help=(
            "baselines=三基线（默认）；planner=规划层评测（planner_paraphrase 用例，"
            "只运行规划器，对比 rule/llm/hybrid）"
        ),
    )
    evaluate_parser.add_argument(
        "--planner",
        default=None,
        choices=("rule", "llm", "hybrid"),
        help=(
            "baselines 套件：C_multi_agent 的规划模式（默认读 planner.yaml，当前 rule；"
            "非 rule 时只运行 C）。planner 套件：只跑这一种配置（默认四种全跑）"
        ),
    )
    evaluate_parser.add_argument(
        "--planner-provider",
        default=None,
        choices=("scripted", "deepseek"),
        help="规划模型来源（llm/hybrid）：scripted=离线脚本（只证明链路）；deepseek=真实模型",
    )
    evaluate_parser.add_argument(
        "--hybrid-multi-domain",
        default=None,
        choices=("rule", "llm"),
        help="hybrid 下规则命中多个领域时：llm=交给模型复核；rule=直接用规则",
    )
    evaluate_parser.add_argument(
        "--planner-cases",
        default="v1",
        choices=("v1", "v2", "all"),
        help="planner 套件的用例版本（默认 v1；all=v1 与 v2 各跑一遍）",
    )
    return parser


# ---------------------------------------------------------------- 身份来源（2.4.5）


def _resolve_identity(
    args: argparse.Namespace, *, fallback: str, require_approver: bool = False
) -> None:
    """解析 `--principal`：显式传入=开发模式自报；否则与 API 一样读环境变量。

    Task 031 / 2.4.5：命令行自报身份只能用于演示/评测，必须向 stderr 明示，
    并把 `identity_source` 记入报告元数据（不是认证，也不是生产身份来源）。
    """

    explicit = getattr(args, "principal", None)
    if explicit:
        print(
            "[dev-mode] 开发模式：命令行自报身份（--principal），不可用于生产",
            file=sys.stderr,
        )
        args.principal = explicit
        args.identity_source = "cli_flag"
        return

    env_value = os.environ.get("DEMO_PRINCIPAL_ID", "").strip()
    if env_value:
        args.principal = env_value
        args.identity_source = "env:DEMO_PRINCIPAL_ID"
    else:
        args.principal = fallback
        args.identity_source = "demo_default"

    if require_approver and not _can_decide_approval(args.principal):
        print(
            f"[dev-mode] {args.principal} 没有审批权限，approve 退回默认审批人 {fallback}",
            file=sys.stderr,
        )
        args.principal = fallback
        args.identity_source = f"{args.identity_source}:approver_fallback"


def _can_decide_approval(principal_id: str) -> bool:
    try:
        record = FixtureRepository.load().principal(principal_id)
    except AgentError:
        return False
    return bool(record.get("can_decide_approval")) and "approval.decide" in (
        record.get("permissions") or []
    )


# ---------------------------------------------------------------- 工具与配置


def _tool_registry(repository: FixtureRepository) -> ToolRegistry:
    """与真实运行一致的只读工具集合（含可用的条款检索工具）。"""

    from .rag.library import build_knowledge_library
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
    return EXIT_OK


def _load_configs():
    from .config.loader import load_all_agent_configs
    from .paths import CONFIG_DIR

    return load_all_agent_configs(CONFIG_DIR)


def _cmd_check() -> int:
    from .llm.factory import validate_model_config

    report = build_registry()
    repository = FixtureRepository.load()
    tools = _tool_registry(repository)
    configs = _load_configs()
    declared = sorted({tool for config in configs.values() for tool in config.allowed_tools})
    # Task 031 / 2.5：模型配置（provider/model/参数/密钥变量名）逐 Agent 校验并输出；
    # 非法配置在这里就失败（退出码 2），不会等到运行时才静默回退。
    models = {
        name: validate_model_config(config) for name, config in sorted(configs.items())
    }
    # Task 031 / 2.6：检索配置只描述真实能力（当前只有 BM25，参数尚未接工具）。
    retrieval = {
        name: (
            config.retrieval_settings.model_dump(mode="json")
            if config.retrieval_settings is not None
            else None
        )
        for name, config in sorted(configs.items())
    }
    # Task 034：规划器配置同样在启动期校验（非法即 exit 2）
    from .config.loader import load_planner_config

    planner_config = load_planner_config()
    payload = {
        "planner": {
            "mode": planner_config.mode,
            "hybrid_multi_domain": planner_config.hybrid_multi_domain,
            "max_domains": planner_config.max_domains,
            "prompt_path": planner_config.prompt_path,
            "model": validate_model_config(planner_config),
        },
        "agents": list(report.registered),
        "skipped": list(report.skipped),
        "capabilities": sorted(report.registry.available_capabilities()),
        "disabled_capabilities": sorted(report.registry.disabled_capabilities()),
        "registered_tools": list(tools.names()),
        "declared_allowed_tools": declared,
        "unimplemented_allowed_tools": sorted(set(declared) - set(tools.names())),
        "models": models,
        "retrieval_settings": retrieval,
    }
    _print_json(payload)
    return EXIT_OK


def _summarize(result: RuntimeResult, *, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    output = result.output or {}
    tool_results = output.get("tool_results", []) or []
    summary: dict[str, Any] = {
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "status": result.status.value,
        "identity": identity,
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


def _identity_payload(bundle: Any, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "principal_id": bundle.trusted.principal_id,
        "identity_source": getattr(bundle, "identity_source", getattr(args, "identity_source", "")),
    }


def _cmd_demo(args: argparse.Namespace) -> int:
    bundle = build_demo_bundle(
        principal_id=args.principal,
        variant=args.variant,
        max_tool_calls=args.budget_tool_calls,
        fixture_path=args.fixture,
    )
    result = asyncio.run(run_demo(bundle))
    identity = {
        "principal_id": args.principal,
        "identity_source": getattr(args, "identity_source", ""),
    }
    _print_json(result if args.full else _summarize(result, identity=identity))
    return EXIT_OK if result.ok else EXIT_BUSINESS_FAILURE


# ---------------------------------------------------------------- ask


def _resolve_ask_provider(args: argparse.Namespace) -> str:
    """统一模型来源：`--model-provider` 优先，旧 `--provider` 仅作弃用别名。"""

    legacy = getattr(args, "provider", None)
    explicit = getattr(args, "model_provider", None)
    mapped = {"fake": "scripted", "deepseek": "deepseek"}.get(legacy) if legacy else None
    if legacy is not None:
        print(
            "[deprecated] --provider 已弃用，请改用 --model-provider"
            "（fake→scripted，deepseek→deepseek）",
            file=sys.stderr,
        )
    if legacy is not None and explicit is not None and mapped != explicit:
        raise UsageError(
            f"--provider {legacy!r} 与 --model-provider {explicit!r} 冲突；只保留一个"
        )
    provider = explicit or mapped or "scripted"
    if provider == "offline":
        raise UsageError(
            "ask 需要模型客户端：--model-provider offline 表示无模型；"
            "请改用 scripted（离线）或 deepseek（需 DEEPSEEK_API_KEY）"
        )
    return provider


def _cmd_ask(args: argparse.Namespace) -> int:
    from .single_demo import build_single_bundle, run_single

    provider = _resolve_ask_provider(args)
    bundle = build_single_bundle(
        question=args.question,
        principal_id=args.principal,
        variant=args.variant,
        provider=provider,
        max_tool_calls=args.budget_tool_calls,
        max_model_calls=args.budget_model_calls,
        max_total_tokens=args.budget_tokens,
        lease_id=args.lease,
        unit_id=args.unit,
        resolve_target=True,
        identity_source=getattr(args, "identity_source", ""),
    )
    if args.max_tool_rounds is not None:
        # 覆盖只影响本次运行，不改磁盘 YAML（配置仍是唯一事实源）
        bundle.agent._config = bundle.agent.config.model_copy(  # noqa: SLF001
            update={"max_tool_rounds": args.max_tool_rounds}
        )

    result = asyncio.run(run_single(bundle))
    payload = result if args.full else _summarize_single(result, bundle, args)
    if args.full:
        payload = {
            **payload.model_dump(mode="json"),
            "target": bundle.target,
            "identity": _identity_payload(bundle, args),
        }
    _print_json(payload)
    return (
        EXIT_OK
        if result.status in (TaskStatus.SUCCESS, TaskStatus.PARTIAL)
        else EXIT_BUSINESS_FAILURE
    )


def _narrative_discrepancies(
    fund_check: dict[str, Any], answer_check: dict[str, Any]
) -> list[dict[str, Any]]:
    """把"模型叙述与可信事实不一致"整理成默认摘要里的差异提示（Task 031 / Z3）。

    复用 Agent 输出的 `fund_check` / `answer_check`，不重新做语义判断。
    """

    items: list[dict[str, Any]] = []
    if fund_check.get("status") == "mismatch":
        items.append(
            {
                "kind": "fund",
                "status": "mismatch",
                "detail": fund_check.get("detail"),
                "problems": list(fund_check.get("problems") or ()),
            }
        )
    if answer_check.get("status") in {"mismatch", "ungrounded"}:
        items.append(
            {
                "kind": "amounts",
                "status": answer_check.get("status"),
                "detail": answer_check.get("detail"),
            }
        )
    return items


def _summarize_single(
    result: RuntimeResult, bundle: Any, args: argparse.Namespace
) -> dict[str, Any]:
    """ask 默认摘要：可信资金结论与模型原话**分栏**展示（Task 031 / Z3）。"""

    output = result.output or {}
    fund_check = output.get("fund_check") or {}
    answer_check = output.get("answer_check") or {}
    fund_conclusion = output.get("fund_conclusion")
    check_status = fund_check.get("status")
    error_details = (result.error.details if result.error is not None else None) or {}
    return {
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "status": result.status.value,
        "identity": _identity_payload(bundle, args),
        # Task 031 / Z1：本次可信目标与来源（由装配层注入，模型不能改写）
        "target": bundle.target,
        "provider": bundle.model_client.provider,
        "model": bundle.model_client.model_name,
        # R2：`model` 是配置名；服务端实际声明的应答模型单独列出（未返回时为空）
        "served_models": (output.get("model") or {}).get("served_models") or [],
        "served_model_mismatch": (output.get("model") or {}).get("served_model_mismatch"),
        # 可信结论：只由工具事实渲染，不经模型（金额来源标注在 source 字段）
        "trusted_conclusion": {
            "source": "tool_facts" if fund_conclusion is not None else "none",
            "fund_conclusion": fund_conclusion,
            "rendered": output.get("authoritative_answer"),
            "check_status": check_status,
            "check_detail": fund_check.get("detail"),
            "verified": check_status == "verified",
        },
        # 模型原话：与可信结论分栏，核验状态单独给出
        "model_narrative": {
            "answer": output.get("answer"),
            "fund_check_status": check_status,
            "answer_check_status": answer_check.get("status"),
            "answer_check_detail": answer_check.get("detail"),
        },
        # 与可信字段不一致时的差异提示（复用现有 narrative 核对结果）
        "narrative_discrepancies": _narrative_discrepancies(fund_check, answer_check),
        "stop_reason": output.get("stop_reason"),
        "rounds": output.get("rounds"),
        "usage": output.get("usage"),
        "task_scope": output.get("task_scope") or error_details.get("task_scope"),
        "tool_calls": output.get("tool_calls", []),
        # Z2：失败/被拒绝/超预算/超时的调用只作审计，不进入取证；这里单独列出
        "failed_tool_calls": output.get("failed_tool_calls")
        or error_details.get("failed_tool_calls", []),
        "rejected_outputs": output.get("rejected_outputs")
        or error_details.get("rejected_outputs", []),
        # R1：问题涉及的领域里哪些取到了事实、哪些缺失（partial 的原因在 warnings）
        "domain_coverage": output.get("domain_coverage")
        or error_details.get("domain_coverage"),
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


# ---------------------------------------------------------------- investigate


def _scripted_calls_for(args: argparse.Namespace) -> list[tuple[str, dict]]:
    """脚本化模型的工具计划：只覆盖本次问题涉及的领域，且只用本租约的数据。"""

    return [
        ("lease.lookup", {"lease_id": args.lease}),
        ("document.search", {"query": args.question, "top_k": 3}),
        ("billing.statement.read", {"lease_id": args.lease}),
        ("property.work_orders.read", {"lease_id": args.lease}),
    ]


def _build_investigation_bundle(
    args: argparse.Namespace, *, control_plane: Any = None, backend: str | None = None
):
    """按 `--model-provider` 装配调查：offline 确定性，scripted/deepseek 走模型引擎。

    Task 031 / 2.5：deepseek 下每个领域 Agent 用**自己 YAML** 的模型参数构造客户端
    （由 `build_investigation_bundle` 内的模型工厂完成），CLI 不再自己建全局客户端。
    """

    from .investigation_demo import build_investigation_bundle

    provider = getattr(args, "model_provider", "offline")
    planner_mode = _effective_planner_mode(args)
    uses_model = provider != "offline" or planner_mode != "rule"
    if planner_mode != "rule" and provider == "offline" and not args.planner_provider:
        raise UsageError(
            f"--planner {planner_mode} 需要规划模型：请加 --planner-provider scripted|deepseek，"
            "或使用 --model-provider scripted|deepseek"
        )
    return build_investigation_bundle(
        principal_id=args.principal,
        variant=args.variant,
        max_tool_calls=args.budget_tool_calls,
        # Task 034：规划模型与 Agent 共享模型调用 / token 预算
        max_model_calls=(args.budget_model_calls if uses_model else 0),
        max_total_tokens=(args.budget_tokens if uses_model else None),
        max_revisions=args.max_revisions,
        backend=backend or args.backend,
        control_plane=control_plane,
        model_provider=provider,
        scripted_calls=(_scripted_calls_for(args) if provider == "scripted" else None),
        planner_mode=planner_mode,
        planner_provider=args.planner_provider,
        hybrid_multi_domain=args.hybrid_multi_domain,
    )


#: CLI 的 PostgreSQL 连接串只从这个环境变量读取（不接受命令行明文）。
_DB_URL_ENV = "COMMERCIAL_DB_URL"


def _postgres_url_from_env() -> str:
    url = os.environ.get(_DB_URL_ENV, "").strip()
    if not url:
        raise UsageError(
            f"--backend postgresql 需要设置环境变量 {_DB_URL_ENV}；"
            "连接串只从环境变量读取，不接受命令行明文"
        )
    if not url.startswith("postgresql"):
        raise UsageError(f"{_DB_URL_ENV} 必须是 postgresql:// 连接串")
    return url


@contextmanager
def _postgres_repository_seam(engine: Any, repository: Any):
    """让 `build_investigation_bundle` 在给定的 PG 只读仓库上完成装配。

    `investigation_demo` 目前只接受 fixture / sqlite（该模块不在 Task 035B
    允许修改的文件内），其 sqlite 分支通过**延迟导入**的
    `bootstrap.build_sqlite_repository` 取得仓库。这里只替换这一次装配使用的
    工厂，使工具、知识库、规划器与调查器拿到同一个 PG 只读仓库，装配结束后立即恢复。
    """

    from .db import bootstrap

    original = bootstrap.build_sqlite_repository

    def _factory(*_args: Any, **_kwargs: Any):
        return engine, repository

    bootstrap.build_sqlite_repository = _factory
    try:
        yield
    finally:
        bootstrap.build_sqlite_repository = original


@contextmanager
def _investigation_assembly(args: argparse.Namespace, *, control_plane: Any = None):
    """装配调查所需的 bundle；PG 后端负责建立并最终释放只读连接。"""

    if getattr(args, "backend", "fixture") != "postgresql":
        yield _build_investigation_bundle(args, control_plane=control_plane)
        return

    if getattr(args, "variant", None):
        # 变体只在读 JSON fixture 时应用；不要让内部装配报出“sqlite 后端”的提示。
        raise UsageError(
            "postgresql 后端不支持 fixture 数据变体（--variant 只作用于 --backend fixture）"
        )

    from sqlalchemy.exc import SQLAlchemyError

    from .db.bootstrap import build_postgres_repository

    url = _postgres_url_from_env()
    try:
        engine, repository = build_postgres_repository(url)
    except (SQLAlchemyError, OSError) as exc:
        # 只报告异常类型：连接串/密码不能进入错误消息或报告。
        raise UsageError(
            f"无法连接 {_DB_URL_ENV} 指向的 PostgreSQL"
            f"（请确认库已迁移并已导入数据）: {type(exc).__name__}"
        ) from None
    try:
        with _postgres_repository_seam(engine, repository):
            # 仓库已由 seam 注入；backend 在此只用于通过装配函数的取值校验。
            bundle = _build_investigation_bundle(
                args, control_plane=control_plane, backend="sqlite"
            )
        # 复查 P3 收尾：替换装配工厂是依赖实现细节的做法；`investigation_demo` 将来改了
        # 取仓库的方式时，这里会静默退回内存 SQLite。断言 bundle 用的就是注入的 PG 仓库。
        if getattr(bundle, "repository", None) is not repository:
            raise RuntimeError(
                "postgresql 后端装配失败：调查装配没有使用注入的 PG 仓库"
                "（investigation_demo 的取仓库方式可能已改变）"
            )
        yield bundle
    finally:
        repository._session.close()  # noqa: SLF001 - 装配资源，仅 CLI 持有
        engine.dispose()


def _effective_planner_mode(args: argparse.Namespace) -> str:
    """命令行未指定时读 planner.yaml（默认 rule）。非法配置在这里就失败（exit 2）。"""

    from .config.loader import load_planner_config

    explicit = getattr(args, "planner", None)
    return explicit or load_planner_config().mode


def _cmd_investigate(args: argparse.Namespace) -> int:
    if args.with_approval:
        return asyncio.run(_investigate_with_control_plane(args))

    with _investigation_assembly(args) as bundle:
        result = asyncio.run(
            run_investigation(
                bundle,
                question=args.question,
                lease_id=args.lease,
                thread_id=args.thread_id,
            )
        )
    _print_json(_investigation_output(result, bundle, args))
    return _investigation_exit_code(result)


async def _investigate_with_control_plane(args: argparse.Namespace) -> int:
    from .control_plane import control_plane
    from .investigation_demo import run_investigation
    from .paths import CHECKPOINT_DB, CONTROL_DB

    base = Path(args.control_dir) if args.control_dir else None
    async with control_plane(
        checkpoint_path=(base / "checkpoints" / "graph.sqlite") if base else CHECKPOINT_DB,
        approval_path=(base / "control" / "approval.sqlite") if base else CONTROL_DB,
    ) as plane:
        with _investigation_assembly(args, control_plane=plane) as bundle:
            thread_id = args.thread_id or f"thread_{bundle.context.run_id}"
            result = await run_investigation(
                bundle,
                question=args.question,
                lease_id=args.lease,
                thread_id=thread_id,
            )
    _print_json(_investigation_output(result, bundle, args))
    return _investigation_exit_code(result)


def _investigation_exit_code(result: Any) -> int:
    """调查的退出码：只有"跑出结果"才算成功。

    - 没有任何子任务结果（例如全部失败、或路由无法判断而要求澄清）→ 业务失败（1）；
    - 有结果但存在冲突/缺失（conflicting/insufficient）属于**有效调查结论** → 0。
    """

    if str(result.verdict) == "needs_clarification":
        return EXIT_BUSINESS_FAILURE
    if not result.results:
        return EXIT_BUSINESS_FAILURE
    return EXIT_OK


def _investigation_output(result: Any, bundle: Any, args: argparse.Namespace) -> dict[str, Any]:
    if args.full:
        payload = dict(result.report or {})
        # 元数据如实记录数据来源；连接串/密码永远不写入报告。
        payload["backend"] = args.backend
        payload["agent_models"] = getattr(bundle, "agent_models", {})
        payload["planner"] = getattr(bundle, "planner_info", {})
        payload["identity"] = _identity_payload(bundle, args)
        return payload
    return _investigation_payload(result, bundle, args)


def _authoritative_amounts_from_results(result: Any) -> list[dict[str, Any]]:
    """从各 billing 子任务输出重建可信资金结论（Task 031 / Z3）。

    确定性 Agent 没有模型叙述，因此这里只做**字段搬运**：
    `invoiced_total` / `paid_total` / `outstanding_total` 来自工具输出，
    渲染文本由 `render_fund_conclusion` 生成，不经过模型。
    """

    from .agents.base.conclusions import build_fund_conclusion, render_fund_conclusion

    items: list[dict[str, Any]] = []
    for item in result.results:
        output = item.get("output") or {}
        if not str(item.get("capability") or "").startswith("billing."):
            continue
        facts = {
            key: output.get(key)
            for key in ("invoiced_total", "paid_total", "outstanding_total")
            if output.get(key) not in (None, "")
        }
        conclusion = build_fund_conclusion(facts)
        if conclusion is None:
            continue
        fund_check = output.get("fund_check")
        check_status = (
            fund_check.get("status") if isinstance(fund_check, dict) else "not_checkable"
        )
        items.append(
            {
                "subtask_id": item.get("subtask_id"),
                "capability": item.get("capability"),
                "agent": item.get("agent"),
                "source": "tool_facts",
                "fund_conclusion": conclusion.as_dict(),
                "rendered": render_fund_conclusion(conclusion),
                "check_status": check_status,
                "check_note": (
                    fund_check.get("detail")
                    if isinstance(fund_check, dict)
                    else "本子任务没有模型叙述，核对状态不适用"
                ),
            }
        )
    return items


def _model_narratives(result: Any) -> list[dict[str, Any]]:
    narratives: list[dict[str, Any]] = []
    for item in result.results:
        output = item.get("output") or {}
        answer = output.get("answer")
        if not answer:
            continue
        fund_check = output.get("fund_check") or {}
        narratives.append(
            {
                "subtask_id": item.get("subtask_id"),
                "agent": item.get("agent"),
                "capability": item.get("capability"),
                "engine": output.get("engine"),
                "answer": answer,
                "fund_check_status": fund_check.get("status")
                if isinstance(fund_check, dict)
                else None,
            }
        )
    return narratives


def _investigation_payload(
    result: Any, bundle: Any, args: argparse.Namespace
) -> dict[str, Any]:
    report = result.report or {}
    return {
        "verdict": result.verdict,
        "route": result.route,
        "revision": result.revision,
        "lease_id": args.lease,
        # 元数据如实记录数据来源；连接串/密码永远不写入报告。
        "backend": args.backend,
        "thread_id": result.thread_id,
        "identity": _identity_payload(bundle, args),
        # Task 031 / 2.7：路由理由（命中了哪些词）与"无法判断领域"的澄清结果
        "routing_reason": report.get("routing_reason", []),
        "clarification": report.get("clarification"),
        # Task 034：规划来源（planner_mode / plan_source / fallback_reason / 规划模型）
        "planner": getattr(bundle, "planner_info", {}),
        "planning": report.get("planning", {}),
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
        # Task 031 / 2.5：按 Agent 列出**实际使用**的模型与参数（offline 时为空）
        "agent_models": getattr(bundle, "agent_models", {}),
        "findings": result.report.get("findings", []),
        "conflicts": list(result.conflicts),
        "missing_information": list(result.missing),
        "failures": list(result.failures),
        # Task 031 / Z3：可信资金结论与模型原话分栏，差异单列
        "authoritative_amounts": _authoritative_amounts_from_results(result),
        "model_narratives": _model_narratives(result),
        "narrative_discrepancies": report.get("narrative_discrepancies", []),
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


# ---------------------------------------------------------------- approve


def _approval_path(args: argparse.Namespace) -> Path:
    from .paths import CONTROL_DB

    if getattr(args, "control_dir", None):
        return Path(args.control_dir) / "control" / "approval.sqlite"
    return CONTROL_DB


def _cmd_approve(args: argparse.Namespace) -> int:
    return asyncio.run(_approve_async(args))


def _approve_dry_run(args: argparse.Namespace) -> int:
    """只做校验：不写入审批台账、不恢复图（Task 031 / 2.4.2）。

    旧实现调用 `ApprovalStore.decide()`，实际写入审批决定但不恢复图，会让台账与
    checkpoint 不一致。现在改为纯校验：读取台账、按真实路径同一套规则预演，
    永不写任何数据。
    """

    from .orchestration.approval import ApprovalError

    path = _approval_path(args)
    if not path.is_file():
        print(
            f"[approval-error] 审批台账不存在: {path}（dry-run 不会创建台账）",
            file=sys.stderr,
        )
        _print_json(
            {
                "dry_run": True,
                "error": {"code": "approval_ledger_missing", "message": f"审批台账不存在: {path}"},
            }
        )
        return EXIT_APPROVAL

    store = ApprovalStore(path)
    repository = FixtureRepository.load()
    principal = repository.principal(args.principal)
    try:
        preview = store.preview_decision(
            args.request_id,
            principal_id=args.principal,
            decision=args.decision,
            draft_version=args.draft_version,
            principal=principal,
            reason=args.reason,
        )
    except ApprovalError as exc:
        print(f"[approval-error] {exc.code}: {exc.message}", file=sys.stderr)
        _print_json(
            {"dry_run": True, "error": {"code": exc.code.value, "message": exc.message}}
        )
        return EXIT_APPROVAL
    _print_json(
        {
            "dry_run": True,
            "wrote_data": False,
            "resumed_graph": False,
            "identity": {
                "principal_id": args.principal,
                "identity_source": getattr(args, "identity_source", ""),
            },
            **preview,
        }
    )
    return EXIT_OK


async def _approve_async(args: argparse.Namespace) -> int:
    from .control_plane import control_plane
    from .investigation_demo import build_investigation_bundle
    from .orchestration.approval import ApprovalError
    from .paths import CHECKPOINT_DB, CONTROL_DB

    if args.dry_run:
        return _approve_dry_run(args)

    base = Path(args.control_dir) if args.control_dir else None
    async with control_plane(
        checkpoint_path=(base / "checkpoints" / "graph.sqlite") if base else CHECKPOINT_DB,
        approval_path=(base / "control" / "approval.sqlite") if base else CONTROL_DB,
    ) as plane:
        bundle = build_investigation_bundle(control_plane=plane)
        try:
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
            return EXIT_APPROVAL

    _print_json(
        {
            "request_id": args.request_id,
            "decision": args.decision,
            "principal_id": args.principal,
            "identity": {
                "principal_id": args.principal,
                "identity_source": getattr(args, "identity_source", ""),
            },
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
    return EXIT_OK


def _cmd_mcp_serve(args: argparse.Namespace) -> int:
    """启动 MCP stdio 网关（Task 033B）。

    启动期失败（档案不存在/禁用/工具不合法/别名冲突）由 `main` 统一转成
    退出码 2；服务运行期间 **stdout 只承载 MCP 协议**，开发模式提示与
    其它诊断信息一律写 stderr。
    """

    from .mcp_gateway.identity import DEV_MODE_WARNING
    from .mcp_gateway.server import load_gateway

    gateway = load_gateway(args.client)
    identity = gateway.startup_identity
    print(
        f"[dev-mode] {DEV_MODE_WARNING}；档案 {identity.client_name}，"
        f"主体 {identity.principal_id}（来源 {identity.source}）",
        file=sys.stderr,
    )
    asyncio.run(gateway.serve_stdio())
    return EXIT_OK


def _cmd_pending(args: argparse.Namespace) -> int:
    approval_path = _approval_path(args)
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
    return EXIT_OK


# ---------------------------------------------------------------- evaluate


def _cmd_evaluate_planner(args: argparse.Namespace) -> int:
    """规划层评测（Task 034）：不执行 Agent，只比较规划决策。"""

    from .evaluation.planner_suite import PLANNER_CONFIGS, render_planner_markdown, run_planner_suite

    if args.planner is None:
        configs = list(PLANNER_CONFIGS)
    elif args.planner == "hybrid":
        configs = ["hybrid_multi_rule" if args.hybrid_multi_domain == "rule" else "hybrid"]
    else:
        configs = [args.planner]
    needs_model = any(name != "rule" for name in configs)
    provider = args.planner_provider
    if needs_model and provider is None:
        if args.model_provider == "deepseek":
            provider = "deepseek"
        else:
            raise UsageError(
                "规划层评测的 llm/hybrid 需要规划模型：请指定 --planner-provider scripted|deepseek"
            )
    versions = ["v1", "v2"] if args.planner_cases == "all" else [args.planner_cases]
    for version in versions:
        reports, written = run_planner_suite(
            configs, cases_version=version, provider=provider, out_dir=args.out
        )
        if not args.quiet:
            print(render_planner_markdown(reports))
        for path in written:
            print(f"[report] {path}")
    return EXIT_OK


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from .evaluation import evaluate, render_markdown, write_report
    from .evaluation.baselines import BASELINES
    from .paths import REPORT_DIR

    if getattr(args, "suite", "baselines") == "planner":
        return _cmd_evaluate_planner(args)

    names = list(BASELINES) if args.baseline == "all" else [args.baseline]
    planner_mode = getattr(args, "planner", None)
    if planner_mode not in (None, "rule"):
        # 只有 C 有规划器：LLM / 混合规划只作用于 C
        if args.baseline not in ("all", "C_multi_agent"):
            raise UsageError(f"--planner {planner_mode} 只作用于 C_multi_agent")
        names = ["C_multi_agent"]
        if args.planner_provider is None and args.model_provider == "offline":
            raise UsageError(
                f"--planner {planner_mode} 需要规划模型：请指定 --planner-provider scripted|deepseek"
            )
    provider = getattr(args, "model_provider", "offline")
    if provider != "offline" and "A_deterministic" in names:
        # A 的定义是"无 Agent、无模型"：混进来会改变基线含义
        names = [name for name in names if name != "A_deterministic"]
        if not names:
            raise ValueError(
                "A_deterministic 不使用模型；请显式指定 B/C 基线或改用 --model-provider offline"
            )
    reports = []
    written: list[str] = []
    for name in names:
        report = asyncio.run(
            evaluate(
                baseline=name,
                split=args.split,
                max_tool_calls=args.max_tool_calls,
                model_provider=provider,
                planner_mode=planner_mode if name == "C_multi_agent" else None,
                planner_provider=args.planner_provider if name == "C_multi_agent" else None,
                hybrid_multi_domain=(
                    args.hybrid_multi_domain if name == "C_multi_agent" else None
                ),
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
    # newline="\n"：避免 Windows 上写出 CRLF（仓库约定 LF，见 .gitattributes）。
    summary_path.write_text(markdown, encoding="utf-8", newline="\n")
    written.append(str(summary_path))

    if not args.quiet:
        print(markdown)
    for path in written:
        print(f"[report] {path}")
    return EXIT_OK


# ---------------------------------------------------------------- search


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
        "identity_source": getattr(args, "identity_source", ""),
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
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    from .env import load_project_env

    # 先加载仓库根 / backend 下的 `.env`（不覆盖已导出的环境变量），
    # 否则用户按 .env.example 填好的密钥会静默失效。
    load_project_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in {"demo", "ask", "investigate", "search"}:
            _resolve_identity(args, fallback=DEFAULT_PRINCIPAL_FALLBACK)
        elif args.command == "approve":
            _resolve_identity(
                args, fallback=DEFAULT_APPROVER_FALLBACK, require_approver=True
            )
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
        if args.command == "mcp-serve":
            return _cmd_mcp_serve(args)
        if args.command == "evaluate":
            return _cmd_evaluate(args)
        if args.command == "search":
            return _cmd_search(args)
    except UsageError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (ConfigError, AgentError, FileNotFoundError, ValueError) as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - 只拦截数据库错误，其余原样抛出
        from sqlalchemy.exc import SQLAlchemyError

        if not isinstance(exc, SQLAlchemyError):
            raise
        # Task 035 复查 P3-2：库连不上 / 未迁移 / 无权限时，SQLAlchemy 的异常消息可能带
        # 连接参数与 SQL；只报告异常类型，不打印消息，也不留 traceback。
        print(
            f"[error] 数据库错误（{type(exc).__name__}）：请确认 COMMERCIAL_DB_URL 指向"
            "已迁移、已导入数据的库，且账号有读取权限；为避免泄露连接信息，不显示详细错误",
            file=sys.stderr,
        )
        return EXIT_USAGE
    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
