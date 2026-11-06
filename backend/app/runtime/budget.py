"""共享调用预算：原子预留 / 结算 / 释放。

为什么需要两阶段：

- **预留**在调用真正发生**之前**扣减额度，避免并发任务同时通过检查后超发；
- **结算**用实际消耗替换预留，调用失败也要结算（确实发生了一次调用尝试）；
- **释放**用于调用根本没发生的情况（例如参数校验失败）。

幂等：`call_id` 是幂等键。同一个 `call_id` 重复预留返回既有预留，
重复结算不会二次计入——这是重放节点不会把预算翻倍的关键（Runtime contracts §10.1）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..agents.base.errors import BudgetExhaustedError
from .types import BudgetUsage

__all__ = ["Budget"]


@dataclass(frozen=True)
class _Reservation:
    kind: str
    amount: int


class Budget:
    """并发安全的调用预算。

    只在事件循环内使用（`asyncio.Lock`）；对应 P0 的单进程 Runtime。
    """

    def __init__(
        self,
        *,
        max_tool_calls: int = 10,
        max_model_calls: int = 0,
        max_total_tokens: int = 0,
    ) -> None:
        if max_tool_calls < 0 or max_model_calls < 0 or max_total_tokens < 0:
            raise ValueError("预算上限不能为负数")
        self._max_tool_calls = max_tool_calls
        self._max_model_calls = max_model_calls
        self._max_total_tokens = max_total_tokens
        self._used: dict[str, int] = {"tool": 0, "model": 0, "tokens": 0}
        self._reserved: dict[str, _Reservation] = {}
        self._settled: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ---------------- 预留 ----------------

    async def reserve_tool_call(self, call_id: str) -> None:
        await self._reserve(call_id, "tool", 1)

    async def reserve_model_call(self, call_id: str) -> None:
        await self._reserve(call_id, "model", 1)

    async def reserve_tokens(self, call_id: str, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("token 预留不能为负")
        await self._reserve(call_id, "tokens", tokens)

    async def _reserve(self, call_id: str, kind: str, amount: int) -> None:
        if not call_id:
            raise ValueError("call_id 不能为空")
        async with self._lock:
            if call_id in self._settled or call_id in self._reserved:
                return
            if not self._within_limit(kind, amount):
                raise BudgetExhaustedError(
                    f"预算不足：{self._describe(kind)} 已用 {self._used[kind]}、"
                    f"预留 {self._reserved_amount(kind)}、上限 {self._limit(kind)}",
                    details={
                        "kind": kind,
                        "used": self._used[kind],
                        "reserved": self._reserved_amount(kind),
                        "limit": self._limit(kind),
                    },
                )
            self._reserved[call_id] = _Reservation(kind=kind, amount=amount)

    # ---------------- 结算 / 释放 ----------------

    async def settle(self, call_id: str, *, tokens: int | None = None) -> None:
        """结算一次调用；重复调用是幂等的。"""

        async with self._lock:
            if call_id in self._settled:
                return
            reservation = self._reserved.pop(call_id, None)
            if reservation is None:
                # 没有预留却来结算：说明调用方绕过了 reserve，直接拒绝而不是静默记账
                raise BudgetExhaustedError(
                    f"call_id {call_id!r} 没有预留记录，拒绝结算",
                    details={"call_id": call_id},
                )
            if reservation.kind == "tokens":
                actual = reservation.amount if tokens is None else tokens
                if not self._within_limit("tokens", actual - reservation.amount, include_reserved=False):
                    actual = max(0, self._max_total_tokens - self._used["tokens"])
                self._used["tokens"] += actual
            else:
                self._used[reservation.kind] += 1
            self._settled[call_id] = reservation.kind

    async def release(self, call_id: str) -> None:
        """释放未真正发生的预留。"""

        async with self._lock:
            self._reserved.pop(call_id, None)

    # ---------------- 查询 ----------------

    def snapshot(self) -> BudgetUsage:
        return BudgetUsage(
            max_tool_calls=self._max_tool_calls,
            max_model_calls=self._max_model_calls,
            max_total_tokens=self._max_total_tokens,
            used_tool_calls=self._used["tool"],
            used_model_calls=self._used["model"],
            used_total_tokens=self._used["tokens"],
        )

    # ---------------- 内部 ----------------

    def _limit(self, kind: str) -> int:
        return {
            "tool": self._max_tool_calls,
            "model": self._max_model_calls,
            "tokens": self._max_total_tokens,
        }[kind]

    def _reserved_amount(self, kind: str) -> int:
        return sum(r.amount for r in self._reserved.values() if r.kind == kind)

    def _within_limit(self, kind: str, amount: int, *, include_reserved: bool = True) -> bool:
        used = self._used[kind]
        reserved = self._reserved_amount(kind) if include_reserved else 0
        return used + reserved + amount <= self._limit(kind)

    @staticmethod
    def _describe(kind: str) -> str:
        return {"tool": "工具调用数", "model": "模型调用数", "tokens": "总 token"}.get(
            kind, kind
        )
