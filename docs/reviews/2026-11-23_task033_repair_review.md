# Task 033 返修确认复查（只看返修改动）

- **复查日期**：2026-11-23（Asia/Shanghai）。
- **复查者**：DeepSeek（与返修者、原审查方不同）。本轮**只读**：不修改源码/测试/配置/文档状态，不提交、不推送、不切分支、不 stash；变异实验只在仓库外副本完成，未碰 `data/`。**未调用付费模型接口，未执行 `pip install`。**
- **复查范围**：[返修确认 Prompt](../handoffs/REVIEW_TASK033_REPAIR_PROMPT.md) 指定的唯一返修提交 `1f8ce86a822577ceb927efb627e26236d63ad1b7`；只确认上一轮 [独立复查](2026-11-23_task033_independent_review.md) 的问题是否关闭、返修是否引入新问题，不重做整轮复查。
- **基线**：当前 `HEAD = d246827456f5e2a522e11807a2218a578410ae6a`（`1f8ce86` 之后只多本复查 Prompt 提交）；`git status --porcelain -uall` 只有允许排除的 `?? .claude/launch.json`。`git diff --stat 3656ecb 1f8ce86`：**15 个文件、468 行新增、40 行删除**；代码只涉及 `knowledge_tools.py`、`rag/library.py`、`mcp_gateway/server.py`、`cli.py` 四个文件。`git ls-files --eol` 显示 `library.py`/`knowledge_tools.py` 工作区为 CRLF、索引为 LF（返修 Prompt 明说这是既有检出状态，不算问题）；其余 15 个文件工作区为 LF。
- **环境**：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18）；`backend/` 下运行，`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；安装 `mcp==2.3.0`。

## 结论

**返修确认通过（有条件收尾）。**

- **P2-1 关闭**：越权 `lease_id`、本租约+越权 `document_ids`、越权 `document_id`、越权 + `include_project_documents`/`include_drafts` 组合均返回 `denied/project_scope_denied`；本项目正常检索仍返回真实证据。`catalog_metas` 确实包含未索引的锦澜合同，且只用于归属判断；`_resolve_allowed()` 仍只从已索引文档集合取检索范围，没有把目录元数据变成可检索数据。离线 heldout A/B/C 各 32 题逐题 **0 差异**、汇总一致；`cli search` 直接走 `KnowledgeService`，不受该工具层改动影响。
- **P2-2 关闭**：新增未知名测试；仓库外副本基线 49 tests 通过，把未知名回退到 `lease.lookup` 后 **4 项失败**，回退到 `document.search` 后 **3 项失败**。
- **P3-1、P3-2、P3-3、P3-5 关闭**；**P3-4 按“生效主体”口径关闭**（档案主体不存在、环境主体不存在在干净环境下均启动失败、CLI exit 2），但存在 `.env` 优先于档案主体的边界（见 §4）。**P3-6 部分关闭**：归档、开发日志、问题日志、README、路线图首行/基线首行已更新，但 `CURRENT_BASELINE` 两处和路线图一处仍写“待独立复查”。
- **§4 的 `.env` 新发现判为 P3，不是 P1/P2（在当前 stdio 本地开发威胁模型下）**：它没有 `tools/call` 路径，启动提示已打印实际主体与来源，README 已写明；但若把配置服务环境的外部方视为不可信，或 `.env` 与档案主体不同，则可静默换项目，应升级为 P2 并在 `mcp-serve` 侧禁止 `.env` 注入该键。详见 §4。
- **未发现新 P1/P2**；本轮通过不等于最终验收，HTTP/OAuth/TLS、Flowise 实连等仍未验证。

## 1. 独立复跑与证据

| 项 | 我的实测 | 与返修自报对比 |
|---|---|---|
| 全量回归 | **Ran 659 tests in 39.397s，OK（skipped=1）**（证据 `repair_unittest.txt` 写 43.402s，同样 659/OK） | 一致 |
| `tests/test_mcp_gateway.py` | **Ran 49 tests in 1.992s，OK**；文件确有 49 个 `def test_` | 自报 41 → 49，一致 |
| 契约自检 | `python tests/smoke_agent_contracts.py` → **全部通过：70 项** | 一致 |
| `check` | `python -m app.cli check` → exit 0 | 一致 |
| 离线 heldout | `evaluate --split heldout --out D:\review033repair_heldout`；A/B/C 各 32 行，与 `20261121T093757_*` 逐行 **0 差异**，summary 相等，cases/scoring binding 相等 | 自报 0 差异，**一致** |
| `stdio_probe.py` | 重跑输出 303 行；与更新后的 `stdio_probe.txt` 归一化 `call_id`/会话 ID/时间后 **0 行差异**；新增 stderr 为启动提示与保留键拒绝记录 | 自报一致 |
| P2-1 反例 | 见 §2；全部越权组合 denied；正常检索 1 条结果、1 条证据；未知租约/未知文档仍 `ok` + 0（目录无归属可判定，归档已说明） | 关闭 |
| P2-2 变异 | 仓库外副本：基线 49 OK；未知名回退 `lease.lookup` → **4 failures**；回退 `document.search` → **3 failures**；移除 `_assert_targets_in_scope` → **3 failures** | 关闭 |
| P3-4 CLI | 干净 profile 主体不存在 → CLI exit 2；`DEMO_PRINCIPAL_ID` 不存在 → exit 2；profile 主体不存在但环境主体有效 → exit 0（见 §4） | 基本关闭，有 `.env` 边界 |
| EOL/密钥 | 15 个改动文件无新增 CRLF；无密钥/Bearer 模式命中；`library.py`/`knowledge_tools.py` 的 `w/crlf` 为既有检出状态；README 中绝对路径是操作示例 | 无新增问题 |

## 2. 逐条确认

### P2-1 关闭

返修位置：`backend/app/tools/knowledge_tools.py` 的 `_assert_targets_in_scope()`（`knowledge_tools.py:93-129`）、`backend/app/rag/library.py` 的 `catalog_metas`（`library.py:53,145-193`）、`invoke()` 在 `_resolve_allowed()` 前调用范围检查（`knowledge_tools.py:176-192`）。

我的反例（星汇主体，`local_dev`，真实注册表）：

| 目标 | 结果 |
|---|---|
| 越权 `lease_id=lease_jl_b101_2025` | `isError=true/status=denied/code=project_scope_denied` |
| 本租约 + 越权 `document_ids=["doc_jl_b101_contract"]` | 同上 |
| 越权 `document_id=doc_jl_b101_contract` | 同上 |
| 越权租约 + `include_project_documents=true/false` | 同上 |
| 越权租约 + `include_drafts=true` | 同上 |
| 本项目 `lease_id=lease_xh_a301_2025` 正常检索 | `ok`，1 条结果 / 1 条证据，页码、条款号存在 |
| 未知租约 / 未知文档 | `ok` + 0（目录没有归属信息，无法判定；归档明确说明“不猜测”） |

根因核对：我直接读 `build_knowledge_library()` 的库对象：

- `indexed_document_ids = ["doc_xh_a301_contract", "doc_xh_property_policy"]`
- `catalog_document_ids = ["doc_jl_b101_contract", "doc_xh_a301_contract", "doc_xh_property_policy"]`
- `missing_documents = ["doc_jl_b101_contract"]`
- 锦澜合同 **不在索引、在目录**；`catalog_metas` 只参与 `_assert_targets_in_scope` 的归属判断。`_resolve_allowed()` 仍用 `self._library.document_ids_for_lease()` / `project_document_ids()`（已索引 `documents`），没有把 `catalog_metas` 加入检索集合；我的正常检索只返回 `prj_xinghui` 文档。

影响面：

- `cli.py search` 走 `KnowledgeService.search`（不是 `DocumentSearchTool`），不受新范围检查影响；
- `baselines.py` / `investigation_demo.py` 通过 `DocumentSearchTool` 使用同一逻辑；离线 heldout A/B/C 各 32 题 0 差异，总汇总一致，未见“空结果继续”的路径被改成失败中断或反之；
- 新增测试 `test_document_search_cross_project_target_is_denied` 使用 `load_gateway()` 的真实注册表（不是旧 `_registry()` 的占位），并断言了跨项目拒绝、本项目真实页码/条款证据；通过（49 tests）。

**P2-1 关闭。**

### P2-2 关闭

返修位置：`backend/tests/test_mcp_gateway.py:916` `test_unknown_tool_name_is_rejected_without_execution`。

- 测试对 `does_not_exist`、`billing.statement.write`、`Billing_Statement_Read` 逐个调用，断言 `isError`、`status != ok`、错误码为 `tool_not_found`/`tool_not_allowed`、`data=null`；并把 `local_dev` 所有允许工具的 `invoke` 打桩，断言无任何工具执行、会话 Trace 无 `ok`。
- 我在仓库外副本重做上一轮变异：基线 49 tests OK；未知名回退 `lease.lookup` → 4 failures；回退 `document.search` → 3 failures。新增测试确实守护未知名称，不会让未知名静默路由到允许工具。

**P2-2 关闭。**

### P3-1 关闭

- `backend/app/cli.py` 的 `_cmd_mcp_serve` 打印 `gateway.startup_identity` 的档案、主体、来源；我的 stdio probe 实际 stderr：
  `[dev-mode] 开发模式：固定主体，不可用于生产；档案 local_dev，主体 principal_ops_xinghui（来源 env:DEMO_PRINCIPAL_ID）`。
- `backend/README.md` §5.3/§5.4 已统一：档案 `principal_id`、启动环境非空 `DEMO_PRINCIPAL_ID` 会覆盖、`.env` 也会覆盖；工具参数不能影响身份。原先“身份只由档案决定”的矛盾措辞已去掉。
- **P3-1 关闭**；`.env` 覆盖本身见 §4。

### P3-2 关闭

- `backend/app/mcp_gateway/server.py:224` 改为 `deque(maxlen=_SESSION_HISTORY)`（32）；`sessions` 属性明确“最近会话快照”。
- `test_session_history_is_bounded` 把 `_SESSION_HISTORY` 调到 3，建 5 个连接后断言 `len(gateway.sessions)==3`，测试通过；没有再用无限 `list`。
- 这是“诊断快照上限”而不是“连接结束即删除”；对当前 stdio 单连接无功能影响，对 HTTP 的长期运行也避免了无限增长。**足够关闭本项**。

### P3-3 关闭

- `_dispatch` 保留键分支在 stderr 打印会话 ID、请求工具名、保留键名（`server.py:347-360`）；没有打印参数值，也没有打印完整 payload。
- 我的 probe/测试实际日志只含 `['principal_id']`，不含 `principal_finance_jinlan` 等值；`test_reserved_key_denial_is_logged_to_stderr` 断言日志含会话 ID 和保留键、且被拦截。
- **P3-3 关闭**。未知工具名仍走执行器并产生执行器 Trace（我实测 1 条），不属于本项的“预拦截无记录”。

### P3-4 基本关闭（保留 `.env` 优先边界）

- 启动期校验在 `GatewayServer.__init__`：`create_session()` 解析生效主体后调用 `repository.principal()`；不存在 → `AgentConfigError`（`server.py:225-234`）。
- 独立验证：
  - 临时档案 `principal_missing`，`environ={}` → `AgentConfigError`；
  - 干净环境 CLI → **exit 2**；
  - `DEMO_PRINCIPAL_ID=principal_missing`，CLI → **exit 2**；
  - 新增测试覆盖了档案/环境两种来源的启动异常（但只测 `load_gateway()`，未直接断言 CLI；我用 CLI 独立补测）。
- **边界**：若档案主体不存在但启动环境/.env 里有一个有效 `DEMO_PRINCIPAL_ID`，服务会以环境主体正常启动（我实测 exit 0）；此时“档案主体不存在”被有效环境主体掩盖。这与 §4 的 `.env` 优先是同一配置优先级问题；按“生效主体必须存在”的口径，P3-4 关闭；按“档案本身必须存在”的严格口径，它只是部分关闭。报告按前者判基本关闭，并把严格口径留给 P3 边界。

### P3-5 关闭（有覆盖边界）

- 新增 8 个测试（49 - 41），确实覆盖：
  - `document.search` 真实注册表跨项目拒绝 + 本项目真实证据；
  - 未知工具名不执行；
  - 大小写/嵌套保留键；
  - CLI 启动失败 stdout 为空；
  - 未知主体启动失败；
  - 启动身份主体/来源；
  - 保留键拒绝日志；
  - 会话历史上限。
- `test_document_search...` 使用 `load_gateway("local_dev")`，不是旧 `_registry()` 的 `DocumentSearchTool(KnowledgeService())` 占位；我确认 `DocumentSearchTool` 在该测试中带 `library=真实 KnowledgeLibrary`，且有真实 PDF 索引。
- 我读过新增断言：没有恒真空断言；`test_session_history` 的 3/5 上限、`test_cli...` 的 stdout 空串、`test_unknown...` 的 `invoked==[]` 都有实际判别力。
- 覆盖边界：新增测试没有直接覆盖 `document.search` 的 `include_project_documents`/`include_drafts` 组合（我的独立反例覆盖且均为 denied），也没有直接测 CLI 未知主体的 exit code（我独立 CLI 补测为 2）；这些是 P3 覆盖细节，不改变本项关闭。

### P3-6 部分关闭

返修更新了：
- `docs/README.md` 033 行（659 tests、返修待确认）；
- 归档 §11、开发日志、问题日志、`backend/README`；
- `CURRENT_BASELINE` 首行、最新回归证据行、路线图首行/`下一步`。

但仍有旧口径：
- `docs/architecture/CURRENT_BASELINE.md:25`：可选扩展行仍写“MCP 的 stdio 第一版已按 Task 033 实施（已自检、待独立复查）”；
- `docs/architecture/CURRENT_BASELINE.md:39`：MCP 网关行仍写“已实施并自检，待独立复查；未推送”；
- `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md:58`：仍写“MCP 的 stdio 第一版已按 Task 033 实施（已自检、待独立复查）”。

这些与“返修已自检、待复查确认”不一致，容易误读；**P3-6 部分关闭**，建议统一三处措辞。`docs/README` 033 行和归档/开发日志/问题日志的提交状态已正确。

## 3. §4 新发现：`.env` 空值语义与身份覆盖

返修发现属实，我复核如下：

- `backend/app/env.py:68`：`if not override and env.get(key): continue`，空字符串 `""` 为假，因此 `.env` 会覆盖调用者显式设置的空值。
- `cli.py:1394-1398` 启动时 `load_project_env()` 读取仓库根/`backend/.env`；`stdio_probe.py` 给子进程设置 `DEMO_PRINCIPAL_ID=""`，仍被 `.env` 的 `principal_ops_xinghui` 覆盖，启动提示来源为 `env:DEMO_PRINCIPAL_ID`；当前 `.env` 的值与 `local_dev` 档案相同，所以没有实际项目切换。
- 我构造了边界：档案 `ghost` 的 `principal_id=principal_missing`、环境/.env 有有效 `principal_ops_xinghui` 时，CLI 实际 **exit 0** 并以环境主体启动；档案主体不存在没有被报告（`GatewayServer` 校验的是生效主体）。
- README 现在已写明 `.env` 会覆盖档案主体，Flowise 示例删掉了 `"DEMO_PRINCIPAL_ID": ""`，启动提示打印实际主体/来源；这几项足以让本地开发者看见真实身份。

**判断：P3，不是当前版本下的 P1/P2。** 理由：① 它没有 `tools/call` 参数路径，也不是“失败当成功”；② 当前 stdio 是明确禁止用于生产的开发模式，服务环境由启动者控制；③ 启动提示与 README 已把实际主体/来源公开，当前 `.env` 与档案一致，没有实际越权。  
**但若把“配置 MCP 服务环境/ `.env` 的外部方”视为不可信，或 Flowise 连接期望 `flowise` 档案而 `.env` 指向另一项目主体，则可以静默换项目，应升级为 P2，并让 `mcp-serve` 不读取 `.env` 的 `DEMO_PRINCIPAL_ID`（或要求显式 `--principal`/`MCP_IDENTITY_SOURCE=profile`）而不是只写文档。** 只写文档对当前本地开发够用，但不构成生产控制；这也解释了 P3-4 的“档案主体被有效环境主体掩盖”边界。

## 4. 回归与副作用

- 全量 659 tests OK（skipped=1）、49 MCP tests、70 契约、`check` exit 0；与返修自报一致。
- 离线 heldout A/B/C 各 32 题逐题 0 差异、汇总一致；P2-1 没有改变离线评测行为。
- **P2-1 有意改变** `document.search` 的越权目标语义（`ok+0` → `denied`），这是任务要求；其他 Agent/CLI 入口没有出现行为变化。`cli search` 直接走服务层，不受该工具层改动影响；`baselines`/`investigation_demo` 的 heldout 0 差异。
- 15 个改动文件无新增 CRLF/密钥；`library.py`/`knowledge_tools.py` 的工作区 CRLF 是 Prompt 说明的既有检出状态，索引为 LF，不是本次问题。
- 没有把 033 写成“已通过最终验收”；文档仍为“返修已自检，待复查确认”，除 P3-6 的旧口径外一致。
- 未调用付费接口；未 `pip install`；未提交/推送；工作区未被我修改。

## 5. 本轮限制

- 未在 Flowise 或 MCP Inspector 中实连；只使用官方 SDK stdio 客户端、内存客户端和 CLI。
- 未实现/验证 Streamable HTTP、OAuth、TLS、并发会话恢复；`.env` 与生产身份边界仅按代码/配置审读。
- heldout 使用现有离线 deterministic/基线套件，不是真实模型重复测量或人工量表。
- 变异测试在仓库外副本完成（复制 backend、fixture、PDF；运行 49 tests）；副本中 `library.py`/`knowledge_tools.py` 的换行状态可能随复制工具变化，但不影响测试结论。
- 本报告只确认 Task 033 返修范围，不重做整轮复查，也不声称最终验收通过。
