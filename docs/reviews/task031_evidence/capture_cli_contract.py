"""Task 031 / 2.4 CLI 证据采集：退出码、approve --dry-run 不写数据、身份来源。

只读取 `app.cli` 的公开入口与临时控制面目录；不修改审批台账/checkpoint 之外的文件。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app import cli

EVIDENCE = Path(__file__).resolve().parent / "after" / "cli_contract_evidence.json"
ENV = {"DEMO_PRINCIPAL_ID": "principal_ops_xinghui"}


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, ENV, clear=False):
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def digest(root: str) -> dict[str, str]:
    base = Path(root)
    return {
        str(path.relative_to(base)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    evidence: dict = {}
    help_text = cli.build_parser().format_help()
    evidence["exit_codes_help_contains"] = [
        item
        for item in ("0=成功", "1=业务结果失败", "2=用法或配置错误", "3=审批错误")
        if item in help_text
    ]
    evidence["ask_offline_usage_exit"] = run(
        ["ask", "A-301 还欠多少？", "--model-provider", "offline"]
    )[0]
    evidence["ask_no_target_usage_exit"] = run(["ask", "现在一共欠多少钱？"])[0]
    evidence["clarification_business_failure_exit"] = run(
        ["investigate", "请帮我看看这个事情"]
    )[0]
    evidence["ask_scripted_success_exit"] = run(["ask", "A-301 还欠多少？"])[0]
    evidence["investigate_scripted_success_exit"] = run(
        ["investigate", "--model-provider", "scripted"]
    )[0]

    # approve --dry-run：台账与 checkpoint 必须逐字节不变；真实审批必须写入
    with tempfile.TemporaryDirectory() as tmp:
        code, out, _ = run(
            [
                "investigate",
                "--with-approval",
                "--control-dir",
                tmp,
                "--thread-id",
                "thread_evidence_dryrun",
            ]
        )
        payload = json.loads(out)
        request = payload["approval_request"]
        before = digest(tmp)
        dry_code, dry_out, dry_err = run(
            [
                "approve",
                request["request_id"],
                "--draft-version",
                str(request["draft_version"]),
                "--principal",
                "principal_property_manager_xinghui",
                "--dry-run",
                "--control-dir",
                tmp,
            ]
        )
        after = digest(tmp)
        dry_payload = json.loads(dry_out)
        _, pending_out, _ = run(["pending", "--control-dir", tmp])
        pending = json.loads(pending_out)
        real_code, real_out, _ = run(
            [
                "approve",
                request["request_id"],
                "--draft-version",
                str(request["draft_version"]),
                "--principal",
                "principal_property_manager_xinghui",
                "--control-dir",
                tmp,
            ]
        )
        _, pending_after_out, _ = run(["pending", "--control-dir", tmp])
        pending_after = json.loads(pending_after_out)
        evidence["approve_dry_run"] = {
            "investigate_exit": code,
            "request_id": request["request_id"],
            "draft_version": request["draft_version"],
            "dry_run_exit": dry_code,
            "dry_run_key_fields": {
                key: dry_payload.get(key)
                for key in (
                    "dry_run",
                    "wrote_data",
                    "resumed_graph",
                    "decided_role",
                    "idempotent",
                    "current_status",
                    "note",
                )
            },
            "dry_run_stderr": dry_err.strip().splitlines(),
            "ledger_bytes_identical_before_after_dry_run": before == after,
            "pending_decisions_after_dry_run": pending["requests"][0]["decisions"],
            "real_approve_exit": real_code,
            "real_approve_status": json.loads(real_out)["approval_status"],
            "pending_decisions_after_real_approve": pending_after["requests"][0][
                "decisions"
            ],
        }

    # 身份来源：默认读 DEMO_PRINCIPAL_ID；显式 --principal 提示开发模式
    _, env_out, _ = run(["ask", "A-301 还欠多少？"])
    _, explicit_out, explicit_err = run(
        ["ask", "A-301 还欠多少？", "--principal", "principal_ops_xinghui"]
    )
    evidence["identity"] = {
        "env_default": json.loads(env_out)["identity"],
        "explicit_flag": json.loads(explicit_out)["identity"],
        "explicit_stderr": explicit_err.strip().splitlines(),
    }
    EVIDENCE.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
