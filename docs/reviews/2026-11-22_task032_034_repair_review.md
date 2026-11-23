# Task 032 / 034 返修确认复查

- **复查日期**：2026-11-23（Asia/Shanghai；文件名沿用用户指定的 `2026-11-22`）。
- **复查者**：DeepSeek（与实施者 Claude Code 不同的模型）。本轮**只读**，不修改源码、测试、评测题、评分规则、配置；不提交、不推送、不切分支、不 stash。
- **复查范围**：只确认上一轮 [Task 032 独立复查](2026-11-22_task032_independent_review.md) 与 [Task 034 独立复查](2026-11-22_task034_independent_review.md) 提出的问题是否关闭，以及返修有没有引入新问题；不重做整轮复查。
- **依据**：[返修确认 Prompt](../handoffs/REVIEW_TASK032_034_REPAIR_PROMPT.md)、上一轮两份复查报告、[032 归档 §10](../prompts/05_frontend/2026-11-22_032_business_workbench_ui.md)、[034 归档 §13](../prompts/04_agents/2026-11-22_034_llm_supervisor_planner.md)、[ADR-006](../decisions/ADR-006-hybrid-planner.md)、实际代码/测试/截图。
- **基线与清单**：当前 `HEAD = 129c26b31f77a2fff92e7ef35e9ba52ab0f67723`（用户新增的 `scripts/dev_loop/` 及 `.gitignore` 两行，按 Prompt 不在本次范围）；Task 032/034 改动仍未提交。`review_repair_2026-11-22_manifest.txt` 声明 44 个文件；正文重算 SHA-256 = `3689caad8c2c9a259012eb96beb702343dcf335b1cb2f7f0dbba727026b6c257`，与清单第 4 行一致；逐文件核对 44 个“返修后哈希”：**0 DIFF、0 MISSING**；反向检查上一轮 manifest：**0 UNLISTED**。清单头部写的基准 HEAD 是 `3be785e`，当前 HEAD 多了用户的 dev_loop 提交，不影响本次文件级核对。
- **环境**：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18）；`backend/` 下执行，`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；临时产物全部写到仓库外（`D:\review*_out`、`D:\repair_test_backend`）。
- **方式**：不采信自报数字。独立复跑全量回归/契约/`check`/JS 回归；离线跑 planner 套件与 heldout；用自建浏览器探针重做 P2-1、P2-2、P3-1、P3-2 的反例；在仓库外副本删掉一条错误码映射，验证同步测试真的会失败；逐张查看重截的 08b 与关键首屏；检查 44 个文件的换行、密钥、绝对路径；核对真实报告哈希未被改写；核对 docs 的关键数字与状态措辞。**未调用任何真实 DeepSeek 接口。**

## 结论

**上一轮两个任务的 P2 条件全部关闭；未发现新 P1/P2。** Task 032 的 P2-1、P2-2 与 6 项 P3 均关闭；Task 034 的 P2-1、P3-2、P3-3、P3-4、P3-5 关闭，P3-1 **部分关闭**（归档已改，但 ADR-006 §5a 仍保留“丢分全部来自规则直通”的旧说法）。本轮另发现 **2 项新 P3**：错误码本地化规则过宽（可能误改非错误文本）；状态文档（ADR / `CURRENT_BASELINE` / 路线图）的旧状态与旧归因残留。未发现新 P1/P2。

两个任务可以视为“上一轮有条件通过的条件已满足”，但**不等于最终验收通过**：正式真实 heldout 对照/重复测量、人工量表、PostgreSQL 实机仍是开放项；034 的真实实际应答模型证据在当前约束下仍不可回溯（归档已如实改为“未记录、不可复核”）。

| 任务 | 条件 | 状态 |
|---|---|---|
| 032 | P2-1 摘要英文错误码 | **关闭** |
| 032 | P2-2 failures 缺失默认 0 | **关闭** |
| 032 | P3-1 未映射错误码 | **关闭**（新 P3-1 为过宽替换边界） |
| 032 | P3-2 completed+conflicting 绿色徽标 | **关闭**（空 verdict 残余边界见 P3-3） |
| 032 | P3-3 no-cache 登记 | **关闭**（已登记披露，仍属范围外偏差） |
| 032 | P3-4 5 秒表/六项清单 | **关闭**（英文扫描与 5 秒表复核；滚动/控制台为自报） |
| 032 | P3-5 X-Actor 措辞 | **关闭** |
| 032 | P3-6 CRLF | **关闭** |
| 034 | P2-1 planner_model / served 证据 | **关闭**（字段、汇总、测试、文档；真实 served 证据仍不可回溯） |
| 034 | P3-1 hybrid 丢分归因 | **部分关闭**（归档已改，ADR §5a 仍残留） |
| 034 | P3-2 code_commit 标识 | **关闭** |
| 034 | P3-3 冻结先后证据 | **关闭**（如实记录边界） |
| 034 | P3-4 planning 键形状 | **关闭** |
| 034 | P3-5 planner-provider 优先级 | **关闭** |

## 1. 独立验证的实际结果

| 验证项 | 我实际运行/看到的结果 | 与自报对比 |
|---|---|---|
| 返修清单 | 44 个文件正文 SHA-256 与清单头一致；逐文件返修后哈希 0 DIFF；反向 0 UNLISTED | 与 Prompt 所述一致 |
| 全量回归 | `-m unittest discover -s tests -p 'test_*.py'` → `Ran 610 tests in 38.150s`，`OK (skipped=1)` | 自报 610，**一致**；比上轮 607 多 3 |
| 契约自检 | `python tests/smoke_agent_contracts.py` → `全部通过：70 项检查` | 一致 |
| `python -m app.cli check` | exit 0；planner 段仍为 `mode=rule`、`deepseek-flash` | 一致 |
| JS 回归 | 真实浏览器 harness：**48 用例 / 185 断言 / 0 失败**（46 fixture + 2 real） | 自报 48/185，**一致**；比上轮 45/163 多 3 用例/22 断言 |
| 新增测试拆分 | `test_task032_display.py` 12（原 11，+1）；`test_task034_integration.py` 22（原 20，+2）；合计 +3 | 与 607→610 相符 |
| 034 planner 套件离线 | v1：rule/llm/hybrid/multi_rule 13/30、13/30、13/30、13/30；调用 0/30/25/23；越权 0。v2：均为 36/66；调用 0/66/49/45；越权 0 | 与上一轮数字**完全一致**（返修只加字段） |
| 034 planner 套件新字段 | 有模型调用的行 **100%** 含 `planner_model`（`provider / model_name / served_models / served_model_mismatch`）；rule 行为 `None`；汇总新增 `served_models / served_model_mismatch_cases / served_model_unknown_cases`；scripted 运行时 served 为 `{}`、unknown 为有调用的题 | 与自报一致 |
| 034 heldout（rule） | A/B/C 各 32 行；与 `20261121T093757_*` 逐题对比（忽略延迟/新增 planning）**0 行差异**；C 行 `planning` 键集合含 `escalation_reason` 且三种模式一致；`bindings.code_worktree=dirty`；Markdown 有“工作区 dirty”字样 | 一致 |
| 034 真实报告 | 20 个 `docs/evaluation/reports/2026*` 文件哈希与上一轮旧 manifest **全部未变**；旧报告行仍没有 `planner_model` 字段（未被回写，符合“已有报告不改写”） | 一致 |
| 034 真实对照文档 | 034 归档 §7.5 已改为“实际应答模型未记录、不可复核”，并补 PX19/PX38 归因；`summary.md` 未改 | 归档侧一致 |
| 032 回归 | 真实 API 的复杂调查/预算失败/简单查询/回问/两级批准/驳回结果与上一轮一致；U3 参数化反例的 verify/report/summary/card 状态一致；跨项目仍 404、display 不落库、MIME/304/路径穿越正常 | 一致 |
| 032 P2-1 反例 | 临时服务 `max_tool_calls=1` 的预算耗尽运行：摘要页签“系统提醒”显示“条款检索不可用（**预算耗尽**）”，不再出现 `budget_exhausted`；重截的 `08b-budget-exhausted-summary.png` 可见 | **关闭** |
| 032 P2-2 反例 | 删除 `failures`、改成 `"invalid"`、删除/对象 `missing_information`：摘要“缺失与失败”计数显示“待核实”并说明哪个字段缺失；两个字段都是空数组时仍显示“0 / 没有缺口” | **关闭** |
| 032 P3-1 反例 | 前端 22 个后端 `ErrorCode` 全部有中文映射；未知码显示“其他错误（原始代码见技术视图）”；在仓库外副本删掉 `tool_timeout` 映射后 `TestErrorCodeLabelsInSync` **FAIL**，证明守护有效 | **关闭**（另见新 P3） |
| 032 P3-2 反例 | `runStatusMeta('completed', {verdict:'conflicting'})` → warning“已完成 · 存在冲突”；`insufficient`/未知非空 verdict 也是 warning；审批 `approved/rejected` 与回问仍优先；`supported` 保持绿色 | **关闭**；列表/Header 代码均传 `verdict` |
| 032 P3-5/P3-6 | `api.js` 头注释与页脚明写“演示模式审批人自选、未接登录认证”；`graph.js` 为 `i/lf w/lf`，`js_harness.json` 无 CR；44 个 manifest 文本文件均无 CRLF | **关闭** |
| 32 位/控制台 | 未独立重测 390 宽 `scrollWidth` 与真实页面控制台；自报清单中的 English scan 我用独立探针扫了 6 个真实运行的摘要/冲突/证据/审批/协作图/节点详情，**0 处英文枚举/内部 ID**；08b/01 截图目测无溢出 | 部分独立；未测项见 §6 |
| 测试弱化 | 无新增 skip；新测试无空断言/恒真断言；删除映射的阴性实验失败；旧 harness 用例全部保留 | 未发现弱化 |
| 换行/泄密 | 44 个文件中文本无 CRLF；无新密钥/绝对路径（`sk-investigation` 是 `task-investigation` 子串、`D:` 命中在历史 issue_log 的旧内容、`core@1.7.4` 是版本串）；临时文件都在仓库外 | 无新增问题 |

## 2. 逐条确认

### 2.1 Task 032

| 编号 | 上一轮问题 | 返修位置（读代码确认） | 我的独立验证与状态 |
|---|---|---|---|
| P2-1 | 摘要“系统提醒”显示 `budget_exhausted` | `i18n.js:163-167` 新增 `localizeErrorCodes`；`report.js:22-25` 的 `localizeStatement` 调用它；`describeMissingItem` 兜底（`i18n.js:191-192`）也改用它 | 真实预算耗尽运行摘要只显示“预算耗尽”，08b 截图可见；真实运行的英文扫描无错误码命中；JS 用例“复查 P2-1”渲染真实 `renderSummary`，不是只测 helper。**关闭** |
| P2-2 | `failures` 缺失/类型异常时摘要显示 0/没有缺口 | `report.js:158-170` 分别判断 `missing_information` 与 `failures`，无效时计数“待核实”并在正文说明字段；空数组基线仍显示 0 与“没有缺口” | 我用真实组件探针复现 4 种异常 + 基线，结果符合；JS 用例“复查 P2-2”覆盖同一组输入。**关闭** |
| P3-1 | 未映射错误码显示“未知状态（tool_timeout）” | `i18n.js:84-108` 补齐 22 个后端错误码；`term('errorCode', 未知值)` 返回“其他错误（原始代码见技术视图）”（`:149-157`） | `TestErrorCodeLabelsInSync` 比对后端 `ErrorCode`、i18n 映射与 JS 的 `BACKEND_ERROR_CODES`；仓库外删映射实验确实 FAIL。**关闭**；本地化规则过宽另见新 P3-1 |
| P3-2 | completed+conflicting 列表/Header 为绿色“已完成” | `view-model.js:97-100` 新增 `COMPLETED_WITH_ISSUE`；`:130-135` 对 conflicting/insufficient/未知非空 verdict 返回 warning；审批与回问分支仍在此之前 | JS 用例 5 条断言通过；`app.js:165-169`（Header）与 `:215-218`（列表）都传 `verdict`。**关闭**；空 verdict 残余边界见 §3 |
| P3-3 | no-cache 超出“只读展示元数据”范围 | 未改代码；032 归档 §10 第 121 行登记为“静态服务响应头改动”，说明只加头、不改路径解析 | 归档登记清楚，MIME/304/穿越实测未回归。**按“登记”要求关闭**（该偏差仍是 Prompt 范围外事项，保留披露） |
| P3-4 | 缺 5 秒逐条答案与六项自查清单；“英文残留已修”不实 | 032 归档 §7.1 补四问表格；§7.2 加注撤回旧说法；§10.1 补六项清单（7 案件 × 4 页签扫描、390 宽 35 视图、17 张重截等） | 5 秒表对照新 `01` 截图成立；我用独立浏览器探针扫 6 个真实运行的业务页签/节点，**0 英文枚举**；清单中的滚动宽度/控制台仍为实施者自报。**关闭（英文与 5 秒部分独立复核；其余为自报）** |
| P3-5 | 审批发 `X-Actor-Id` 与“不发送自报身份”字面矛盾 | `api.js:1-11` 新增“演示边界”段；`index.html:194-196` 页脚改写 | 措辞与行为一致：说明审批人从白名单自选、未接登录认证，生产需真实认证。**关闭** |
| P3-6 | `graph.js` / `js_harness.json` CRLF | 两者已转 LF；`graph.js` 的 `git diff --ignore-cr-at-eol` 仍只有上轮那 7 行新增/1 行删除，证明不是重写代码 | `git ls-files --eol` = `i/lf w/lf`；js_harness 无 CR；44 个 manifest 文本文件全部无 CRLF。**关闭** |

### 2.2 Task 034

| 编号 | 上一轮问题 | 返修位置（读代码确认） | 我的独立验证与状态 |
|---|---|---|---|
| P2-1 | 规划层评测逐题无 `planner_model`/`served_models`；真实对照声称实际应答一致却无证据 | `planner_suite.py:286` 逐题行加 `planner_model`；`:349-386` 汇总加 `served_models / served_model_mismatch_cases / served_model_unknown_cases`；`:422` Markdown 显示工作区；`test_task034_integration.py:407-449` 覆盖一致/不一致/未返回三种；归档 §7.5:318 改为“未记录、不可复核”；§13 记录返修 | 离线 llm 套件所有有调用的行均有 `planner_model`，汇总字段正确；新测试通过；4 份真实报告哈希与旧 manifest 全部一致、未被改写；文档已撤下确定说法。**关闭**（真实 served 证据仍不可回溯，符合“不新增付费调用”；归档已如实说明） |
| P3-1 | §7.5 把 hybrid 丢分写成“全部来自规则直通” | 034 归档 §7.5:344 改为“主要”，补 PX19（模型回问）与 multi_rule PX38（模型多派 lease） | 归档文字与逐题记录一致。**归档侧关闭**；ADR-006 §5a:71 仍是旧的“丢分全部来自规则直通”，见新 P3-2。**部分关闭** |
| P3-2 | `code_commit` 不能标识被测代码 | `runner.py:48-64` 新增 `_git_worktree_state`；`EvaluationReport.code_worktree`（`:84`）写入 bindings（`:93`）与 Markdown（`:455`）；planner 报告也写入 `:159` 与 Markdown `:422` | 我离线生成 heldout 报告：`bindings.code_worktree=dirty`，Markdown 显示“工作区 dirty”；planner 套件同样为 `dirty`；旧报告未回写。**关闭** |
| P3-3 | 冻结先后证据有限 | 未改代码；034 归档 §13 第 405 行如实记录“git 历史无法证明（用例与代码都未提交）”，仅保留哈希/mtime/用户确认 | 表述诚实，没有夸大为已证明。**关闭（按如实记录要求）** |
| P3-4 | 规则直达 `planning` 无 `escalation_reason` | `investigation.py:193-210` 的 `rule_planning_record` 增加 `escalation_reason: None`；hybrid 升级路径只覆盖值 | CLI rule/llm/hybrid 的 planning 均有 `escalation_reason`；heldout C 的 32 行键集合一致；A/B/C 逐题仍 0 差异；`test_planning_record_shape_is_uniform` 通过。**关闭** |
| P3-5 | `--planner-provider` 优先级未写明 | `ADR-006` §5:60 明写“给 planner-provider 就用它；省略沿用 model-provider；两者都 offline 时 exit 2” | 与 `cli.py` 的 `_planner_client` 实际解析一致（planner_provider 优先）。**关闭** |

## 3. 发现的新问题

### P1

无。

### P2

无。返修未改变规划决策、子任务、核验结论或金额计算；测试没有被弱化；无新增安全/数据问题。

### P3

**P3-1（新）错误码本地化规则过宽，可能误改非错误文本。**

- 位置：`backend/app/api/static/js/i18n.js:163-167`。`localizeErrorCodes` 把**任何**括号内或“失败:”后的 `[a-z][a-z_]*` 都当作错误码，交给 `term('errorCode', ...)`；未映射值会被替换成“其他错误（原始代码见技术视图）”。
- 自建探针：`localizeErrorCodes('本次检查（pending）')` → `本次检查（其他错误（原始代码见技术视图））`；`localizeErrorCodes('查询失败：some_future_code')` 同样改写成“其他错误”。`localizeStatement` 又用于 `findings[].statement`（`report.js:135`）与审批提醒，因此如果合同摘录/告警正文里出现 `(pending)`、`(in progress)` 等普通英文括号词，事实文本会被错误地标成“其他错误”。
- 影响范围：当前真实运行数据中我只找到 `（budget_exhausted）` 这一处，均有明确错误码语义，未造成现有用户可见错误；因此是 P3 边界/可维护性，不是 P2。建议只替换已知 `ErrorCode` 集合，或把未知括号内容包成“`未知错误（原值见技术视图）`”而不要覆盖原文。

**P3-2（新/残留）状态文档仍留有旧状态与旧归因。**

- `docs/decisions/ADR-006-hybrid-planner.md:4` 仍写“已实施并自检……**待独立复查**”；`:71` 仍写 hybrid“丢分全部来自规则单领域直通 / 误命中直通”，与 034 归档 §7.5 已修正的“主要”及 PX19/PX38 说明矛盾。
- `docs/architecture/CURRENT_BASELINE.md:3` 先说“复查有条件通过、P2/P3 已返修、待复查确认”，同一行后半段仍保留“Task 032（……实施自检，待独立复查）与 Task 034（……实施自检，待独立复查）”的旧口径。
- `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md:3` 仍写 Task 032/034“实施自检、未提交”，`:44` 的进度判断仍写“U3 部分修复”，与 §17 已补的“610 tests、P2/P3 已返修”不一致。
- 这些都不构成“已通过”误报，数字（610 / 70 / 48 / 185）在 README、`docs/README`、`CURRENT_BASELINE`、路线图 §17、开发日志中已更新；问题是同一文档/ADR 里旧结论残留，属于文档一致性 P3。建议由实施者最后统一同步，不需改代码。

**P3-3（残余边界，非本轮引入）`completed` 且 `verdict` 缺失/空串仍显示绿色“已完成”。**

- `view-model.js:130-134` 只把 `verdict` 非空的 conflicting/insufficient/未知值降级为 warning；`verdict === ''` 时落入 `RUN_STATUS.completed` 的 success“已完成”。测试用例只覆盖 `verdict: 'weird'`（非空），没有覆盖缺失/空串。
- 当前 API 路径中 `run.verdict` 与报告 verdict 都由后端写入，我没有在真实 API 记录里找到 completed+空 verdict；因此这是防御性边界，不是现网问题。建议在 `runStatusMeta` 中把 completed 且无 verdict 视为“需复核/未知”，并补一条断言。

## 4. 返修有没有引入副作用

- **判定逻辑**：`planner_suite` 的四种离线配置正确数/调用数/越权数与上一轮完全一致；`mode=rule` heldout A/B/C 与 `20261121T093757_*` 仍 **0 行差异**；说明只加字段、未改变规划决策。032 的 `case-status.js` 未被修改，U3 独立探针的 verify/report/summary/card 状态不变；金额格式、跨项目隔离、静态 MIME/304/路径穿越均无回归。
- **测试**：+3 个测试分别是错误码同步、planner 套件逐题 `planner_model`、planning 键形状；JS +3 用例为 P2-1、P2-2、P3-1/2 相关断言。删除错误码映射的阴性实验证明 `TestErrorCodeLabelsInSync` 不是空测；`git diff` 未显示新增 skip/空断言/恒真断言。
- **证据/文档**：真实 20 个报告哈希未变；17 张截图重截且 `round1/` 仍保留；旧报告不被回写；归档/README/基线/日志的 610 / 70 / 48 / 185 与状态“有条件通过、返修待确认”基本一致（残留见 P3-2）。
- **换行/泄密**：44 个 manifest 文本文件无 CRLF；`graph.js` 仅换行差异（内容 diff 与上轮一致）；无新密钥/绝对路径；临时验证产物在仓库外。

## 5. 通过条件与建议

1. 上一轮两个任务的 P2 已全部关闭，本轮没有新的 P1/P2；建议把两个任务的“有条件通过”条件视为**已满足**，但不改写成“最终验收通过”。
2. 建议实施者顺手修两项 P3：限制 `localizeErrorCodes` 只处理已知错误码（或保留未知原始内容）；统一 ADR、`CURRENT_BASELINE` 首行、路线图首行/进度判断中的旧状态与旧归因。
3. P3-3 的 completed+空 verdict 可加一条防御断言；不影响当前 API 数据。
4. 034 的真实实际应答模型证据在当前“不新增付费调用”的约束下仍不可回溯；若以后需要，只能重新授权跑真实对照（llm 组约 66 次/10.8 万 token，四组约 160 次/26.3 万 token，按上次报告口径）。本轮不调用。

## 6. 本轮限制

- 未调用真实 DeepSeek 接口；真实对照只核对已存报告哈希与文档，不重跑服务端应答模型证据。
- 截图“重截”按文件哈希/manifest 与 08b、01 逐张查看确认；390 宽 `scrollWidth`、真实页面控制台、两轮视觉自检没有独立重复测量，相关数字仍为实施者自报。
- 浏览器验证使用 headless Chrome 的真实 ES 模块与真实 API 返回体，但不等于完整人工浏览器操作；人工视觉/首屏结论仍以用户或人工复查为准。
- 本轮只新增本报告；未更新开发日志、`CURRENT_BASELINE` 或路线图，未提交/推送。
