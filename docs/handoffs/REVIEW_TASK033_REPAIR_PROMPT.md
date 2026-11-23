# 复查 Prompt：Task 033 返修确认（只看返修改动）

- 编写：2026-11-23（Asia/Shanghai），Claude Code（返修者）。
- 给：上一轮复查者 DeepSeek（或其他与返修者不同的模型 / 人）。
- 性质：**只读复查**，只确认 [上一轮复查](../reviews/2026-11-23_task033_independent_review.md) 提出的问题是否真的关闭、返修有没有引入新问题。不重做整轮复查。
- 上一轮结论：**有条件通过**，无 P1；P2 两项、P3 六项。

---

## 0. 硬性约束（与上一轮相同）

1. 不调用付费模型接口；不 `pip install`。
2. 不提交、不推送、不切分支、不 stash、不改工作区文件；变异实验在仓库外副本里做；不碰 `data/`。
3. 环境：`D:\anacada\envs\commercial-agent\python.exe`，在 `backend/` 下运行，设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
4. 报告新写的文本文件用 LF。

## 1. 返修范围

- **返修只有一个提交**：`1f8ce86a822577ceb927efb627e26236d63ad1b7`。看差异：`git diff 3656ecb 1f8ce86`（15 个文件；代码只有 `knowledge_tools.py`、`rag/library.py`、`mcp_gateway/server.py`、`cli.py` 四个，其余是测试、证据和文档）。
- 开始前确认 `git rev-parse HEAD` 是 `1f8ce86` 或其后只多了本 Prompt 的提交，`git status --porcelain` 除 `.claude/` 外为空。
- 返修记录：[033 归档 §11](../prompts/04_agents/2026-11-23_033_mcp_gateway.md)。

## 2. 返修自报数字（独立复跑）

| 项 | 上一轮实测 | 返修后自报 |
|---|---|---|
| 全量回归 | 651 OK（skipped=1） | **659** OK（skipped=1） |
| `tests/test_mcp_gateway.py` | 41 | **49** |
| 契约 / `check` | 70 / exit 0 | 70 / exit 0 |
| 离线 heldout（`evaluate --split heldout --out <仓库外目录>`）对比 `20261121T093757_*` | —— | A/B/C 各 32 题 **0 差异**，汇总一致（忽略延迟、`planning`、cost） |
| `stdio_probe.py` 对比 `stdio_probe.txt` | 一致 | 已重新生成；比旧证据多两行 stderr（新启动提示、拒绝记录） |

证据：`docs/reviews/task033_evidence/repair_unittest.txt`、`repair_smoke.txt`、`stdio_probe.txt`。

## 3. 逐条确认（每条写：做了什么、看到了什么、关闭 / 部分关闭 / 未关闭）

| 编号 | 上一轮问题 | 返修位置 | 请这样验证 |
|---|---|---|---|
| P2-1 | `document.search` 点名越权目标返回 `ok` + 0 条 | `tools/knowledge_tools.py` 的 `_assert_targets_in_scope`；`rag/library.py` 新增 `catalog_metas` | 重做上一轮的两个反例（越权 `lease_id`；本租约 + 越权 `document_ids`），再试越权 `document_id`、越权 + `include_project_documents`/`include_drafts` 组合、本项目正常检索。**特别核对**：返修说根因之一是锦澜合同缺 PDF、不在已索引文档里——确认 `catalog_metas` 确实包含未索引文档，且只用于判断归属、没有被用来扩大可检索范围 |
| P2-1 影响面 | 修在共享工具层，所有调用 `document.search` 的 Agent 都受影响 | 同上 | 独立跑一次离线 heldout 并逐题对比；搜索调用 `DocumentSearchTool` 的其它入口（`baselines.py`、`investigation_demo.py`、`cli.py search`），判断越权目标改报错后有没有让某条路径从“空结果继续”变成“失败中断”，以及这是否合理 |
| P2-2 | 未知工具名无测试守护 | `tests/test_mcp_gateway.py::test_unknown_tool_name_is_rejected_without_execution` | 在仓库外副本重做你上一轮的“未知名回退 `lease.lookup`”变异，确认现在会失败；再换一个回退目标（例如 `document.search`）试一次 |
| P3-1 | 启动提示不显示主体；README 自相矛盾 | `cli.py` 的 `_cmd_mcp_serve`；`server.py` 的 `startup_identity`；`backend/README.md` §5.3 / §5.4 | 启动一次看 stderr；读 README 两节是否一致 |
| P3-2 | `_sessions` 只增不减 | `server.py`：`deque(maxlen=_SESSION_HISTORY)` | 判断上限做法是否足够（相对“连接结束即移除”）；测试 `test_session_history_is_bounded` 是否真的测到上限 |
| P3-3 | 预拦截拒绝无记录 | `server.py` 的 `_dispatch` 保留键分支 | 看 stderr 记录内容；确认没有把参数值（可能含敏感信息）原样写进日志 |
| P3-4 | 主体不存在仍能启动 | `GatewayServer.__init__` | 档案主体不存在、`DEMO_PRINCIPAL_ID` 指向不存在主体，两种都应启动失败、CLI 退出码 2 |
| P3-5 | 测试覆盖边界 | `test_mcp_gateway.py` 新增 8 个测试 | 检查有没有空断言 / 恒真断言；`test_document_search_cross_project_target_is_denied` 是否用的是**真实**注册表（上一轮的 `_registry()` 里 `document.search` 只是占位） |
| P3-6 | 033C 提交状态陈旧 | 归档、开发日志、问题日志 | 核对提交哈希与状态措辞 |

## 4. 返修中的新发现（请判断处理是否妥当）

返修者在重跑 `stdio_probe.py` 时发现：`.env` 加载（`app/env.py` 的 `load_env_file`）把**空值当作未设置**，所以 `.env` 里的 `DEMO_PRINCIPAL_ID` 会覆盖 MCP 档案主体，客户端传 `DEMO_PRINCIPAL_ID=""` 也拦不住。当前 `.env` 的值与档案相同，没有实际影响。返修**没有改代码**（改加载语义会影响网页演示），只在 `backend/README.md` 写明，并从 Flowise 配置示例里删掉了 `"DEMO_PRINCIPAL_ID": ""`。

请判断：这是否构成 P1 / P2（例如：外部 MCP 客户端的配置者以为用的是 `flowise` 档案的主体，实际被 `.env` 换成了别的主体）；只写文档是否足够，还是应该让 `mcp-serve` 不从 `.env` 读取这一项。**只给结论和建议，不要修改。**

## 5. 回归与副作用

1. 复跑全量回归、契约、`check`、离线 heldout 对比、`stdio_probe.py`，记录实际数字。
2. 返修有没有改变 033 范围之外的行为（除了 P2-1 有意改变 `document.search` 的越权语义）。
3. 新改的文件里有没有密钥、CRLF（`git ls-files --eol`；注意 `library.py` / `knowledge_tools.py` 在工作区本来就是 CRLF 检出、索引为 LF，这不算问题）。
4. 各文档对 033 的状态措辞是否一致，是否写成了“已通过”。

## 6. 报告

- 写到 `docs/reviews/2026-11-23_task033_repair_review.md`。
- 开头写结论：每个条件关闭 / 部分关闭 / 未关闭，以及是否发现新问题（P1 / P2 / P3 分级）；§4 的新发现单独给出判断。
- 写明本轮限制。不要声称最终验收通过；不要更新开发日志、`CURRENT_BASELINE` 或路线图。
