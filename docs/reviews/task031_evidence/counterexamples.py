"""Task 031 原始反例复跑脚本（Z1 / Z2 / Z3）。

同一个脚本在**改动前**（HEAD 干净工作树）与**改动后**（当前工作区）各跑一次，
把真实输出保存到 `docs/reviews/task031_evidence/{before,after}/counterexamples.json`。
脚本只使用两版代码都存在的公开入口，不 import Task 031 新增的接口。

在 `backend/` 的代码树上执行：

    $env:PYTHONPATH="<repo>/backend"
    python docs/reviews/task031_evidence/counterexamples.py <输出文件>
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

LEASE_A301 = "lease_xh_a301_2025"
LEASE_B101 = "lease_jl_b101_2025"


def _tool_turn(name: str, arguments: dict) -> object:
    from app.llm.model_client import ModelToolCall, ModelTurn

    return ModelTurn(
        text="",
        tool_calls=(
            ModelToolCall(
                call_id="c1",
                name=name,
                arguments=dict(arguments),
                arguments_json=json.dumps(arguments, ensure_ascii=False),
            ),
        ),
    )


def _run_cli(argv: list[str], turns: list | None = None) -> dict:
    from app import cli
    from app.llm.model_client import FakeChatModelClient

    stdout, stderr = io.StringIO(), io.StringIO()
    patcher = None
    if turns is not None:
        client = FakeChatModelClient(turns, provider="fake", model_name="counterexample")
        patcher = patch("app.single_demo._build_model_client", return_value=client)
        patcher.start()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(argv)
    finally:
        if patcher is not None:
            patcher.stop()
    text = stdout.getvalue().strip()
    payload = json.loads(text) if text.startswith("{") else {}
    return {
        "argv": argv,
        "exit": code,
        "status": payload.get("status"),
        "error_code": (payload.get("error") or {}).get("code"),
        "stdout_keys": sorted(payload),
        "stderr_head": stderr.getvalue().strip().splitlines()[:3],
        "payload": payload,
    }


def case_z1_ask_wrong_target() -> dict:
    """Z1：问题 A-301，模型却查 B-101；旧代码 success，新代码必须业务失败。"""

    answer = "A301 应收 0.00、已收 0.00、未收 0.00，已经结清。"
    result = _run_cli(
        ["ask", "A301现在还欠多少", "--provider", "fake"],
        turns=[
            _tool_turn("billing.statement.read", {"lease_id": LEASE_B101}),
            type(_tool_turn("x", {}))(text=answer),
        ],
    )
    payload = result.pop("payload")
    result.update(
        {
            "answer_or_narrative": payload.get("answer")
            or (payload.get("model_narrative") or {}).get("answer"),
            "target_mode": (payload.get("target") or {}).get("mode"),
            "target_lease": (payload.get("target") or {}).get("lease_id"),
            "evidence_count": payload.get("evidence_count"),
            "failed_tool_calls": payload.get("failed_tool_calls"),
            "trusted_conclusion_source": (payload.get("trusted_conclusion") or {}).get(
                "source"
            ),
        }
    )
    return result


def case_z2_failed_tool_counted_as_evidence() -> dict:
    """Z2：目标 A-301，工具参数非法 → 旧代码仍 success/facts={}；新代码必须失败。"""

    from app.agents.base.contracts import AgentRequest
    from app.agents.single.agent import SingleToolAgent
    from app.config.loader import load_agent_config
    from app.fixtures.repository import FixtureRepository
    from app.llm.model_client import FakeChatModelClient
    from app.paths import CONFIG_DIR
    from app.runtime.budget import Budget
    from app.runtime.types import TraceLog, TrustedContext
    from app.tools.fixture_tools import build_fixture_tools
    from app.tools.registry import ToolRegistry

    client = FakeChatModelClient(
        [
            _tool_turn(
                "billing.statement.read",
                {"lease_id": LEASE_A301, "unexpected_field": "x"},
            ),
            type(_tool_turn("x", {}))(text="已经核对，没有问题。"),
        ],
        provider="fake",
        model_name="z2-counterexample",
    )
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    agent = SingleToolAgent(
        load_agent_config(CONFIG_DIR / "single.yaml"),
        model_client=client,
        tool_registry=registry,
        budget=Budget(max_tool_calls=6, max_model_calls=6, max_total_tokens=4000),
        trace_log=TraceLog(),
    )
    trusted = TrustedContext(
        trace_id="trace_z2",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=frozenset({"billing.read", "lease.read", "property.read"}),
    )
    result = asyncio.run(
        agent.handle(
            AgentRequest(
                task_id="task_z2",
                capability="single.investigate",
                payload={"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            ),
            trusted.to_agent_context(run_id="run_z2"),
        )
    )
    data = result.output or {}
    return {
        "status": result.status.value,
        "error_code": result.error.code.value if result.error is not None else None,
        "facts": data.get("facts"),
        "evidence_count": len(data.get("evidence") or ()),
        "tool_calls": data.get("tool_calls"),
        "failed_tool_calls": data.get("failed_tool_calls"),
        "error_details_keys": sorted((result.error.details or {})) if result.error else [],
    }


def case_z3_default_summary() -> dict:
    """Z3：默认摘要是否展示可信资金结论（旧代码只有模型原话）。"""

    correct = "应收 52596.00、已收 34560.00、未收 18036.00。"
    ask = _run_cli(
        ["ask", "A-301 还欠多少？", "--provider", "fake"],
        turns=[_tool_turn("billing.statement.read", {}), type(_tool_turn("x", {}))(text=correct)],
    )
    ask_payload = ask.pop("payload")
    ask.update(
        {
            "has_trusted_conclusion": "trusted_conclusion" in ask_payload,
            "trusted_conclusion": ask_payload.get("trusted_conclusion"),
            "raw_answer_field": ask_payload.get("answer"),
            "model_narrative": ask_payload.get("model_narrative"),
            "narrative_discrepancies": ask_payload.get("narrative_discrepancies"),
        }
    )

    investigate = _run_cli(["investigate"])
    investigate_payload = investigate.pop("payload")
    investigate.update(
        {
            "has_authoritative_amounts": "authoritative_amounts" in investigate_payload,
            "authoritative_amounts": investigate_payload.get("authoritative_amounts"),
            "model_narratives": investigate_payload.get("model_narratives"),
            "narrative_discrepancies": investigate_payload.get("narrative_discrepancies"),
        }
    )
    return {"ask": ask, "investigate": investigate}


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "-"
    report = {
        "z1_ask_wrong_target": case_z1_ask_wrong_target(),
        "z2_failed_tool_counted_as_evidence": case_z2_failed_tool_counted_as_evidence(),
        "z3_default_summary": case_z3_default_summary(),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if target == "-":
        print(text)
    else:
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"[written] {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
