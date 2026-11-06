"""Task 012：持久检查点、人工审批、暂停恢复与故障注入。

验证边界（必须如实理解）：

- checkpoint 与审批台账都是**本地 SQLite**，用于单机演示与回归；不宣称分布式恰好一次；
- 恢复的是**流程位置**，不是"未完成的外部副作用"；本项目没有任何外部副作用；
- 「进程退出后恢复」用"另开 control_plane / 另开事件循环再恢复"来验证，
  等价于 CLI 分两个进程执行，但不是真的重启操作系统。
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.control_plane import control_plane
from app.fixtures.repository import FixtureRepository
from app.investigation_demo import build_investigation_bundle
from app.orchestration.approval import (
    ApprovalConflictError,
    ApprovalExpiredError,
    ApprovalStore,
    ApprovalValidationError,
    DraftVersionMismatchError,
    DuplicatePrincipalError,
    PermissionDeniedForApprovalError,
    ProjectScopeDeniedForApprovalError,
    SelfApprovalForbiddenError,
    StageOrderViolationError,
    build_approval_request,
)
from app.paths import CHECKPOINT_DB, CONTROL_DB, DATA_DIR

QUESTION = (
    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
    "并要求减免费用。请核对合同、账单、付款和工单，分析争议原因。"
)
LEASE = "lease_xh_a301_2025"


def _rule() -> object:
    repository = FixtureRepository.load()
    from app.orchestration.approval import ApprovalRule

    raw = repository.snapshot()["approval_role_rules"]["rent_reduction_draft"]
    return ApprovalRule.from_fixture("rent_reduction_draft", raw)


def _draft(repository: FixtureRepository, version: int = 2) -> dict:
    drafts = repository.snapshot()["approval_drafts"]
    item = next(
        value
        for value in drafts.values()
        if int(value["draft_version"]) == version
    )
    return item


class TestApprovalStoreRules(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = ApprovalStore(Path(self._tmp.name) / "approval.sqlite")
        self.repository = FixtureRepository.load()
        self.rule = _rule()
        self.request = build_approval_request(
            draft=_draft(self.repository),
            rule=self.rule,  # type: ignore[arg-type]
            thread_id="thread_t1",
            run_id="run_t1",
            trace_id="trace_t1",
            requested_by="principal_ops_xinghui",
        )
        self.store.create(self.request)

    def _principal(self, principal_id: str) -> dict:
        return self.repository.principal(principal_id)

    def test_serial_stages_require_two_distinct_principals(self) -> None:
        outcome = self.store.decide(
            self.request.request_id,
            principal_id="principal_property_manager_xinghui",
            decision="approve",
            draft_version=self.request.draft_version,
            principal=self._principal("principal_property_manager_xinghui"),
        )
        self.assertFalse(outcome.fully_approved)
        self.assertEqual(outcome.request.status, "pending")

        outcome = self.store.decide(
            self.request.request_id,
            principal_id="principal_finance_xinghui",
            decision="approve",
            draft_version=self.request.draft_version,
            principal=self._principal("principal_finance_xinghui"),
        )
        self.assertTrue(outcome.fully_approved)
        self.assertEqual(len(self.store.decisions(self.request.request_id)), 2)

    def test_finance_cannot_skip_property_manager(self) -> None:
        with self.assertRaises(StageOrderViolationError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_finance_xinghui",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_finance_xinghui"),
            )

    def test_requester_cannot_self_approve(self) -> None:
        request = build_approval_request(
            draft=_draft(self.repository),
            rule=self.rule,  # type: ignore[arg-type]
            thread_id="thread_self",
            run_id="run",
            trace_id="trace",
            requested_by="principal_finance_xinghui",
        )
        self.store.create(request)
        with self.assertRaises(SelfApprovalForbiddenError):
            self.store.decide(
                request.request_id,
                principal_id="principal_finance_xinghui",
                decision="approve",
                draft_version=request.draft_version,
                principal=self._principal("principal_finance_xinghui"),
            )

    def test_permission_denied_without_decide_permission(self) -> None:
        with self.assertRaises(PermissionDeniedForApprovalError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_billing_xinghui_readonly",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_billing_xinghui_readonly"),
            )

    def test_cross_project_approval_denied(self) -> None:
        with self.assertRaises(ProjectScopeDeniedForApprovalError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_finance_jinlan",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_finance_jinlan"),
            )

    def test_version_mismatch_is_rejected(self) -> None:
        with self.assertRaises(DraftVersionMismatchError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_property_manager_xinghui",
                decision="approve",
                draft_version=1,
                principal=self._principal("principal_property_manager_xinghui"),
            )

    def test_expired_request_is_rejected_and_marked(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=30)
        with self.assertRaises(ApprovalExpiredError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_property_manager_xinghui",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_property_manager_xinghui"),
                now=future,
            )
        stored = self.store.get(self.request.request_id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.status, "expired")
        self.assertEqual(self.store.decisions(self.request.request_id), [])

    def test_same_principal_cannot_fill_both_stages(self) -> None:
        self.store.decide(
            self.request.request_id,
            principal_id="principal_property_manager_xinghui",
            decision="approve",
            draft_version=self.request.draft_version,
            principal=self._principal("principal_property_manager_xinghui"),
        )
        # 伪造一个同时具备两个角色的主体：仍必须被"同一人不得重复签署"拦住
        forged = dict(self._principal("principal_property_manager_xinghui"))
        forged["approval_roles"] = ["property_manager", "finance"]
        with self.assertRaises(Exception) as ctx:
            self.store.decide(
                self.request.request_id,
                principal_id="principal_property_manager_xinghui",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=forged,
            )
        self.assertIsInstance(ctx.exception, DuplicatePrincipalError)

    def test_reject_stops_the_chain(self) -> None:
        outcome = self.store.decide(
            self.request.request_id,
            principal_id="principal_property_manager_xinghui",
            decision="reject",
            draft_version=self.request.draft_version,
            principal=self._principal("principal_property_manager_xinghui"),
            reason="证据不足",
        )
        self.assertEqual(outcome.request.status, "rejected")
        with self.assertRaises(ApprovalConflictError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_finance_xinghui",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_finance_xinghui"),
            )

    def test_duplicate_stage_decision_is_idempotent(self) -> None:
        for _ in range(2):
            outcome = self.store.decide(
                self.request.request_id,
                principal_id="principal_property_manager_xinghui",
                decision="approve",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_property_manager_xinghui"),
            )
        self.assertEqual(outcome.request.status, "pending")
        self.assertEqual(len(self.store.decisions(self.request.request_id)), 1)

    def test_create_is_idempotent_per_thread_and_version(self) -> None:
        again = build_approval_request(
            draft=_draft(self.repository),
            rule=self.rule,  # type: ignore[arg-type]
            thread_id="thread_t1",
            run_id="run_t2",
            trace_id="trace_t2",
            requested_by="principal_ops_xinghui",
        )
        existing = self.store.create(again)
        self.assertEqual(existing.request_id, self.request.request_id)
        self.assertEqual(len(self.store.find_by_thread("thread_t1")), 1)

    def test_invalid_decision_value_rejected(self) -> None:
        with self.assertRaises(ApprovalValidationError):
            self.store.decide(
                self.request.request_id,
                principal_id="principal_property_manager_xinghui",
                decision="maybe",
                draft_version=self.request.draft_version,
                principal=self._principal("principal_property_manager_xinghui"),
            )


class TestControlPlaneSeparation(unittest.TestCase):
    def test_paths_are_distinct_and_gitignored(self) -> None:
        self.assertNotEqual(CHECKPOINT_DB, CONTROL_DB)
        self.assertTrue(str(CHECKPOINT_DB).startswith(str(DATA_DIR)))
        self.assertTrue(str(CONTROL_DB).startswith(str(DATA_DIR)))

    def test_gitignore_excludes_runtime_state(self) -> None:
        import subprocess

        project_root = DATA_DIR.parent
        for target in ("data/checkpoints/graph.sqlite", "data/control/approval.sqlite"):
            result = subprocess.run(
                ["git", "check-ignore", "-q", target],
                cwd=project_root,
                check=False,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, msg=f"{target} 未被 .gitignore 忽略")


class TestPausedAndResumedFlow(unittest.IsolatedAsyncioTestCase):
    async def test_investigation_pauses_then_resumes_across_control_plane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkpoint = base / "graph.sqlite"
            approval = base / "approval.sqlite"

            async with control_plane(
                checkpoint_path=checkpoint, approval_path=approval
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                first = await bundle.investigator.investigate(
                    question=QUESTION, lease_id=LEASE, context=bundle.context,
                    thread_id="thread_flow",
                )
                self.assertEqual(first.approval_status, "pending_approval")
                self.assertIsNotNone(first.approval_request)
                self.assertIsNone(first.approved_draft)
                request = plane.approval_store.pending()[0]
                self.assertEqual(request.draft_version, 2)

            # 进程退出等价：新的 control_plane（新连接）恢复同一条 thread
            async with control_plane(
                checkpoint_path=checkpoint, approval_path=approval
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                stage1 = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_property_manager_xinghui",
                )
                self.assertEqual(stage1.approval_status, "pending_next_stage")
                self.assertIsNone(stage1.approved_draft)

            async with control_plane(
                checkpoint_path=checkpoint, approval_path=approval
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                stage2 = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_finance_xinghui",
                )
                self.assertEqual(stage2.approval_status, "approved")
                self.assertIsNotNone(stage2.approved_draft)
                assert stage2.approved_draft is not None
                self.assertEqual(stage2.approved_draft["status"], "approved_draft_only")
                self.assertEqual(stage2.approved_draft["executed_side_effects"], [])
                self.assertEqual(stage2.approved_draft["draft_version"], 2)
                self.assertEqual(stage2.approved_draft["amount"], "700.00")

                duplicate = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_finance_xinghui",
                )
                self.assertEqual(duplicate.approval_status, "approved")
                self.assertTrue(
                    any("重复恢复" in warning for warning in duplicate.warnings)
                )
                self.assertEqual(len(plane.approval_store.decisions(request.request_id)), 2)

    async def test_rejected_draft_never_produces_approved_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            async with control_plane(
                checkpoint_path=base / "graph.sqlite",
                approval_path=base / "approval.sqlite",
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                await bundle.investigator.investigate(
                    question=QUESTION, lease_id=LEASE, context=bundle.context,
                    thread_id="thread_reject",
                )
                request = plane.approval_store.pending()[0]
                result = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="reject",
                    draft_version=request.draft_version,
                    principal_id="principal_property_manager_xinghui",
                )
                self.assertEqual(result.approval_status, "rejected")
                self.assertIsNone(result.approved_draft)
                stored = plane.approval_store.get(request.request_id)
                assert stored is not None
                self.assertEqual(stored.status, "rejected")

    async def test_resume_with_stale_version_is_refused_and_graph_stays_paused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            async with control_plane(
                checkpoint_path=base / "graph.sqlite",
                approval_path=base / "approval.sqlite",
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                await bundle.investigator.investigate(
                    question=QUESTION, lease_id=LEASE, context=bundle.context,
                    thread_id="thread_stale",
                )
                request = plane.approval_store.pending()[0]
                with self.assertRaises(DraftVersionMismatchError):
                    await bundle.investigator.resume(
                        request_id=request.request_id,
                        decision="approve",
                        draft_version=1,
                        principal_id="principal_property_manager_xinghui",
                    )
                snapshot = await bundle.investigator._graph.aget_state(  # noqa: SLF001
                    {"configurable": {"thread_id": "thread_stale"}}
                )
                self.assertEqual(snapshot.next, ("approval",))

    async def test_budget_exhaustion_blocks_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            async with control_plane(
                checkpoint_path=base / "graph.sqlite",
                approval_path=base / "approval.sqlite",
            ) as plane:
                # 预算恰好只够完成子任务，审批门必然拿不到额度
                bundle = build_investigation_bundle(
                    control_plane=plane,
                    max_tool_calls=4,
                )
                result = await bundle.investigator.investigate(
                    question=QUESTION, lease_id=LEASE, context=bundle.context,
                    thread_id="thread_budget",
                )
                self.assertIn(
                    result.approval_status, {"blocked_budget", "pending_approval"}
                )
                if result.approval_status == "blocked_budget":
                    self.assertTrue(
                        any("预算耗尽" in warning for warning in result.warnings)
                    )
                    self.assertEqual(plane.approval_store.pending(), [])


class TestApprovalIdentityAndAudit(unittest.IsolatedAsyncioTestCase):
    async def test_resume_reuses_persisted_request_id(self) -> None:
        """回归 F5：恢复后返回的审批请求必须就是台账里那条，不能是新随机 ID。"""

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            async with control_plane(
                checkpoint_path=base / "graph.sqlite",
                approval_path=base / "approval.sqlite",
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                await bundle.investigator.investigate(
                    question=QUESTION, lease_id=LEASE, context=bundle.context,
                    thread_id="thread_identity",
                )
                request = plane.approval_store.pending()[0]

                first = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_property_manager_xinghui",
                )
                self.assertEqual(
                    first.approval_request["request_id"], request.request_id
                )

                second = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_finance_xinghui",
                )

                # 1) 返回的 ID 必须在台账里真实存在
                returned_id = second.approval_request["request_id"]
                self.assertEqual(returned_id, request.request_id)
                stored = plane.approval_store.get(returned_id)
                self.assertIsNotNone(stored, "返回的审批请求必须能在台账中查到")
                assert stored is not None

                # 2) ID / 版本 / 状态 / 阶段与持久记录完全一致
                self.assertEqual(second.approval_status, stored.status)
                self.assertEqual(stored.status, "approved")
                self.assertEqual(second.approval_request["draft_version"], stored.draft_version)
                self.assertEqual(
                    [stage["status"] for stage in second.approval_request["stages"]],
                    ["approved", "approved"],
                )
                self.assertEqual(
                    second.approved_draft["request_id"], stored.request_id
                )
                self.assertEqual(
                    [item["decided_by"] for item in second.approved_draft["approved_stages"]],
                    ["principal_property_manager_xinghui", "principal_finance_xinghui"],
                )

    async def test_approval_reason_is_persisted(self) -> None:
        """审批意见必须落到审计表（API/CLI 传递 `reason` 的落点）。"""

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            async with control_plane(
                checkpoint_path=base / "graph.sqlite",
                approval_path=base / "approval.sqlite",
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                await bundle.investigator.investigate(
                    question=QUESTION, lease_id=LEASE, context=bundle.context,
                    thread_id="thread_reason",
                )
                request = plane.approval_store.pending()[0]
                await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="reject",
                    draft_version=request.draft_version,
                    principal_id="principal_property_manager_xinghui",
                    reason="证据不足，需补充附件B",
                )
                decisions = plane.approval_store.decisions(request.request_id)
                self.assertEqual(decisions[0]["reason"], "证据不足，需补充附件B")


class TestTerminalIdempotencyIsGuarded(unittest.IsolatedAsyncioTestCase):
    """回归 S1：终态审批的幂等分支不得绕过版本与授权校验。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    async def _approved_request(self):
        async with control_plane(
            checkpoint_path=self.base / "graph.sqlite",
            approval_path=self.base / "approval.sqlite",
        ) as plane:
            bundle = build_investigation_bundle(control_plane=plane)
            await bundle.investigator.investigate(
                question=QUESTION, lease_id=LEASE, context=bundle.context,
                thread_id="thread_s1",
            )
            request = plane.approval_store.pending()[0]
            for principal in (
                "principal_property_manager_xinghui",
                "principal_finance_xinghui",
            ):
                await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id=principal,
                )
            return plane.approval_store.get(request.request_id)

    async def test_wrong_version_cannot_replay_as_approved(self) -> None:
        stored = await self._approved_request()
        assert stored is not None
        async with control_plane(
            checkpoint_path=self.base / "graph.sqlite",
            approval_path=self.base / "approval.sqlite",
        ) as plane:
            bundle = build_investigation_bundle(control_plane=plane)
            with self.assertRaises(DraftVersionMismatchError):
                await bundle.investigator.resume(
                    request_id=stored.request_id,
                    decision="approve",
                    draft_version=999,
                    principal_id="principal_finance_xinghui",
                )

    async def test_unauthorised_principal_cannot_replay(self) -> None:
        stored = await self._approved_request()
        assert stored is not None
        async with control_plane(
            checkpoint_path=self.base / "graph.sqlite",
            approval_path=self.base / "approval.sqlite",
        ) as plane:
            bundle = build_investigation_bundle(control_plane=plane)
            with self.assertRaises(PermissionDeniedForApprovalError):
                await bundle.investigator.resume(
                    request_id=stored.request_id,
                    decision="approve",
                    draft_version=stored.draft_version,
                    principal_id="principal_billing_xinghui_readonly",
                )

    async def test_correct_replay_is_still_idempotent(self) -> None:
        stored = await self._approved_request()
        assert stored is not None
        async with control_plane(
            checkpoint_path=self.base / "graph.sqlite",
            approval_path=self.base / "approval.sqlite",
        ) as plane:
            bundle = build_investigation_bundle(control_plane=plane)
            replay = await bundle.investigator.resume(
                request_id=stored.request_id,
                decision="approve",
                draft_version=stored.draft_version,
                principal_id="principal_finance_xinghui",
            )
            self.assertEqual(replay.approval_status, "approved")
            self.assertIsNotNone(replay.approved_draft)


class TestNoApprovalWithoutControlPlane(unittest.IsolatedAsyncioTestCase):
    async def test_offline_bundle_keeps_approval_unavailable(self) -> None:
        bundle = build_investigation_bundle()
        result = await bundle.investigator.investigate(
            question=QUESTION, lease_id=LEASE, context=bundle.context,
            thread_id="thread_offline",
        )
        self.assertEqual(result.approval_status, "unavailable")
        self.assertIsNone(result.approved_draft)
        self.assertTrue(any("未配置审批通道" in item for item in result.warnings))
        # 草案仍然出现在报告里，但绝不自动"通过"
        self.assertIn("proposed_draft", result.report)

    async def test_no_draft_when_lease_has_no_pending_draft(self) -> None:
        """没有待审批草案的租约不应凭空产生审批对象。"""

        from app.orchestration.investigation import build_reduction_draft

        bundle = build_investigation_bundle()
        draft = build_reduction_draft(
            repository=bundle.repository,
            lease_id="lease_jl_b101_2025",
            amount="100.00",
            evidence_ids=["x"],
        )
        self.assertIsNone(draft)

    async def test_arrears_question_still_surfaces_known_variance(self) -> None:
        """fixture 的账单本身就存在租金差额，因此纯欠费问题也会被标为需人工复核。

        这不是缺陷：报告只陈述事实，是否需要减免仍由人决定。
        """

        bundle = build_investigation_bundle()
        result = await bundle.investigator.investigate(
            question="A-301 现在还有多少钱没交？",
            lease_id=LEASE,
            context=bundle.context,
            thread_id="thread_arrears",
        )
        self.assertEqual(result.verdict, "conflicting")
        self.assertEqual(result.approval_status, "unavailable")
        self.assertIn("proposed_draft", result.report)


if __name__ == "__main__":
    unittest.main()
