"""Task 033C：MCP 网关 stdio 手动连接脚本。

运行方式（从仓库根目录）：

    D:/anacada/envs/commercial-agent/python.exe -X utf8 docs/reviews/task033_evidence/stdio_probe.py

脚本先把工作目录切到 `backend/`（与在 backend 下运行等价），再用 MCP 官方
Python SDK（mcp==2.3.0）的 stdio 客户端启动真实 CLI：

    python -m app.cli mcp-serve --transport stdio --client local_dev

依次执行初始化、`tools/list`、`lease_lookup`（星汇 A-301 合同）和一次参数带
`principal_id`、预期被拒绝的调用，逐步打印请求、结果与服务端 stderr。
本脚本不修改任何业务状态，也不调用模型接口。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client

#: docs/reviews/task033_evidence/ → reviews → docs → 仓库根 → backend/
BACKEND = Path(__file__).resolve().parents[3] / "backend"

CLIENT_PROFILE = "local_dev"
LEASE_ID = "lease_xh_a301_2025"  # 星汇 · A-301 商铺租赁合同
REJECTED_ARGUMENTS = {
    "lease_id": LEASE_ID,
    # 保留键：身份/权限/预算只能来自服务端会话，客户端不能自报。
    "principal_id": "principal_finance_jinlan",
}


def _emit(title: str, body: str = "") -> None:
    print(f"\n=== {title} ===")
    if body:
        print(body)


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _describe_tools(listing: Any) -> None:
    tools = listing.tools
    print(f"工具数: {len(tools)}")
    for tool in tools:
        print(f"\n- name: {tool.name}")
        print(f"  description: {tool.description}")
        schema = tool.input_schema or {}
        print(
            "  inputSchema: "
            + json.dumps(
                {
                    "properties": sorted((schema.get("properties") or {}).keys()),
                    "required": schema.get("required") or [],
                },
                ensure_ascii=False,
            )
        )
        output_schema = tool.output_schema or {}
        properties = output_schema.get("properties") or {}
        status_enum = (properties.get("status") or {}).get("enum")
        print(
            "  outputSchema: "
            + json.dumps(
                {
                    "title": output_schema.get("title"),
                    "status": status_enum,
                    "data_declared_as_nullable": "anyOf" in (properties.get("data") or {}),
                },
                ensure_ascii=False,
            )
        )


def _describe_call(request: dict[str, Any], result: Any) -> None:
    print("请求:")
    print(_json(request))
    print(f"\nisError: {result.is_error}")
    print("structuredContent:")
    print(_json(result.structured_content))
    if result.content:
        text = result.content[0].text
        same = json.loads(text) == result.structured_content
        print(f"content[0].text 与 structuredContent 相同: {same}")


async def _scenario(errlog: Any) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "app.cli",
            "mcp-serve",
            "--transport",
            "stdio",
            "--client",
            CLIENT_PROFILE,
        ],
        cwd=str(BACKEND),
        env={
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            # 显式清空，确保身份只来自客户端档案，不受调用者环境影响。
            "DEMO_PRINCIPAL_ID": "",
        },
    )

    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            _emit(
                "1. 初始化（initialize）",
                "请求: initialize（SDK 默认协议版本与客户端能力）",
            )
            initialized = await session.initialize()
            server = initialized.server_info
            print(
                f"结果: server={server.name} {server.version}, "
                f"protocol={initialized.protocol_version}"
            )
            if initialized.instructions:
                print(f"instructions: {initialized.instructions}")

            _emit("2. 列出工具（tools/list）", "请求: tools/list {}")
            listing = await session.list_tools()
            _describe_tools(listing)

            _emit(
                "3. 调用 lease_lookup（星汇 A-301 合同，预期成功）",
                "",
            )
            request = {"name": "lease_lookup", "arguments": {"lease_id": LEASE_ID}}
            result = await session.call_tool(request["name"], request["arguments"])
            _describe_call(request, result)

            _emit(
                "4. 调用 lease_lookup 但参数带 principal_id（预期被拒绝）",
                "",
            )
            request = {"name": "lease_lookup", "arguments": REJECTED_ARGUMENTS}
            result = await session.call_tool(request["name"], request["arguments"])
            _describe_call(request, result)


def main() -> int:
    # 证据文件统一 LF（仓库约定），不受 Windows 文本模式的 CRLF 转换影响。
    sys.stdout.reconfigure(newline="\n")
    print("=== Task 033C MCP stdio 手动连接记录（mcp==2.3.0 SDK 客户端）===")
    print(f"启动命令: {sys.executable} -m app.cli mcp-serve --transport stdio --client {CLIENT_PROFILE}")
    print(f"工作目录: {BACKEND}")

    os.chdir(BACKEND)

    errlog = tempfile.NamedTemporaryFile(
        mode="w+", encoding="utf-8", suffix=".log", delete=False
    )
    try:
        asyncio.run(asyncio.wait_for(_scenario(errlog), timeout=120))
        errlog.flush()
        errlog.seek(0)
        stderr_text = errlog.read().strip()
    finally:
        errlog.close()
        Path(errlog.name).unlink(missing_ok=True)

    _emit("5. 服务端 stderr（启动提示与诊断，stdout 只承载 MCP 协议）")
    print(stderr_text or "（空）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
