"""Task 031 / 2.7 回归：路由兜底不得静默落到 billing + 路由理由必须进报告。

覆盖：

1. 词表契约（`app.orchestration.vocabulary` 是唯一词表来源，`ask` 路径也 import 它）；
2. 无法归类的问题 → `needs_clarification` / `route=clarification` /
   零子任务、零工具调用、无失败、不进入审批；
3. 有领域命中时原路由与子任务不变：单领域 deterministic、多领域 fanout、
   纯欠费问题收窄到 billing；
4. `report["routing_reason"]` 普通运行也有，且 `matched` 的词确实出现在问题文本里；
5. 补查（revision）与审批恢复不得丢失路由理由。

全部离线：fixture + 受控工具，不调用模型、不访问网络。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.control_plane import control_plane
from app.investigation_demo import build_investigation_bundle, run_investigation
from app.orchestration.investigation import RuleBasedPlanner
from app.orchestration.vocabulary import (
    DOMAINS,
    DOMAIN_CAPABILITIES,
    DOMAIN_HINTS,
    DOMAIN_LABELS,
    matched_domains,
    matched_words,
)
from app.tools.base import BaseTool

LEASE = "lease_xh_a301_2025"

MULTI_DOMAIN_QUESTION = (
    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
    "并要求减免费用。请核对合同、账单、付款和工单，分析争议原因，"
    "指出证据与缺失信息，形成供人工审核的处理方案。"
)
PROPERTY_QUESTION = "空调维修了几次？"
ARREARS_QUESTION = "A-301 现在还有多少钱没交？"

#: 完全不含任何领域词的问法（应走 clarification，而不是猜一个领域）
UNMATCHED_QUESTIONS = (
    "请帮我看看这个事情",
    "你好",
    "这个月情况怎么样？",
)

#: Task 009 原始规则表：**一个词都不许丢**（词表迁移不等于删词）
TASK009_WORDS: dict[str, tuple[str, ...]] = {
    "lease": ("合同", "租约", "条款", "递增", "免租", "押金", "续租", "租期"),
    "billing": (
        "账单",
        "租金",
        "费用",
        "欠费",
        "付款",
        "核销",
        "多收",
        "少收",
        "金额",
        "发票",
    ),
    "property": ("空调", "维修", "工单", "报修", "故障", "投诉", "漏水", "电梯"),
}


class _FlakyOnceTool(BaseTool):
    """第一次超时、之后成功的工具包装（触发一次补查）。"""

    def __init__(self, inner: BaseTool) -> None:
        self._inner = inner
        self.calls = 0
        self.name = inner.name
        self.version = inner.version
        self.description = inner.description
        self.required_permissions = inner.required_permissions
        self.timeout_seconds = inner.timeout_seconds
        self.max_attempts = 1
        self.input_model = inner.input_model
        self.output_model = inner.output_model

    async def invoke(self, payload: object, context: object):
        from app.agents.base.errors import AgentError, ErrorCode

        self.calls += 1
        if self.calls == 1:
            raise AgentError("第一次调用超时", code=ErrorCode.TOOL_TIMEOUT)
        return await self._inner.invoke(payload, context)


async def _investigate(question: str, *, bundle=None):
    active = bundle or build_investigation_bundle()
    result = await run_investigation(active, question=question, lease_id=LEASE)
    return active, result


class TestVocabularyContract(unittest.TestCase):
    """词表是唯一来源，名字/语义被 ask 路径与规划器共同依赖，不能漂移。"""

    def test_domains_and_labels_are_stable(self) -> None:
        self.assertEqual(DOMAINS, ("lease", "billing", "property"))
        self.assertEqual(set(DOMAIN_LABELS), set(DOMAINS))
        self.assertEqual(set(DOMAIN_CAPABILITIES), set(DOMAINS))
        self.assertEqual(set(DOMAIN_HINTS), set(DOMAINS))
        for domain in DOMAINS:
            self.assertTrue(DOMAIN_LABELS[domain])
            self.assertIsInstance(DOMAIN_HINTS[domain], tuple)
            self.assertTrue(DOMAIN_HINTS[domain])
        self.assertEqual(DOMAIN_LABELS["lease"], "合同/租约")
        self.assertEqual(DOMAIN_LABELS["billing"], "账单/费用")
        self.assertEqual(DOMAIN_LABELS["property"], "物业工单")

    def test_task009_words_are_all_kept(self) -> None:
        for domain, words in TASK009_WORDS.items():
            for word in words:
                self.assertIn(
                    word,
                    DOMAIN_HINTS[domain],
                    f"Task 009 词表 {domain}.{word} 不能被删掉",
                )

    def test_planner_uses_shared_vocabulary_not_a_copy(self) -> None:
        """规划器的旧属性名必须指向同一份词表，否则会再次分叉。"""

        planner = RuleBasedPlanner()
        self.assertIs(planner._LEASE_HINTS, DOMAIN_HINTS["lease"])
        self.assertIs(planner._BILLING_HINTS, DOMAIN_HINTS["billing"])
        self.assertIs(planner._PROPERTY_HINTS, DOMAIN_HINTS["property"])

    def test_every_hint_matches_its_own_domain(self) -> None:
        for domain, hints in DOMAIN_HINTS.items():
            for hint in hints:
                self.assertIn(
                    hint,
                    matched_domains(f"请核对一下{hint}").get(domain, ()),
                    f"词表自相矛盾：{domain}.{hint} 未命中自己的领域",
                )

    def test_no_domain_matched_returns_empty_mapping(self) -> None:
        for text in ("", "你好", "请帮我看看这个事情", "这个月情况怎么样？"):
            self.assertEqual(matched_domains(text), {}, text)
        # 防御：None 也不能抛（调用方可能传入未填的问题）
        self.assertEqual(matched_domains(None), {})  # type: ignore[arg-type]

    def test_matched_words_are_actual_substrings(self) -> None:
        text = "账单金额都对不上，空调也坏了"
        matched = matched_domains(text)
        self.assertEqual(matched["billing"], ("账单", "金额"))
        self.assertEqual(matched["property"], ("空调",))
        for words in matched.values():
            for word in words:
                self.assertIn(word, text)
        self.assertEqual(set(matched_words(text)), {"账单", "金额", "空调"})

    def test_colloquial_additions_match(self) -> None:
        """Prompt §2.7 明示可补充的口语说法（来源见 planner_vocabulary.md）。"""

        self.assertEqual(matched_domains("物业费怎么算"), {"billing": ("物业费",)})
        self.assertEqual(matched_domains("管理费涨了"), {"billing": ("管理费",)})
        self.assertEqual(matched_domains("冷气坏了"), {"property": ("冷气",)})
        self.assertIn("不制冷", matched_domains("空调不制冷")["property"])


class TestUnmatchedQuestionIsClarification(unittest.TestCase):
    """核心回归：未命中任何领域时不得默认 billing。"""

    def _assert_clarification(self, bundle, result) -> None:
        report = result.report
        self.assertEqual(result.verdict, "needs_clarification")
        self.assertEqual(result.route, "clarification")
        self.assertEqual(report["verdict"], "needs_clarification")
        self.assertEqual(report["route"], "clarification")
        # 零子任务 / 零工具调用 / 无失败
        self.assertEqual(result.results, ())
        self.assertEqual(result.failures, ())
        self.assertEqual(result.missing, ())
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["agent_results"], [])
        self.assertEqual(report["failures"], [])
        self.assertEqual(bundle.trace_log.snapshot(), ())
        self.assertEqual(bundle.budget.snapshot().used_tool_calls, 0)
        # 未执行，而不是"执行了但缺资料"
        self.assertEqual(report["completeness"], "not_executed")
        self.assertTrue(report["requires_human_review"])
        # 未命中时没有子任务可解释，理由为空；排查信息在 clarification 里
        self.assertEqual(report["routing_reason"], [])
        # 不进入审批
        self.assertEqual(result.approval_status, "not_required")
        self.assertNotIn(
            result.approval_status, {"pending", "ready", "pending_approval"}
        )
        self.assertIsNone(result.approval_request)
        self.assertIsNone(result.approved_draft)
        self.assertNotIn("proposed_draft", report)

    def test_unclassified_question_returns_clarification(self) -> None:
        bundle = build_investigation_bundle()
        bundle, result = asyncio.run(_investigate("请帮我看看这个事情", bundle=bundle))
        self._assert_clarification(bundle, result)

    def test_greeting_and_generic_questions_also_clarify(self) -> None:
        for question in UNMATCHED_QUESTIONS:
            with self.subTest(question=question):
                bundle, result = asyncio.run(_investigate(question))
                self._assert_clarification(bundle, result)

    def test_clarification_payload_shape(self) -> None:
        _, result = asyncio.run(_investigate("请帮我看看这个事情"))
        clarification = result.report["clarification"]
        self.assertEqual(
            set(clarification),
            {"reason", "message", "available_domains", "question"},
        )
        self.assertEqual(clarification["reason"], "no_domain_matched")
        self.assertIn("无法判断", clarification["message"])
        self.assertIn("合同", clarification["message"])
        self.assertIn("账单", clarification["message"])
        self.assertIn("物业", clarification["message"])
        self.assertTrue(clarification["question"])
        available = clarification["available_domains"]
        self.assertEqual(
            [item["domain"] for item in available], list(DOMAINS)
        )
        for item in available:
            self.assertEqual(item["label"], DOMAIN_LABELS[item["domain"]])
            self.assertEqual(
                item["capability"], DOMAIN_CAPABILITIES[item["domain"]]
            )
        # 报告必须可 JSON 序列化（CLI 直接输出）
        payload = json.dumps(result.report, ensure_ascii=False)
        self.assertIn("needs_clarification", payload)

    def test_planner_backward_compatible_plan_still_two_tuple(self) -> None:
        planner = RuleBasedPlanner()
        self.assertEqual(planner.plan("你好", {"lease_id": LEASE}), ([], "clarification"))


class TestDomainHitRoutesUnchanged(unittest.TestCase):
    """有命中时行为保持不变（含纯欠费收窄逻辑）。"""

    def test_property_question_is_deterministic(self) -> None:
        bundle, result = asyncio.run(_investigate(PROPERTY_QUESTION))
        self.assertEqual(result.route, "deterministic")
        self.assertEqual(
            [item["capability"] for item in result.results],
            ["property.work_orders"],
        )
        self.assertEqual(len(bundle.trace_log.snapshot()), 1)
        reason = result.report["routing_reason"]
        self.assertEqual(len(reason), 1)
        self.assertEqual(reason[0]["domain"], "property")
        self.assertEqual(reason[0]["label"], DOMAIN_LABELS["property"])
        self.assertEqual(reason[0]["subtask_id"], "st_1_property")
        self.assertEqual(reason[0]["capability"], "property.work_orders")
        self.assertIn("空调", reason[0]["matched"])
        self.assertIn("维修", reason[0]["matched"])
        for word in reason[0]["matched"]:
            self.assertIn(word, PROPERTY_QUESTION)

    def test_multi_domain_question_fans_out(self) -> None:
        bundle, result = asyncio.run(_investigate(MULTI_DOMAIN_QUESTION))
        self.assertEqual(result.route, "fanout")
        self.assertEqual(
            {item["capability"] for item in result.results},
            {"lease.query", "billing.statement", "property.work_orders"},
        )
        self.assertEqual(
            [item["subtask_id"] for item in result.results],
            ["st_1_lease", "st_2_billing", "st_3_property"],
        )
        reason = result.report["routing_reason"]
        self.assertEqual([item["domain"] for item in reason], list(DOMAINS))
        for item in reason:
            self.assertTrue(item["matched"], f"{item['domain']} 应记录命中的词")
            for word in item["matched"]:
                self.assertIn(word, MULTI_DOMAIN_QUESTION)
        # 理由与实际执行的子任务逐条对齐
        self.assertEqual(
            [(item["subtask_id"], item["capability"]) for item in reason],
            [(item["subtask_id"], item["capability"]) for item in result.results],
        )

    def test_plain_arrears_question_stays_billing(self) -> None:
        """口语欠费问题（"还有多少钱没交"）不能被误判成无法归类。"""

        _, result = asyncio.run(_investigate(ARREARS_QUESTION))
        self.assertEqual(result.route, "deterministic")
        self.assertEqual(
            [item["capability"] for item in result.results], ["billing.statement"]
        )
        reason = result.report["routing_reason"]
        self.assertEqual(len(reason), 1)
        self.assertEqual(reason[0]["domain"], "billing")
        self.assertIn("没交", reason[0]["matched"])
        self.assertNotIn("narrowing", reason[0], "单领域问题不涉及收窄")

    def test_pure_arrears_narrowing_is_kept_and_explained(self) -> None:
        question = "免租期和空调都说了，还欠多少？"
        planner = RuleBasedPlanner()
        detail = planner.plan_detailed(question, {"lease_id": LEASE})
        self.assertEqual(detail.route, "deterministic")
        self.assertEqual(
            [item["capability"] for item in detail.subtasks], ["billing.statement"]
        )
        reason = detail.routing_reason
        self.assertEqual(len(reason), 1)
        self.assertEqual(reason[0]["domain"], "billing")
        narrowing = reason[0]["narrowing"]
        self.assertEqual(narrowing["reason"], "pure_arrears_question")
        self.assertEqual(
            {item["domain"] for item in narrowing["dropped"]},
            {"lease", "property"},
        )
        for dropped in narrowing["dropped"]:
            self.assertTrue(dropped["matched"])
            for word in dropped["matched"]:
                self.assertIn(word, question)

        # 图路径同样只有一个子任务（收窄逻辑在真实运行里生效）
        bundle, result = asyncio.run(_investigate(question))
        self.assertEqual(result.route, "deterministic")
        self.assertEqual(
            [item["capability"] for item in result.results], ["billing.statement"]
        )
        self.assertEqual(len(bundle.trace_log.snapshot()), 1)

    def test_routing_reason_written_on_normal_run(self) -> None:
        _, result = asyncio.run(_investigate(MULTI_DOMAIN_QUESTION))
        reason = result.report["routing_reason"]
        self.assertTrue(reason)
        self.assertIsInstance(reason, list)
        for item in reason:
            self.assertEqual(
                set(item),
                {"domain", "label", "matched", "capability", "subtask_id"},
            )
            self.assertEqual(item["label"], DOMAIN_LABELS[item["domain"]])
        # CLI 直接 json.dump 报告：理由必须可序列化
        self.assertIn("routing_reason", json.dumps(result.report, ensure_ascii=False))


class TestRoutingReasonSurvivesRecovery(unittest.TestCase):
    def test_routing_reason_survives_revision(self) -> None:
        """补查会重跑子任务，但计划与理由来自 plan_node，不能被清掉。"""

        bundle = build_investigation_bundle(
            variant="v_oct_rent_corrected", max_revisions=1
        )
        flaky = _FlakyOnceTool(bundle.tool_registry.get("property.work_orders.read"))
        bundle.tool_registry.register(flaky, replace=True)

        result = asyncio.run(
            run_investigation(
                bundle, question=MULTI_DOMAIN_QUESTION, lease_id=LEASE
            )
        )
        self.assertEqual(flaky.calls, 2, "应恰好补查一次")
        self.assertEqual(result.revision, 1)
        reason = result.report["routing_reason"]
        self.assertEqual([item["domain"] for item in reason], list(DOMAINS))
        for item in reason:
            for word in item["matched"]:
                self.assertIn(word, MULTI_DOMAIN_QUESTION)


class TestRoutingReasonSurvivesApprovalResume(unittest.IsolatedAsyncioTestCase):
    async def test_routing_reason_survives_approval_resume(self) -> None:
        """审批中断/恢复读的是 checkpoint：报告里的路由理由不能丢。"""

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            async with control_plane(
                checkpoint_path=base / "graph.sqlite",
                approval_path=base / "approval.sqlite",
            ) as plane:
                bundle = build_investigation_bundle(control_plane=plane)
                first = await bundle.investigator.investigate(
                    question=MULTI_DOMAIN_QUESTION,
                    lease_id=LEASE,
                    context=bundle.context,
                    thread_id="thread_2_7_recovery",
                )
                self.assertEqual(first.approval_status, "pending_approval")
                self.assertEqual(
                    [item["domain"] for item in first.report["routing_reason"]],
                    list(DOMAINS),
                )
                request = plane.approval_store.pending()[0]
                self.assertEqual(request.draft_version, 2)

                stage1 = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_property_manager_xinghui",
                )
                self.assertEqual(stage1.approval_status, "pending_next_stage")
                self.assertEqual(
                    [item["domain"] for item in stage1.report["routing_reason"]],
                    list(DOMAINS),
                    "恢复后报告不得丢失路由理由",
                )

                stage2 = await bundle.investigator.resume(
                    request_id=request.request_id,
                    decision="approve",
                    draft_version=request.draft_version,
                    principal_id="principal_finance_xinghui",
                )
                self.assertEqual(stage2.approval_status, "approved")
                self.assertEqual(
                    [item["domain"] for item in stage2.report["routing_reason"]],
                    list(DOMAINS),
                )


if __name__ == "__main__":
    unittest.main()
