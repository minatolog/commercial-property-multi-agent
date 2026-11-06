"""FastAPI 适配层（Task 014）。

安全边界：

1. **身份由服务端注入**：请求体/查询参数里出现 `principal_id` / `permissions` 一律 400；
   真实身份来自 `DEMO_PRINCIPAL_ID`（默认 `principal_ops_xinghui`）。
2. **审批动作再校验**：审批人只能从服务端白名单（`DEMO_APPROVERS`）里选，
   前端传什么角色都不改变权限。
3. **错误可追踪**：每个响应带 `X-Trace-Id`，错误体统一 `{"error": {code, message, trace_id}}`。
4. **展示层不碰内部**：路由只调用 `WorkflowService`，不 import 数据库模型或 Agent 类。

启动（在 `backend/` 下）：

    python -m app.api            # 或 uvicorn app.api.app:app --reload

演示页：<http://127.0.0.1:8000/>
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..agents.base.errors import AgentError
from ..orchestration.approval import ApprovalError
from .service import (
    DEFAULT_APPROVER_ALLOWLIST,
    DEFAULT_PRINCIPAL,
    ApiError,
    WorkflowService,
)

__all__ = ["app", "create_app"]

STATIC_DIR = Path(__file__).resolve().parent / "static"

#: 客户端**不允许**自报的身份相关字段
FORBIDDEN_FIELDS = frozenset({"principal_id", "permissions", "roles", "approval_roles"})


def _service(request: Request) -> WorkflowService:
    return request.app.state.service  # type: ignore[no-any-return]


def create_app(*, service: WorkflowService | None = None) -> FastAPI:
    app = FastAPI(
        title="commercial-property-multi-agent",
        description="商业地产多 Agent 工作流演示 API（只读分析 + 人工审批）",
        version="1.0.0",
    )
    app.state.service = service or WorkflowService(
        principal_id=os.environ.get("DEMO_PRINCIPAL_ID", DEFAULT_PRINCIPAL),
        approver_allowlist=tuple(
            item.strip()
            for item in os.environ.get(
                "DEMO_APPROVERS", ",".join(DEFAULT_APPROVER_ALLOWLIST)
            ).split(",")
            if item.strip()
        ),
    )

    @app.middleware("http")
    async def attach_trace_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        trace_id = request.headers.get("X-Trace-Id") or f"api_{uuid.uuid4().hex[:12]}"
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
        )

    @app.exception_handler(AgentError)
    async def handle_agent_error(request: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": exc.code.value,
                    "message": exc.message,
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
        )

    @app.exception_handler(ApprovalError)
    async def handle_approval_error(request: Request, exc: ApprovalError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": exc.code.value,
                    "message": exc.message,
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        page = STATIC_DIR / "index.html"
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.get("/api/meta")
    async def meta(request: Request) -> dict[str, Any]:
        svc = _service(request)
        return {
            "service": "commercial-property-multi-agent",
            "trusted_principal": svc.principal_id,
            "approver_allowlist": list(svc.approver_allowlist),
            "note": "身份由服务端注入；请求不能自报 principal 或权限",
        }

    @app.post("/api/runs", status_code=201)
    async def submit_run(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        leaked = FORBIDDEN_FIELDS & set(payload)
        if leaked:
            raise ApiError(
                "invalid_request",
                f"请求不得包含身份字段: {sorted(leaked)}（身份由服务端注入）",
            )
        result = await _service(request).submit(
            question=str(payload.get("question", "")),
            lease_id=str(payload.get("lease_id", "")),
            with_approval=bool(payload.get("with_approval", True)),
            max_tool_calls=int(payload.get("max_tool_calls", 12)),
        )
        return result

    @app.get("/api/runs")
    async def list_runs(request: Request, limit: int = 50) -> dict[str, Any]:
        runs = _service(request).list_runs(limit=max(1, min(limit, 200)))
        return {"count": len(runs), "runs": runs}

    @app.get("/api/runs/{run_id}")
    async def get_run(request: Request, run_id: str) -> dict[str, Any]:
        return _service(request).get_run(run_id)

    @app.get("/api/runs/{run_id}/traces")
    async def get_traces(request: Request, run_id: str) -> dict[str, Any]:
        return _service(request).get_traces(run_id)

    @app.post("/api/runs/{run_id}/approvals")
    async def decide(request: Request, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        leaked = FORBIDDEN_FIELDS & set(payload)
        if leaked:
            raise ApiError(
                "invalid_request",
                f"请求不得包含身份字段: {sorted(leaked)}（审批人由服务端白名单决定）",
            )
        actor = request.headers.get("X-Actor-Id") or ""
        if not actor:
            raise ApiError(
                "invalid_request",
                "缺少 X-Actor-Id 请求头（只允许服务端白名单内的审批人）",
            )
        decision = str(payload.get("decision", "approve"))
        if decision not in {"approve", "reject"}:
            raise ApiError("invalid_request", f"非法 decision: {decision!r}")
        draft_version = payload.get("draft_version")
        if not isinstance(draft_version, int):
            raise ApiError("invalid_request", "draft_version 必须是整数")
        return await _service(request).decide(
            run_id=run_id,
            actor_id=actor,
            decision=decision,
            draft_version=draft_version,
            reason=payload.get("reason"),
        )

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - 手动启动
    import uvicorn

    uvicorn.run(
        "app.api.app:app",
        host=os.environ.get("DEMO_HOST", "127.0.0.1"),
        port=int(os.environ.get("DEMO_PORT", "8000")),
        reload=False,
    )
