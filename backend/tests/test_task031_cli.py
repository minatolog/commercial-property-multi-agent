"""Task 031 / 2.4 回归：CLI 参数清理、退出码与身份来源。

覆盖 Prompt 第 2.4 节五个改动点：
1. `ask` 与 `investigate` 统一 `--model-provider`；旧 `--provider` 是弃用别名；
   `investigate` 补 `--budget-model-calls`。
2. `approve --dry-run` **只校验、不写任何数据**（台账逐字节不变）。
3. 删除无效参数 `approve --thread-id`（恢复所用 thread_id 一律取自台账）。
4. 退出码分开：0 成功 / 1 业务结果失败 / 2 用法或配置错误 / 3 审批错误。
5. `--principal` 默认读取 `DEMO_PRINCIPAL_ID`；显式传入时提示开发模式并记录来源。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app import cli

_PRINCIPAL_ENV = {"DEMO_PRINCIPAL_ID": "principal_ops_xinghui"}


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, _PRINCIPAL_ENV, clear=False):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _digest_tree(root: str | Path) -> dict[str, str]:
    base = Path(root)
    return {
        str(path.relative_to(base)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


class TestUnifiedModelProvider(unittest.TestCase):
    def _args(self, **kwargs) -> argparse.Namespace:
        base = {"provider": None, "model_provider": None}
        base.update(kwargs)
        return argparse.Namespace(**base)

    def test_default_ask_provider_is_scripted(self) -> None:
        self.assertEqual(cli._resolve_ask_provider(self._args()), "scripted")

    def test_legacy_fake_maps_to_scripted_with_warning(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            provider = cli._resolve_ask_provider(self._args(provider="fake"))
        self.assertEqual(provider, "scripted")
        self.assertIn("已弃用", stderr.getvalue())

    def test_legacy_deepseek_is_accepted(self) -> None:
        with redirect_stderr(io.StringIO()):
            self.assertEqual(
                cli._resolve_ask_provider(self._args(provider="deepseek")), "deepseek"
            )

    def test_conflicting_flag_and_provider_is_usage_error(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(cli.UsageError):
                cli._resolve_ask_provider(
                    self._args(provider="fake", model_provider="deepseek")
                )

    def test_offline_is_rejected_for_ask(self) -> None:
        with self.assertRaises(cli.UsageError) as ctx:
            cli._resolve_ask_provider(self._args(model_provider="offline"))
        self.assertIn("ask 需要模型", str(ctx.exception))

    def test_ask_help_lists_unified_provider_and_deprecation(self) -> None:
        ask_help = io.StringIO()
        with redirect_stdout(ask_help):
            with self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["ask", "--help"])
        text = ask_help.getvalue()
        self.assertIn("--model-provider", text)
        self.assertIn("已弃用", text)
        top_help = cli.build_parser().format_help()
        self.assertIn("退出码", top_help)

    def test_investigate_has_model_call_budget(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["investigate", "--help"])
        self.assertIn("--budget-model-calls", buffer.getvalue())

    def test_cli_rejects_offline_ask_with_exit_2(self) -> None:
        code, out, err = run_cli(["ask", "A-301 还欠多少？", "--model-provider", "offline"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(out.strip(), "")
        self.assertIn("ask 需要模型", err)


class TestApproveParameterCleanup(unittest.TestCase):
    def test_thread_id_is_no_longer_accepted(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(
                    [
                        "approve",
                        "apr_x",
                        "--draft-version",
                        "1",
                        "--thread-id",
                        "thread_x",
                    ]
                )
        self.assertEqual(ctx.exception.code, 2)

    def test_dry_run_help_says_validation_only(self) -> None:
        parser = cli.build_parser()
        approve = parser._subparsers._group_actions[0].choices["approve"]
        help_text = approve.format_help()
        self.assertIn("不写入台账、不恢复图", help_text)
        self.assertIn("只做校验", help_text)


class TestApproveDryRunDoesNotWrite(unittest.TestCase):
    def _prepare_pending_request(self, control_dir: str) -> dict:
        code, out, err = run_cli(
            [
                "investigate",
                "--with-approval",
                "--control-dir",
                control_dir,
                "--thread-id",
                "thread_cli_dryrun",
            ]
        )
        self.assertEqual(code, cli.EXIT_OK, err)
        payload = json.loads(out)
        self.assertEqual(payload["approval_status"], "pending_approval")
        return payload["approval_request"]

    def test_dry_run_leaves_ledger_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._prepare_pending_request(tmp)
            before = _digest_tree(tmp)
            code, out, err = run_cli(
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
            self.assertEqual(code, cli.EXIT_OK, err)
            payload = json.loads(out)
            self.assertTrue(payload["dry_run"])
            self.assertFalse(payload["wrote_data"])
            self.assertFalse(payload["resumed_graph"])
            self.assertEqual(payload["decided_role"], "property_manager")
            self.assertFalse(payload["idempotent"])
            # 台账与 checkpoint 都没有任何字节变化，也没有新增文件
            self.assertEqual(before, _digest_tree(tmp))
            # 台账里仍然没有任何审批决定
            code, out, _ = run_cli(["pending", "--control-dir", tmp])
            pending = json.loads(out)
            self.assertEqual(pending["pending_count"], 1)
            self.assertEqual(pending["requests"][0]["decisions"], [])

    def test_dry_run_does_not_create_missing_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "control" / "approval.sqlite"
            code, out, err = run_cli(
                [
                    "approve",
                    "apr_x",
                    "--draft-version",
                    "1",
                    "--dry-run",
                    "--control-dir",
                    tmp,
                ]
            )
            self.assertEqual(code, cli.EXIT_APPROVAL, err)
            self.assertFalse(missing.exists())
            self.assertEqual(json.loads(out)["error"]["code"], "approval_ledger_missing")

    def test_dry_run_with_wrong_principal_is_approval_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._prepare_pending_request(tmp)
            code, out, _ = run_cli(
                [
                    "approve",
                    request["request_id"],
                    "--draft-version",
                    str(request["draft_version"]),
                    "--principal",
                    "principal_ops_xinghui",
                    "--dry-run",
                    "--control-dir",
                    tmp,
                ]
            )
            self.assertEqual(code, cli.EXIT_APPROVAL)
            self.assertEqual(json.loads(out)["error"]["code"], "permission_denied")

    def test_real_approve_after_dry_run_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._prepare_pending_request(tmp)
            before = _digest_tree(tmp)
            code, out, err = run_cli(
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
            self.assertEqual(code, cli.EXIT_OK, err)
            payload = json.loads(out)
            self.assertEqual(payload["approval_status"], "pending_next_stage")
            # 真实审批必须写入台账（与 dry-run 形成对照）
            self.assertNotEqual(before, _digest_tree(tmp))
            code, out, _ = run_cli(["pending", "--control-dir", tmp])
            decisions = json.loads(out)["requests"][0]["decisions"]
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["role"], "property_manager")


class TestExitCodes(unittest.TestCase):
    def test_help_documents_exit_codes(self) -> None:
        text = cli.build_parser().format_help()
        for fragment in ("0=成功", "1=业务结果失败", "2=用法或配置错误", "3=审批错误"):
            self.assertIn(fragment, text)

    def test_business_failure_is_1_not_2(self) -> None:
        """有目标但零事实（Z2）必须映射为业务失败 1，而不是用法错误 2。"""

        from app.llm.model_client import FakeChatModelClient, ModelToolCall, ModelTurn

        turn = ModelTurn(
            text="",
            tool_calls=(
                ModelToolCall(
                    call_id="c1",
                    name="billing.statement.read",
                    arguments={"lease_id": "lease_xh_a302_2025"},
                    arguments_json='{"lease_id": "lease_xh_a302_2025"}',
                ),
            ),
        )
        client = FakeChatModelClient(
            [turn, ModelTurn(text="已核对，没有问题。")], provider="fake", model_name="m"
        )
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, _PRINCIPAL_ENV, clear=False):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with patch("app.single_demo._build_model_client", return_value=client):
                    code = cli.main(["ask", "A-301 还欠多少？"])
        self.assertEqual(code, cli.EXIT_BUSINESS_FAILURE)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "failed")

    def test_usage_error_is_2(self) -> None:
        code, _, err = run_cli(["ask", "现在欠多少钱？"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("可信目标", err)

    def test_investigation_clarification_is_business_failure(self) -> None:
        code, out, _ = run_cli(["investigate", "请帮我看看这个事情"])
        self.assertEqual(code, cli.EXIT_BUSINESS_FAILURE)
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], "needs_clarification")
        self.assertTrue(payload["clarification"])
        self.assertEqual(payload["tool_traces"], [])

    def test_investigation_with_results_is_success(self) -> None:
        code, out, _ = run_cli(["investigate"])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue(json.loads(out)["agent_results"])


class TestIdentitySource(unittest.TestCase):
    def test_fallback_equals_api_default_principal(self) -> None:
        from app.api.service import DEFAULT_PRINCIPAL

        self.assertEqual(cli.DEFAULT_PRINCIPAL_FALLBACK, DEFAULT_PRINCIPAL)

    def test_explicit_principal_warns_and_marks_cli_flag(self) -> None:
        args = argparse.Namespace(principal="principal_ops_xinghui")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            cli._resolve_identity(args, fallback=cli.DEFAULT_PRINCIPAL_FALLBACK)
        self.assertEqual(args.identity_source, "cli_flag")
        self.assertIn("开发模式", stderr.getvalue())
        self.assertIn("不可用于生产", stderr.getvalue())

    def test_environment_principal_is_used_by_default(self) -> None:
        args = argparse.Namespace(principal=None)
        with patch.dict(os.environ, {"DEMO_PRINCIPAL_ID": "principal_ops_xinghui"}):
            cli._resolve_identity(args, fallback="unused-fallback")
        self.assertEqual(args.principal, "principal_ops_xinghui")
        self.assertEqual(args.identity_source, "env:DEMO_PRINCIPAL_ID")

    def test_default_fallback_when_environment_is_empty(self) -> None:
        args = argparse.Namespace(principal=None)
        with patch.dict(os.environ, {"DEMO_PRINCIPAL_ID": ""}):
            cli._resolve_identity(args, fallback=cli.DEFAULT_PRINCIPAL_FALLBACK)
        self.assertEqual(args.principal, cli.DEFAULT_PRINCIPAL_FALLBACK)
        self.assertEqual(args.identity_source, "demo_default")

    def test_approver_without_permission_falls_back_with_warning(self) -> None:
        args = argparse.Namespace(principal=None)
        stderr = io.StringIO()
        with patch.dict(os.environ, {"DEMO_PRINCIPAL_ID": "principal_ops_xinghui"}):
            with redirect_stderr(stderr):
                cli._resolve_identity(
                    args,
                    fallback=cli.DEFAULT_APPROVER_FALLBACK,
                    require_approver=True,
                )
        self.assertEqual(args.principal, cli.DEFAULT_APPROVER_FALLBACK)
        self.assertIn("approver_fallback", args.identity_source)
        self.assertIn("没有审批权限", stderr.getvalue())

    def test_ask_summary_records_identity_source(self) -> None:
        code, out, err = run_cli(
            ["ask", "A-301 还欠多少？", "--principal", "principal_ops_xinghui"]
        )
        self.assertEqual(code, cli.EXIT_OK, out + err)
        payload = json.loads(out)
        self.assertEqual(payload["identity"]["identity_source"], "cli_flag")
        self.assertIn("开发模式", err)


class TestCheckCommand(unittest.TestCase):
    def test_check_reports_models_and_retrieval_settings(self) -> None:
        code, out, _ = run_cli(["check"])
        self.assertEqual(code, cli.EXIT_OK)
        payload = json.loads(out)
        self.assertIn("models", payload)
        for name in ("lease", "billing", "property", "single", "compliance"):
            self.assertIn(name, payload["models"])
            self.assertIn("model_name", payload["models"][name])
            self.assertIn("api_key_env_present", payload["models"][name])
        self.assertIn("retrieval_settings", payload)
        for settings in payload["retrieval_settings"].values():
            if settings is not None:
                # Task 031 / 2.6：未实现能力字段不得再出现在配置里
                for forbidden in (
                    "vector_store",
                    "embedding_model",
                    "rerank_top_n",
                    "bm25_weight",
                    "vector_weight",
                    "min_score",
                ):
                    self.assertNotIn(forbidden, settings)


if __name__ == "__main__":
    unittest.main()
