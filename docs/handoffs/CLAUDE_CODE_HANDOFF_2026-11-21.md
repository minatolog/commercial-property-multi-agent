# 交接给 Claude Code：Task 031 返修（R1–R4）及后续任务

> 本文件由对话模式中的 Claude 于 2026-11-21 写成。对话模式无法运行本项目的测试（没有 Python 3.11 与项目依赖），因此转到 Claude Code 在本机 `commercial-agent` 环境中完成。**新会话看不到之前的对话，本文件包含继续工作所需的全部上下文。**

## 0. 开始前必须做的事

1. 确认运行环境。按 Task 031 归档，解释器是 `D:\anacada\envs\commercial-agent\python.exe`（Python 3.11）。先运行：
   ```powershell
   conda run -n commercial-agent python -c "import langgraph, fastapi; print('ok')"
   ```
   如果当前终端不能 `conda activate`，后续命令统一用 `conda run -n commercial-agent ...` 或直接用上面的解释器路径。所有测试命令都在 `backend/` 下执行，并设置 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`。
2. 阅读（按顺序）：
   - `docs/reviews/2026-11-21_task031_acceptance_review.md`（**本次返修的依据**，R1–R5 的完整描述）
   - `docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md`（Task 031 实施归档）
   - `docs/handoffs/DEEPSEEK_TASK031_CORE_FIXES_PROMPT.md`（Task 031 原始要求）
   - `docs/architecture/CURRENT_BASELINE.md`
3. 跑一次全量回归，记录**返修前**的基线：
   ```powershell
   python -m unittest discover -s tests -p "test_*.py"
   python tests/smoke_agent_contracts.py
   ```
   Task 031 自报为 529 tests OK（skipped=1）、70 项契约。如果你的结果不同，先停下来向用户报告，不要直接开始改。

## 1. 当前仓库状态

- HEAD 为 `e3b3594`，Task 031 的全部改动**未提交**。
- 工作区中属于用户的既有改动：`.gitignore` 新增的 Flowise 三行、未跟踪的 `tools/flowise/`。**保留，不改、不删、不提交。**
- 对话模式的 Claude 只新增了以下文档，没有改任何代码：
  - `docs/handoffs/DEEPSEEK_TASK031_CORE_FIXES_PROMPT.md`、`DEEPSEEK_TASK032_BUSINESS_WORKBENCH_UI_PROMPT.md`、`DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md`
  - `docs/reviews/2026-11-21_task031_acceptance_review.md`
  - 本文件
- **不提交、不推送**，除非用户在会话中明确要求。

## 2. 返修任务

建议顺序：R3 → R1 → R2 → R4。先统一换行符，后续 diff 才干净。

### R3 换行符（先做；提交前必须完成）

已核实的事实：
- HEAD 中**所有文本文件都是 LF**，只有 PDF、PNG 等二进制文件含 CR。
- Task 031 把 27 个已跟踪的文本文件改成了 CRLF（包括 `.gitignore`、`README.md`、多个源码、测试和开发日志）。原始 diff 显示 +15,286/−12,976 行，忽略换行符后实际只有 +2,697/−387。
- Task 031 新增的未跟踪文件里，评测报告 JSON/MD、证据 JSON 和 Task 031 归档 `.md` 也是 CRLF；新增的 `.py` 测试和词表文档是 LF。
- 根因之一：`backend/app/evaluation/runner.py` 约第 516 行与 `backend/app/cli.py` 约第 1119 行使用 `Path.write_text(...)` 而没有指定 `newline`，在 Windows 上会写出 CRLF。

要做的：
1. 新增 `.gitattributes`：`* text=auto eol=lf`，并把 `*.pdf`、`*.png`、`*.jpg`、`*.sqlite`、`*.db` 等声明为 `binary`。
2. 把本轮改动和新增的**文本**文件统一转为 LF。不要碰二进制文件和 `tools/flowise/`。
3. 上面两处 `write_text` 加 `newline="\n"`，避免以后再生成 CRLF。
4. 验收：`git diff --stat` 与 `git diff --stat --ignore-cr-at-eol` 的结果一致；`git diff --ignore-cr-at-eol .gitignore` 仍只有 Flowise 三行。
5. 转换会改变评测报告文件的字节，但已核实没有任何文件记录这些报告自身的哈希，可以直接转换。

### R1 部分取证仍判成功（P2）

问题：`backend/app/agents/base/evidence.py` 的 `minimum_evidence_reason(scope, facts)` 只检查 `facts` 是否非空。问题同时涉及两个领域（如"A-301 租期和欠款？"），账单工具失败、合同工具成功时，Single 路径（`backend/app/agents/single/agent.py` 约第 207 行）返回 SUCCESS。测试 `backend/tests/test_task031_z2_evidence.py` 中的 `test_failed_call_does_not_enter_facts_when_another_call_succeeds`（约第 355 行）断言 `status in {SUCCESS, PARTIAL}`，放过了这种情况。

要做的：
1. 有失败调用，且问题涉及的某个领域没有取得任何事实时，结果为 PARTIAL，warnings 中写明缺了哪个领域。"问题涉及哪些领域"复用现有词表：`backend/app/orchestration/vocabulary.py` 的 `matched_domains`（`single_demo._business_domains` 已在用）。领域与工具 / 事实键的对应关系，请以现有代码为准确定，不要另造一套。
2. 检查 LLM 领域 Agent 路径（`backend/app/agents/base/llm_agent.py` 约第 208 行）是否存在同样的问题。领域 Agent 只负责一个 capability，并已有 `check_capability_output`；如果判断不需要改，在归档里写明理由。
3. 测试：把上述用例收紧为只接受 PARTIAL；新增对照用例"两个领域都成功 → SUCCESS"；新增"只问一个领域、那个领域失败、另一个无关工具成功"的用例，明确它应该是什么状态并说明理由。
4. 确认 PARTIAL 在 CLI 退出码、评测评分和 API 展示中的含义一致；如果引起评测结果变化，逐题记录，不改评测题和评分规则。

### R2 报告中的模型名是配置名，不是服务端实际模型（P2）

问题：DeepSeek 官方公告（https://api-docs.deepseek.com/news/news260424）称 `deepseek-chat` 于 2026-07-24 15:59 UTC 后完全下线（下线前路由到 `deepseek-v4-flash`）。但本项目 `docs/evaluation/reports/real_model_v2/` 中 2026-11-06 的 4 份报告都以 `deepseek-chat` 调用成功并消耗了真实 token。报告里的 `model_name` 只是配置值，服务端实际由哪个模型应答从未记录。Task 031 归档中"真实调用会失败"的说法与此矛盾。

要做的：
1. `backend/app/llm/langchain_client.py` 中把响应转成 `ModelTurn` 的位置（约第 209–220 行，已在读取 `response_metadata` 的 `finish_reason`），同时读取服务端返回的模型标识（ChatOpenAI 一般在 `response_metadata["model_name"]`；以实际安装的 langchain-openai 版本为准）。把它加入 `ModelTurn` 或 usage 记录（字段可以叫 `served_model`，缺失时为 `None`）。
2. 汇总到 Agent 输出和评测报告的 `models_by_agent`（`backend/app/evaluation/runner.py`、`baselines.py`）：同时报告"配置模型名"和"实际应答模型名"（可能有多个），两者不一致时标注。
3. 测试用伪造的响应对象（带 `response_metadata`），**不调用付费接口**。
4. 修正 Task 031 归档第 6.6 节和第 7 节表格中"真实调用会失败"的表述，改为："官方公告已下线；本项目 11-06 实测以该名字仍可调用，实际应答模型当时未记录。"同步在 `CURRENT_BASELINE.md` 的真实模型证据一行注明"历史报告中的模型名为配置名"。**不改历史报告文件本身。**

### R4 dry-run 副本改用 SQLite 备份接口（P3）

问题：`backend/app/orchestration/approval.py` 的 `_copy_for_preview` 依次用 `shutil.copy2` 复制主库、`-wal`、`-shm`。并发写入时三者可能不一致，`-shm` 也不应该复制。

要做的：改用 `sqlite3.connect(源).backup(sqlite3.connect(副本))` 生成一致性快照，两个连接都显式关闭（Windows 下否则无法清理临时目录）。保留"台账不存在时报错且不创建台账"的行为。补一个测试：预演后原台账逐字节不变，且预演结果与真实执行一致。

### R5 不要改（等用户决定）

`ask` 在问题命中业务词但没有目标时直接报用法错误（例如"免租期一般怎么约定？"也会被拒）。是否放宽由用户决定，本次不改。

## 3. 完成标准

1. 全量回归与契约自检通过，记录**实际**数字（与返修前基线对比，说明新增了哪些测试）。
2. `python -m app.cli check` exit 0；`python -m app.cli ask "A-301 现在还有多少钱没交？"` 和 `python -m app.cli investigate --model-provider scripted` 正常。
3. 离线评测重跑一次：`python -m app.cli evaluate --split heldout`，和 Task 031 改动后的报告（`docs/evaluation/reports/20261121T085431_*`）逐题对比；有变化逐题说明。
4. R3 的验收条件全部满足。
5. 归档：在 Task 031 归档末尾追加"返修（R1–R4）"一节，写清改了什么、证据、遗留问题；更新开发日志、问题日志（根因、修法、如何防止复发）、`CURRENT_BASELINE.md`；在 `docs/reviews/2026-11-21_task031_acceptance_review.md` 末尾追加"返修结果"一节，逐条对应 R1–R4。正文和状态表保持一致。
6. 向用户汇报：每项"做了什么 / 证据 / 遗留"。不要声称最终验收通过：实现者和复查者应该分开，建议用户请 DeepSeek 或 Codex 复查本次返修。

## 4. 之后的任务（返修完成、用户确认后再开始）

1. **Task 032 前端改版**：`docs/handoffs/DEEPSEEK_TASK032_BUSINESS_WORKBENCH_UI_PROMPT.md`。Prompt 写的是"给 DeepSeek"，由 Claude Code 执行同样适用。Claude Code 可以启动服务，并在浏览器中查看页面、截图自查。另外要注意：`needs_clarification` 的运行目前在 API 中记为 `completed`，界面必须单独展示为"需要补充信息"。
2. **Task 033 MCP 网关**：`docs/handoffs/DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md`。
3. 每个任务完成后都由另一个模型（DeepSeek 或 Codex）独立复查，再开始下一个。一次只做一个任务。
