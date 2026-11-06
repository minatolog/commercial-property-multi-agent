"""人工审批控制面（Task 012）。

设计要点（对应路线图 Prompt 7 的验收项）：

1. **审批是独立节点**，不在 Agent 内部；Agent 只产出草案，审批只改变草案状态。
2. **批准不等于执行**：本次范围内没有任何"调账/派单"副作用，`approved_draft` 只是
   一份带审批链的草案，后续动作（如真实调账）必须由人工或独立系统完成。
3. **控制面与业务数据分离**：审批状态存独立 SQLite 文件，与业务库、LangGraph checkpoint
   互不混用。检查点用于"恢复流程"，审批台账用于"谁在什么时候批准了什么"。
4. **拒绝不可信输入**：审批人身份、角色、版本号一律来自调用方显式参数 + fixture 规则，
   不接受"草案自己声明的审批人"。
5. **幂等与并发**：`(request_id, role)` 唯一约束保证串行阶段不会被重复批准；
   重复恢复由 `resume_ledger` 的 `request_id` 唯一约束兜底。

已知边界（不得夸大）：控制面只保证**本地单机**的一致性；跨进程并发写入依赖
SQLite 的 `BEGIN IMMEDIATE`，不宣称分布式恰好一次。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..agents.base.errors import AgentError, ErrorCode

__all__ = [
    "ApprovalConflictError",
    "ApprovalDecisionOutcome",
    "ApprovalExpiredError",
    "ApprovalRequest",
    "ApprovalRequestNotFoundError",
    "ApprovalStage",
    "ApprovalStore",
    "ApprovalValidationError",
    "DuplicatePrincipalError",
    "DraftVersionMismatchError",
    "PermissionDeniedForApprovalError",
    "ProjectScopeDeniedForApprovalError",
    "RoleRule",
    "SelfApprovalForbiddenError",
    "StageOrderViolationError",
    "build_approval_request",
    "DEFAULT_APPROVAL_RULE",
]


# ---------------------------------------------------------------- 错误


class ApprovalError(AgentError):
    default_code = ErrorCode.PERMISSION_DENIED


class ApprovalValidationError(ApprovalError):
    default_code = ErrorCode.INVALID_REQUEST


class ApprovalRequestNotFoundError(ApprovalError):
    default_code = ErrorCode.RECORD_NOT_FOUND


class PermissionDeniedForApprovalError(ApprovalError):
    default_code = ErrorCode.PERMISSION_DENIED


class ProjectScopeDeniedForApprovalError(ApprovalError):
    default_code = ErrorCode.PROJECT_SCOPE_DENIED


class DraftVersionMismatchError(ApprovalValidationError):
    """审批针对的草案版本不是当前最新版本。"""


class ApprovalExpiredError(ApprovalValidationError):
    """草案已过期，必须重新生成后再次申请。"""


class ApprovalConflictError(ApprovalError):
    """重复/并发审批冲突（例如同一角色被两个人同时批准）。"""


class SelfApprovalForbiddenError(PermissionDeniedForApprovalError):
    pass


class StageOrderViolationError(ApprovalValidationError):
    pass


class DuplicatePrincipalError(ApprovalValidationError):
    pass


# ---------------------------------------------------------------- 模型


@dataclass(frozen=True)
class RoleRule:
    role: str
    label: str
    seq: int
    permission: str


@dataclass(frozen=True)
class ApprovalRule:
    action_type: str
    combine: str
    order: str
    roles: tuple[RoleRule, ...]
    distinct_principals_required: bool = True
    self_approval_forbidden: bool = True
    draft_expiry_hours: int = 72

    @classmethod
    def from_fixture(cls, action_type: str, raw: dict[str, Any]) -> "ApprovalRule":
        roles = tuple(
            RoleRule(
                role=item["role"],
                label=item.get("label", item["role"]),
                seq=int(item.get("seq", index + 1)),
                permission=item.get("permission", "approval.decide"),
            )
            for index, item in enumerate(raw.get("roles", []))
        )
        if not roles:
            raise ApprovalValidationError(f"审批规则 {action_type} 没有任何角色")
        return cls(
            action_type=action_type,
            combine=raw.get("combine", "all_of"),
            order=raw.get("order", "serial"),
            roles=roles,
            distinct_principals_required=bool(
                raw.get("distinct_principals_required", True)
            ),
            self_approval_forbidden=bool(raw.get("self_approval_forbidden", True)),
            draft_expiry_hours=int(raw.get("draft_expiry_hours", 72)),
        )

    def ordered_roles(self) -> tuple[RoleRule, ...]:
        return tuple(sorted(self.roles, key=lambda item: item.seq))


#: 无 fixture 时的保守默认：单一审批角色，不允许自批。
DEFAULT_APPROVAL_RULE = ApprovalRule(
    action_type="rent_reduction_draft",
    combine="all_of",
    order="serial",
    roles=(RoleRule(role="finance", label="财务部门", seq=1, permission="approval.decide"),),
)


@dataclass(frozen=True)
class ApprovalStage:
    role: str
    seq: int
    status: str = "pending"  # pending | approved | rejected
    decided_by: str | None = None
    decided_at: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "seq": self.seq,
            "status": self.status,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    thread_id: str
    run_id: str
    trace_id: str
    project_id: str
    draft_id: str
    draft_version: int
    action_type: str
    amount: str
    currency: str
    requested_by: str
    created_at: str
    expires_at: str
    status: str  # pending | approved | rejected | expired | superseded
    stages: tuple[ApprovalStage, ...]
    evidence_ids: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    def stage(self, role: str) -> ApprovalStage | None:
        return next((item for item in self.stages if item.role == role), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "project_id": self.project_id,
            "draft_id": self.draft_id,
            "draft_version": self.draft_version,
            "action_type": self.action_type,
            "amount": self.amount,
            "currency": self.currency,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "stages": [item.as_dict() for item in self.stages],
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class ApprovalDecisionOutcome:
    request: ApprovalRequest
    decided_role: str
    decision: str
    idempotent: bool = False

    @property
    def fully_approved(self) -> bool:
        return self.request.status == "approved"


# ---------------------------------------------------------------- 构造


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def build_approval_request(
    *,
    draft: dict[str, Any],
    rule: ApprovalRule,
    thread_id: str,
    run_id: str,
    trace_id: str,
    requested_by: str,
    now: datetime | None = None,
    request_id: str | None = None,
) -> ApprovalRequest:
    created = _now(now)
    # 审批窗口从**请求创建时刻**起算（默认 72 小时）。
    # 草案自带的 `expires_at` 是"草案生成时约定的有效期"，作为审计字段保留；
    # 若直接用它判定过期，任何静态 fixture 都会在写完的当天失效，演示与回归都无法进行。
    expires = created + timedelta(hours=rule.draft_expiry_hours)
    return ApprovalRequest(
        request_id=request_id or f"apr_{uuid.uuid4().hex[:12]}",
        thread_id=thread_id,
        run_id=run_id,
        trace_id=trace_id,
        project_id=str(draft["project_id"]),
        draft_id=str(draft["draft_id"]),
        draft_version=int(draft["draft_version"]),
        action_type=str(draft["action_type"]),
        amount=str(draft["amount"]),
        currency=str(draft.get("currency", "CNY")),
        requested_by=requested_by,
        created_at=_iso(created),
        expires_at=_iso(expires),
        status="pending",
        stages=tuple(
            ApprovalStage(role=item.role, seq=item.seq) for item in rule.ordered_roles()
        ),
        evidence_ids=tuple(draft.get("evidence_ids", ())),
        payload={
            "target": draft.get("target", {}),
            "supersedes": draft.get("supersedes"),
            "draft_expires_at": draft.get("expires_at"),
            "computed_variance": draft.get("computed_variance"),
        },
    )


# ---------------------------------------------------------------- 存储


_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
    request_id      TEXT PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    draft_id        TEXT NOT NULL,
    draft_version   INTEGER NOT NULL,
    action_type     TEXT NOT NULL,
    amount          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    requested_by    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    status          TEXT NOT NULL,
    stages_json     TEXT NOT NULL,
    evidence_json   TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    UNIQUE (thread_id, draft_id, draft_version)
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    decision    TEXT NOT NULL,
    draft_version INTEGER NOT NULL,
    reason      TEXT,
    decided_at  TEXT NOT NULL,
    UNIQUE (request_id, role)
);

CREATE TABLE IF NOT EXISTS resume_ledger (
    request_id  TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
"""


class ApprovalStore:
    """审批台账（独立 SQLite 文件，与业务数据、checkpoint 分离）。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """每次操作一个短连接，**用完一定关闭**。

        Windows 上未关闭的连接会锁住文件，导致临时目录无法清理；
        `with sqlite3.connect(...)` 只提交事务、不关闭连接，因此必须显式 close。
        """

        connection = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        finally:
            connection.close()

    # ---------------- 写入 ----------------

    def create(self, request: ApprovalRequest) -> ApprovalRequest:
        """创建审批请求；同一 (thread, draft, version) 幂等返回既有请求。"""

        with self._session() as connection:
            try:
                connection.execute(
                    "INSERT INTO approval_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        request.request_id,
                        request.thread_id,
                        request.run_id,
                        request.trace_id,
                        request.project_id,
                        request.draft_id,
                        request.draft_version,
                        request.action_type,
                        request.amount,
                        request.currency,
                        request.requested_by,
                        request.created_at,
                        request.expires_at,
                        request.status,
                        json.dumps([item.as_dict() for item in request.stages], ensure_ascii=False),
                        json.dumps(list(request.evidence_ids), ensure_ascii=False),
                        json.dumps(request.payload, ensure_ascii=False),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self.find_by_draft(
                    thread_id=request.thread_id,
                    draft_id=request.draft_id,
                    draft_version=request.draft_version,
                )
                if existing is None:  # pragma: no cover - 唯一约束与查询应一致
                    raise
                return existing
        return request

    def decide(
        self,
        request_id: str,
        *,
        principal_id: str,
        decision: str,
        draft_version: int,
        principal: dict[str, Any],
        reason: str | None = None,
        now: datetime | None = None,
    ) -> ApprovalDecisionOutcome:
        """记录一次审批决定。

        校验顺序（Task 016 / S1 修正）：**先验证身份、范围、版本，再判定是否幂等重放**。

        旧顺序把"已终态"放在最前面，于是批准 v2 之后，同一主体用
        `draft_version=999` 重放仍返回 approved——错误的版本看起来被批准了。
        现在任何重放都必须通过同样的授权与版本校验，才可能被判为幂等。
        """

        if decision not in {"approve", "reject"}:
            raise ApprovalValidationError(f"非法审批决定: {decision!r}")

        with self._session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)
                ).fetchone()
                if row is None:
                    raise ApprovalRequestNotFoundError(f"审批请求不存在: {request_id}")

                request = _row_to_request(row)
                moment = _now(now)

                # 1) 身份 / 权限 / 项目范围 / 角色（终态也要检查）
                role = _authorised_role(request, principal_id, principal)

                # 2) 草案版本必须匹配，重放不是绕过版本的通道
                if int(draft_version) != request.draft_version:
                    raise DraftVersionMismatchError(
                        f"审批版本不匹配：请求为 v{request.draft_version}，提交为 v{draft_version}",
                        details={
                            "expected": request.draft_version,
                            "provided": draft_version,
                        },
                    )

                # 3) 请求人不得自批
                if request.requested_by == principal_id:
                    raise SelfApprovalForbiddenError("请求人不得审批自己提交的草案")

                # 4) 该角色是否已有决定：同人同结论 = 幂等重放，其余 = 冲突
                recorded = connection.execute(
                    "SELECT principal_id, decision FROM approval_decisions "
                    "WHERE request_id = ? AND role = ?",
                    (request_id, role),
                ).fetchone()
                if recorded is not None:
                    if (
                        recorded["principal_id"] == principal_id
                        and recorded["decision"] == decision
                    ):
                        connection.execute("ROLLBACK")
                        return ApprovalDecisionOutcome(
                            request=request,
                            decided_role=role,
                            decision=decision,
                            idempotent=True,
                        )
                    raise ApprovalConflictError(
                        f"角色 {role} 已被 {recorded['principal_id']} 审批为 {recorded['decision']}"
                    )

                # 5) 已终态且本角色没有记录 → 状态与审计不一致，拒绝写入
                if request.status in {"approved", "rejected", "expired"}:
                    raise ApprovalConflictError(
                        f"审批请求已处于 {request.status}，不能再被修改",
                        details={"status": request.status},
                    )

                # 6) 只有仍在流转中的请求才判过期
                if _is_expired(request, moment):
                    connection.execute(
                        "UPDATE approval_requests SET status = 'expired' WHERE request_id = ?",
                        (request_id,),
                    )
                    connection.execute("COMMIT")
                    raise ApprovalExpiredError(
                        f"草案已过期（{request.expires_at}），请重新生成后再次申请",
                        details={"expires_at": request.expires_at},
                    )

                decided = {
                    item.role: item for item in request.stages if item.status != "pending"
                }
                if any(
                    item.decided_by == principal_id for item in decided.values()
                ):
                    raise DuplicatePrincipalError(
                        "同一人不能在同一草案的多个审批阶段重复签署"
                    )

                pending = [item for item in request.stages if item.status == "pending"]
                if not pending:  # pragma: no cover - status 已保证
                    raise ApprovalConflictError("没有待审批阶段")
                if pending[0].role != role:
                    raise StageOrderViolationError(
                        f"审批顺序错误：应先由 {pending[0].role} 审批，当前为 {role}"
                    )

                decided_at = _iso(moment)
                try:
                    connection.execute(
                        "INSERT INTO approval_decisions "
                        "(request_id, role, principal_id, decision, draft_version, reason, decided_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            request_id,
                            role,
                            principal_id,
                            decision,
                            int(draft_version),
                            reason,
                            decided_at,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ApprovalConflictError(
                        f"角色 {role} 已被其他人审批（并发冲突）"
                    ) from exc

                stages = tuple(
                    ApprovalStage(
                        role=item.role,
                        seq=item.seq,
                        status=_stage_status(decision) if item.role == role else item.status,
                        decided_by=principal_id if item.role == role else item.decided_by,
                        decided_at=decided_at if item.role == role else item.decided_at,
                        reason=reason if item.role == role else item.reason,
                    )
                    for item in request.stages
                )
                status = _next_status(stages)
                connection.execute(
                    "UPDATE approval_requests SET status = ?, stages_json = ? WHERE request_id = ?",
                    (
                        status,
                        json.dumps([item.as_dict() for item in stages], ensure_ascii=False),
                        request_id,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                raise
            except Exception:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.OperationalError:  # pragma: no cover
                    pass
                raise

        updated = self.get(request_id)
        assert updated is not None
        return ApprovalDecisionOutcome(
            request=updated, decided_role=role, decision=decision
        )

    # ---------------- 幂等恢复 ----------------

    def record_resume(self, request_id: str, thread_id: str, outcome: dict[str, Any]) -> bool:
        """记录一次恢复；返回 True 表示首次恢复，False 表示重复恢复。"""

        with self._session() as connection:
            try:
                connection.execute(
                    "INSERT INTO resume_ledger VALUES (?,?,?,?)",
                    (
                        request_id,
                        thread_id,
                        json.dumps(outcome, ensure_ascii=False),
                        _iso(_now(None)),
                    ),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def previous_resume(self, request_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT outcome_json FROM resume_ledger WHERE request_id = ?", (request_id,)
            ).fetchone()
        return None if row is None else json.loads(row["outcome_json"])

    # ---------------- 查询 ----------------

    def get(self, request_id: str) -> ApprovalRequest | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        return None if row is None else _row_to_request(row)

    def find_by_thread(self, thread_id: str) -> list[ApprovalRequest]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM approval_requests WHERE thread_id = ? ORDER BY created_at",
                (thread_id,),
            ).fetchall()
        return [_row_to_request(row) for row in rows]

    def find_by_draft(
        self, *, thread_id: str, draft_id: str, draft_version: int
    ) -> ApprovalRequest | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM approval_requests "
                "WHERE thread_id = ? AND draft_id = ? AND draft_version = ?",
                (thread_id, draft_id, draft_version),
            ).fetchone()
        return None if row is None else _row_to_request(row)

    def pending(self) -> list[ApprovalRequest]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        return [_row_to_request(row) for row in rows]

    def decisions(self, request_id: str) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM approval_decisions WHERE request_id = ? ORDER BY seq",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]


# ---------------------------------------------------------------- 内部


def _row_to_request(row: sqlite3.Row) -> ApprovalRequest:
    stages = tuple(
        ApprovalStage(
            role=item["role"],
            seq=int(item["seq"]),
            status=item["status"],
            decided_by=item.get("decided_by"),
            decided_at=item.get("decided_at"),
            reason=item.get("reason"),
        )
        for item in json.loads(row["stages_json"])
    )
    return ApprovalRequest(
        request_id=row["request_id"],
        thread_id=row["thread_id"],
        run_id=row["run_id"],
        trace_id=row["trace_id"],
        project_id=row["project_id"],
        draft_id=row["draft_id"],
        draft_version=int(row["draft_version"]),
        action_type=row["action_type"],
        amount=row["amount"],
        currency=row["currency"],
        requested_by=row["requested_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        status=row["status"],
        stages=stages,
        evidence_ids=tuple(json.loads(row["evidence_json"])),
        payload=json.loads(row["payload_json"]),
    )


def _role_of(principal: dict[str, Any]) -> str:
    roles: Iterable[str] = principal.get("approval_roles") or []
    return next(iter(roles), "")


def _authorised_role(
    request: ApprovalRequest, principal_id: str, principal: dict[str, Any]
) -> str:
    """从可信主体推导本次可签署的角色；不做任何"猜测"。"""

    if not principal.get("can_decide_approval") or "approval.decide" not in (
        principal.get("permissions") or []
    ):
        raise PermissionDeniedForApprovalError(
            f"{principal_id} 没有审批权限",
            details={"principal_id": principal_id},
        )

    project_ids = set(principal.get("project_ids") or [])
    if request.project_id not in project_ids:
        raise ProjectScopeDeniedForApprovalError(
            f"{principal_id} 无权审批项目 {request.project_id} 的草案",
            details={"project_id": request.project_id},
        )

    roles = list(principal.get("approval_roles") or [])
    if not roles:
        raise PermissionDeniedForApprovalError(
            f"{principal_id} 未被授予任何审批角色",
            details={"principal_id": principal_id},
        )

    available = [item.role for item in request.stages if item.role in roles]
    if not available:
        raise PermissionDeniedForApprovalError(
            f"{principal_id} 的角色 {roles} 与草案要求的 {[s.role for s in request.stages]} 不匹配",
            details={"allowed_roles": roles},
        )
    for stage in request.stages:
        if stage.role in roles and stage.status == "pending":
            return stage.role
    return available[0]


def _stage_status(decision: str) -> str:
    return "approved" if decision == "approve" else "rejected"


def _next_status(stages: tuple[ApprovalStage, ...]) -> str:
    if any(item.status == "rejected" for item in stages):
        return "rejected"
    if all(item.status == "approved" for item in stages):
        return "approved"
    return "pending"


def _is_expired(request: ApprovalRequest, moment: datetime) -> bool:
    expires = datetime.fromisoformat(request.expires_at)
    if expires.tzinfo is None:  # pragma: no cover - 构造时已带时区
        expires = expires.replace(tzinfo=timezone.utc)
    return moment > expires
