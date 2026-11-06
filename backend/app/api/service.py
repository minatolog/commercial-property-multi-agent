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
                "INSERT INTO runs (run_id, thread_id, principal_id, lease_id, question, status,"
                " verdict, approval_status, approval_request_id, report_json, traces_json,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, verdict=excluded.verdict,"
                " approval_status=excluded.approval_status,"
                " approval_request_id=excluded.approval_request_id,"
                " report_json=excluded.report_json, traces_json=excluded.traces_json,"
                " updated_at=excluded.updated_at",
                (
                    payload["run_id"],
                    payload["thread_id"],
                    payload["principal_id"],
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

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return None if row is None else _row(row)

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(row) for row in rows]

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
    """API 的唯一入口：把 HTTP 请求翻译成核心工作流调用。"""

    principal_id: str = DEFAULT_PRINCIPAL
    approver_allowlist: tuple[str, ...] = DEFAULT_APPROVER_ALLOWLIST
    index: RunIndex = field(default_factory=RunIndex)
    checkpoint_path: Path | None = None
    approval_path: Path | None = None

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
        record = self.index.get(run_id)
        if record is None:
            raise ApiError("run_not_found", f"运行不存在: {run_id}", status_code=404)
        return record

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [self._summary(item) for item in self.index.list(limit=limit)]

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
        if actor_id not in self.approver_allowlist:
            raise ApiError(
                "permission_denied",
                f"{actor_id} 不在服务端审批人白名单内",
                status_code=403,
            )
        record = self.get_run(run_id)
        request_id = record.get("approval_request_id")
        if not request_id:
            raise ApiError("approval_not_found", "该运行没有待审批请求", status_code=409)

        async with self._control(True) as plane:
            bundle = build_investigation_bundle(control_plane=plane)
            try:
                result = await bundle.investigator.resume(
                    request_id=request_id,
                    decision=decision,
                    draft_version=draft_version,
                    principal_id=actor_id,
                )
            except ApprovalError as exc:
                raise ApiError(exc.code.value, exc.message, status_code=409) from exc
            updated = self.index.get(run_id) or record
            updated.update(
                {
                    "status": "completed" if result.approval_status in {"approved", "rejected"} else "awaiting_approval",
                    "verdict": result.verdict or updated.get("verdict"),
                    "approval_status": result.approval_status,
                    "approval_request_id": request_id,
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
