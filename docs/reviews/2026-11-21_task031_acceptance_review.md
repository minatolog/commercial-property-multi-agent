# Task 031 独立复查（Claude，2026-11-21）

- 复查对象：工作区未提交改动（HEAD `e3b3594` 之上），DeepSeek 实施归档 `docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md`。
- 复查方式：逐文件阅读代码与测试 diff，核对归档中的说法；**本次复查环境无法运行项目测试**（无 Python 3.11 与项目依赖），测试通过数（529 / 70）采信实施方在 `commercial-agent` 环境中的输出，未独立复跑。
- 结论：**有条件通过**。主体工作扎实、诚实，无"为通过而削弱测试"的情况；R1、R2 修复后可关闭，R3 必须在提交前处理。

## 已核实通过的项

| 项 | 核实内容 |
|---|---|
| 既有测试修改 | 只有 3 处既有断言被改：未命中领域由"走 billing"改为"回问"（行为本就要求改变）；模型名由硬编码改为读配置；删除已移除字段的 schema 用例。未发现降低标准 |
| Z1 | `resolve_ask_target` 对 `--lease` / `--unit` / 问题中解析出的铺位号，均按主体 `project_ids` 经只读仓库校验；冲突与无法解析均报用法错误 |
| Z2 | `partition_tool_executions` 同时要求"执行成功"与"输出属于本次目标"；失败与越界调用只进审计；Single 与 LLM 两条路径共用；合法零结果有专门用例 |
| Z3 | `ask` / `investigate` 默认摘要分栏展示可信资金结论与模型叙述，写反金额时 `mismatch` 可见 |
| 模型配置 | 逐 Agent 按 YAML 构造客户端；缓存键覆盖实际传给 `ChatOpenAI` 的全部参数（base_url 按 provider 固定）；非法配置启动期失败 |
| 配置真实性 | `RetrievalSettings` 删除未实现字段并 `extra="forbid"` |
| `approve --dry-run` | 在临时副本上执行真实 `decide()`，原台账不写；连接显式关闭，Windows 下临时目录可清理 |
| 路由兜底与词表 | 新增 14 词中有 8 道 heldout 题包含新增词，但这些词来自 Task 013 既有 `_ARREARS_HINTS`；改动前这些题本就默认落 billing，A/B 结果完全不变，C 仅 H27 由失败变通过且理由成立（该题期望明确失败）。未发现为分数调词 |
| 评测资产 | `docs/evaluation/cases/`、评分规则、历史报告均未修改 |
| 文档一致性 | README、`CURRENT_BASELINE.md`、路线图均标注"待独立复查"，数字与归档一致，没有夸大 |

## 发现

### R1 [P2] 部分取证仍判成功

`minimum_evidence_reason` 只检查 `facts` 是否非空。问题同时问两件事（如"A-301 租期和欠款？"），账单工具失败、合同工具成功时，结果为 `SUCCESS`：用户问的欠款没有取到，状态却是成功。对应用例 `test_failed_call_does_not_enter_facts_when_another_call_succeeds` 断言 `status in {SUCCESS, PARTIAL}`，允许了这种情况。

修复要求：存在失败调用、且问题涉及的某个领域没有取得任何事实时，状态应为 `PARTIAL`，并在 warnings 中写明缺了哪个领域；把该用例收紧为只接受 `PARTIAL`，并补"两个领域都成功 → SUCCESS"的对照用例。

### R2 [P2] 报告中的模型名是配置名，不是服务端实际使用的模型

归档写"`deepseek-chat` 已于 2026-07-24 下线，真实调用会失败"（DeepSeek 官方公告确有此日期，下线前路由到 `deepseek-v4-flash`）。但本项目 2026-11-06 的 4 份真实模型报告均以 `deepseek-chat` 调用成功并消耗真实 token，与"会失败"矛盾。说明报告里的 `model_name` 只是配置值，服务端实际由哪个模型应答并未记录，历史真实模型结果的模型归属不精确。

修复要求：
1. 真实调用时从响应元数据中读取服务端返回的模型标识（LangChain 响应的 `response_metadata`），与配置名一起写入报告和 `models_by_agent`；两者不一致时标注。
2. 修正归档中"真实调用会失败"的表述，改为"官方公告已下线，但 11-06 实测仍可调用，实际应答模型未记录"。
3. 在 `CURRENT_BASELINE.md` 的真实模型证据一行注明：历史报告的模型名为配置名。
不需要为此调用付费接口；用 scripted 或 mock 响应测试字段读取即可。

### R3 [P3，提交前必须处理] 27 个文件的换行符由 LF 改成了 CRLF

包括 `.gitignore`（Prompt 要求不动）、`README.md`、多个核心源码与测试、开发日志等。按原始 diff 统计为 15,286 行新增 / 12,976 行删除，忽略换行符后实际只有 2,697 / 387，复查和 `git blame` 都会被噪音淹没。仓库没有 `.gitattributes`。

修复要求：新增 `.gitattributes`（`* text=auto eol=lf`，二进制文件除外），把本轮改动的文件统一恢复为 LF，确认 `git diff --stat` 与 `--ignore-cr-at-eol` 的结果一致后再提交。`.gitignore` 的内容改动（Flowise 三行）是用户原有的，保留。

### R4 [P3] dry-run 副本用文件拷贝，不是一致性快照

`_copy_for_preview` 依次拷贝主库、`-wal`、`-shm`。并发写入时三者可能不一致，`-shm` 也不应拷贝。单机演示规模风险很低，建议改用 `sqlite3.Connection.backup()` 生成副本，并补一个"预演期间另一进程写入"的用例或在文档注明限制。

### R5 [产品决定，需用户确认] `ask` 的保守边界

问题命中业务词但没有目标时直接报用法错误（如"免租期一般怎么约定？"），实施方已在归档中提出。是否增加 `--explain` 或政策类问题的判定，由用户决定。另外，回问（`needs_clarification`）的运行在 API 中仍记为 `completed`，Task 032 的界面需要专门展示"需要补充信息"，不能显示成完成。

## 下一步

1. 让 DeepSeek 修复 R1、R2、R3（R4 可选），只改这些点，修完重跑全量回归并更新归档。
2. 用户确认 R5 的产品边界。
3. 返修复查通过后再开始 Task 032。

## 返修结果（Claude Code，2026-11-21）

返修由 Claude Code 在本机 `commercial-agent` 环境（Python 3.11.18）完成。这是**实施方自检，不是复查结论**；实施和复查应由不同的人做，请 DeepSeek 或 Codex 独立复查后再关闭。详细说明见 [Task 031 归档第 10 节](../prompts/06_testing/2026-11-21_031_core_correctness_fixes.md)，证据见 `task031_evidence/repair/`。

返修前复跑：529 tests OK（skipped=1）、70 项契约，与实施方自报一致（本复查当时没能复跑的数字，现已确认）。

| 编号 | 做了什么 | 证据 | 遗留 |
|---|---|---|---|
| R1 | Single 路径存在失败调用时，按问题涉及的领域（`matched_domains`）核对事实覆盖：部分缺失 → PARTIAL，warnings 写明缺哪个领域；全部缺失、只有无关领域的事实 → `insufficient_evidence`。LLM 领域 Agent 不改：它只负责一个 capability，按问题领域判缺失会错误降级 lease 子任务；跨领域缺失由 Coordinator 汇总 | 原用例收紧为只接受 PARTIAL；新增两领域都成功 / 先失败后纠正 / 只问一个领域且它失败 / 没有失败调用 / LLM 路径对照，以及领域归属单元测试，共 8 个 | 真实模型 B 基线没有重跑 |
| R2 | `ModelTurn.served_model` 从 `response_metadata` 读取；Agent 输出、评测 `models_by_agent`、Markdown 报告和 `ask` 摘要同时给出配置名和实际应答名，不一致时标注，未记录为 `None`；归档第 6.6 节与第 7 节、`CURRENT_BASELINE.md` 已更正，历史报告没有改 | `test_task031_r2_served_model.py`，9 个，全部用伪造响应，没有调用付费接口 | 服务端不返回 `model` 时，langchain-openai 会用配置名回填，无法区分 |
| R3 | 新增 `.gitattributes`；本轮文本文件全部转为 LF；两处 `write_text` 加 `newline="\n"` | `git diff --stat` 与 `--ignore-cr-at-eol` 完全一致（40 个原改动文件 +2697/−387 不变，含返修后为 42 个文件）；`.gitignore` 只有 Flowise 三行；报告写出不含 `\r` 有回归 | 未改动的已跟踪文件仍按 autocrlf 检出，不影响 diff |
| R4 | `_copy_for_preview` 改用 `sqlite3` 备份接口，源连接 `query_only`（`mode=ro` 会在台账目录遗留 `-wal`/`-shm`，实测后放弃），两个连接显式关闭，不再复制 `-shm` | 预演前后主库/`-wal`/`-shm` SHA-256 不变；WAL 中未 checkpoint 的提交可见；预演结果与真实 `decide()` 一致；台账不存在时不创建；原 CLI dry-run 用例通过 | 进程崩溃残留 WAL 且没有其他连接时，关闭会触发 checkpoint，主库字节会变（内容等价） |
| R5 | **没改**；用户 2026-11-21 决定**保持现状**：有业务词无目标继续按用法错误拒绝 | 用户在会话中的明确答复 | 不放宽；如以后需要政策类问答，另立任务 |

整体回归：551 tests OK（skipped=1，新增 22 个）、70 项契约；`check`、`ask "A-301 现在还有多少钱没交？"`、`investigate --model-provider scripted` 都是 exit 0；离线 heldout 重跑（`20261121T093757_*`）与 `20261121T085431_*` 逐题一致。改动未提交。
