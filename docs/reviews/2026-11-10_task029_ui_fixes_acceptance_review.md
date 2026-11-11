# Task 029 修复独立复查（Task 030）

- 日期：2026-11-10（Asia/Shanghai）。
- 用户原始要求：检查本次修复状态。
- 起点：本地 main / 8569cc2；027 实现、028 审查、029 修复及文档仍未提交。本轮不声明远端同步状态。
- **结论：U1、U2 的原始反例已通过；U3 的 report.error 路径已修复，但缺字段/类型异常和互相矛盾的核验字段仍可能显示成功，U3 只能记部分修复。**
- 本轮只写审查与同步状态文档，不改实现或测试，不提交/推送，不发出真实模型请求。

## 1. 发现与验收判断

### U3-A [P2] 复核标记类型异常、部分必需字段缺失仍显示核验通过

位置：`backend/app/api/static/js/view-model.js:678`、`:681`、`:718`、`:721`。

verifyNode 计算了 failures、narrative_discrepancies 的字段类型，却没有把它们的缺失/无效状态纳入 incomplete；requires_human_review 仅判断 true 和 undefined，null、字符串、数字最终都落到 success。reportNode 也有相同的布尔类型漏洞（:767、:770）。

独立反例以真实复杂报告为结构基础，构造 supported、complete、冲突/缺口/失败/叙述差异均明确为空、requires_human_review=false 的正常基线，再逐项修改：

| 仅修改的字段 | 当前实际 verify / report |
|---|---|
| requires_human_review=null | success / success |
| requires_human_review="true" | success / success |
| requires_human_review=1 | success / success |
| 删除 failures，或 failures="invalid" | success / success |
| 删除 narrative_discrepancies，或改成对象 | success / success |

因此“字段三态已覆盖异常”的自检结论范围过大。以上是构造的兼容性/异常输入，不是本轮服务实际产生了这些畸形字段。

验收要求：需要布尔值的地方必须确认为 boolean；未知/类型异常不能当 false。可兼容省略的字段也必须说明语义，不能未经依据把缺失视为明确通过。新增只改变一个字段的参数化用例，保留完整 supported 的正常成功测试。

### U3-B [P2] 报告节点与核验节点仍可能互相矛盾，非空冲突也未必降级

位置：`backend/app/api/static/js/view-model.js:693`（核验分支）、`:727`–`:773`（报告分支）。

reportNode 只检查 verdict、findings 与复核标记，没有联合 conflicts、missing_information、failures、narrative_discrepancies 或 completeness。独立构造的 supported + requires_human_review=false 基线上：

| 额外输入 | verify 实际输出 | report 实际输出 |
|---|---|---|
| 当前 failures 含 timeout | failed：存在失败子任务 | success：报告已生成 · 证据一致 |
| narrative_discrepancies 含 mismatch | partial：叙述与字段不一致 | success：报告已生成 · 证据一致 |
| missing_information 非空 | partial：存在资料缺口 | success：报告已生成 · 证据一致 |
| completeness=partial | partial：调查未完整 | success：报告已生成 · 证据一致 |
| conflicts 非空 | success：证据核验通过 | success：报告已生成 · 证据一致 |
| conflicts 缺失/类型异常 | unknown：核验字段不完整 | success：报告已生成 · 证据一致 |

特别是 verifyNode 读取了 conflicts 数量，却没有据非空数组本身降级，依赖 verdict=conflicting；字段相互矛盾时可出现两个绿灯。当前正常后端通常保持这些字段一致，本轮正常 API 没出现上述矛盾；但 029 明确承诺异常兼容和联合判定，不能用正常路径不产生它来宣称该项完成。

验收要求：集中、复用核验状态解释，避免报告节点另写一套更弱的判断。区分报告文档生成和结论可信；报告可以已生成，但有失败、冲突、差异、缺口或字段无效时，不能再断言“证据一致”。优先展示明确的负面事实，字段冲突标需复核/状态不一致。回归应同时断言 verify、report 和相应摘要的一致性。

### D1 [P3] 当前路线图仍保留两套相反的修复状态

复查开始时，路线图顶部写 Task 029 已修复，但同页后面的 Task 028 当前更新、步骤 9 和进度判断仍写 U1–U3 全部待修。Task 029 实施日志与检查点存在，只是排列在早期 Prompt 记录后；本轮不将其误报为缺失。

本轮已按独立证据同步当前路线图与基线：U1/U2 通过，U3 部分修复；保留旧报告、自检、Prompt 和历史日志，不改写历史结果。后续返修也须同步正文和状态表，不能只叠加顶部结论。

## 2. 已确认通过的成果

| 项目 | 本轮独立证据 |
|---|---|
| U1：预算失败参与状态 | 独立临时控制面的真实 API 返回失败子任务 2 个；现有 JS 把 billing/property 映射为 failed，带 budget_exhausted；3 个已记录子任务、1 个结果、2 个失败、6 条 Trace，Trace 全部关联 |
| U1：失败审计、多子任务、恢复 | 阅读集中索引和组件，现有 JS 回归相应用例通过；resolved_failures 不覆盖成功，多子任务保留；无关联 Trace 单列是已披露限制 |
| U2：合同/工单节点 | 真实复杂报告 6 条 finding；现有 JS 映射为 lease=4、billing=1、property=1；跨领域/未知/无证据用例通过，不改变证据页分组 |
| U3：原始 error 反例 | 现有真实 JS 对 report.error 输出 plan=unknown、verify=unknown、report=failed，无原来的三个绿灯 |
| 正常/冲突/不足 | 正常单领域和复杂 API 运行结果能正确区分相关领域与冲突/不足；完整 supported fixture 仍可成功 |

U1/U2 的通过指 028 缺陷及本次所述范围，不证明所有未来协议扩展或 Agent 动态展示都完成。

## 3. 本轮实际验证

- 全量：在 backend 目录运行项目 Python 的 `-m unittest discover -s tests -p 'test_*.py'`，**409 tests，21.873 秒，OK（skipped=1）**。包含新 test_ui_view_model 的无头浏览器执行；没有再单独重复整套。
- 契约：`python tests/smoke_agent_contracts.py`，**57 项通过**。
- 另用隔离临时控制面取得复杂调查、预算耗尽、简单账单的真实 API 返回；没有审批或修改用户既有任务，没有启动新持久服务。
- 在 node_repl 导入实际本地 view-model.js 和 ui-model-cases.js，执行原回归：**17 用例、84 断言、0 失败，含 2 个真实 API 用例**。此项是纯模块执行，非新截图或人工页面操作。
- 另执行 **15 个变体**（1 个正常基线、14 个异常/不一致输入），复现 U3-A/U3-B；结果见 [独立映射证据](task030_ui_mapping_evidence.json)。不把这 15 个反例称为新增永久测试或正常 API 失败。
- 查看 DeepSeek 已交的预算失败节点详情和 error fixture PNG，画面与已修的原始反例相符。本轮没有额外手动浏览器视觉验收或新截图；无头回归主要测试模型函数，不能等同完整 DOM/交互覆盖。
- 修复报告正确区分真实 API 与注入异常截图；保留原有 10 张图片及报告。

测试覆盖仍有遗漏：原“字段类型异常”用例继承 requires_human_review=true，容易让报告节点因复核标记而降级，掩盖其未独立检查异常字段。预算真实用例的一条 OR 断言在 failures.length>0 时恒真（ui-model-cases.js:545），但同用例前一条逐失败领域状态断言有效，因此不能说整个 U1 测试无效。建议删掉冗余断言并补上本轮缺口，重点验证真实行为。

## 4. 网页 AI 接入状态没有改变

`backend/app/api/service.py:367` 仍调用 build_investigation_bundle 而不传 engine/model_client/max_model_calls；默认值为 deterministic、None、0。API 请求结构也未增加实际模型装配通道。页面仍是规则演示，不会因 .env 有 Key 自动使用 DeepSeek。

本次 029 范围本就不含真实模型接入，不能将此记为返修偷漏；但必须对项目进度明确：网页真实模型运行、领域回答展示和最终综合分析仍未完成。CLI 已有模型路径不是网页已接入的证据。本轮未调用真实模型，不关闭 Z1–Z3、独立配置、PG 或正式评测事项。

## 5. 下一步与提交状态

建议集中补完 U3-A/U3-B 和相应 JS 行为回归，保留现有 UI；完成后再单独推进网页真实模型链路与综合分析，不将两者混成“前端都好了”。

HEAD 仍 8569cc2；029 修复及本轮审查均未提交。没有重建数据库、改实现/测试、重启用户服务、发布或推送。当前仍为可演示原型/版本候选，Task 029 尚不能按 U1–U3 全部通过关闭。
