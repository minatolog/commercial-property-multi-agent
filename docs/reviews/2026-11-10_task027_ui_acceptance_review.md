# Task 027 协作工作台独立复查（Task 028）

- 日期：2026-11-10（Asia/Shanghai）。
- 用户要求：检查 DeepSeek 本次成果。
- 起点：main / 8569cc2；Task 027 源码、资源、截图及文档在工作区，未提交。Codex 先前提供的调研文档也仍未提交。
- **结论：模板复用、前端拆分、协作版式与既有接口集成已有实际成果；状态与发现映射存在 U1–U3，暂不建议将 Task 027 标为全部验收。**
- 本轮没有修前端/后端源码、没有改测试、没有付费模型调用或 Git 提交/推送。修改的是审查文档与当前状态入口；另重启了此前由 Codex 启动的旧预览进程。

## 1. 独立验证结果

| 项目 | Codex 本轮实际结果 |
|---|---|
| 全量回归 | `python -m unittest discover -s tests -p 'test_*.py'`：403 tests，21.661 秒，OK（skipped=1）；包含现有 API 测试 |
| 契约自检 | `python tests/smoke_agent_contracts.py`：57 项通过 |
| Tabler 资源 | 三份本地文件 SHA-256 与 THIRD_PARTY_NOTICES 一致；另外从 npm 读取 core-1.7.4.tgz 验证 version=1.7.4 / license=MIT，CSS/JS 对比上游仅有 sourceMappingURL 注释及尾部空白差异 |
| tarball SHA-256 | `ccb1631d26cec2589d357556c8fe86bbba75ef0bcf672a4939a7ed5d4ab7319c`，与 DeepSeek 记录一致；仅在内存中检查包内容，不安装或运行包脚本 |
| 实际改动边界 | Python 业务改动仅 app.py 的 StaticFiles 挂载；其余为页面/模块/静态资源和 API 静态测试、文档；未见 Agent/预算/数据库/评分源码变更 |
| 复杂调查 | 独立端口 8019、临时控制面：fanout；lease/billing/property 为 success/partial/partial，合同条款、账单、工单、冲突和缺失实际返回 |
| 简单账单 | deterministic；仅 billing 的结果与工具记录，未拆多领域 |
| 两级审批 | 临时合成任务：物业批准后 pending_next_stage，财务批准后 approved；approved_draft_only，executed_side_effects=[] |
| 驳回 | 另建临时合成任务：请求 rejected，阶段为 rejected/pending；未审批用户既有任务 |
| 失败路径 | 工具预算 max_tool_calls=1 的真实 API 运行，账单/物业出现在 failures，随后直接执行现有 view-model.js，复现 U1 |
| 节点发现 | 实际复杂报告有 6 条 finding；直接执行现有 JS，合同节点只映射 1 条、物业节点 0 条，复现 U2 |
| 异常形状 | 按 WorkflowService 异常分支实际使用的 status=failed + report.error 形状测试 JS，plan/verify/report 均 success，复现 U3；此项是结构化反例，不是宣称真实服务本轮发生了内部崩溃 |
| 视觉范围 | 读取了 DeepSeek 提交的桌面总览、节点/调用记录、390px 窄屏 PNG；版式较旧页明确改善。未冒充 Codex 新截图或完整浏览器独立验收 |
| 浏览器复验限制 | 浏览器连接器无可用 host；Windows computer-use 随后因无法可靠确认当前浏览器 URL 被工具停止，已停止 UI 操作，没有以其他浏览器自动化绕过 |
| Git 格式 | git diff --check 通过；最终文档核验另记于本任务归档 |

解释器为 `D:\anacada\envs\commercial-agent\python.exe`。独立运行数据在 `%TEMP%\codex-task028-ui-review`；临时验收服务在 8019，检查完成后关闭，不影响用户 8000 服务。直接执行 JS 是本地纯映射测试，不是浏览器交互或新一轮视觉验收。

## 2. 发现 U1 [P1] 失败 Agent 被误标成“本次未调用”，错误与 Trace 归属随之丢失

位置：`backend/app/api/static/js/view-model.js:165`（agentParticipation）、`:465`（traceRows）；`backend/app/api/static/js/components/report.js:527`（agentSummarySection）；规划子任务数量也只按 agent_results 计算。

原因：agentParticipation 只查 report.agent_results。实际 Graph 将失败结果写到 report.failures，失败记录带 capability/subtask_id，但不会留在 agent_results。没有找到 result 就返回 not_called 和空 subtaskId；节点详情因此查不到失败原因和该子任务的 Trace，调用筛选也没有 Agent 归属。

本轮真实反例：A-301 跨领域问题、max_tool_calls=1、with_approval=false。API 返回 status=failed、verdict=insufficient；账单 st_2_billing 与物业 st_3_property 都明确 budget_exhausted。现有 JS 却返回：

```json
{
  "agent:billing": {"state": "not_called", "label": "本次未调用", "subtaskId": ""},
  "agent:property": {"state": "not_called", "label": "本次未调用", "subtaskId": ""}
}
```

同一结果里这两个 Agent 有实际工具拒绝记录，traceRows 的 agent 却为空。规划卡只显示 1 个子任务，而真实计划执行了 3 个，其中 2 个失败。节点详情还断言“本次问题没有规划到该领域”，与后端事实相反。

修复验收：由有效结果、当前未解决 failures 和 Trace 建立明确的 subtask/capability 映射，失败与未参与区分。不要按下标猜 Agent；如果失败缺少必要关联信息就标未知。以失败为终态的节点须保留 subtask ID、错误码、工具尝试和筛选归属；补查成功后的旧失败不能覆盖最终成功。回归至少覆盖正常未参与、预算耗尽、权限拒绝/超时、失败后恢复。

## 3. 发现 U2 [P2] 物业节点漏掉全部工单发现，合同节点漏掉条款发现

位置：`backend/app/api/static/js/view-model.js:209`（evidenceDomain）、`:289`（findingsForAgent）。

原因：evidenceDomain 返回 documents/work_orders/lease/billing；findingsForAgent 把结果直接与 Agent key lease/billing/property 比较。documents 与 lease、work_orders 与 property 永远不能相等。

实际复杂报告中：3 条合同条款归为 documents，工单“相关工单 3 条，未关闭 1 条”归为 work_orders。现有 JS 的各节点发现数量为 lease=1、billing=1、property=0。完整报告仍能看到这些 finding，因此是节点详情丢失，并非后端没有查到。前缀启发式已披露，不足以解释这些固定类别也未连通。

修复验收：区分证据展示分组和 Agent 归属，至少正确处理 documents→Lease、work_orders→Property；同时避免跨领域证据较多时用多数票误归属。有明确 source/subtask/capability 的应优先用可信来源关联；不能确定归属则标“未关联”而不是隐藏。当前 A-301 至少应看到 Lease 的租约与 3 条合同摘录、Billing 金额、Property 工单结果；与全量报告对应且不重复编造。

## 4. 发现 U3 [P2] 异常/缺字段报告会把规划、核验、报告画成绿色成功

位置：`backend/app/api/static/js/view-model.js:296`（planNode）、`:316`（verifyNode）、`:325`（reportNode）。

原因：只要 run.report 为真，plan 默认 success；verify 把缺失数组当空，再把无冲突/缺失/失败判 success；report 没有 requires_human_review=true 就判 success。没有判断 report.error、必要字段是否存在，verify 也未把 verdict=insufficient 或叙述不一致等情况作为明确约束。

直接执行现有 JS 的反例：

```json
{"status":"failed","report":{"error":{"code":"internal_error","message":"injected test error"}}}
```

得到 plan=success（规划已完成）、verify=success（未发现冲突）、report=success（报告已生成）。这个形状来自 WorkflowService.submit 的 AgentError 持久化分支，并非一个从未出现于生产代码的臆造协议。报告摘要能显示错误，不抵消首屏协作图的错误绿灯。

修复验收：显式区分无事件/字段未提供、失败、部分完成与成功。report.error 不能显示为成功报告，缺少核验依据不显示“未发现冲突”。缺失数组与明确空数组区分；verdict/conflicts/missing/failures/叙述校验/人工复核等共同决定展示，不能只数三组数组。补充真实异常形状、旧记录缺字段、insufficient、正常支持与存在冲突的映射回归。

## 5. 已处理的运行问题：8000 服务未加载新增静态挂载

审查开始时，8000 仍是此前 Codex 启动的 74604 进程：读取新 index.html 返回 200，但 `/static/js/app.js`、`/static/css/workbench.css` 均 404，用户无法正常用新版页面。

核对进程完整命令行确为本仓库 Python/uvicorn/8000 后，Codex 仅重启该预览服务，新进程 74624。随后 `/`、JS、业务 CSS、Tabler CSS、`/api/meta` 均 200 且 MIME 正确。没有修改源码、删除运行库或批准用户原有草案。

此运行接线问题已处理，不计入 U1–U3 的待修代码项。交付时应说明静态挂载变更需要重启服务，不能只给用户一个仍返回 404 的旧进程地址。

## 6. 评价与当前进度

这次美化有实际完成度：真实复用 Tabler、本地固定资源及许可/哈希齐全、HTML/CSS/JS 拆分、默认规则演示标识、正常/部分完成显示、报告 tabs、审批意见、网络错误与详情请求序号等都已实现。现有 403 项 Python 回归主要验证后端和静态装配，不能覆盖新增的 JS 领域映射；本轮三项反例说明还缺前端行为测试。

**建议保留现有版式，先做一次小范围 U1–U3 返修，无需重做页面或引入 React。** 窄屏协作区排在表单/历史之后、产品文案过多暴露字段名，可作为体验改进，暂不与真实性问题同级阻塞。

Task 027 状态：已实施、自检通过、独立复查待修。项目仍为可演示原型/版本候选；Z1–Z3、独立模型配置、完整处置建议、PostgreSQL/真实模型正式评测继续独立管理。本轮审查不关闭这些任务。
