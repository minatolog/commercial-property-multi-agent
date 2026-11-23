# Task 031 返修（R1–R4）独立复查

- **复查日期**：2026-11-21（Asia/Shanghai）。
- **复查者**：DeepSeek（与实施者 Claude Code 不同的模型；本次复查只读，不修改源码/测试/评测资产）。
- **复查依据**：[Task 031 独立复查（含末尾“返修结果”）](2026-11-21_task031_acceptance_review.md)、[交接给 Claude Code](../handoffs/CLAUDE_CODE_HANDOFF_2026-11-21.md) 第 2、3 节、[Task 031 归档第 10 节](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)。
- **复查代码基线**：`HEAD 3be785e`（“任务重构”，作者 minatolog，2026-11-21 20:48），工作区干净；`main` 与 `origin/main` 同为 `3be785e`。**注意**：返修文档写于该提交之前，其中“改动仍未提交”等表述已与仓库现状不符；本复查以实际提交内容为准。该提交同时包含 Task 031 原实施、R1–R4 返修、证据目录，以及用户侧的 `tools/flowise/`（5 个文件，其中 `package-lock.json` 42,988 行）与 `.gitignore` 的 Flowise 三行——这些不属于返修范围，复查时未做改动。
- **环境**：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18）；`langchain-core 1.7.6`、`langchain-openai 1.7.4`；命令均在 `backend/` 下执行，设置 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`。
- **复查方式**：不采信自报数字。独立运行全量回归、契约自检、`check` / `ask` / `investigate --model-provider scripted`、离线 heldout 评测；对 R1 自建双领域反例与控制场景；对 R2 用伪造的 ChatOpenAI 响应验证“真实解析链”，再走 B/C 评测与 `ask` 摘要；对 R3 检查提交 blob 换行、`.gitattributes`、写文件代码与生成报告字节；对 R4 自建 CLI dry-run 字节一致性与“台账不存在不创建”用例。**未调用任何付费模型接口。**

## 结论

**有条件通过。**

R1–R4 的实现、测试与交接第 3 节列出的完成标准经独立复跑成立：未发现 P1/P2 问题，返修订正了原复查的 R1/R2 缺陷，R3 已满足提交前要求（且已随用户提交证明），R4 达到交接主方案要求。剩余 3 项均为 **P3**：当前状态文档与仓库现状不一致、R1 的一个字面范围外残余边界、R4 的一个并发说明缺口。条件见文末；不要求重做实现。

## 1. 独立验证的实际结果

| 验证项 | 我实际运行的结果 | 与自报/基线对比 |
|---|---|---|
| 全量回归 | `Ran 551 tests in 32.948s`，`OK (skipped=1)` | 自报 551；返修前 529 → **一致** |
| 新增测试拆分 | `test_task031_z2_evidence` 25（原 17，+8）；`test_task031_r2_served_model` 9；`test_task031_r3_r4` 5 → 合计 +22 | 529+22=551，**一致** |
| 契约自检 | `python tests/smoke_agent_contracts.py` → `全部通过：70 项检查` | 自报 70，**一致** |
| `python -m app.cli check` | exit 0；5 个 Agent 的 `models` 各 7 键；`retrieval_settings` 仅 `enabled/top_k` | **一致** |
| `ask "A-301 现在还有多少钱没交？"` | exit 0；`status=success`；`target.source=question_parse`；`domain_coverage={asked:[billing],covered:[billing],missing:[]}`；可信金额 52596.00/34560.00/18036.00；`served_models=[]`、`served_model_mismatch=null`（scripted 无响应元数据） | **一致** |
| `investigate --model-provider scripted` | exit 0；`verdict=conflicting`、`route=fanout`；`agent_models` 4 个 Agent；`authoritative_amounts` 非空；`routing_reason` 3 条 | **一致** |
| R5 边界（未改项） | `ask "免租期一般怎么约定？"` → exit 2 | 与“用户决定保持现状”一致 |
| 离线 heldout 重跑 | 写入仓库外临时目录：A 20/30（0.6667）、B 21/30（0.7）、C 24/30（0.8）；正确率 0.7267/0.7756/0.8822；路由命中 24/32、0/32、27/32；`models_by_agent={}`；用例 SHA `cf22fd46…`、fixture `bcff5ce9…`、`scoring-v3.3` 均未变 | 与 `20261121T093757_*` 及 `20261121T085431_*` 逐题对比：**0 行差异**（忽略延迟）；通过数与自报一致 |

未发现测试被削弱或跳过增加：`skipped=1` 与返修前相同（既有“本机已配置密钥跳过缺密钥用例”）；原有 Z1/Z2/Z3/CLI 断言全部保留通过。

## 2. 逐项对照 R1–R4

### R1 部分取证不能判成功（重点反例）——**通过（满足交接文字要求）**

交接 §2-R1 的四项“要做的”逐条核对：

| 要求 | 核对结果 |
|---|---|
| 有失败调用 + 问题涉及的某领域无事实 → PARTIAL，warnings 写明领域；领域判定复用 `matched_domains` 与现有工具/事实映射 | **实现并验证**：`evidence.domain_coverage` / `missing_domain_outcome`；Single 路径接入；输出含 `domain_coverage`。我的反例 A 实测 `status=partial`、`missing=[billing]`、warning 含“部分取证：问题涉及的领域 billing（账单/费用） 没有取得任何事实”。 |
| 检查 LLM 领域 Agent 路径；不改则写明理由 | **满足**：未改 LLM 领域 Agent；归档 §10.2 写明理由（领域 Agent 只负责一个 capability，跨领域缺失由 Coordinator 汇总，避免 lease 子任务被 billing 问题错误降级）；测试 `test_llm_domain_agent_judges_only_its_capability` 固定该行为。我的场景 F（问题含 lease 词、billing 子任务成功）实测 `status=success`，符合设计。 |
| 原用例收紧为只接受 PARTIAL；补“两领域都成功 → SUCCESS”；补“只问一个领域、该领域失败、无关工具成功”的用例并说明状态 | **满足**：`test_failed_call_does_not_enter_facts_when_another_call_succeeds` 现断言 `TaskStatus.PARTIAL` 且断言 `domain_coverage`、`facts` 不含失败工具、warnings 含 billing；新增 `test_two_domains_both_succeed_is_success`、`test_two_domains_failure_then_correction_is_success`、`test_only_asked_domain_failed_unrelated_tool_succeeded_is_failure`、`test_unrelated_extra_tool_without_failures_is_unchanged` 及 3 个领域归属/零结果 helper 用例。 |
| PARTIAL 在 CLI 退出码、评测评分、API 展示中含义一致；评测变化逐题记录 | **基本一致**：CLI 中 `status=partial`、exit 0（与 Task 031 退出码约定“有明确警告的部分完成算成功”一致）；B 评测路径实测 `status=ok` 且 `errors` 记录“部分取证”警告、按既有事实评分；离线 heldout 逐题与其他报告**完全一致**（R1 不进入确定性路径）。真实模型 B 基线未重跑（归档已列为遗留）。 |

**我的独立反例（全部经真实 `app.cli.main` 的装配/Runtime/摘要路径，仅替换模型响应）**：

| 场景 | 构造 | 实际结果 |
|---|---|---|
| A（R1 原始问题） | “A-301 租期和欠款？”；lease.lookup 成功 + billing.statement.read 参数非法失败 | exit 0；`status=partial`；`domain_coverage.asked=[lease,billing]`、`covered=[lease]`、`missing=[billing]`；warnings 1 条“部分取证：……billing（账单/费用）”；`failed_tool_calls` 1 条；evidence 8 条（仅 lease） |
| B（对照） | 同上，两领域都成功 | exit 0；`status=success`；`missing=[]`；warnings 空 |
| C（反向对照） | 只问欠款；billing 失败、无关 property 成功 | exit 1；`status=failed`、`error=insufficient_evidence`；`asked=[billing]`、`missing=[billing]`；错误信息“其他领域的事实回答不了这个问题” |
| D（失败后纠正） | billing 先参数非法、随后纠正成功（另查了 property） | exit 0；`status=success`；`missing=[]`；`failed_tool_calls` 仍保留 1 条审计 |
| E（无失败调用） | 只问欠款；billing 成功 + 多余 property 成功 | exit 0；`status=success`；`missing=[]`（R1 不误伤） |
| F（LLM 路径） | billing 领域 Agent，问题含“租期”“欠款” | `status=success`；只按 billing capability 判定（符合归档理由） |
| **G（P3 残余）** | 双领域问题，模型只查 lease，**无失败调用** | **exit 0；`status=success`；`missing=[billing]`；warnings 为空**（详见发现 P3-2） |
| **H（P3 残余）** | 只问 billing，模型只查 lease，**无失败调用** | **exit 0；`status=success`；`missing=[billing]`；warnings 为空**（同一残余） |

另测“执行成功但输出越界（rejected_outputs）”场景：status 仍为 `partial`（因为越界原因进入 warnings），但没有“缺哪个领域”的专门告警；不构成 false success，仅提示文案不同。

### R2 报告区分配置名与实际应答模型——**通过**

交接 §2-R2 的四项：

1. **`ModelTurn.served_model` 读取 `response_metadata`**：已实现（`_to_model_turn` 读 `model_name`，回退 `model`）。我另用本机安装的 `langchain-openai 1.7.4` + 伪造 HTTP 客户端走**真实 `ainvoke` 路径**验证：服务端返回 `model="served-model-x"` 时 `AIMessage.response_metadata["model_name"]='served-model-x'`；响应不带 `model` 时被回填为配置名——与归档 10.3 的说明一致。
2. **汇总到 Agent 输出和评测 `models_by_agent`，配置名/实际名并列、不一致标注、多个去重、未记录为 `None`**：端到端验证（伪造 `LangChainChatModelClient`，不联网）：
   - B 基线报告：`bindings.models_by_agent.single = {model_name: "deepseek-chat", served_models: ["deepseek-v4-flash-1017"], served_model_mismatch: true}`；`bindings.model.note` 明写“model_name 为配置名”；Markdown 表出现“实际应答模型”列与 `⚠ deepseek-v4-flash-1017（与配置名不一致）`。
   - C 基线报告：billing/lease/property 三个 Agent 均带 `served_models` 且 mismatch=true；未参与 C 的 `single` 为 `served_models=[]`、mismatch=`null`（未记录 ≠ 一致）。
   - `ask` 默认摘要：同时输出 `served_models` 与 `served_model_mismatch=True`，配置名仍在 `model`/`model_name`。
   - 一致名、未记录、跨题合并的回归在 `test_task031_r2_served_model.py`（9 项，全部伪造响应，**无付费调用**）。
3. **测试不调用付费接口**：9 项测试 + 我的验证均为伪造响应；未发现网络调用。
4. **文档更正与历史报告不动**：归档 §6.6 / §7 已由“真实调用会失败”改为“官方公告已下线；11-06 实测以该名字仍可调用，实际应答模型当时未记录，历史报告中的 model_name 是配置名”；`CURRENT_BASELINE.md` 真实模型行注明“历史报告中的模型名为配置名”；`git diff e3b3594 3be785e -- docs/evaluation/reports/real_model_dev docs/evaluation/reports/real_model_v2` 为空（历史报告未改）。

**遗留限制（归档已写明，属可接受）**：服务端不返回 `model` 时 langchain-openai 用配置名回填，无法区分“服务端确认一致”与“未返回”；需原始响应体才能彻底区分，本轮未做。历史真实调用的实际应答模型已不可追溯。

### R3 换行符——**通过（提交前要求已满足，且已被提交证明）**

交接 §2-R3 五项的独立核对（针对实际提交 `e3b3594..3be785e`）：

| 要求 | 核对结果 |
|---|---|
| 新增 `.gitattributes`（`* text=auto eol=lf`，二进制声明） | 存在且内容正确（`*.bat/*.cmd` CRLF；pdf/png/jpg/gif/ico/webp/sqlite/sqlite3/db/zip/xlsx/docx/pptx/woff/woff2 为 `binary`） |
| 本轮改动/新增文本文件统一 LF，不碰二进制与 `tools/flowise` | 提交内 **112 个改动文件的所有 blob 均不含 CR**；`git ls-files --eol` 的索引侧 `i/crlf = 0`（325 个 `i/lf`、16 个空文件 `i/none`、20 个 `i/-text` 二进制判定） |
| 两处 `write_text` 加 `newline="\n"` | `runner.write_report` 与 `cli` summary 均已加；全仓库 `app/` 内仅这两处 `write_text` |
| `git diff --stat` 与 `--ignore-cr-at-eol` 一致；`.gitignore` 只有 Flowise 三行 | 两种统计**完全相同**（112 files changed, 84,657 insertions(+), 392 deletions(-)）；`.gitignore` diff 仅 +3 行 Flowise。说明：84,657 行中的大部分是用户提交的 `tools/flowise/package-lock.json`（42,988 行）与评测/证据 JSON，不是返修代码 |
| 转换会改变评测报告字节（无哈希引用） | 我新生成离线 heldout 报告（4 个文件）**全部为 LF**，`\r` 不存在；返修后提交的 `20261121T093757_*` 亦为 LF |

**边界说明（已在归档记录，非缺陷）**：本机 `core.autocrlf=true` 为系统级配置，**未改动的**已跟踪文件在工作区仍可能按 CRLF 检出（`git ls-files --eol` 显示 145 个 `w/crlf`），但索引与提交内容为 LF，`git status` 干净、不影响 diff；`.gitattributes` 生效后重新检出即为 LF。原“未提交状态”的 `git diff` 已无法复现（用户已提交），但提交 blob 检查是更强的证据。

### R4 dry-run 副本改用 SQLite 备份接口——**通过**

交接 §2-R4 的三项：

1. **改用 `sqlite3` `Connection.backup()`，两个连接显式关闭，不再复制 `-shm`**：代码已确认（源连接 `PRAGMA query_only=ON`，`destination`/`source` 均在 `finally` 关闭；无 `shutil.copy2`、无 `-shm` 复制）。
2. **保留“台账不存在时报错且不创建”**：我独立经 CLI 验证——台账不存在时 `approve --dry-run` exit 3、`error_code=approval_ledger_missing`、目录未创建。
3. **补测试：预演后原台账逐字节不变，且预演结果与真实执行一致**：`test_task031_r3_r4` 5 项通过（含主库/`-wal`/`-shm` SHA-256 不变、预演与真实 `decide()` 逐字段一致、WAL 中未 checkpoint 的提交可见、规则仍生效、缺失台账不创建）；我另用真实 CLI 流程复核：dry-run 前后控目录内**所有文件字节不变**、台账决定数 0；随后真实 approve 写入 1 条决定（`pending_next_stage`）。

**边界（P3 观察）**：交接允许“补并发用例或文档注明限制”；现有测试覆盖了“另一连接保持打开、提交仍在 WAL”的一致性，归档也注明了“崩溃残留 WAL”的边界，但 **backup 执行期间另一进程并发写入** 的行为（SQLite backup 可能重启/返回忙）没有单独用例或文字说明。单机演示规模风险很低。

## 3. 交接第 3 节“完成标准”核对

| # | 完成标准 | 状态 |
|---|---|---|
| 1 | 全量回归与契约通过，记录实际数字，与返修前对比并说明新增测试 | **满足**：551 / 70；+22=8+9+5；我独立复跑一致 |
| 2 | `check` exit 0；`ask`、`investigate --model-provider scripted` 正常 | **满足**：三者 exit 0，输出关键字段正常 |
| 3 | 离线评测重跑并与 `20261121T085431_*` 逐题对比 | **满足**：我独立重跑并与 085431、093757 对比，逐题 0 差异；A20/B21/C24 |
| 4 | R3 验收条件全部满足 | **满足**：提交内无 CR blob、统计一致、`.gitignore` 仅 Flowise、生成报告 LF |
| 5 | 归档：031 归档追加返修节、更新开发日志/问题日志/`CURRENT_BASELINE`；复查报告追加“返修结果”；正文和状态表一致 | **部分满足**：交接点名的 4 处已更新且相互一致（`CURRENT_BASELINE` 已写 551 与返修）；但其它**当前状态**文档未同步（见 P3-1） |
| 6 | 汇报每项“做了什么/证据/遗留”；不声称最终验收通过 | **满足**：返修结果表齐全，明确“实施自检、不是复查结论” |

## 4. 发现（分级）

**P1：无。**
**P2：无。**

### P3-1 当前状态文档未同步（返修后数字与仓库现状不一致）

- `CURRENT_BASELINE.md` 已更新为“551 tests / 返修 R1–R4”，但下列文档仍写 529/未提交：
  - 根 `README.md`：第 42 行（“529 项”）、281、286、322、352 行（529），且未提返修 R1–R4；
  - `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`：第 11、38 行（529，无返修说明）；
  - `docs/README.md`：第 107 行 031 索引（“529 tests … 未提交”）；
  - `docs/checkpoints/git_history.md`：第 7–14 行仍是 Task 031 `Pending` + 529，没有返修/提交记录；
  - `docs/issues/issue_log.md` 第 9 行、031 归档第 469 行、复查报告“整体回归”段仍写“未提交”（实际 HEAD `3be785e` 已在 `origin/main`）。
- 影响：项目自身规则要求“正文和状态表一致”；当前入口（`CURRENT_BASELINE`）与进度表/索引/检查点对同一状态的描述不同。属文档一致性 P3，不涉及实现。
- 建议（条件 C1）：关闭 Task 031 前统一为“551 tests / R1–R4 已返修待复查 / HEAD 3be785e 已提交（如确为推送，也如实记录）”；检查点补提交记录。

### P3-2 R1 字面范围外的残余边界：模型漏查已问领域且无失败调用时仍判成功

- 复现（场景 G/H）：问题“A-301 租期和欠款？”或“A-301 还欠多少？”，模型只调用成功的 `lease.lookup`，**没有任何失败调用**；结果是 `exit 0 / status=success / warnings=[]`，但输出中 `domain_coverage.missing` 已显示缺少 `billing`。
- 原因：`missing_domain_outcome` 按交接要求只在 `failed_tool_calls` 非空时介入；这是有意的防误报设计（无失败时可能只是模型选择少查）。
- 定性：**不属于本次交接 R1 的验收范围**（交接文字明确以“存在失败调用”为前提），且不是回归；但它与 R1 同属“问的没答全却判成功”的用户可见问题，且新字段 `domain_coverage` 已暴露该缺口却未联动状态/warnings。
- 建议（条件 C2）：在归档/问题日志中明确记录为“已知残余（不在本次范围）”，或后续任务评估“无失败调用时也按 missing 领域告警/降级”（需同时防止词表误命中造成的 false partial）。

### P3-3 R4 并发写备份边界未单独说明

- 现状：实现与测试达到交接主方案；WAL 未 checkpoint 的一致性已有用例；崩溃残留 WAL 边界已记录。但“backup 期间另一进程持续写入”的行为没有用例或文字边界说明。
- 建议（条件 C3，可并入文档）：在归档 §10.4 补一句并发写期间的预期（SQLite backup 的一致性/重试与可能的 `database is locked`），或补一个并发写用例。

### 其他观察（不计问题）

1. **R2 限制已被如实记录**：服务端不返回 `model` 时无法与“一致”区分；历史报告实际应答模型不可追溯——与实施自述一致，不构成缺陷。
2. **C 基线报告列出未使用的 `single` Agent 行**（`served_models=[]`、“未记录”）：这是 Task 031 起 `agent_models` 覆盖全部 LLM 实现配置的既有行为，非本次返修引入；真实模型 C 报告会看到一行未参与运行的 `single`，可读性可改进。
3. **`investigate` 默认摘要不展示逐 Agent 实际应答模型**：R2 要求的是“Agent 输出和评测报告”，两者均满足；CLI investigate 的 `agent_models` 是装配期静态条目。若希望命令行也能看到 served 信息，可另立小改动（非本次范围）。
4. **跨领域“部分取证”与既有 warnings 的关系**：rejected_outputs（执行成功但越界）不触发 R1 的“缺领域”专门告警，但仍因越界原因进入 warnings → 状态为 PARTIAL，不会 false success。
5. **仓库状态变化**：`3be785e` 同时提交了用户侧 `tools/flowise`（含 42,988 行 `package-lock.json`）与 Flowise 三行 `.gitignore`，超出 Task 031/返修范围；返修文档中的“未提交/不推送”已过时。发布/回滚时需知悉该提交范围。

## 5. 结论与条件

**有条件通过**：R1–R4 的代码、测试与交接第 3 节中与实现相关的完成标准均经独立复核成立，无 P1/P2；可在满足以下 P3 条件后关闭 Task 031（均不要求改代码逻辑）：

- **C1（必须，P3）**：同步“当前状态”文档——根 `README.md`、路线图、`docs/README.md` 031 索引、`docs/checkpoints/git_history.md` 更新为 551 tests / 返修 R1–R4 / 实际提交 `3be785e`；修正各文档“未提交”的过时表述，保持正文与状态表一致。
- **C2（必须，P3）**：对 R1 残余（无失败调用但漏查已问领域 → success）给出书面结论：记入“已知残余/后续任务”或另立修复；不得默认“R1 已完全覆盖”。
- **C3（建议，P3）**：在归档 §10.4 补一句 backup 期间并发写的边界，或补一条并发用例。

满足 C1/C2 后，建议关闭 Task 031，再按用户安排启动 Task 032；R5（`ask` 有业务词无目标即拒绝的保守边界）用户已决定保持现状，本次复查确认实现与决定一致。

## 6. 复查边界（未做/未采信）

- **未调用付费模型**；`DEEPSEEK_API_KEY` 存在于本机但未发起任何真实请求；R2 仅用伪造响应验证真实解析链。
- **真实模型 B/C 基线未重跑**（需要付费调用且超出本次授权）；R1 对真实模型 B 的影响、R2 的 served 字段在真实 DeepSeek 响应中的表现，均以“伪造响应 + 代码路径”验证，未以真实调用背书。归档已把“真实模型 B 基线没有重跑”列为遗留。
- 未修改源码、测试、评测用例、评分规则、历史报告与归档；仅新增本报告文件。未提交、未推送。
- 我的临时脚本与评测输出均在仓库外（`D:\task031_review_*`）；复查结束时除本报告外工作区保持干净（`git status` 仅本文件未跟踪）。
