# 任务单 033C：MCP 网关手动连接验证与文档归档

- 编写：2026-11-23，Claude Code。由 `scripts/dev_loop/` 执行。
- 前置：033A、033B 已完成并提交。**先阅读 `backend/app/mcp_gateway/` 全部代码、`tests/test_mcp_gateway.py`、原 Prompt [`DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md`](DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md) §7，以及 [Task 032 归档](../prompts/05_frontend/2026-11-22_032_business_workbench_ui.md) 的章节格式。**
- 本任务**不改任何代码和测试**。

## 1. 只新增 / 修改这些文件

| 文件 | 内容 |
|---|---|
| `docs/reviews/task033_evidence/stdio_probe.py` | 手动连接脚本：用 SDK 的 stdio 客户端启动 `python -m app.cli mcp-serve --transport stdio --client local_dev`，依次做初始化、`tools/list`、调用 `lease_lookup`（星汇 A-301 合同）、调用一次会被拒绝的请求（参数带 `principal_id`），把每一步的请求与结果打印出来 |
| `docs/reviews/task033_evidence/stdio_probe.txt` | 上面脚本的实际输出（在 `backend/` 下运行，原样保存，不要手改） |
| `docs/reviews/task033_evidence/unittest.txt`、`smoke.txt` | 全量回归与契约自检的实际输出 |
| `docs/prompts/04_agents/2026-11-23_033_mcp_gateway.md` | 任务归档（格式见下） |
| `backend/README.md` | 新增“MCP 网关”一节 |
| `docs/README.md` | 任务表登记 Task 033 |
| `docs/development_logs/development_log.md` | 最上方新增一条 |
| `docs/issues/issue_log.md` | 最上方新增一条（实施中遇到的问题；没有就写“无新问题”及理由） |
| `docs/architecture/CURRENT_BASELINE.md` | 更新日期行与“最新回归证据”行 |
| `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` | 更新首行与“下一步” |

不要改其它文件，也不要改这些文件里与 Task 033 无关的历史条目。

## 2. 内容要求

- **归档**：按 032 归档的章节格式写（目标与范围、实际改动、设计要点、测试点逐条结果、手动连接记录、安全边界、遗留问题、对应 Git Commit Hash）。
  - 测试点逐条结果：原 Prompt §5 的 10 点 + stdio 冒烟，每点写测试名和结果。
  - SDK 版本：`mcp==2.3.0`，并写明 low-level `Server` 的实际用法。
  - Commit Hash：033A / 033B 的实际提交用 `git log --oneline -5` 查出来写上；033C 本身写 `Pending`。
  - 下一版（Streamable HTTP + OAuth）你认为**最大的风险**，写具体，不要泛泛而谈。
- **`backend/README.md` 的 MCP 网关一节**：启动命令、两个客户端档案的区别、安全边界（只读、身份只来自会话、保留键拦截、预算按会话、开发模式固定主体不可用于生产）、Flowise 如何以 stdio 方式连接（用 `flowise` 档案，写清命令与工作目录）、下一版计划。
- **数字一律来自实际运行**：测试数、契约数写 `unittest.txt` / `smoke.txt` 里的数字。
- **状态措辞**：Task 033 写“已实施并自检，待独立复查；未推送”。不要写“已通过”“已验收”。
- 不调用任何付费模型接口。

## 3. 验收标准

- 只改第 1 节列出的文件；没有改任何代码和测试。
- `stdio_probe.txt` 是真实输出，能看到工具列表、一次成功调用（金额为字符串）和一次被拒绝的调用（`isError` 为真）。
- 文档里的数字与证据文件一致；各文档对 Task 033 的状态说法一致。
- 新文件 UTF-8、LF。
