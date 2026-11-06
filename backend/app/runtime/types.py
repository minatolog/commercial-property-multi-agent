"""Runtime 层类型：可信上下文、证据、Trace 与执行结果。

设计边界（对应 Runtime contracts §1–§5）：

- **可信上下文**（`TrustedContext`）只能由已认证入口构造，权限与项目范围
  绝不从 `AgentRequest.payload`、模型输出或检索文档读取。
- **证据**（`Evidence`）由工具产出草稿，执行器统一补齐来源字段
  （工具名、调用 ID、采集时刻、合成标记），工具无法伪造来源。
- **Trace** 记录调用链（call id / trace id / 参数摘要 / 状态 / 错误码 /
  attempt / 耗时），不记录原始参数，避免泄露密钥。

本模块只依赖 `agents.base` 的既有契约，不引入并行 V1/V2 生命周期。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..agents.base.contracts import AgentContext, AgentErrorDetail, AgentResult, TaskStatus

__all__ = [
    "RESERVED_PAYLOAD_KEYS",
    "BudgetUsage",
    "Evidence",
    "EvidenceDraft",
    "RuntimeResult",
    "ToolExecution",
    "ToolStatus",
    "ToolTrace",
    "TraceLog",
    "TrustedContext",
]

#: payload 中不允许出现的键：这些属于可信上下文或运行时状态，
#: 由 Runtime 注入。出现在 payload 里一律按非法请求拒绝。
RESERVED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "permissions",
        "project_ids",
        "principal_id",
        "tenant_id",
        "user_id",
        "budget",
        "deadline_at",
        "trace_id",
        "allowed_tools",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(payload: Any) -> str:
    """稳定 JSON 序列化，用于内容哈希与参数摘要。"""

    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


class TrustedContext(BaseModel):
    """可信执行上下文。

    只能由 Runtime 从"已认证会话"构造；`from_principal` 用于从 fixture 的
    可信主体表（模拟服务端会话）构造，绝不是从用户 payload 读取。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    project_ids: frozenset[str] = Field(min_length=1)
    permissions: frozenset[str] = frozenset()
    commercial_tenant_ids: frozenset[str] | None = None
    deadline_at: datetime | None = None

    def to_agent_context(self, *, run_id: str | None = None) -> AgentContext:
        """转换为既有 `AgentContext`（新增字段均有默认值，向后兼容）。

        `run_id` 由 Runtime 在每次执行开始时生成，用于把本 run 的 Trace
        与共享 append-only TraceLog 中的历史记录区分开（F2）。
        """

        tenant_id = None
        if self.commercial_tenant_ids and len(self.commercial_tenant_ids) == 1:
            tenant_id = next(iter(self.commercial_tenant_ids))
        return AgentContext(
            trace_id=self.trace_id,
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=self.principal_id,
            permissions=self.permissions,
            principal_id=self.principal_id,
            project_ids=self.project_ids,
            deadline_at=self.deadline_at,
        )

    @classmethod
    def from_principal(
        cls,
        principal: dict[str, Any],
        *,
        trace_id: str,
        deadline_at: datetime | None = None,
    ) -> "TrustedContext":
        """从可信主体记录构造（服务端会话替身）。

        只接受已经过认证的主体记录；不解析任何用户输入。
        """

        return cls(
            trace_id=trace_id,
            principal_id=principal["principal_id"],
            project_ids=frozenset(principal["project_ids"]),
            permissions=frozenset(principal.get("permissions", [])),
            commercial_tenant_ids=(
                frozenset(principal["commercial_tenant_ids"])
                if principal.get("commercial_tenant_ids") is not None
                else None
            ),
            deadline_at=deadline_at,
        )


class EvidenceDraft(BaseModel):
    """工具产出的证据草稿。

    工具只能声明"引用哪条记录、哪些字段"；来源字段由执行器补齐，
    因此工具无法把自己伪装成别的工具或别的调用。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    kind: Literal["db_fact", "document_clause"] = "db_fact"
    project_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    as_of_date: date
    entity: str | None = None
    record_id: str = Field(min_length=1)
    fields: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """可追溯的结构化证据（Runtime contracts §3.1）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    kind: Literal["db_fact", "document_clause"]
    source_tool: str
    tool_call_id: str
    project_id: str
    dataset_version: str
    as_of_date: date
    collected_at: datetime
    synthetic: bool = True
    entity: str | None = None
    record_id: str
    fields: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def materialize(
        cls,
        draft: EvidenceDraft,
        *,
        source_tool: str,
        tool_call_id: str,
        collected_at: datetime | None = None,
    ) -> "Evidence":
        return cls(
            evidence_id=draft.evidence_id,
            kind=draft.kind,
            source_tool=source_tool,
            tool_call_id=tool_call_id,
            project_id=draft.project_id,
            dataset_version=draft.dataset_version,
            as_of_date=draft.as_of_date,
            collected_at=collected_at or _utcnow(),
            synthetic=True,
            entity=draft.entity,
            record_id=draft.record_id,
            fields=draft.fields,
        )

    def content_hash(self) -> str:
        """证据内容哈希：同 ID 同内容才可幂等合并。"""

        payload = {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "project_id": self.project_id,
            "dataset_version": self.dataset_version,
            "as_of_date": self.as_of_date.isoformat(),
            "entity": self.entity,
            "record_id": self.record_id,
            "fields": self.fields,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class ToolStatus(StrEnum):
    """工具调用终态。"""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    DENIED = "denied"
    BUDGET_EXHAUSTED = "budget_exhausted"


class ToolTrace(BaseModel):
    """单次工具调用尝试的 Trace 记录（不含原始参数）。

    `run_id` 把 Trace 明确归属到一次 Runtime 执行：共享 TraceLog 仍保留全部历史，
    但 `RuntimeResult.tool_traces` 只截取本次 run 的记录，避免复用 Runtime 时
    把先前执行的调用混进当前评测结果（F2）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    trace_id: str
    run_id: str | None = None
    tool_name: str
    args_digest: str
    status: str
    error_code: str | None = None
    attempt: int = 0
    duration_ms: float = 0.0
    started_at: datetime


class ToolExecution(BaseModel):
    """一次逻辑工具调用的最终结果（含全部尝试的 Trace）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str
    tool_name: str
    status: str
    data: dict[str, Any] | None = None
    evidence: tuple[Evidence, ...] = ()
    error: AgentErrorDetail | None = None
    attempts: int = 0
    duration_ms: float = 0.0
    traces: tuple[ToolTrace, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == ToolStatus.OK


class TraceLog:
    """进程内 Trace 收集器。

    只追加、不覆盖；Runtime 在结束时快照，用于结果与 CLI 输出。
    """

    def __init__(self) -> None:
        self._items: list[ToolTrace] = []

    def add(self, trace: ToolTrace) -> None:
        self._items.append(trace)

    def extend(self, traces: tuple[ToolTrace, ...] | list[ToolTrace]) -> None:
        self._items.extend(traces)

    def snapshot(self) -> tuple[ToolTrace, ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)


class BudgetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tool_calls: int
    max_model_calls: int
    max_total_tokens: int
    used_tool_calls: int = 0
    used_model_calls: int = 0
    used_total_tokens: int = 0


class RuntimeResult(BaseModel):
    """Runtime 对外返回的结构化结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    trace_id: str
    status: TaskStatus
    output: dict[str, Any] | None = None
    evidence: tuple[Evidence, ...] = ()
    tool_traces: tuple[ToolTrace, ...] = ()
    warnings: tuple[str, ...] = ()
    error: AgentErrorDetail | None = None
    budget: BudgetUsage
    agent_result: AgentResult | None = None

    @property
    def ok(self) -> bool:
        return self.status is TaskStatus.SUCCESS
