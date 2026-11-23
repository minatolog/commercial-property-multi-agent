# Task 032（业务流程工作台 + U3 收尾）独立复查

- **复查日期**：2026-11-22（Asia/Shanghai）。
- **复查者**：DeepSeek（独立复查模型；实施者为 Claude Code。本轮只读，不修改源码、测试、评测题、评分规则与配置，不提交、不推送、不切分支、不 stash）。
- **复查依据**：[复查交接 Prompt](../handoffs/REVIEW_TASK032_034_PROMPT.md)、[Task 032 实施 Prompt](../handoffs/DEEPSEEK_TASK032_BUSINESS_WORKBENCH_UI_PROMPT.md)、[Task 032 归档](../prompts/05_frontend/2026-11-22_032_business_workbench_ui.md)、[U3 原始复查（Task 030）](2026-11-10_task029_ui_fixes_acceptance_review.md)、`CURRENT_BASELINE.md`、路线图、实际代码/测试/截图。
- **代码基线与清单核对**：`HEAD = 3be785e0f4363b45c0bec152501ce5b54b08ad1f`；Task 032 改动未提交。按交接 Prompt §1 核对 manifest：109 个文件（M=34，A=75），清单正文 SHA-256 重算 `1f9565b8dfa28ffbfc270a72b5ae67a21fae13f84ef9f279b9d640fcd206926f` 与头部一致；逐文件复算 **0 缺失、0 哈希不符**；`git status --porcelain -uall` 112 项 = 109 + manifest 本身 + 复查 Prompt + 允许排除的 `.claude/launch.json`；无意外文件。**清单核对通过，无需要先停下的差异。**
- **环境**：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11.18）；`backend/` 下执行，`PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`；临时控制面、截图探针与运行数据全部在仓库外（`D:\review032_out`）。浏览器：`C:\Program Files\Google\Chrome\Application\chrome.exe`（headless）。
- **复查方式**：不采信自报数字。独立复跑全量回归/契约/`check`；用 `TestClient` + 临时 `RunIndex/checkpoint/approval` 真实提交并操作复杂调查、预算耗尽、简单查询、回问、两级批准/驳回；独立构造跨项目反例与只读 display 范围反例；实测静态资源 MIME、`Cache-Control` 与路径穿越；复跑真实浏览器 JS 回归（45 用例/163 断言）并另写浏览器探针，用真实 API 返回体扫描主视图英文枚举、复做 U3 全部反例、渲染摘要页签检查缺失字段；逐张查看 `task032_screenshots/` 的 11 类截图与 round1。**未调用任何付费接口**（网页为确定性引擎）。

## 结论

**有条件通过。**

工作台改版、只读 display 元数据、U3-A/U3-B 收尾与 11 类截图整体成立：607 tests / 70 契约 / 45 用例 163 断言/0 失败与自报一致；跨项目测试未泄漏；静态资源 MIME、304、路径穿越安全；U3 原始反例全部按预期降级；首屏 5 秒测试可回答四个问题。未发现 P1 问题。**P2 两项**：① 摘要页签“系统提醒”直接显示后端告警中的英文错误码 `budget_exhausted`（最终截图 08b 可复现），违反“主视图不出现英文枚举”，实施者“英文扫描唯一残留已修”的自检结论不成立；② 摘要页签“缺失与失败”在 `failures` 字段缺失/类型异常时仍显示计数 0 与“报告没有列出资料缺口或失败”，违反“字段缺失/类型异常不能默认成功或 0”，U3-A 在这一条渲染路径上未收口。另有 6 项 P3。条件见 §4。

## 1. 独立验证的实际结果

| 验证项 | 我实际运行/看到的结果 | 与自报对比 |
|---|---|---|
| 全量回归 | `-m unittest discover -s tests -p 'test_*.py'` → `Ran 607 tests in 38.809s`，`OK (skipped=1)` | 自报 606 → 607（缓存 +1），**一致** |
| 新增测试 | `test_task032_display.py` 11 个 test method | 自报 11，**一致** |
| 契约自检 | `python tests/smoke_agent_contracts.py` → `全部通过：70 项检查` | 自报 70，**一致** |
| JS 真实浏览器回归 | 通过 `tests/test_ui_view_model.py` 的 harness 跑真实静态模块：`totalCases=45`、`totalAssertions=163`、`fixtureCases=43`、`realCases=2`、`failedCases=0` | 自报 45/163，**一致** |
| 复杂调查 API | `POST /api/runs`（A-301 复杂问题）→ `status=awaiting_approval`、`verdict=conflicting`、`approval_status=pending_approval`；`display.lease` = 云端咖啡（合成租户）/A-301/A座/星汇广场；`display.records` 26 条 | 真实运行，无自报冲突 |
| 简单查询 | `A-301 现在还有多少钱没交？` → `status=completed`、`verdict=conflicting`、`route=deterministic`，仅 `st_1_billing` 参与 | 与截图 07 的 A-302 简单查询同构 |
| 预算耗尽 | `max_tool_calls=1` → `status=failed`、`verdict=insufficient`、`completeness=partial`、2 个 `budget_exhausted` 失败子任务 | 与截图 08/08b 一致 |
| 回问运行 | `请帮我看看这个事情` → API `status=completed`、`verdict=needs_clarification`、`completeness=not_executed`、`route=clarification`、零子任务 | 自报“API 仍记 completed”，**一致** |
| 两级审批 | 物业批准 → `pending_next_stage`；财务驳回 → `rejected`，run `status=completed`、`approval_status=rejected`；另一条两级都批准 → `approved`，`report.approved_draft` 存在 | 真实操作成功，无假按钮 |
| 跨项目反例 | 模拟一条 `project_ids=["prj_jinlan"]` 的运行：xinghui 服务 `GET` → **404**，列表不含它，响应体无“锦澜/B-101”；`DisplayBuilder(scope={"prj_xinghui"})` 对 `lease_jl_b101_2025` 与锦澜文档均返回 `None`；空 scope 什么都不返回 | 未泄漏 |
| display 只读 | `get_run_view` 只在返回副本上加 `display`；SQLite `report_json/traces_json` 中无 `display`；无新增写接口（`git diff app.py/service.py` 核对） | **一致** |
| `/api/meta.principals` | 仅 `principal_ops_xinghui / principal_property_manager_xinghui / principal_finance_xinghui` 三个中文角色名；无租户/租约 ID | **一致** |
| 静态资源与缓存 | `/static/js/app.js` → 200、`application/javascript`、`Cache-Control: no-cache`、ETag；带 `If-None-Match` → **304**；首页 `no-cache`；`/static/vendor/tabler/css/tabler.min.css` → 200 `text/css` | 自报“静态资源加 no-cache”，**一致** |
| 路径穿越 | `/static/../app.py`、`/static/%2e%2e/app.py`、`/static/js/%2e%2e/%2e%2e/app.py` 均 **404**；不存在的静态文件 404 | 防护有效 |
| 无远程资源 | 首页 `remote_urls=[]`；只加载本地 `/static/vendor/tabler/js/tabler.min.js` 与 `/static/js/app.js`；无 CDN/远程字体/图片；vendor 本地存在 | **一致** |
| U3 原始反例 | 用真实 `view-model.js` / `case-status.js` 复做 Task 030 表格：U3-A（`requires_human_review` null/"true"/1/删除、`failures` 删除/"invalid"、`narrative_discrepancies` 删除/对象）→ verify/report/summary/card 均为 unknown；U3-B（failures/timeout、narrative mismatch、missing 非空、completeness=partial、conflicts 非空但 verdict=supported、conflicts 缺失/类型异常）→ 分别为 failed/partial/unknown，三处一致，报告节点不再显示“证据一致” | **全部通过**（独立探针结果与实施者参数化用例一致） |
| 真实运行主视图英文扫描 | 6 个真实 API 运行（复杂待审批、简单、预算失败、回问、已驳回、已批准）渲染摘要/冲突/证据/审批/协作图/节点详情，通用英文 token 扫描只命中 1 处：预算失败摘要页签的 `budget_exhausted`（见 P2-1）；其余未命中 | **发现自检未覆盖的残留** |
| 摘要缺失字段反例 | 基线报告删除 `failures`（或改成字符串），摘要页签渲染“缺失与失败 **0** · 报告没有列出资料缺口或失败。”，同时上方结论为“结论待核实：报告字段不完整” | **发现 P2-2** |
| 截图 | 11 类全部存在（01–11），另有 04b/05b/06b/08b/12/13 与 round1 两张；逐张查看，数据与 fixture/真实运行一致，未见 mock 痕迹；窄屏 390、1280×800 均无肉眼可见横向溢出 | 与归档截图清单一致 |
| 金额格式化单测 | `"18036.00"`→`¥18,036.00`；`"0.00"`→`¥0.00`；`"-756.00"`→`-¥756.00`；`"1234567.5"`→`¥1,234,567.50`；空→`未提供`；`"12abc"`→`金额格式异常（12abc）` | Prompt §7.3 六个输入**全有测试且通过** |

## 2. 逐项对照交接 §4.3

### 2.1 §2 技术约束与只读后端

- 无 React/Vue/Vite/Next、无构建链、无 CDN/远程字体/图片；只使用本地 Tabler 1.7.4 + 原生 ES modules（静态资源清单通过 `/static` 逐项访问验证）。
- `app/api/display.py` 只读：查表、原样搬运字段、按可信项目范围过滤、不落库；`service.get_run_view` 只返回副本；无新增写接口、无权限语义变化。新增字段有 `test_task032_display.py` 11 项测试。
- **范围说明（P3-3）**：`app/api/app.py:56-61/163/169` 新增的 `RevalidatingStaticFiles` 与首页 `Cache-Control: no-cache` 属于“静态服务行为”改动，不是 Prompt §2 允许的“只读展示元数据”。它是后续会话为修缓存问题加的、归档 §8 已披露；我实测未影响 MIME、304、路径穿越，故记 P3 而非违规功能问题。

### 2.2 §4 真实性规则

| 规则 | 核对 |
|---|---|
| 执行中不伪造进度，不用 `setTimeout` 演出完成 | `app.js` 提交后 `beginPending` 只把页面切到“调查执行中”占位，节点/页签统一显示等待文案；`setTimeout` 仅用于 5 秒后隐藏页面提示条（`app.js:105`）和复制按钮复位（`dom.js:86`），不驱动步骤/状态。**通过** |
| `completed` 不等于结案；`awaiting_approval` 不等于结案；`conflicting`/部分完成不能全绿 | `runStatusMeta`（`view-model.js:109-126`）对 `needs_clarification`、审批 `approved/rejected` 做了专门处理；`awaiting_approval` 是 warning“待审批，未结案”；详情结论卡在冲突/部分完成时全部 warning（实测 `complex_pending` 四张卡 warning，`budget_fail` 为 failed/unknown/warning/failed）。**但**：completed+conflicting 的运行在列表/案件头仍显示绿色“已完成”徽标，见 P3-2。 |
| 字段缺失/类型异常显示“未提供/待核实/需复核”，不默认成功或 0 | U3 参数化用例全部通过；独立复做一致。**但摘要页签 `failures` 缺失时仍显示 0，见 P2-2。** |
| 金额只展示后端结构化字段，前端只做字符串格式化 | `format.js` 无 `parseFloat/Number()`（只有 `formatNumber` 用字符串正则；`Number()` 只用于时长/序号/草案版本，不用于金额）；卡片金额来自 `conflicts[].amount`/`authoritative_amounts`/`proposed_draft.amount`，草案金额单独标注“预设草案金额，非计算结论”。**通过** |
| 安全渲染：用户输入、证据、错误信息转义 | `dom.js` 只用 `textContent`/文本节点；全前端无 `innerHTML/insertAdjacentHTML/outerHTML/document.write`（仅注释提到）；`renderRaw` 的 JSON 走 `<pre>` 文本；无模板字符串拼 HTML。**通过** |
| 前端不发送自报身份字段，不暴露 `.env` | 提交运行只发 `question/lease_id/with_approval/max_tool_calls`；无 principal/permissions。**但审批决定仍由前端发送 `X-Actor-Id`（`api.js:89-98`）**，值从服务端白名单选择；服务端校验 allowlist + 运行所有权。这是 027 起的既有演示机制（本轮未改 `api.js`），与 `api.js:1-7` 注释字面矛盾，见 P3-5。 |
| 快速切换案件时旧响应不覆盖新案件 | `selectRun` 用 `AbortController` + `detailSeq` 双保险（`app.js:306-327`），旧响应 `seq !== state.detailSeq` 直接丢弃；列表加载也有 `listSeq`。**代码审读通过**（未独立做浏览器并发注入）。 |

### 2.3 §5 U3 收尾

- 把 Task 030 原表逐行对到 `ui-model-cases.js:526-554`：U3-A 8 行、U3-B 7 行，共 15 行参数化反例；每行只改一个字段（另保留完整 supported 基线成功用例）。
- 每行断言 `equal(got, {verify, report, summary, card})`，其中 `got` 同时来自 `buildGraphModel`、`summaryModel`、`conclusionCards`；另断言报告节点标签不含“证据一致”。我的独立探针复做的状态与实施者表格完全一致。
- 核验解释集中为 `case-status.js:interpretVerification`，核验节点/报告节点/结论卡/步骤条/摘要共用；组件里仍有 `report.verdict`/`conflicts` 的直接读取，但用于“回问/错误/审批单”等**布局与事实展示**，没有另写一套成功/失败判定；`report.requires_human_review` 直接读取处只显示“是/否/待核实”（`report.js:789`）。**没有发现绕开 `interpretVerification` 的核验绿灯逻辑。**
- 测试有意改动 3 处（归档 §6.1）：预算报告节点 partial→failed 是 U3-B 的**收紧**（截图 08 也显示报告节点 failed/警告），不是为过测试而放宽；节点标签本地化；删除 030 指出的恒真断言。核对 `git diff` 的删除行与此一致，未发现新增空断言/`skip`/`except: pass`。

### 2.4 §7.1 “5 秒测试”（亲自看截图）

以 `01-complex-pending-1440x900.png` 回答 Prompt 的四问：

1. **哪个租户/铺位/什么问题？** 标题“云端咖啡（合成租户）· A-301”，问题类型“租金差异”，下方原文“商铺 A-301 投诉最近三个月租金金额不一致…”。
2. **有没有冲突、差多少钱？** 结论卡“存在冲突：账单租金与合同计费规则不一致”；金额卡“+¥756.00 · 账单多计”，来源“账单核算（合同计费规则 vs 账单明细单价）”。
3. **走到哪一步、下一步等谁？** 步骤条第 5 步高亮“物业审批 · 等待物业管理部门审批”；下一步卡“等待物业管理部门审批”。
4. **有没有需要人工复核？** 第 3 步“证据核验 · 发现冲突·需复核”，结论卡副文案“冲突并列呈现，需人工复核”。

四项均可在首屏找到答案，与归档 §7.1 的方向一致；但归档 §7.1 只写了“看哪些元素”，没有**逐条**回答四问（P3-4）。

### 2.5 §7.2 截图与视觉

- 11 类齐全：01 复杂待审批首屏、02 冲突、03 证据、04 物业已批/待财务（+04b 审批单）、05 归档（+05b）、06 驳回（+06b）、07 简单查询、08 预算耗尽（+08b 摘要）、09 1280×800、10 390 窄屏、11 技术视图；另 12 回问、13 摘要、round1 两张。逐张查看：数据与 fixture/API 返回值一致，无 mock 痕迹；状态均有文字+图标；金额格式统一；未见横向溢出或压字；高饱和色块目测不超过 3 处（深蓝主按钮/当前步骤、语义色只用于小徽标与色条）——此判断是视觉主观结论。
- **但**：08b 摘要页签的“系统提醒”里出现英文 `budget_exhausted`（P2-1）；归档 §7.2 的“主视图英文扫描唯一残留已修”与最终截图矛盾。
- 归档没有提交 Prompt §7.2 要求的六项逐条自查清单（P3-4）；round1 只保留 2 张首屏截图，作为“两轮自查”证据偏薄，但与归档描述不冲突。

### 2.6 §7.3 功能回归

- 新建/切换/刷新/批准/驳回：我用临时服务真实提交、读取、两级批准与驳回，状态、审批单、`approved_draft` 与截图一致；无假按钮（`decisionForm` 的批准/驳回绑定 `onDecide`，只有当前阶段渲染，见 `report.js:608-648`）。
- **未独立重跑真实浏览器控制台检查**：我的 headless 探针/harness 无模块错误、无 panel 渲染错误；归档声称控制台无错误、三档宽度无横向溢出，属实施者自报，本轮未重复测量。
- 金额格式化 6 个输入均有测试并通过；`formatNumber`/`formatVariance` 也与字符串处理一致。

## 3. 实施者自认风险点的独立判断

| 风险点 | 我的判断 |
|---|---|
| 1. 回问运行 API 仍记 `completed` | 属实：API `status=completed`、`verdict=needs_clarification`；界面通过 `runStatusMeta` 显示 warning“需要补充信息”，列表筛选 value=completed 的标签是“已结束”，因此不直接误导用户；CLI/评测按 `verdict` 判断，不会把回问当成功。归档已披露。**风险可接受，记 P3 边界说明**：外部消费者若只读 `status` 会误读。 |
| 2. `i18n.term()` 缺失映射显示“未知状态（原值）” | 对当前真实数据，主视图扫描只发现 1 处英文（预算告警，且它**不是**经过 `term` 的路径，见 P2-1）；对未映射的新错误码（如 `tool_timeout`），我构造的运行会让协作节点/摘要显示“未知状态（tool_timeout）”，确实会在主视图露出英文。设计“不空白、不猜”可以理解，但与 Prompt“主视图不出现英文枚举”有边界冲突，记 P3-1（P2-1 是当前已真实出现的那一处）。 |
| 3. 预算耗尽报告节点 partial→failed 是否只为过测试 | 是修复：U3-B 要求报告节点在存在失败时不能显示“证据一致”，failed/“报告已生成·存在失败子任务”比 partial 更准确；截图 08 与真实 API 都显示失败；不是放宽断言。**通过** |
| 4. 后续会话加 `Cache-Control: no-cache` 是否影响 MIME/路径穿越 | 实测 JS/CSS MIME 正确、304 正常、三种路径穿越均 404；`RevalidatingStaticFiles` 只加响应头，不改路径解析。**功能安全**；但它是允许范围之外的静态服务改动，记 P3-3。 |
| 5. 前置条件是“Task 031 通过独立复查”，实际为“有条件通过” | 属实；Task 031 的复查条件 C1/C3 已由 Task 034 会话同步，C2（R1 残余）即 Task 034 §2.6，已修复（见 034 报告）。032 的新功能不依赖未完成条件，**可接受**，归档 §1 已写明。 |

## 4. 问题清单

### P1

无。跨项目读取被 404/范围过滤挡住；无写接口、无 XSS（只用 `textContent`）、无金额计算；未发现“界面误报通过/证据一致”的新路径（U3 原始反例全部降级）。

### P2

**P2-1 摘要页签“系统提醒”直接显示后端告警中的英文错误码 `budget_exhausted`。**

- 位置：`backend/app/api/static/js/components/report.js:22-25` 的 `localizeStatement` 只处理租约状态与金额千分位；`:162-166` 用 `localizeStatement(warning)` 渲染 `report.warnings`，没有复用 `describeMissingItem` 的括号错误码转换（`i18n.js:150-167`）。
- 复现：临时服务提交 `max_tool_calls=1` 的复杂调查 → 打开“案件摘要”页签 → “系统提醒 2”中出现“条款检索不可用（**budget_exhausted**），本次结论不含合同条款证据”。最终截图 `docs/reviews/task032_screenshots/08b-budget-exhausted-summary.png` 可肉眼看到该英文。
- 影响：违反 Prompt §6“主视图里不出现英文枚举、内部字段名或 ID”，并使归档 §7.2 的“英文扫描唯一残留已修”不成立；不是 P1，因为没有误报结论/数据，且技术视图外只此一处。
- 建议：告警渲染改走 `describeMissingItem`（或对括号内错误码调用 `term('errorCode', ...)`），并加一条“渲染真实 warnings 不含英文码”的浏览器用例；现有 `ui-model-cases.js:579` 只测了 `describeMissingItem` 这个未被该路径使用的 helper，属于测试没有覆盖所声称行为。

**P2-2 摘要页签“缺失与失败”在 `failures` 字段缺失/类型异常时仍显示 0 与“报告没有列出资料缺口或失败”。**

- 位置：`backend/app/api/static/js/components/report.js:150-160`：`failures = vm.asArray(report.failures)` 把缺失/非数组一律当空数组，随后只在 `missing_information` 不是数组时才提示“未提供资料缺口字段”，`failures` 的状态没有参与判断。
- 复现（我另写的浏览器探针，真实组件）：以完整 supported 基线删除 `report.failures`（或置为 `"invalid"`）→ 摘要页签渲染“缺失与失败 **0** · 报告没有列出资料缺口或失败。”，同页上方却是“结论待核实：报告字段不完整（缺少或类型异常：failures）”。这违反 Prompt §4“字段缺失、类型异常…不能默认成功或 0”，也是 U3-A 在摘要渲染路径上的同类残余。
- 覆盖缺口：U3 参数化用例断言的“摘要”是 `vm.summaryModel`（`view-model.js:919`，产品页面并未渲染它），没有断言真实 `renderSummary` 的这段文本；因此 15 行反例全绿但真实摘要仍有此问题。
- 建议：分别判断 `missing_information` 与 `failures` 的数组状态；任一缺失/非数组时显示“未提供/待核实”，不要显示 0；把该文本纳入 U3 用例（渲染真实组件或复用 `arrayField`）。

### P3

1. **未映射错误码的前瞻性缺口**：`i18n.js:135-141` 的 fallback 会输出“未知状态（原值）”。对当前真实运行没有触发，但 `view-model.js:1030-1032` 的节点关键发现会用 `term('errorCode', code)`；我构造 `tool_timeout`/`deadline_exceeded` 类失败时主视图会出现“查询失败：未知状态（tool_timeout）”。建议补 `ErrorCode` 全量映射，或对失败码单独走 `describeMissingItem` 的兜底。
2. **completed + conflicting 的绿色状态徽标**：`view-model.js:109-126` 对 `status=completed` 且 `verdict=conflicting/insufficient` 仍返回 success“已完成”；`app.js:165-181`（案件头）与 `app.js:215-229`（列表）直接使用该徽标。实测 API 简单运行 `status=completed`、`verdict=conflicting`，列表/头部是绿色“已完成”，只有详情卡片是 warning。归档 §7.2 自检未覆盖这一组合；建议 completed 时结合 verdict 显示“已完成 · 存在冲突/需复核”或 warning 语气。
3. **后端改动超出“只读展示元数据”范围**：`app/api/app.py:56-61/163/169` 的 no-cache 头不是展示元数据。功能安全（MIME/304/穿越实测通过），归档 §8 已披露；建议在任务范围里明确“静态缓存响应头”为单独一类允许改动，或拆成独立小任务。
4. **验收文档缺项**：Prompt §7.1 要求“用截图逐条说明首屏四个问题的答案在哪里”，§7.2 要求提交六项逐条自查清单；归档 §7.1 只有一句“以截图 01 为准”，§7.2 只列“发现并已修”的 10 项，没有六项清单，也没有逐条 5 秒答案。另 §7.2 的“唯一残留已修”被 P2-1 推翻。建议补文档并说明自检范围（哪些页签/哪些错误码被扫描）。
5. **审批人身份仍由前端发送 `X-Actor-Id`**：`api.js:89-98` 在审批时发该头，而 `api.js:1-7` 注释写“不发送自报身份字段”；服务端只校验 allowlist + 运行所有权，演示环境无登录认证，因此任何客户端都能以白名单内任一审批人身份提交。该行为 027 起就有、本轮未改 `api.js`，属于继承的演示边界，不是 032 新增；建议在文档中明确“演示模式下审批人可自选、生产需真实认证”，避免被当成已实现鉴权。
6. **工作区换行**：`backend/app/api/static/js/components/graph.js` 工作副本为 CRLF（`git ls-files --eol`: `i/lf w/crlf`），`docs/reviews/task032_evidence/js_harness.json` 也是 CRLF（PowerShell 重定向产物）。`.gitattributes` 的 `* text=auto eol=lf` 会在提交时归一为 LF，因此不是提交内容问题；但证据 JSON 与归档“新写入文本 LF”的约定不一致，建议重新生成为 UTF-8/LF（manifest 中其余文本文件均为 LF）。

## 5. 通过条件与返修建议

1. 修 P2-1：真实告警渲染路径本地化错误码，并补浏览器用例覆盖 **warnings**（不是只测 helper）。
2. 修 P2-2：摘要“缺失与失败”区分字段缺失/类型异常；把真实 `renderSummary` 文本纳入 U3 断言。
3. 复核 P3-2：completed+conflicting 的徽标语义与颜色；P3-3 在任务范围中登记静态缓存头改动；P3-4 补齐 §7.1/§7.2 文档与自查范围；P3-5 明确演示审批边界；P3-6 重新生成 LF 证据文件。
4. 以上不需要重做页面结构或 U3 核心逻辑；修完后重跑 607 tests / 70 契约 / JS 45 用例并重截 08b 摘要页签即可。
5. **建议不把本报告当作最终验收**：视觉结论（色块数量、首屏观感）以人工/用户最终判断为准；本轮未重复测量浏览器控制台与三档宽度。

## 6. 本轮限制

- 未调用付费模型；网页本身为确定性引擎，未验证真实模型接入（归档已列为遗留）。
- 未独立做真实浏览器控制台/三档宽度测量；使用了 headless Chrome 的 harness 与自建探针（真实 ES 模块、真实 API 返回体），但不能完全等同人工浏览器操作。
- 截图“是否真实运行”依据画面数据与 fixture/API 一致、无 mock 痕迹及归档记录判断，无法从 PNG 元数据反证运行来源。
- 未修改任何源码/测试/配置；临时控制面、探针与运行数据在 `D:\review032_out`（仓库外）。
