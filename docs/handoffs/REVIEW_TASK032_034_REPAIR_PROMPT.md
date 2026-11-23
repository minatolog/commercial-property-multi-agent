# 复查 Prompt：Task 032 / 034 返修确认（只看返修改动）

- 编写：2026-11-22（Asia/Shanghai），Claude Code（实施者兼返修者）。
- 给：上一轮复查者 DeepSeek（或其他与实施者不同的模型 / 人）。
- 性质：**只读复查**，范围只限上一轮复查提出的问题是否真的关闭，以及返修有没有引入新问题。不重做整轮复查。
- 上一轮结论：[Task 032 复查](../reviews/2026-11-22_task032_independent_review.md)、[Task 034 复查](../reviews/2026-11-22_task034_independent_review.md)，均为**有条件通过**，无 P1。

---

## 0. 硬性约束（与上一轮相同）

1. **不调用付费模型接口**；任何命令都不要带 `--planner-provider deepseek` / `--model-provider deepseek`。用户这次明确选择“不新增付费调用”。
2. 不提交、不推送、不切分支、不 stash；不碰 `data/`；临时产物写到仓库外。
3. 不改源码、测试、评测题、评分规则与配置。
4. 环境：`D:\anacada\envs\commercial-agent\python.exe`（Git Bash 里的 `python` 是占位程序，必须写完整路径）；在 `backend/` 下运行，设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
5. 报告新写的文本文件用 LF。

## 1. 返修范围与清单核对

- 基线仍是 `3be785e`，Task 032 / 034 的全部改动未提交。之后用户另行提交了 `129c26b`（只新增 `scripts/dev_loop/` 与 `.gitignore` 两行，是开发辅助脚本），所以当前 `HEAD = 129c26b`；`scripts/dev_loop/` 下的未提交改动同样**不在本次复查范围内**，不必审查，也不算越界。下面的清单核对不受影响（2026-11-23 已复跑：无 DIFF、无 UNLISTED）。
- [`docs/reviews/review_repair_2026-11-22_manifest.txt`](../reviews/review_repair_2026-11-22_manifest.txt) 列出**上一轮复查之后**变动的 44 个文件，每行给出“复查时哈希 / 返修后哈希 / 路径”。复查时哈希来自上一轮的 [`review_handoff_2026-11-22_manifest.txt`](../reviews/review_handoff_2026-11-22_manifest.txt)。核对方法（仓库根目录，Git Bash）：

  ```bash
  F=docs/reviews/review_repair_2026-11-22_manifest.txt
  tail -n +6 "$F" | sha256sum            # 应等于清单第 4 行的正文哈希
  tail -n +6 "$F" | while read old new p; do
    [ "$(sha256sum "$p" | cut -d' ' -f1)" = "$new" ] || echo "DIFF $p"; done
  # 反向：上一轮清单里哈希变了、但不在本清单的文件
  tail -n +6 docs/reviews/review_handoff_2026-11-22_manifest.txt | while read h s p; do
    [ "$(sha256sum "$p" | cut -d' ' -f1)" = "$h" ] || grep -q "  $p\$" "$F" || echo "UNLISTED $p"; done
  ```

- 没有改动前的文件副本（改动未提交），无法直接 `git diff` 出“只含返修”的补丁。**请以 §3 列出的函数 / 段落为入口阅读**，必要时对照上一轮报告引用的行号。
- 44 个文件中：17 张截图与 2 张结构图是重新生成的图片；`graph.js` **只改了换行符**（CRLF → LF，P3-6），可用 `git diff --ignore-cr-at-eol --stat` 确认它对 HEAD 的内容差异与复查时一致。

## 2. 返修自报数字（需要独立复跑）

| 项 | 上一轮复查实测 | 返修后自报 |
|---|---|---|
| 全量回归 | 607 tests OK（skipped=1） | **610** tests OK（skipped=1）；+3 为 `TestErrorCodeLabelsInSync`、`test_suite_rows_record_planner_model_and_served_models`、`test_planning_record_shape_is_uniform` |
| 契约自检 | 70 | 70 |
| `python -m app.cli check` | exit 0 | exit 0 |
| JS 回归（`tests/test_ui_view_model.py`） | 45 用例 / 163 断言 | **48 用例 / 185 断言**（46 fixture + 2 real），0 失败 |

证据：`docs/reviews/task032_evidence/repair_unittest.txt`、`docs/reviews/task032_evidence/js_harness.json`。

## 3. 逐条确认（每条写：你做了什么、看到了什么、是否关闭）

### 3.1 Task 032

| 编号 | 上一轮问题 | 返修位置 | 请这样验证 |
|---|---|---|---|
| P2-1 | 摘要“系统提醒”显示 `budget_exhausted` | `static/js/i18n.js` 新增 `localizeErrorCodes`；`components/report.js` 的 `localizeStatement` 调用它；`describeMissingItem` 的兜底也改用它 | 用上一轮的复现方法（临时服务、`max_tool_calls=1` 的复杂调查、打开“案件摘要”）；看重截的 `08b-budget-exhausted-summary.png`；检查 JS 用例“复查 P2-1”是否调用了真实的 `renderSummary`，而不是只测 helper |
| P2-2 | `failures` 缺失 / 类型异常时摘要显示“0 · 没有缺口” | `components/report.js` 的 `renderSummary` 中“缺失与失败”段：两个字段分别判断，无效时计数显示“待核实” | 重做上一轮的探针（删除 `failures`、改成 `"invalid"`）；再试 `missing_information` 缺失 / 为对象；确认两个字段都是空数组时仍显示“0 · 没有缺口”（不误伤） |
| P3-1 | 未映射错误码显示“未知状态（tool_timeout）” | `i18n.js` 的 `errorCode` 补齐后端 22 个值；`term('errorCode', 未知值)` 返回“其他错误（原始代码见技术视图）” | 对照 `backend/app/agents/base/errors.py` 的 `ErrorCode`；看 `tests/test_task032_display.py::TestErrorCodeLabelsInSync` 能否真的抓住前后端不一致（例如临时在副本里删一个映射看测试是否失败，**在仓库外副本里做**） |
| P3-2 | `completed + conflicting` 在列表 / 案件头为绿色“已完成” | `view-model.js` 的 `runStatusMeta` 与新增 `COMPLETED_WITH_ISSUE` | 用上一轮的 `A-301 现在还有多少钱没交？` 简单运行（completed + conflicting）看列表与案件头；确认审批结论（已批准 / 已驳回）与回问仍按原逻辑优先 |
| P3-3 | `Cache-Control: no-cache` 超出“只读展示元数据”范围 | 未改代码，在 032 归档 §10 登记为本任务的静态服务响应头改动 | 判断登记是否足够 |
| P3-4 | 缺 5 秒测试逐条答案与六项自查清单；“英文残留已修”不实 | 032 归档 §7.1 表格、§7.2 注记、§10.1 清单 | 核对清单里的实测方法与结论是否可信（例如自己再扫一遍主视图英文） |
| P3-5 | 审批发 `X-Actor-Id` 与“不发送自报身份”字面矛盾 | `static/js/api.js` 头注释、`index.html` 页脚 | 只看措辞是否准确，不要求实现认证 |
| P3-6 | CRLF | `graph.js`、`js_harness.json` | `git ls-files --eol` 与 `file` |

### 3.2 Task 034

| 编号 | 上一轮问题 | 返修位置 | 请这样验证 |
|---|---|---|---|
| P2-1 | 规划层评测逐题无 `planner_model` / `served_models`；归档声称实际应答一致却无证据 | `evaluation/planner_suite.py`：逐题行新增 `planner_model`；`summarise_planner_rows` 新增 `served_models`、`served_model_mismatch_cases`、`served_model_unknown_cases`。034 归档 §7.5 的说法改为“未记录，不可复核”，§13 记录返修 | 离线跑一次 `evaluate_planner("llm", provider="scripted")` 看逐题字段；读新测试是否覆盖“一致 / 不一致 / 服务端未返回”三种情况；确认 4 份已有真实报告**未被改写**（哈希应与上一轮清单一致），且归档 / ADR / 基线里不再有“实际应答均为 deepseek-flash”的确定说法 |
| P3-1 | §7.5 把 hybrid 丢分归因为“全部来自规则直通” | 034 归档 §7.5 第 3 条 | 对照逐题记录核实 PX19、PX38 的描述 |
| P3-2 | `code_commit` 不能标识被测代码 | `evaluation/runner.py` 新增 `_git_worktree_state`；heldout 与规划层报告 `bindings.code_worktree`，Markdown 汇总也显示 | 离线生成一份报告（写到仓库外）看字段；当前工作区应为 `dirty` |
| P3-3 | 冻结先后证据有限 | 未改代码，034 归档 §13 如实记录 | 判断表述是否诚实 |
| P3-4 | 规则直达 `planning` 无 `escalation_reason` | `orchestration/investigation.py` 的 `rule_planning_record` | 确认三种来源键形状一致；确认 `mode=rule` 的离线 heldout 与 `20261121T093757_*` 仍逐题 0 差异（新增键不影响判分） |
| P3-5 | `--planner-provider` 优先级未写明 | `ADR-006-hybrid-planner.md` §5 | 与 `cli.py` 的实际行为对照 |

### 3.3 回归与副作用

1. 复跑全量回归、契约、`check`、JS 回归，记录实际数字；检查新增测试有没有空断言、恒真断言、`skip`。
2. 返修有没有改变任何**判定逻辑**之外的行为：规划决策、子任务、核验结论、金额展示都不应变化（返修只加字段、改文案与展示颜色）。
3. 新改动的文件里有没有密钥、绝对路径、CRLF。
4. 文档一致性：`CURRENT_BASELINE.md`、路线图、`docs/README.md`、根 `README.md`、开发日志、问题日志里的数字（610 / 70 / 48 / 185）与状态措辞是否一致，有没有把“有条件通过 + 返修待确认”写成“已通过”。

## 4. 报告

- 写到 `docs/reviews/2026-11-22_task032_034_repair_review.md`。
- 开头写结论：**每个条件是否关闭**（逐条：关闭 / 部分关闭 / 未关闭），以及是否发现新问题（按 P1 / P2 / P3 分级）。
- 写明本轮限制（例如没有独立做人工视觉判断、没有付费调用）。
- 不要声称最终验收通过：正式真实 heldout 对照与重复测量、人工量表、PostgreSQL 实机仍是开放项。
