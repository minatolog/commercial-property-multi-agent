# 给 DeepSeek 的返修 Prompt：Task 029 协作工作台 U1–U3

请在当前 `D:\commercial-property-multi-agent` 仓库直接完成本次返修，实现、测试、自检并归档后汇报，不要仅回复方案。

目标：保留 Task 027 已完成的 Tabler 工作台，修复 Task 028 独立复查确认的 U1–U3，让协作图、节点详情、报告与调用记录准确反映后端事实。本轮是小范围修复，不重新设计页面，不开启项目其他工作包，不自动提交或推送 Git。

## 1. 先读依据，确认真实起点

完整阅读：

- `docs/reviews/2026-11-10_task027_ui_acceptance_review.md`（本轮缺陷和验收依据）；
- `docs/architecture/CURRENT_BASELINE.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`；
- `docs/README.md`、适用的 `AGENTS.md`（若存在）；
- `docs/handoffs/DEEPSEEK_TASK027_MULTI_AGENT_UI_PROMPT.md`；
- `backend/app/api/static/js/view-model.js`、`js/components/graph.js`、`js/components/report.js`、`js/app.js`；
- `backend/app/api/service.py`、`backend/app/orchestration/investigation.py` 中与报告、失败、恢复和 Trace 相关的实际输出契约；
- `backend/tests/test_api.py` 和现有相关测试。

先检查 Git 状态、分支、HEAD 与未提交变更。Codex 上轮审查时为 main / 8569cc2，Task 027 与审查文档未提交；这是历史快照，实施时以实际 Git 为准。保留已有成果，不使用 reset、clean、整目录覆盖或删除来制造干净工作区。

全局编号 029 已为本次返修 Prompt 登记。沿用 029 归档追加实施记录，保留原始用户 Prompt；若仓库已发生编号冲突，先核对实际历史再明确记录调整，不能覆盖别的任务。

## 2. U1 / P1：失败 Agent 不能显示成未调用

已确认根因：`agentParticipation`、`traceRows` 和规划数量只依赖 `report.agent_results`。后端会把失败子任务放在 `report.failures`，使它们没有 Agent 归属、subtask ID、错误与工具记录；节点详情错误断言“本次问题没有规划到该领域”。

必须先复现：使用 A-301 的跨领域问题，`max_tool_calls=1`、`with_approval=false`。上轮实际返回 status=failed、verdict=insufficient，billing 与 property 的 failure.error_code 为 budget_exhausted，前端却显示 not_called。问题措辞和 API 参数以当前真实接口为准，不伪造结果。

修复要求：

1. 在展示模型层集中建立子任务/能力/Agent 的关联，供协作图、详情、Trace 表格与筛选共同使用；不要各组件复制一套推断逻辑。
2. 对照实际契约，合并有效结果、当前未解决失败及可关联 Trace。失败须保留 subtask ID、能力、错误码、后端实际提供的错误信息和工具尝试；没有工具执行也可有失败记录，不能因此判未参与。
3. 明确区分“确实未参与”“失败”“部分完成”“成功”和“信息不足”。不能只因 agent_results 没有一项就断言没规划；Trace 单独存在且无法确认终态时，不猜成功或失败。
4. Trace 的 Agent/能力归属不能依赖结果数组顺序，也不能靠 subtask ID 字符串硬编码猜测。关联信息不足时显示未知，保留原始记录。
5. 处理补查/重试：先核对后端如何表达当前失败与历史失败，不凭数组顺序猜最终状态。补查成功后的旧失败不能覆盖当前有效成功；失败历史仍应可审计。一个领域有多条子任务时保留它们的记录，不用 find 第一条静默丢弃。
6. 修正规划卡数量语义：有真实计划字段则据实计数；没有时只能标“已记录子任务”等可证明的含义，对结果和失败按真实 subtask ID 去重，不能把成功数冒充规划总数。
7. 节点详情、协作图、调用记录筛选保持一致，删除或改正“只认 report.agent_results”等错误注释和产品文案。

## 3. U2 / P2：条款和工单发现必须关联到正确节点

已确认根因：evidenceDomain 的 documents/work_orders 是证据展示分组，而 Agent key 为 lease/billing/property；findingsForAgent 直接比较，导致匹配失败。

上轮实际复杂报告有 6 条 finding：租约 1 条、合同条款 3 条、账单 1 条、工单 1 条；节点却仅显示 Lease=1、Billing=1、Property=0。完整报告仍有数据。

修复要求：

1. 分开“证据展示分组”和“finding 的 Agent 来源”，不破坏现有证据页分组。
2. 优先使用当前协议真实提供的 source、subtask、capability、Agent 结果内证据等明确关联。先看字段结构，不能假设后端已经提供不存在的来源字段。
3. 必须回退到证据分类时，集中定义 documents→lease、work_orders→property 等关系并说明这是展示推断；不能直接比较两套 key。
4. 未知前缀/无证据不自动归 Lease；跨领域、多来源或无法可靠归属的 finding 显示“跨领域/未关联”等准确状态，并在报告或明确的未关联区域可见。不要靠多数票把跨领域发现归给错误 Agent，也不要为了凑数复制到全部节点。
5. 这次 A-301 fixture 应能在 Lease 看到租约和三条条款、Billing 看到账单、Property 看到工单；ID、页码、原文与总报告一致。计数属于当前 fixture 的回归期望，不能在实现中硬编码 6 条或上述文本。
6. 节点详情的归属说明与实际算法一致，不继续笼统写“按证据 ID 前缀归属”来描述使用了明确来源的记录。

## 4. U3 / P2：缺失数据与异常不能默认绿色成功

现有 planNode / verifyNode / reportNode 因 report 对象为真、缺失数组转空、未提供 requires_human_review 就按 false 处理，把异常也画成成功。

必须复现后端 AgentError 分支实际持久化的结构形状：

```json
{"status":"failed","report":{"error":{"code":"internal_error","message":"injected test error"}}}
```

上轮 JS 对此显示“规划已完成 / 未发现冲突 / 报告已生成”且全部绿色。

修复要求：

1. 建立清晰、保守的状态判定：显式成功、部分完成、失败、未执行、数据不足分别处理；可复用小型映射函数，避免组件各自猜测。
2. report.error 不能被当作有效成功报告；缺少核验字段不能宣称“未发现冲突”。区分字段缺失、类型无效和明确空数组，兼容历史记录时展示未知/信息不足，不抛出页面异常。
3. 据当前实际契约联合判定 verdict、completeness、conflicts、missing_information、当前 failures、叙述一致性/资金核验及人工复核标记，不能仅数三个数组。
4. 区分“报告文档生成成功”和“结论得到支持”：有完整但证据不足/冲突的报告可以显示已生成，但应同时明确需复核/证据不足，不能出现暗示业务核验通过的绿灯。
5. 不把整个 run.status=failed 机械传播成所有历史步骤失败。某步骤已有明确完成证据则据实显示；没有事件证据时不臆造规划完成、核验通过或精确执行过程。
6. 不添加伪造逐节点时间、实时进度、思考链或百分比，继续使用等待态和结果回顾模式。

## 5. 修改范围与兼容性

- 保留 Tabler 1.7.4 本地资源、许可、现有版式、FastAPI 同源静态架构和模块拆分；无需引入 React、Langflow 服务或大型构建链。
- 优先修改 view-model 和必要渲染组件；确需改后端输出时，先证明当前数据无法表达所需关联，采用最小兼容扩展并补契约回归，不能为了前端绿灯删失败或改变业务结论。
- 不改 Agent 算法、预算/权限规则、资金计算、审批语义、数据库结构或评分标准；不重建数据库，不调用付费模型。
- 保留两级审批、驳回、历史选择、请求竞态保护、工具筛选和网络错误处理。批准草案仍不执行真实业务写操作。
- Z1–Z3、独立模型配置、完整处置建议、PostgreSQL 实机、正式真实评测仍属其他待办，本轮不能写成已解决。

## 6. 必须完成的验证

添加能真正运行当前 JavaScript 模块的行为回归，优先使用环境已有的轻量测试能力；不能只在 Python 中检查源码包含某字符串，也不能把算法抄一份进测试来“验证”副本。测试说明写清运行命令与所需运行时，不为本任务引入大型前端框架。

至少覆盖这些不同语义（可合理参数化，不要求每项独立文件）：

| 场景 | 期望 |
|---|---|
| 正常单领域 | 只有真实相关领域参与，其余未参与 |
| 正常多领域 | Agent、子任务数量语义、发现及 Trace 归属一致 |
| 工具预算耗尽 | 失败领域可见，保留错误和实际工具尝试 |
| 权限拒绝 / 超时 | 不显示未调用，不把失败历史隐藏 |
| 补查成功 / 多子任务 | 当前终态准确，旧失败可追溯，不丢其他子任务 |
| 租约、条款、账单、工单发现 | 分组与 Agent 归属正确，总报告数据不丢失 |
| 跨领域、未知证据、无证据 | 不误归、不重复编造，未关联项可见 |
| report.error / 报告缺字段或类型无效 | 无虚假成功，无渲染崩溃 |
| insufficient / conflicting / 叙述不一致 | 明确证据不足、冲突或复核状态 |
| 明确 supported 且核验字段完整 | 可显示正常成功，避免一律降级为未知 |

保留至少一个从真实 API 输出进入现有 JS 模型的复验，覆盖复杂调查与预算失败。其他难以稳定触发的异常可用符合真实契约的结构化 fixture，报告明确区分实际运行与构造测试，不假称真实运行发生了异常。

在 `backend` 目录使用项目环境运行：

```powershell
& 'D:\anacada\envs\commercial-agent\python.exe' -m unittest discover -s tests -p 'test_*.py'
& 'D:\anacada\envs\commercial-agent\python.exe' tests/smoke_agent_contracts.py
```

403 tests / skipped=1、57 项契约是上轮基线，新增测试后如实报告实际数量；未运行不能复制旧结果。

如工具可用，进行真实浏览器验收：正常复杂调查、预算失败、节点详情/调用筛选，以及两级批准与驳回；桌面和窄屏无横向溢出、控制台无新增错误、资源正常加载。API 测试用独立临时控制面，不审批或修改用户现有任务。异常页可用明确标记的测试 fixture，不污染正常历史。

保存本轮新截图到 `docs/reviews/task029_screenshots/`，准确注明哪些来自真实 API、哪些来自注入 fixture；旧截图不能冒充新证据。若浏览器工具不可用或中止，明确剩余视觉验收，不绕过工具限制，不因此放弃可完成的实现和非浏览器测试。

预览服务需要重启时先确认对应仓库进程，保留数据；核实 `/`、业务 JS/CSS、Tabler 资源均 200 且 MIME 正确，不留下只读到新 HTML 的旧服务。

## 7. 文档和交付

1. 在 `docs/prompts/05_frontend/2026-11-10_029_ui_mapping_fixes.md` 追加实际实施记录，保留原始用户 Prompt 和 Codex 编写阶段记录。
2. 新建 `docs/reviews/2026-11-10_task029_ui_mapping_fix_report.md`，按 U1/U2/U3 分别写复现、根因、修改文件、修复前后结果、测试命令与证据、剩余限制。
3. 同步 docs 索引、开发日志、问题记录、Git 检查点、当前基线和路线图。U1–U3 按实际证据更新；保留 Task 028 审查与 Task 027 自检原文，通过新报告关联修复，不回写旧报告伪造当时已通过。
4. 结束运行 `git diff --check`，检查 UTF-8、Markdown 围栏/新增链接、编号及敏感信息；汇报实际分支、HEAD、修改范围和未提交状态。
5. 不自动提交或推送；提供 GitHub Desktop 可用的 Summary 和 Description 建议。

最终回复请先给 U1–U3 各自“已修复 / 未修复 / 部分修复”的证据，再列测试实际结果和待办。不以 Python 回归全绿替代前端行为验证，不宣称整个项目已经完成。完成本次范围后停止，等待用户决定下一项任务。
