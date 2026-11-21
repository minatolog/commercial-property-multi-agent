"""Task 031 返修 R3（报告写出 LF）与 R4（dry-run 副本用 SQLite 备份接口）。"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.fixtures.repository import FixtureRepository
from app.orchestration.approval import (
    ApprovalRequestNotFoundError,
    ApprovalStore,
    StageOrderViolationError,
    build_approval_request,
)

PM = "principal_property_manager_xinghui"
FINANCE = "principal_finance_xinghui"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestR4PreviewUsesConsistentSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "approval.sqlite"
        self.store = ApprovalStore(self.path)
        self.repository = FixtureRepository.load()
        from app.orchestration.approval import ApprovalRule

        raw = self.repository.snapshot()["approval_role_rules"]["rent_reduction_draft"]
        rule = ApprovalRule.from_fixture("rent_reduction_draft", raw)
        draft = next(
            value
            for value in self.repository.snapshot()["approval_drafts"].values()
            if int(value["draft_version"]) == 2
        )
        self.request = build_approval_request(
            draft=draft,
            rule=rule,
            thread_id="thread_r4",
            run_id="run_r4",
            trace_id="trace_r4",
            requested_by="principal_ops_xinghui",
        )
        self.store.create(self.request)

    def _kwargs(self, principal_id: str) -> dict:
        return {
            "principal_id": principal_id,
            "decision": "approve",
            "draft_version": self.request.draft_version,
            "principal": self.repository.principal(principal_id),
        }

    def _sidecars(self) -> dict[str, str | None]:
        return {
            suffix: (_sha(Path(f"{self.path}{suffix}")) if Path(f"{self.path}{suffix}").is_file() else None)
            for suffix in ("", "-wal", "-shm")
        }

    def test_preview_leaves_ledger_byte_identical_and_matches_real_decide(self) -> None:
        before = self._sidecars()
        preview = self.store.preview_decision(self.request.request_id, **self._kwargs(PM))
        self.assertEqual(before, self._sidecars(), "预演不得改动主库 / -wal / -shm 的任何字节")
        self.assertFalse(self.store.decisions(self.request.request_id))

        real = self.store.decide(self.request.request_id, **self._kwargs(PM))
        self.assertEqual(preview["decided_role"], real.decided_role)
        self.assertEqual(preview["idempotent"], real.idempotent)
        self.assertEqual(preview["current_status"], real.request.status)
        # 预演快照上的请求状态与真实执行后的状态逐字段一致（时间戳字段除外）
        def _stable(data):
            if isinstance(data, dict):
                return {k: _stable(v) for k, v in data.items() if not k.endswith("_at")}
            if isinstance(data, list):
                return [_stable(item) for item in data]
            return data

        self.assertEqual(_stable(preview["request"]), _stable(real.request.as_dict()))
        self.assertEqual(
            [item["role"] for item in self.store.decisions(self.request.request_id)],
            [preview["decided_role"]],
        )

    def test_preview_sees_commits_still_in_wal(self) -> None:
        """另一个连接一直开着（主库不会 checkpoint），WAL 里已提交的决定也必须进快照。"""

        holder = sqlite3.connect(self.path)
        try:
            holder.execute("SELECT count(*) FROM sqlite_master").fetchone()
            self.store.decide(self.request.request_id, **self._kwargs(PM))
            wal = Path(f"{self.path}-wal")
            self.assertTrue(wal.is_file() and wal.stat().st_size > 0, "前置条件：提交仍在 WAL 中")
            before = self._sidecars()

            # 第二阶段（财务）预演：只有快照包含 WAL 中的第一阶段决定才会通过
            preview = self.store.preview_decision(self.request.request_id, **self._kwargs(FINANCE))
            self.assertEqual(preview["decided_role"], "finance")
            self.assertEqual(before, self._sidecars())
        finally:
            holder.close()

    def test_preview_still_enforces_rules(self) -> None:
        with self.assertRaises(StageOrderViolationError):
            self.store.preview_decision(self.request.request_id, **self._kwargs(FINANCE))
        self.assertFalse(self.store.decisions(self.request.request_id))

    def test_missing_ledger_is_error_and_not_created(self) -> None:
        missing = Path(self._tmp.name) / "nested" / "approval.sqlite"
        store = ApprovalStore.__new__(ApprovalStore)
        store.path = missing  # 不走 __init__：__init__ 会建表
        with self.assertRaises(ApprovalRequestNotFoundError):
            store.preview_decision(self.request.request_id, **self._kwargs(PM))
        self.assertFalse(missing.exists())


class TestR3ReportsAreWrittenWithLF(unittest.TestCase):
    def test_write_report_uses_lf(self) -> None:
        from app.evaluation.runner import EvaluationReport, write_report

        report = EvaluationReport.__new__(EvaluationReport)
        # 只需要 write_report 用到的属性
        object.__setattr__(report, "started_at", "2026-11-21T00:00:00Z")
        object.__setattr__(report, "split", "heldout")
        object.__setattr__(report, "baseline", "A_test")
        report.as_dict = lambda: {"a": [1, 2], "b": {"c": "多行\n文本"}}  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as tmp:
            target = write_report(report, out_dir=tmp)
            data = target.read_bytes()
        self.assertIn(b"\n", data)
        self.assertNotIn(b"\r", data)


if __name__ == "__main__":
    unittest.main()
