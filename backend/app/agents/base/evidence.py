"""能力级最低结果契约（Task 021 / N4）与取证审计（Task 031 / Z2）。

问题背景（N4）：`LLMToolAgent` 只要模型给出非空文本就结束循环，图又把"Agent 返回成功"
当成"子任务证据充分"。于是模型完全可以一次工具都不调、直接回一句"账单没有问题"，
而调查结果仍是 `verdict=supported` / `completeness=complete`。

问题背景（Z2）：`accepted` 只看 `scope.accepts_output`，而失败 `ToolExecution` 的
`data` 是 `None`/`{}`，实体校验发现不了问题；于是"调用失败 + 模型说已核对"也能
通过最低取证判断，`status=success / facts={} / evidence=0`。这里把"哪些调用可以算取证"
收敛成一处定义，SingleToolAgent 与 LLMToolAgent 共用：

| 调用 | 归属 |
|---|---|
| `execution.ok` 且 `scope.accepts_output` 为 `None` | `accepted` → 事实 / 证据 |
| `execution.ok` 但输出不属于本次目标 | `rejected_outputs` → 仅审计（不计事实、不计证据） |
| 执行失败（参数非法 / 拒绝 / 超时 / 预算耗尽） | `failed_tool_calls` → 仅审计 |
| 调用前被可信范围拒绝 / 模型参数无法解析 | `failed_tool_calls`（status=rejected_arguments）→ 仅审计 |

为什么把契约放在这里而不是写进 Prompt：

- Prompt 是**请求**，契约是**约束**。模型可以忽略前者，代码不能忽略后者；
- 同一个契约要被两处使用——Agent 出口（拿不到事实就别返回成功）与图核验
  （不轻信 Agent 自称成功），单点定义才能保证两处口径一致；
- 换模型、换引擎（deterministic / llm）时契约不变，因此这里只描述
  "这个能力必须产出哪些字段"，不描述如何取数。

契约只覆盖**业务取数能力**。没有登记的 capability 视为"允许纯说明"，
不做字段要求——把未知能力也硬填一张表，等于用编造的门槛制造通过/失败。

**合法的零结果不算失败**：工具执行成功且查询结果为空（0 条工单、0.00 未收、
条款检索无命中）仍然产出事实（`0` / `"未检索到匹配条款"`），必须继续判成功；
只有"一条可取信事实都没有"才失败。`0` / 空列表是有效取值，`None` / 空字符串不是。
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import ErrorCode

__all__ = [
    "REQUIRED_RESULT_FIELDS",
    "required_fields",
    "check_capability_output",
    "partition_tool_executions",
    "evidence_of_executions",
    "minimum_evidence_reason",
    "tool_domain",
    "domain_coverage",
    "missing_domain_outcome",
    "failed_call_detail",
    "rejected_argument_detail",
    "parse_error_details",
]


#: capability → 必须由**工具结果**填充的输出字段（空表示允许无取数）。
#:
#: 这些字段全部由工具输出搬运而来（见 `facts.py` / 各确定性 Agent），
#: 因此"字段缺失"等价于"这次没有拿到该能力的真实数据"。
REQUIRED_RESULT_FIELDS: dict[str, tuple[str, ...]] = {
    "billing.statement": (
        "lease_id",
        "invoiced_total",
        "paid_total",
        "outstanding_total",
    ),
    "billing.arrears_check": ("lease_id", "outstanding_total"),
    "property.work_orders": ("work_order_count", "open_count"),
    "lease.query": ("lease",),
    "lease.renewal_evaluation": ("lease",),
}


def required_fields(capability: str) -> tuple[str, ...]:
    return REQUIRED_RESULT_FIELDS.get(capability, ())


def check_capability_output(
    capability: str, output: Mapping[str, Any] | None
) -> list[str]:
    """返回缺失的必需字段说明；空列表表示满足契约。"""

    fields = required_fields(capability)
    if not fields:
        return []
    data: Mapping[str, Any] = output or {}
    return [
        f"能力 {capability} 缺少必需事实 {name}"
        for name in fields
        if not _filled(data.get(name))
    ]


def _filled(value: Any) -> bool:
    """字段是否真的带着工具结果。

    `0` / `False` / 空列表都是**有效取值**（例如"零条工单"），
    只有 `None`、空字符串、`"None"` 字符串与"全为空的映射"才算缺失。
    """

    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in {"", "None", "none", "NaN"}
    if isinstance(value, Mapping):
        return any(_filled(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return True
    return True


# ---------------- 取证审计（Task 031 / Z2） ----------------


def _code_value(code: Any) -> str | None:
    if code is None:
        return None
    return code.value if hasattr(code, "value") else str(code)


def failed_call_detail(execution: Any) -> dict[str, Any]:
    """把一次**执行失败**的 `ToolExecution` 投影成可审计明细。

    只保留元数据（谁、调了什么工具、什么状态、什么错误码、错误信息），
    不含工具数据（失败时本来也没有可信数据）。
    """

    error = getattr(execution, "error", None)
    return {
        "call_id": getattr(execution, "call_id", None),
        "tool": getattr(execution, "tool_name", None),
        "status": getattr(execution, "status", None),
        "error_code": _code_value(getattr(error, "code", None)),
        "message": getattr(error, "message", "") if error is not None else "",
    }


def rejected_argument_detail(tool_name: str, reason: str | None) -> dict[str, Any]:
    """调用**执行前**就被可信范围/参数校验拒绝的审计条目（没有 call_id）。"""

    return {
        "call_id": None,
        "tool": tool_name,
        "status": "rejected_arguments",
        "error_code": ErrorCode.INVALID_TOOL_ARGUMENTS.value,
        "message": str(reason or ""),
    }


def parse_error_details(turns: Any) -> tuple[dict[str, Any], ...]:
    """模型返回的工具调用本身无法解析（`parse_error`）→ 仅审计。

    这类调用不会产生 `ToolExecution`，因此只能从模型回合里取原始调用记录；
    不能因为"没执行"就从审计里消失。
    """

    details: list[dict[str, Any]] = []
    for turn in turns or ():
        for call in getattr(turn, "tool_calls", ()) or ():
            error = getattr(call, "parse_error", None)
            if not error:
                continue
            details.append(
                {
                    "call_id": getattr(call, "call_id", None),
                    "tool": getattr(call, "name", None),
                    "status": "rejected_arguments",
                    "error_code": ErrorCode.INVALID_TOOL_ARGUMENTS.value,
                    "message": str(error),
                }
            )
    return tuple(details)


def partition_tool_executions(
    executions: Any,
    scope: Any,
) -> tuple[tuple[Any, ...], tuple[str, ...], tuple[dict[str, Any], ...]]:
    """按 Z2 口径拆分工具执行结果。

    返回 `(accepted, rejected_outputs, failed_tool_calls)`：

    - `accepted`：**执行成功**且输出仍属于本次目标（`accepts_output` 无拒绝原因）；
    - `rejected_outputs`：执行成功但输出越界（不能并入事实/证据，只留原因）；
    - `failed_tool_calls`：执行失败（参数非法/拒绝/超时/预算耗尽）的审计明细。

    为什么必须同时要求 `ok` 与"输出可接受"：失败执行的 `data` 是 `None`，
    只做实体校验会把它误判为"属于本次目标"；反之，成功但返回了别的实体的调用
    也不能因为它"执行成功"就成为本次目标的证据。
    """

    accepted: list[Any] = []
    rejected_outputs: list[str] = []
    failed_tool_calls: list[dict[str, Any]] = []
    for execution in executions or ():
        if not getattr(execution, "ok", False):
            failed_tool_calls.append(failed_call_detail(execution))
            continue
        reason = (
            scope.accepts_output(execution.tool_name, execution.data or {})
            if scope is not None
            else None
        )
        if reason is None:
            accepted.append(execution)
        else:
            rejected_outputs.append(reason)
    return tuple(accepted), tuple(rejected_outputs), tuple(failed_tool_calls)


def evidence_of_executions(executions: Any) -> tuple[Any, ...]:
    """只从 `accepted` 执行里取证据（越界/失败的调用证据一律不进最终证据集）。"""

    return tuple(
        item
        for execution in executions or ()
        for item in (getattr(execution, "evidence", ()) or ())
    )


def minimum_evidence_reason(scope: Any, facts: Mapping[str, Any] | None) -> str | None:
    """最低取证判定：有目标的业务查询零事实 → 返回失败原因；否则 `None`。

    纯说明任务（`requires_evidence=False`）不受此限；合法零结果（工单 0 条、
    条款无命中）仍然产生事实键，因此不会被误判。
    """

    if scope is None or not getattr(scope, "requires_evidence", False):
        return None
    if facts:
        return None
    return (
        "这是有目标的业务查询，但没有取得任何属于本次目标的工具事实"
        "（失败、被拒绝或越界的调用都不算取证）"
    )


# ---------------- 领域覆盖（Task 031 返修 / R1） ----------------
#
# 问题背景（R1）：`minimum_evidence_reason` 只看 facts 是否非空。问题同时问两件事
# （"A-301 租期和欠款？"），账单工具失败、合同工具成功时，facts 非空 → SUCCESS：
# 用户问的欠款没有取到，状态却是成功。
#
# 口径（全部复用既有定义，不另造词表/映射）：
#
# - "问题涉及哪些领域"：`orchestration.vocabulary.matched_domains`（与 RuleBasedPlanner、
#   `ask` 目标识别同一份词表）；
# - "工具属于哪个领域"：工具名的命名空间（`lease.lookup` → lease、
#   `billing.statement.read` → billing、`property.work_orders.read` → property）；
#   命名空间不是领域时（`document.search`），用工具声明的 `required_permissions`
#   （`lease.read` → lease），且只在恰好对应一个领域时才归属；
# - "某领域取得了事实"：该领域有 accepted 工具产出了非空事实（`facts_of_executions`
#   的 per_tool；合法零结果 `"0"` / `"未检索到匹配条款"` 同样算事实）。
#
# 判定（只在**存在失败调用**时生效，没有失败时行为不变）：
#
# | 情形 | 结果 |
# |---|---|
# | 问题涉及的领域都取得了事实 | 不变（SUCCESS） |
# | 部分领域取得事实、部分没有 | PARTIAL，warnings 写明缺了哪个领域 |
# | 问题涉及的领域一个都没取得事实（只有无关领域的事实） | INSUFFICIENT_EVIDENCE |
#
# 最后一行为什么是失败而不是 PARTIAL：PARTIAL 的含义是"回答了一部分"。用户只问了欠款、
# 账单调用失败、模型顺手查了合同——合同事实回答不了问题的任何一部分，与
# `minimum_evidence_reason` 的"零事实"是同一种情况，只是被无关事实掩盖了。


def tool_domain(tool_name: str, required_permissions: Any = ()) -> str | None:
    """工具所属的业务领域；无法唯一归属时返回 `None`（不参与覆盖判定）。"""

    from ...orchestration.vocabulary import DOMAINS

    namespace = str(tool_name or "").split(".", 1)[0]
    if namespace in DOMAINS:
        return namespace
    by_permission = {
        str(permission).split(".", 1)[0]
        for permission in (required_permissions or ())
    } & set(DOMAINS)
    if len(by_permission) == 1:
        return next(iter(by_permission))
    return None


def domain_coverage(
    question: str,
    per_tool_facts: Mapping[str, Mapping[str, Any]] | None,
    *,
    domain_of: Any = None,
) -> dict[str, list[str]]:
    """问题涉及的领域、取得事实的领域与缺失的领域（均按 `DOMAINS` 顺序）。

    `domain_of(tool_name) -> str | None` 由调用方提供（通常基于工具注册表的
    `required_permissions`）；缺省只看工具命名空间。
    """

    from ...orchestration.vocabulary import DOMAINS, matched_domains

    resolve = domain_of or tool_domain
    asked = list(matched_domains(question))
    covered_set = {
        resolve(tool)
        for tool, facts in (per_tool_facts or {}).items()
        if facts and any(_filled(value) for value in facts.values())
    }
    covered = [domain for domain in DOMAINS if domain in covered_set]
    missing = [domain for domain in asked if domain not in covered_set]
    return {"asked": asked, "covered": covered, "missing": missing}


def missing_domain_outcome(
    coverage: Mapping[str, Any], failed_tool_calls: Any
) -> tuple[str | None, str | None]:
    """按 R1 口径给出 `(失败原因, 告警)`，二者至多一个非空。

    - 没有失败调用、或问题没有命中任何领域 → `(None, None)`（行为不变）；
    - 问题涉及的领域一个都没取到事实 → 失败原因（调用方抛 INSUFFICIENT_EVIDENCE）；
    - 只缺一部分 → 告警（`warnings` 非空 → PARTIAL）。
    """

    from ...orchestration.vocabulary import DOMAIN_LABELS

    if not failed_tool_calls:
        return None, None
    asked = list(coverage.get("asked") or ())
    missing = list(coverage.get("missing") or ())
    if not asked or not missing:
        return None, None
    labels = "、".join(f"{domain}（{DOMAIN_LABELS.get(domain, domain)}）" for domain in missing)
    if len(missing) == len(asked):
        return (
            f"问题涉及的领域 {labels} 没有取得任何事实（相关工具调用失败）；"
            "其他领域的事实回答不了这个问题，不能算取证",
            None,
        )
    return None, f"部分取证：问题涉及的领域 {labels} 没有取得任何事实（存在失败的工具调用），结果只回答了一部分"
