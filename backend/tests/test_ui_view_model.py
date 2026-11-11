"""Task 029：前端展示映射的真实 JavaScript 行为回归。

Task 028 的 U1–U3 都发生在 `backend/app/api/static/js/view-model.js` 里，
纯 Python 断言或对 JS 文本做正则匹配都无法发现。这里用**真实浏览器**加载
`app/api/static/tests/ui-model-harness.html`，由浏览器执行真实的 ES 模块，
Python 只负责三件事：

1. 用隔离控制面实际调用 `POST /api/runs`，取得真实返回体（含预算耗尽失败）；
2. 起一个只读静态服务，把静态目录和真实返回体交给浏览器；
3. 解析浏览器写回的结果并断言。

找不到 Chrome/Edge 时整类跳过并说明原因，不静默通过。
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.service import RunIndex, WorkflowService

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "static"
HARNESS_PATH = "/tests/ui-model-harness.html"
REAL_RUNS_PATH = "/__tests__/real-runs.json"

COMPLEX_QUESTION = (
    "商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，"
    "并要求减免费用。请核对合同、账单、付款和工单。"
)
LEASE = "lease_xh_a301_2025"

_BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _find_browser() -> str | None:
    override = os.environ.get("UI_TEST_BROWSER")
    if override and Path(override).exists():
        return override
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in _BROWSER_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


class _StaticHandler(SimpleHTTPRequestHandler):
    """只读静态服务：静态目录 + 注入的真实运行 JSON。"""

    real_runs: bytes = b"{}"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 接口
        if self.path.split("?")[0] == REAL_RUNS_PATH:
            body = type(self).real_runs
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args: Any) -> None:  # 静默：不污染测试输出
        pass


def _build_real_runs() -> dict[str, Any]:
    """用隔离控制面真实调用 API，得到进入 JS 模型的真实返回体。"""

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        service = WorkflowService(
            index=RunIndex(base / "runs.sqlite"),
            checkpoint_path=base / "graph.sqlite",
            approval_path=base / "approval.sqlite",
        )
        client = TestClient(create_app(service=service))
        runs: dict[str, Any] = {}

        def submit(name: str, **overrides: Any) -> None:
            payload = {"question": COMPLEX_QUESTION, "lease_id": LEASE}
            payload.update(overrides)
            response = client.post("/api/runs", json=payload)
            if response.status_code != 201:
                runs[name] = {"error": response.json()}
                return
            run_id = response.json()["run_id"]
            runs[name] = client.get(f"/api/runs/{run_id}").json()

        submit("complex_approval", with_approval=True)
        submit("budget_fail", with_approval=False, max_tool_calls=1)
        submit("simple", question="A-301 现在还有多少钱没交？", with_approval=False)
        return {"runs": runs, "meta": client.get("/api/meta").json()}


def _run_harness(browser: str, real_runs: dict[str, Any]) -> dict[str, Any]:
    _StaticHandler.real_runs = json.dumps(real_runs, ensure_ascii=False).encode("utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StaticHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as profile:
            command = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                "--disable-background-networking",
                f"--user-data-dir={profile}",
                "--virtual-time-budget=20000",
                "--dump-dom",
                f"http://127.0.0.1:{port}{HARNESS_PATH}",
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
        match = re.search(r'<pre id="ui-results">(.*?)</pre>', completed.stdout, re.S)
        if not match:
            raise AssertionError(
                "harness 没有返回结果；浏览器 stderr 片段："
                + (completed.stderr or "")[:1500]
            )
        return json.loads(html.unescape(match.group(1)))
    finally:
        server.shutdown()
        server.server_close()


class TestViewModelJavaScriptBehaviour(unittest.TestCase):
    """对 Task 028 的 U1–U3 做可重复的浏览器级回归。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.browser = _find_browser()
        if not cls.browser:
            raise unittest.SkipTest(
                "未找到 Chrome/Edge，跳过前端 JS 行为回归（不视为通过）；"
                "可用 UI_TEST_BROWSER 指定浏览器路径"
            )
        cls.real_runs = _build_real_runs()
        cls.harness = _run_harness(cls.browser, cls.real_runs)

    def test_harness_passes_all_cases(self) -> None:
        result = self.harness.get("result") or {}
        failures = [
            f"{case['name']} -> {failure}"
            for case in result.get("cases", [])
            for failure in case["failures"]
        ]
        self.assertIsNone(self.harness.get("error"), failures)
        self.assertTrue(self.harness.get("ok"), failures)
        self.assertEqual(result.get("failedCases"), 0, failures)

    def test_fixture_and_real_cases_are_both_present(self) -> None:
        result = self.harness["result"]
        self.assertGreaterEqual(result["fixtureCases"], 12, result)
        self.assertGreaterEqual(result["realCases"], 2, result)
        self.assertGreaterEqual(result["totalAssertions"], 60, result)

    def test_u1_failed_agent_is_not_reported_as_not_called(self) -> None:
        """U1：真实预算耗尽运行里，失败领域必须带错误码与工具记录。"""

        budget = self.real_runs["runs"]["budget_fail"]
        failures = budget["report"]["failures"]
        self.assertTrue(failures, "本次真实运行没有复现预算耗尽失败")
        names = {case["name"] for case in self.harness["result"]["cases"]}
        self.assertIn("真实 API：工具预算耗尽", names)
        self.assertIn("工具预算耗尽：失败可见，保留错误码与工具尝试", names)

    def test_u2_nodes_see_clause_and_work_order_findings(self) -> None:
        """U2：真实复杂报告里合同条款与工单发现必须能映射到 Agent 节点。"""

        complex_run = self.real_runs["runs"]["complex_approval"]
        findings = complex_run["report"]["findings"]
        documents = [
            item for item in findings
            if (item.get("source") or {}).get("document_id")
        ]
        self.assertGreaterEqual(len(documents), 3, "真实报告应有 3 条条款类发现")
        names = {case["name"] for case in self.harness["result"]["cases"]}
        self.assertIn("真实 API：A-301 复杂调查", names)

    def test_u3_report_error_never_renders_success(self) -> None:
        """U3：report.error 结构在真实 JS 里不得判成功。"""

        names = {case["name"] for case in self.harness["result"]["cases"]}
        self.assertIn("report.error：规划 / 核验 / 报告均不给绿灯", names)

    def test_harness_page_is_not_linked_from_product_page(self) -> None:
        """测试入口不应出现在产品页面资源里。"""

        index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("ui-model-harness", index)
        self.assertNotIn("/tests/", index)


if __name__ == "__main__":
    unittest.main()
