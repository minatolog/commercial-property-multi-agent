"""LangGraph 持久检查点（Task 012）。

关键区分（路线图 Prompt 7 的检查点要求）：

| 存储 | 回答的问题 | 位置 |
|---|---|---|
| LangGraph checkpoint | 「这个任务执行到哪一步、恢复后从哪继续」 | `data/checkpoints/graph.sqlite` |
| 审批台账 | 「谁在什么时候批准了哪个草案版本」 | `data/control/approval.sqlite` |
| 业务数据 | 「租约/账单/工单是什么」 | fixture 或只读数据库 |

三者物理分离：清空 checkpoint 不应影响审批审计，删除审批台账也不应改变业务数据。

标识约定：

- `thread_id`：一条调查任务的持久线索，**跨进程恢复靠它**；
- `run_id`：一次 Runtime 执行；
- `request_id`：一次审批请求；
- `trace_id`：整条调查链路，恢复后保持不变。

为什么用 `AsyncSqliteSaver`：图以 `ainvoke` 运行，LangGraph 会调用 `aget_tuple`，
同步的 `SqliteSaver` 会直接抛 `NotImplementedError`。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from ..paths import CHECKPOINT_DB, CONTROL_DB

__all__ = [
    "CHECKPOINT_DB",
    "CONTROL_DB",
    "checkpoint_config",
    "open_checkpointer",
]


@asynccontextmanager
async def open_checkpointer(path: str | Path | None = None) -> AsyncIterator[Any]:
    """打开异步 SQLite checkpointer；调用方必须在同一事件循环内使用。

    `allowed_msgpack_modules` 显式放行**本项目**的两个状态类型：
    LangGraph 对未知类型的反序列化会告警，并在未来版本中直接拒绝。
    只放行确知的两个模块，不使用 `True`（那会放行任意类型）。
    """

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    import aiosqlite

    target = Path(path) if path is not None else CHECKPOINT_DB
    target.parent.mkdir(parents=True, exist_ok=True)
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.agents.base.contracts", "AgentContext"),
            ("app.agents.base.contracts", "AgentOutput"),
        ]
    )
    async with aiosqlite.connect(str(target)) as connection:
        saver = AsyncSqliteSaver(connection, serde=serde)
        await saver.setup()
        yield saver


def checkpoint_config(thread_id: str) -> dict[str, Any]:
    if not thread_id:
        raise ValueError("thread_id 不能为空：没有它就无法恢复同一条任务线")
    return {"configurable": {"thread_id": thread_id}}
