"""控制面装配（Task 012）：checkpointer + 审批台账一起开、一起关。

为什么单独一个模块：
- `AsyncSqliteSaver` 需要一个长生命周期的连接，必须由调用方显式关闭，不能藏在全局变量里；
- CLI 的 `investigate` 与 `approve` 是**两个进程**，它们靠同一个 checkpoint 文件
  与同一个审批台账文件衔接，路径必须一致。

存储位置（均在 `data/` 下，已被 `.gitignore` 排除）：

| 文件 | 内容 |
|---|---|
| `data/checkpoints/graph.sqlite` | LangGraph 检查点（恢复流程用） |
| `data/control/approval.sqlite` | 审批请求 / 决策审计 / 恢复幂等台账 |
| `data/business/business.sqlite` | 只读业务数据副本（Task 010，可选） |
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from .orchestration.approval import ApprovalStore
from .orchestration.checkpointing import open_checkpointer
from .paths import CHECKPOINT_DB, CONTROL_DB

__all__ = ["ControlPlane", "control_plane"]


@dataclass
class ControlPlane:
    checkpointer: Any
    approval_store: ApprovalStore
    checkpoint_path: Path
    approval_path: Path


@asynccontextmanager
async def control_plane(
    *,
    checkpoint_path: str | Path | None = None,
    approval_path: str | Path | None = None,
) -> AsyncIterator[ControlPlane]:
    checkpoint = Path(checkpoint_path) if checkpoint_path else CHECKPOINT_DB
    approval = Path(approval_path) if approval_path else CONTROL_DB
    async with open_checkpointer(checkpoint) as checkpointer:
        yield ControlPlane(
            checkpointer=checkpointer,
            approval_store=ApprovalStore(approval),
            checkpoint_path=checkpoint,
            approval_path=approval,
        )
