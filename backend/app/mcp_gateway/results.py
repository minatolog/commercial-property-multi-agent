"""`ToolExecution` → 统一结果信封 / MCP `CallToolResult`（Task 033A）。

协议外壳只负责**呈现**，不改变语义：

- **只有执行器判定成功（`ToolExecution.ok`）才是 `ok`**。任何失败都必须以
  `isError: true` 返回，并带上执行器的错误码，不能"看起来成功"；
- 状态映射写成显式表（`_STATUS_TO_RESULT` / `_CODE_TO_RESULT`），
  表里没有的状态或错误码一律落到 `error`，不做乐观猜测；
- 金额保持为字符串：执行器已经用 `model_dump(mode="json")` 把 `Decimal`
  序列化成十进制字符串，信封走 pydantic JSON 模式，任何路径都不经过 `float`；
  `envelope_output_schema` 里金额字段也声明为 `string`；
- 证据原样带出（`Evidence` 的全部字段，含文档、版本、页码、条款号等）。

结果同时放进 `structuredContent` 和一条 JSON 文本 `content`，两者内容一致。
"""

from __future__ import annotations

import json
from typing import Any, Final, Literal, TypeAlias

from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import core_schema

from ..agents.base.errors import ErrorCode
from ..runtime.types import ToolExecution, ToolStatus

__all__ = [
    "RESULT_STATUSES",
    "EnvelopeError",
    "ResultStatus",
    "ToolResultEnvelope",
    "envelope_output_schema",
    "to_call_tool_result",
    "to_envelope",
]

ResultStatus: TypeAlias = Literal["ok", "denied", "error", "timeout", "budget_exhausted"]

RESULT_STATUSES: Final[tuple[ResultStatus, ...]] = (
    "ok",
    "denied",
    "error",
    "timeout",
    "budget_exhausted",
)

#: 执行器终态 → 信封状态。未列出的状态一律 `error`。
_STATUS_TO_RESULT: Final[dict[str, ResultStatus]] = {
    ToolStatus.OK.value: "ok",
    ToolStatus.DENIED.value: "denied",
    ToolStatus.TIMEOUT.value: "timeout",
    ToolStatus.BUDGET_EXHAUSTED.value: "budget_exhausted",
    ToolStatus.ERROR.value: "error",
}

#: 执行器错误码 → 信封状态；与 `ToolExecutor._status_for` 保持一致。
#: 未列出的错误码（如 `invalid_tool_arguments` / `record_not_found`）一律 `error`。
_CODE_TO_RESULT: Final[dict[str, ResultStatus]] = {
    ErrorCode.TOOL_NOT_FOUND.value: "denied",
    ErrorCode.TOOL_NOT_ALLOWED.value: "denied",
    ErrorCode.PERMISSION_DENIED.value: "denied",
    ErrorCode.PROJECT_SCOPE_DENIED.value: "denied",
    ErrorCode.BUDGET_EXHAUSTED.value: "budget_exhausted",
    ErrorCode.TOOL_TIMEOUT.value: "timeout",
}

_ERROR_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "minLength": 1},
        "message": {"type": "string"},
    },
    "required": ["code", "message"],
    "additionalProperties": False,
}


class _StringDecimalSchema(GenerateJsonSchema):
    """让 `Decimal` 在输出 Schema 中声明为 `string`。

    pydantic 默认生成 `{"anyOf": [{"type": "number"}, {"type": "string"}]}`，
    这会让外部客户端以为金额可以是浮点数。网关的金额只以十进制字符串传输，
    因此这里把 `Decimal` 的 Schema 固定为 `string`。
    """

    def decimal_schema(self, schema: core_schema.DecimalSchema) -> JsonSchemaValue:
        return {"type": "string"}


class EnvelopeError(BaseModel):
    """信封里的错误信息（只暴露执行器错误码与消息）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str


class ToolResultEnvelope(BaseModel):
    """MCP 工具调用的统一结果信封（Payload Schema 见 `envelope_output_schema`）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str = Field(min_length=1)
    status: ResultStatus
    #: 失败时为空（`None`），与 `envelope_output_schema` 的 nullable 声明一致。
    data: dict[str, Any] | None = None
    evidence: tuple[dict[str, Any], ...] = ()
    error: EnvelopeError | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> "ToolResultEnvelope":
        if self.status == "ok":
            if self.error is not None:
                raise ValueError("status=ok 的信封不能携带 error")
        else:
            if self.data is not None:
                raise ValueError("失败信封的 data 必须为空")
            if self.error is None:
                raise ValueError("失败信封必须携带 error")
        return self


def _resolve_status(execution: ToolExecution) -> ResultStatus:
    """执行器结果 → 信封状态。

    - 只有"执行器判定成功且没有错误详情"才是 `ok`；
    - 有错误码时以错误码为准（与执行器的 `_status_for` 同源）；
    - 没有错误码但有终态时按终态表映射；
    - 其余（未知终态、缺失错误详情）一律 `error`，宁可报错也不乐观放行。
    """

    if execution.error is None and execution.ok:
        return "ok"
    if execution.error is not None:
        return _CODE_TO_RESULT.get(execution.error.code.value, "error")
    return _STATUS_TO_RESULT.get(execution.status, "error")


def _fallback_error(execution: ToolExecution) -> EnvelopeError:
    """执行器没有给出错误详情时，生成一个可审计的错误。"""

    return EnvelopeError(
        code=ErrorCode.INTERNAL_ERROR.value,
        message=(
            f"工具 {execution.tool_name!r} 以状态 {execution.status!r} 结束，"
            "但执行器未提供错误详情"
        ),
    )


def to_envelope(execution: ToolExecution) -> ToolResultEnvelope:
    """把一次执行结果转成结果信封。"""

    status = _resolve_status(execution)
    is_ok = status == "ok"

    error: EnvelopeError | None = None
    if not is_ok:
        if execution.error is not None:
            error = EnvelopeError(
                code=execution.error.code.value,
                message=execution.error.message,
            )
        else:
            error = _fallback_error(execution)

    return ToolResultEnvelope(
        call_id=execution.call_id,
        status=status,
        data=execution.data if is_ok else None,
        evidence=tuple(item.model_dump(mode="json") for item in execution.evidence),
        error=error,
    )


def _envelope_json_text(payload: dict[str, Any]) -> str:
    """信封的 JSON 文本；`payload` 与 `structuredContent` 是同一份数据。"""

    # `allow_nan=False`：宁可序列化失败，也不把 NaN/Infinity 发成非法 JSON。
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def to_call_tool_result(execution: ToolExecution) -> CallToolResult:
    """`ToolExecution` → MCP `CallToolResult`（结构化 + 文本两份同内容）。"""

    envelope = to_envelope(execution)
    # 只序列化一次：`structuredContent` 与文本内容必须逐字节同源。
    payload = envelope.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=_envelope_json_text(payload))],
        structured_content=payload,
        is_error=envelope.status != "ok",
    )


def envelope_output_schema(output_model: type[BaseModel]) -> dict[str, Any]:
    """生成信封的 JSON Schema。

    `data` 部分是 `output_model.model_json_schema()`（`Decimal` 一律为 `string`），
    并使用 `anyOf [data, null]`：失败信封的 `data` 为空，也必须能通过同一份 Schema。
    Schema 中的 `$ref` 指向文档根部的 `$defs`，因此把模型自带的 `$defs`
    提升到信封根部，避免嵌套后引用失效。
    """

    data_schema = output_model.model_json_schema(schema_generator=_StringDecimalSchema)
    defs = data_schema.pop("$defs", None)

    envelope: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{output_model.__name__}ToolResultEnvelope",
        "type": "object",
        "properties": {
            "call_id": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": list(RESULT_STATUSES)},
            "data": {
                "description": "成功时为工具输出；失败时为空（null）。金额一律为十进制字符串。",
                "anyOf": [data_schema, {"type": "null"}],
                "default": None,
            },
            "evidence": {
                "description": "执行器补齐来源字段的证据，原样带出。",
                "type": "array",
                "items": {"type": "object"},
            },
            "error": {
                "description": "失败时的执行器错误码与消息。",
                "anyOf": [_ERROR_SCHEMA, {"type": "null"}],
                "default": None,
            },
        },
        "required": ["call_id", "status", "data", "evidence", "error"],
        "additionalProperties": False,
    }
    if defs:
        envelope["$defs"] = defs
    return envelope
