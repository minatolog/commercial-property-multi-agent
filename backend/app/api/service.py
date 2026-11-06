"""WorkflowRunner 适配层（Task 014）。

职责边界（路线图 Prompt 9 的检查点）：

```text
HTTP 层（app/api/app.py）  →  WorkflowService（本模块）  →  Investigator / AgentRegistry / 审批台账
```

- **展示层不得直接访问数据库或 Agent 内部类**：API 只调用本模块；
- **删除展示层不影响 CLI 与评测**：CLI / evaluation 都不 import `app.api`；
- **可信身份由服务端注入**：请求体里的身份字段一律拒绝，身份只来自服务端配置的白名单；
- **运行索引只是投影**：`runs.sqlite` 便于列表/详情查询，权威状态仍是 checkpoint 与审批台账。

为什么不用内存字典：审批恢复可能在另一个进程发生（CLI 先跑调查，网页再点批准），
内存索引会看不到前一次运行。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..agents.base.errors import AgentError
from ..control_plane import control_plane
from ..investigation_demo import build_investigation_bundle
from ..orchestration.approval import ApprovalError
from ..paths import DATA_DIR

__all__ = [
    "ApiError",
    "RunIndex",
    "WorkflowService",
    "DEFAULT_APPROVER_ALLOWLIST",
    "DEFAULT_PRINCIPAL",
]

#: 演示用可信主体：真实部署必须换成会话/OIDC 解析出的身份。
DEFAULT_PRINCIPAL = "principal_ops_xinghui"

#: 允许执行审批动作的服务端白名单（两级审批需要两个不同主体）。
DEFAULT_APPROVER_ALLOWLIST: tuple[str, ...] = (
    "principal_property_manager_xinghui",
    "principal_finance_xinghui",
)

RUNS_DB: Path = DATA_DIR / "api" / "runs.sqlite"


class ApiError(Exception):
    """对外错误：HTTP 层负责翻译成状态码 + 可追踪错误体。"""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL,
    principal_id      TEXT NOT NULL,
    project_ids_json  TEXT,
    grant_project_ids_json TEXT,
    lease_id          TEXT NOT NULL,
    question          TEXT NOT NULL,
    status            TEXT NOT NULL,
    verdict           TEXT,
    approval_status   TEXT,
    approval_request_id TEXT,
    report_json       TEXT,
    traces_json       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunIndex:
    """运行索引（投影，不是事实源）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else RUNS_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session() as connection:
            connection.executescript(_SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """为已存在的旧库补列。

        - `project_ids_json`（Task 016）：报告**数据范围**；
        - `grant_project_ids_json`（Task 017 / R3）：创建者当时的**授权范围**，
          只作审计，不用于授权判断。

        旧记录缺列时一律留空——空范围在 `get`/`list` 里意味着**默认拒绝**，
        直到 `WorkflowService` 用可信主体 + 目标租约回填（无法回填就保持隔离）。
        """

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "project_ids_json" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN project_ids_json TEXT")
        if "grant_project_ids_json" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN grant_project_ids_json TEXT")

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def upsert(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record)
        payload.setdefault("created_at", _now())
        payload["updated_at"] = _now()
        with self._session() as connection:
            connection.execute(
                "INSERT INTO runs (run_id, thread_id, principal_id, project_ids_json,"
                " grant_project_ids_json, lease_id,"
                " question, status, verdict, approval_status, approval_request_id, report_json,"
                " traces_json, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, verdict=excluded.verdict,"
                " approval_status=excluded.approval_status,"
                " approval_request_id=excluded.approval_request_id,"
                " report_json=excluded.report_json, traces_json=excluded.traces_json,"
                " project_ids_json=excluded.project_ids_json,"
                " grant_project_ids_json=excluded.grant_project_ids_json,"
                " updated_at=excluded.updated_at",
                (
                    payload["run_id"],
                    payload["thread_id"],
                    payload["principal_id"],
                    json.dumps(sorted(payload.get("project_ids") or []), ensure_ascii=False),
                    json.dumps(
                        sorted(payload.get("grant_project_ids") or []), ensure_ascii=False
                    ),
                    payload["lease_id"],
                    payload["question"],
                    payload["status"],
                    payload.get("verdict"),
                    payload.get("approval_status"),
                    payload.get("approval_request_id"),
                    json.dumps(payload.get("report"), ensure_ascii=False)
                    if payload.get("report") is not None
                    else None,
                    json.dumps(payload.get("traces"), ensure_ascii=False)
                    if payload.get("traces") is not None
                    else None,
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
        return payload

    def get(self, run_id: str, *, project_ids: frozenset[str] | None = None) -> dict[str, Any] | None:
        """按 run_id 取运行。

        `project_ids` 是**所有权边界**：不属于调用方项目范围的运行一律视为不存在
        （不返回 403，避免用 ID 探测他人数据是否存在）。

        Task 017（R2）：记录的数据范围缺失时**默认拒绝**。旧库升级后不会自动拥有
        范围标签，若对 `None/[]` 放行，修复前创建的运行就仍然跨项目可读——
        而它们恰恰是迁移本该保护的对象。
        """

        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        record = _row(row)
        if project_ids is None:
            return record
        scope = set(record.get("project_ids") or ())
        if not scope & set(project_ids):
            return None
        return record

    def list(
        self, *, limit: int = 50, project_ids: frozenset[str] | None = None
    ) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        records = [_row(row) for row in rows]
        if project_ids is None:
            return records
        scope = set(project_ids)
        return [
            record
            for record in records
            if set(record.get("project_ids") or ()) & scope
        ]

    def unscoped(self) -> list[dict[str, Any]]:
        """没有数据范围标签的记录（旧库升级后的遗留项）。"""

        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM runs WHERE project_ids_json IS NULL"
                " OR project_ids_json IN ('', '[]') ORDER BY created_at"
            ).fetchall()
        return [_row(row) for row in rows]

    def set_scope(
        self, run_id: str, *, project_ids: list[str], grant_project_ids: list[str] | None = None
    ) -> None:
        with self._session() as connection:
            connection.execute(
                "UPDATE runs SET project_ids_json = ?,"
                " grant_project_ids_json = COALESCE(?, grant_project_ids_json),"
                " updated_at = ? WHERE run_id = ?",
                (
                    json.dumps(sorted(project_ids), ensure_ascii=False),
                    None
                    if grant_project_ids is None
                    else json.dumps(sorted(grant_project_ids), ensure_ascii=False),
                    _now(),
                    run_id,
                ),
            )

    def by_approval_request(self, request_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE approval_request_id = ?", (request_id,)
            ).fetchone()
        return None if row is None else _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "thread_id": row["thread_id"],
        "principal_id": row["principal_id"],
        # 报告数据范围（授权用）与创建者授权范围（审计用）分开存放
        "project_ids": json.loads(row["project_ids_json"]) if row["project_ids_json"] else [],
        "grant_project_ids": (
            json.loads(row["grant_project_ids_json"])
            if row["grant_project_ids_json"]
            else []
        ),
        "lease_id": row["lease_id"],
        "question": row["question"],
        "status": row["status"],
        "verdict": row["verdict"],
        "approval_status": row["approval_status"],
        "approval_request_id": row["approval_request_id"],
        "report": json.loads(row["report_json"]) if row["report_json"] else None,
        "traces": json.loads(row["traces_json"]) if row["traces_json"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@dataclass
class WorkflowService:
    """API 的唯一入口：把 HTTP 请求翻译成核心工作流调用。

    `project_ids` 是本服务实例的**数据边界**：既用于运行记录的所有权字段，
    也用于查询时过滤。运行 ID 是随机的，但**不允许**把随机性当权限。
    """

    principal_id: str = DEFAULT_PRINCIPAL
    approver_allowlist: tuple[str, ...] = DEFAULT_APPROVER_ALLOWLIST
    index: RunIndex = field(default_factory=RunIndex)
    checkpoint_path: Path | None = None
    approval_path: Path | None = None
    #: 本实例可信主体的项目范围；`None` 表示从 fixture 读取（测试可显式注入）
    project_ids: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.project_ids is None:
            self.project_ids = self._resolve_scope()
        self._backfill_legacy_scope()

    def _resolve_scope(self) -> frozenset[str]:
        from ..fixtures.repository import FixtureRepository

        try:
            principal = FixtureRepository.load().principal(self.principal_id)
        except Exception:  # noqa: BLE001 - 未知主体一律视为无范围（默认拒绝）
            return frozenset()
        return frozenset(principal.get("project_ids") or [])

    def _report_scope(self, *, principal_id: str, lease_id: str) -> frozenset[str]:
        """报告**实际数据**所属项目（不是创建者的全部授权范围）。

        Task 017（R3）：把授权范围当数据范围写进记录，会让"授权里有 A、B 两个项目"
        的创建者产出的 A 项目报告，被只授权 B 的主体整体读走。这里按目标租约
        （及商铺）解析真实归属；解析不出来就返回空集合，由查询侧默认拒绝。
        """

        from ..fixtures.repository import FixtureRepository

        try:
            repository = FixtureRepository.load()
            principal = repository.principal(principal_id)
            granted = frozenset(principal.get("project_ids") or [])
            facts = repository.lease_facts(project_ids=granted, lease_id=lease_id)
        except Exception:  # noqa: BLE001 - 越权/不存在都按"无法确定范围"处理
            return frozenset()
        owners = {
            str(item.get("project_id"))
            for item in (facts.get("lease"), facts.get("unit"))
            if isinstance(item, dict) and item.get("project_id")
        }
        return frozenset(owners)

    def _backfill_legacy_scope(self) -> None:
        """旧库升级后回填数据范围；回填不了就保持空（查询侧默认拒绝）。

        `RunIndex.get` 对空范围默认拒绝，所以未回填的记录等于被隔离，而不是被放行。
        """

        for record in self.index.unscoped():
            scope = self._report_scope(
                principal_id=record["principal_id"], lease_id=record["lease_id"]
            )
            if not scope:
                continue
            self.index.set_scope(
                record["run_id"],
                project_ids=sorted(scope),
                grant_project_ids=sorted(self.project_ids or ()),
            )

    # ---------------- 提交 ----------------

    async def submit(
        self,
        *,
        question: str,
        lease_id: str,
        with_approval: bool = True,
        max_tool_calls: int = 12,
    ) -> dict[str, Any]:
        if not question.strip():
            raise ApiError("invalid_request", "question 不能为空")
        if not lease_id.strip():
            raise ApiError("invalid_request", "lease_id 不能为空")

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        thread_id = f"thread_{run_id}"
        async with self._control(with_approval) as plane:
            bundle = build_investigation_bundle(
                principal_id=self.principal_id,
                max_tool_calls=max_tool_calls,
                control_plane=plane,
                run_id=run_id,
            )
            try:
                result = await bundle.investigator.investigate(
                    question=question,
                    lease_id=lease_id,
                    context=bundle.context,
                    thread_id=thread_id,
                )
            except AgentError as exc:
                self.index.upsert(
                    {
                        "run_id": run_id,
                        "thread_id": thread_id,
                        "principal_id": self.principal_id,
                        # 失败记录同样只标"报告数据范围"；解析不出就留空（默认拒绝）
                        "project_ids": sorted(
                            self._report_scope(
                                principal_id=self.principal_id, lease_id=lease_id
                            )
                        ),
                        "grant_project_ids": sorted(self.project_ids or ()),
                        "lease_id": lease_id,
                        "question": question,
                        "status": "failed",
                        "report": {"error": {"code": exc.code.value, "message": exc.message}},
                    }
                )
                raise ApiError(exc.code.value, exc.message, status_code=422) from exc
            record = self._record(
                run_id=run_id,
                thread_id=thread_id,
                lease_id=lease_id,
                question=question,
                result=result,
                bundle=bundle,
            )
            stored = self.index.upsert(record)
        return self._summary(stored)

    # ---------------- 查询 ----------------

    def get_run(self, run_id: str) -> dict[str, Any]:
        record = self.index.get(run_id, project_ids=self.project_ids)
        if record is None:
            raise ApiError("run_not_found", f"运行不存在: {run_id}", status_code=404)
        return record

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [
            self._summary(item)
            for item in self.index.list(limit=limit, project_ids=self.project_ids)
        ]

    def get_traces(self, run_id: str) -> dict[str, Any]:
        record = self.get_run(run_id)
        return {
            "run_id": record["run_id"],
            "thread_id": record["thread_id"],
            "traces": record.get("traces") or [],
        }

    # ---------------- 审批 ----------------

    async def decide(
        self,
        *,
        run_id: str,
        actor_id: str,
        decision: str,
        draft_version: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        # 顺序很关键：先确认调用方可访问该运行（含项目所有权），再判断其审批角色。
        # 反过来的话，跨项目主体会拿到 403/409 之类"运行确实存在"的信号。
        record = self.get_run(run_id)
        if actor_id not in self.approver_allowlist:
            raise ApiError(
                "permission_denied",
                f"{actor_id} 不在服务端审批人白名单内",
                status_code=403,
            )
        request_id = record.get("approval_request_id")
        if not request_id:
            raise ApiError("approval_not_found", "该运行没有待审批请求", status_code=409)

        async with self._control(True) as plane:
            # 恢复时也要用同一条运行身份（批准人不是请求人，不能借 resume 换 run_id）
            bundle = build_investigation_bundle(
                control_plane=plane, run_id=record.get("run_id")
            )
            try:
                result = await bundle.investigator.resume(
                    request_id=request_id,
                    decision=decision,
                    draft_version=draft_version,
                    principal_id=actor_id,
                    reason=reason,
                )
            except ApprovalError as exc:
                raise ApiError(exc.code.value, exc.message, status_code=409) from exc
            updated = self.index.get(run_id, project_ids=self.project_ids) or record
            updated.update(
                {
                    "status": "completed" if result.approval_status in {"approved", "rejected"} else "awaiting_approval",
                    "verdict": result.verdict or updated.get("verdict"),
                    "approval_status": result.approval_status,
                    "approval_request_id": (
                        (result.approval_request or {}).get("request_id") or request_id
                    ),
                    "report": {
                        **(updated.get("report") or {}),
                        "approval_status": result.approval_status,
                        "approved_draft": result.approved_draft,
                        "approval_request": result.approval_request,
                        "approval_warnings": list(result.warnings),
                    },
                }
            )
            self.index.upsert(updated)
        return self._summary(updated) | {"approved_draft": result.approved_draft}

    # ---------------- 内部 ----------------

    def _control(self, with_approval: bool):
        if not with_approval:
            return _NoControl()
        return control_plane(
            checkpoint_path=self.checkpoint_path,
            approval_path=self.approval_path,
        )

    def _record(
        self,
        *,
        run_id: str,
        thread_id: str,
        lease_id: str,
        question: str,
        result: Any,
        bundle: Any,
    ) -> dict[str, Any]:
        request = result.approval_request or {}
        keeps_approval = result.approval_status in {"pending_approval", "pending_next_stage"}
        status = (
            "awaiting_approval"
            if keeps_approval
            else ("failed" if result.verdict == "insufficient" else "completed")
        )
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "principal_id": self.principal_id,
            # 数据范围（授权用）≠ 创建者授权范围（grant_project_ids，审计用）
            "project_ids": sorted(
                self._report_scope(principal_id=self.principal_id, lease_id=lease_id)
            ),
            "grant_project_ids": sorted(self.project_ids or ()),
            "lease_id": lease_id,
            "question": question,
            "status": status,
            "verdict": result.verdict,
            "approval_status": result.approval_status,
            "approval_request_id": request.get("request_id"),
            "report": {
                **(result.report or {}),
                "approval_request": result.approval_request,
                "approved_draft": result.approved_draft,
                "warnings": list(result.warnings),
                "conflicts": list(result.conflicts),
                "missing_information": list(result.missing),
                "failures": list(result.failures),
                "budget": bundle.budget.snapshot().model_dump(),
            },
            "traces": [
                {
                    "subtask_id": trace.subtask_id,
                    "tool": trace.tool_name,
                    "status": trace.status,
                    "attempt": trace.attempt,
                    "duration_ms": trace.duration_ms,
                    "run_id": trace.run_id,
                }
                for trace in bundle.trace_log.snapshot()
            ],
        }

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": record["run_id"],
            "thread_id": record["thread_id"],
            "lease_id": record["lease_id"],
            "question": record["question"],
            "status": record["status"],
            "verdict": record.get("verdict"),
            "approval_status": record.get("approval_status"),
            "approval_request_id": record.get("approval_request_id"),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }


class _NoControl:
    """不使用控制面时的空上下文（保持同一调用形态）。"""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False
