# 版本候选修复复查（Task 017）

- 日期：2026-11-07（Asia/Shanghai）。
- 用户请求：DeepSeek 说已修复，继续查找实际问题。
- 代码基线：`main` / `bf30dd5`，检查开始时工作区干净，与本地 `origin/main` 一致。
- 审查范围：`041b2c5..bf30dd5` 的变更、上轮反例、修复后的边界场景。
- 结论：**上轮主要反例已有实质修复；仍有 4 项 P1 和 3 项 P2 问题，本次不能确认全部修复完成。**
- 本轮只检查、运行验证和归档文档，未修改业务代码，未安装依赖，未调用外部模型或 PostgreSQL，未提交或推送。
- 本次为用户临时要求的独立复查，不恢复逐任务 Codex 审查流程。

## 1. 修复核实结果

使用 `D:\anacada\envs\commercial-agent\python.exe`，在 `backend/` 执行。

| 验证 | 本次实际结果 |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py'` | 238 tests，16.007 秒，OK |
| `python tests/smoke_agent_contracts.py` | 57 项检查通过 |
| `python -m app.cli investigate --backend sqlite` | exit 0，原 snapshot 装配异常未再出现，实际调用 4 次工具 |
| F1：互换应收/已收/未收三个事实字段 | 判失败，0/3；原来会给满分的问题已修正 |
| F2：H06/H11 的三个基线 | 均返回 denied，均按预期通过，原状态不公平计分已修正 |
| F4：修正租金变体中首次失败、补查成功 | 两次调用，最终 supported、complete，当前 failures/missing 为空 |
| F5 + 审批意见：两级批准 | request_id 与台账一致、status=approved，两次 reason 均持久化 |
| S1：已批准 v2 后以 v999 重放 | 抛 DraftVersionMismatchError |
| S2：实际 SQLite 装配 | PRAGMA query_only=1 |
| F6：首轮非法 LangChain 工具调用 | failed / model_error，未再被当作空答案成功 |
| F7、F8、S3、S4 的新增回归 | 已纳入并通过 238 项测试；下面额外检查发现它们未覆盖的边界 |

重新在内存运行三个 `evaluate(..., split='heldout')`，未覆盖历史报告：

| 基线 | 可计分题 | 通过 | 未自动计分 | 模型调用 |
|---|---:|---:|---|---:|
| A_deterministic | 30 | 20 | H25、H26 | 0 |
| B_single_agent | 30 | 21 | H25、H26 | 0 |
| C_multi_agent | 30 | 23 | H25、H26 | 0 |

与当前 README 报告一致。这仍是离线规则/工具执行路径的结果，不是实测模型质量对照。修复有价值，但 238 项测试通过不能覆盖下面的额外反例。

## 2. 仍需修正的问题

编号 R1–R7 仅在本报告内使用，不与前一轮 F/S 编号混淆。

### R1 [P1] 复用持久 thread_id 时，旧结果可以掩盖本次越权失败

- 位置：`backend/app/orchestration/investigation.py:81`、`:302`、`:523`、`:850`、`:864`。
- 原因：results/failures 是追加 reducer。再次 `investigate()` 传 `results=[]` 不会清除已有 checkpoint 结果；新的计划仍使用相同 subtask_id。核验又将“历史中有同 ID 成功结果”视为当前失败已解决。
- 本次复现：
  1. 使用临时控制面、`v_oct_rent_corrected`、星汇主体，以 thread `shared_audit_thread` 调查 A-301 账单，得到 supported / 未收 17280.00。
  2. 换一个新的 bundle，使用仅有金鹭范围的 `principal_finance_jinlan`，复用同一 thread，再调查星汇 A-301。
  3. 新工具 trace 确实是 `denied / project_scope_denied`；最终结果却是 `supported`、`failures=[]`，报告仍包含星汇的应收 51840.00、已收 34560.00、未收 17280.00。
- 影响：持久化状态可绕过本次工具授权结果；同主体的失败重跑也可能返回旧数据并误报成功。
- 边界：本次通过核心 Investigator 公共方法及显式 thread_id 复现；当前 HTTP 创建运行时自动分配新 thread_id，未声称 HTTP 请求体能注入 thread_id。
- 修复验收：明确“新运行”与“恢复”的语义；对已有 thread 的新 investigate 拒绝、分配新 run，或执行经过授权且完整的状态重置。checkpoint 绑定主体、租约、运行身份；禁止用旧 run 的结果消除新 run 的失败。测试跨主体复用、换租约、同主体重跑失败、正常审批恢复。

### R2 [P1] 旧运行记录升级后没有项目标签，详情查询默认放行

- 位置：`backend/app/api/service.py:100`、`:172`。
- 原因：旧库迁移只新增 project_ids_json 列，没有回填；`get()` 对 `None/[]` 的记录跳过范围校验，形成默认放行。list() 却会过滤掉它们，列表不可见并不代表详情安全。
- 本次复现：按修复前 schema 新建临时 runs 库，插入星汇运行；交给当前 RunIndex 自动迁移。金鹭主体查询已知旧 run_id，`get_run()` 返回星汇报告，记录 scope=[]，但 list_count=0。
- 影响：修复前创建的本地运行仍然跨项目可读，旧数据恰是该迁移应保护的对象。
- 修复验收：缺失范围默认拒绝；迁移时从可信主体/目标租约等来源回填，无法可靠回填则隔离。覆盖真实旧 schema 升级后的 detail/traces/decide，空授权主体以及 NULL/空列表记录。不能通过“列表已经过滤”代替详情授权。

### R3 [P1] 把创建者全部授权项目当作报告所属项目，扩大读取范围

- 位置：`backend/app/api/service.py:419`、`:173`（异常记录路径 `:287` 也采用相同标签口径）。
- 原因：记录 project_ids 使用服务主体的完整授权集合，而不是报告实际数据所属项目；随后任意一个项目交集都能读取整份报告。
- 本次复现：使用服务端支持的可信 `project_ids={'prj_xinghui','prj_jinlan'}` 配置提交 A-301 的星汇账单调查。随后只授权金鹭的主体，能读取该星汇报告，因为 record_scope 被写成两个项目。另外在内存 fixture 副本中实际授予创建者两个项目，再经默认 WorkflowService/调查装配复现，结果相同，创建者的运行上下文与服务范围均为两个项目。
- 边界：多项目权限通过可信配置或内存 fixture 副本注入，未修改仓库 fixture，未声称请求体能扩权；现有默认主体主要是单项目，因此原回归没有暴露此问题。
- 修复验收：分别保存创建者授权范围与报告数据范围；按目标租约/证据计算实际项目集合，明确多项目报告是要求完整范围还是做安全分段。测试多项目管理员生成单项目报告、跨项目汇总报告、单项目读者访问。

### R4 [P1] 未签署草案和正式合同版本混合进入调查结论

- 位置：`backend/app/rag/catalog.py:41`；`backend/app/rag/library.py:126`、`:135`、`:143`；`backend/app/agents/lease/agent.py:117`。
- 原因：DocumentMeta 记录了 document_status，但装配、索引、检索和返回条款没有执行状态策略；Lease Agent 只限定 document_id，不限定有效/签署版本。documents/indexed 字典还以 document_id 单独为键覆盖元数据，但底层索引保留多个版本，二者口径不同。
- 本次复现：临时目录登记同一 A-301 文档的 v1 signed（递增 5%）和 v2 draft（未签署草案，递增 20%）；使用正式 Lease Agent 和受控工具查询“合同租金递增百分之二十”。报告首项引用 v2 draft，将其作为一般“合同第 1 页 5.2 条”finding 输出，没有结构化签署状态或适用性提示；v1 也同时作为一般合同事实输出。
- 影响：文档真实存在且属于正确租约，也不能据此当作生效依据；上轮文档归属修复没有完成“签署/草案、版本适用”边界。
- 修复验收：规定默认检索的有效状态/版本；显式比较草案时作为草案证据单列，不能与已签署条款等同。目录/索引/引用共同绑定 document_id + version + status + 适用范围，增加签署版、未签署新草案、历史失效版本的对照。

### R5 [P2] 工具调用后模型返回空回答，仍标记任务成功

- 位置：`backend/app/runtime/tool_loop.py:188`。
- 原因：空回答检查要求同时 `not executions and not evidence`。只要前面调用过工具，就放过最后一轮空输出。
- 本次复现：Fake 的第一轮正常执行 billing.arrears.calculate；第二轮 `ModelTurn(text='')`。实际 `status='success'`、`stop_reason='final_answer'`、answer 为空、13 条 evidence、1 次工具调用。
- 影响：有取数证据不等于完成用户问答；上轮“空输出不得伪装成功”的修复只覆盖了无前序工具的情形。
- 修复验收：定义最终答案完成条件，空最终输出应有限重试或明确未完成；如要返回纯结构化工具结果，使用显式结果类型和状态，而不是空 answer + final_answer。测试正常工具后空输出、失败工具后空输出、有内容最终输出。

### R6 [P2] 有账单冲突时，可恢复的工单失败不会进入补查

- 位置：`backend/app/orchestration/investigation.py:489`。
- 原因：补查仍被限制为 verdict == insufficient；账单差额将总体 verdict 提升为 conflicting，其他子任务的可恢复错误随即失去补查机会。
- 本次复现：使用默认 A-301 变体，调查“核对账单和空调工单”；Property 第一次返回可重试 tool_timeout，第二次会成功。结果 calls=1、revision=0、verdict=conflicting、completeness=partial，第二次没有发生。
- 影响：上轮正确恢复测试使用了无租金差额的变体，但主要演示场景恰有差额；默认场景的补查能力不完整。报告仍如实标为 partial，因此本项未把失败误报完整。
- 修复验收：基于当前未解决且可重试的子任务、预算和 revision 上限决定是否补查，不以其他领域的冲突阻止恢复；冲突本身保留。覆盖“差额 + 首次超时后恢复”和“差额 + 永久失败”。

### R7 [P2] 证据只按条款号子串关联，混入其他版本的引用

- 位置：`backend/app/orchestration/investigation.py:744`。
- 原因：finding 的 evidence_ids 采用 `clause_id in evidence_id` 匹配，忽略 document_id、version、page，甚至可能将 5.1 与 5.1.1 混合。
- 本次复现：R4 两个版本均有 5.2 条；v2 的“20%”finding 同时绑定 `doc_xh_a301_contract#v2#p1#5.2` 和 `doc_xh_a301_contract#v1#p1#5.2`，v1 的“5%”finding 也绑定这两个 ID。
- 影响：source 声称某一版本，证据集合却指向相互矛盾的版本，审计时不能可靠判定哪个原文支持哪个结论。
- 修复验收：按完整 chunk_id 或 document_id/version/page/clause_id 复合键精确关联。即使在显式版本比较场景中，同条款编号的两个 finding 也要分别绑定自身证据；增加 5.1/5.1.1 和不同文档相同条号测试。

## 3. 进度判断与后续顺序

1. **本轮修复不是无效工作**：金额字段绑定、预期拒绝评分、SQLite/RAG 接线、单次补查状态、审批 ID/版本/意见、基础非法模型响应处理均已改善，独立复现结果如上。
2. **第一优先是 R1–R4**：这四项会造成旧数据/其他项目数据混入当前输出，或把草案作为正式依据。先修授权、持久状态边界和证据适用性。
3. **随后处理 R5–R7**：明确任务成功定义，补齐主要冲突场景下的恢复，以及精确引用关联。
4. **真实集成仍未完成**：本次没有真实模型或 PostgreSQL 验证。调查装配仍是规则 Planner + 工具代理；评测的 B 仍是规则多工具循环，evaluate 绑定离线模型。真实模型注入、B/C 运行入口可在无密钥时先用 Fake/适配器测试开发；实际调用验证才依赖凭据。不要把尚未实现的装配统称为“只缺 API Key”。
5. 当前 README 已披露多项真实服务限制，保留这些说明。完成上述修复后仍应把项目标为版本候选，直至实际完成真实集成与对应验收。

## 4. 本轮工作区与安全边界

所有攻击性/越权反例只访问本项目合成数据；控制面、旧 schema 迁移、合同 PDF 均在临时目录，未操作真实客户数据。完整 unittest、契约检查和离线评测未新增业务源码；离线评测直接在内存运行，历史报告未被覆盖。

本轮归档文件见 Task 017 Prompt。未自动执行修复或 Git 操作。建议 DeepSeek 逐项核对本报告，按验收标准补缺口，不以测试数量或“全部修复”自述代替行为证据。
