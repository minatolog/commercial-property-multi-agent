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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

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


class RunRequest(BaseModel):
    """提交运行的请求体（Task 016 / S3：严格校验，非法输入一律 4xx）。

    `extra="forbid"` 同时承担两件事：拒绝拼写错误的字段，以及
    在出现 `principal_id` 之类的身份字段时直接被 Pydantic 拦下（再经业务层给出明确文案）。
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    lease_id: str = Field(min_length=1, max_length=64)
    with_approval: StrictBool = True
    max_tool_calls: StrictInt = Field(default=12, ge=1, le=50)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(default="approve", pattern="^(approve|reject)$")
    draft_version: StrictInt = Field(ge=1, le=1000)
    reason: str | None = Field(default=None, max_length=1000)


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

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """把 Pydantic 校验失败统一成可追踪的 422。

        修复前：`max_tool_calls="abc"` / `None` / `-1` 会抛 500，
        `question=null` 被 `str()` 成 "None" 后创建任务（S3）。
        """

        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())[1:]) or "body",
                "message": str(error.get("msg", "")),
            }
            for error in exc.errors()
        ]
        leaked = sorted(
            {
                str(part)
                for error in exc.errors()
                for part in error.get("loc", ())
                if str(part) in FORBIDDEN_FIELDS
            }
        )
        code = "invalid_request"
        message = "请求参数不合法"
        if leaked:
            message = f"请求不得包含身份字段: {leaked}（身份由服务端注入）"
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": details,
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
        )

    @app.post("/api/runs", status_code=201)
    async def submit_run(request: Request, payload: RunRequest) -> dict[str, Any]:
        return await _service(request).submit(
            question=payload.question,
            lease_id=payload.lease_id,
            with_approval=payload.with_approval,
            max_tool_calls=payload.max_tool_calls,
        )

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
    async def decide(
        request: Request, run_id: str, payload: ApprovalRequest
    ) -> dict[str, Any]:
        actor = request.headers.get("X-Actor-Id") or ""
        if not actor:
            raise ApiError(
                "invalid_request",
                "缺少 X-Actor-Id 请求头（只允许服务端白名单内的审批人）",
            )
        return await _service(request).decide(
            run_id=run_id,
            actor_id=actor,
            decision=payload.decision,
            draft_version=payload.draft_version,
            reason=payload.reason,
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
