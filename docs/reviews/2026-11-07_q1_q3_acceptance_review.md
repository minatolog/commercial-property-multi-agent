# Q1–Q3 交付独立复查（Task 025）

- 日期：2026-11-07（Asia/Shanghai）。
- 依据：用户发送 DeepSeek 完成说明截图，要求结合此前上下文核实交付。
- 代码基线：`main` / `f2cc67d`；开始时工作区干净。`git ls-remote origin refs/heads/main` 确认 GitHub main 同为 `f2cc67de844a0c4cf00c2af6a2d549ce22601f82`。
- 结论：**Q1 指定反例通过；Q2 的 B 基线与直接目标请求已有修复，但默认 ask 装配和 Single 失败结果判断仍有两个 P1；Q3 原金额写反/错误结清反例通过，默认 CLI 的可信金额展示尚有 P2 接线缺口。**
- 本轮未改业务源码，未新增真实模型请求或费用，未连接 PostgreSQL，未提交或推送。

## 1. 截图与实际仓库一致性

截图中的提交链与仓库一致：

1. `66ded2b`：token 闸门、共用 TaskScope、资金结论及回归测试。
2. `158ab55`：Task 024 文档和历史 Task 022/023 入库。
3. `f2cc67d`：检查点 hash 回填。

因此这次已看到实际的新代码。截图中“22 条独立复验 22/22”为 DeepSeek 的报告；本轮 Codex 另行运行下述测试和反例，不将截图里的复验次数计为自己的验证结果。

## 2. 本轮独立验证

解释器：`D:\anacada\envs\commercial-agent\python.exe`，测试在 `backend/` 执行。

| 项目 | 实际结果 |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py'` | 399 tests，22.469 秒，OK（skipped=1） |
| `python tests/smoke_agent_contracts.py` | 57 项通过 |
| scripted 调查 CLI | exit 0、conflicting、failures=[]；模型 6 次、工具 4 次、exceeded_tokens=0 |
| Q1：token 零额度 | 实际物理调用 0 次 |
| Q1：上限 5，首次响应 10 tokens，再进入图补查 | 实际物理调用 1 次，tokens=10、exceeded_tokens=5、tokens_exhausted=true |
| Q2：B 基线指定 A-301，模型调用 B-101 | status=failed、facts={}、insufficient_evidence，未产生错误归属事实 |
| Q3：三项金额互换 | fund_check=mismatch、passed=false |
| Q3：“应收 52596.00，未收 0.00，已经全部结清” | fund_check=mismatch、passed=false |

离线 heldout 在内存重跑，没有覆盖历史报告：scoring-v3.3 下 A 20/30、B 21/30、C 23/30，均零模型调用。资金结论 verified 数为 9、11、11；C 另有 3 题 unverified，已在新报告结构中单列。

上述结果支持关闭原 Q1 和认可 Q3 的指定反例修复。资金结论机械解析的已知边界仍需如实披露，不等于任意自由叙述都能自动验证。

## 3. 尚未覆盖的入口问题

### Z1 [P1] 默认 ask 入口未传目标，业务查询被当成 explain，范围约束失效

- 位置：`backend/app/single_demo.py:81`、`:129`；`backend/app/cli.py` 的 ask 参数和 `_cmd_ask()`；`backend/app/agents/single/agent.py:108`。
- 原因：SingleToolAgent 已接入 TaskScope，但默认 build_single_bundle 仍只传 `payload={"question": question}`；没有 lease_id/unit_id/lease_ids，ask 也没有明确目标参数或可信目标解析。因此“A-301 欠多少”的业务查询会得到 mode=explain，模型调用不受本次目标约束。
- 本次复现：完整经过 `cli.main(['ask', 'A301现在还欠多少', '--provider', 'fake'])` 的参数解析、装配、Runtime 和摘要输出，只替换 Fake 模型响应；在内存 fixture 给可信主体星汇/金鹭两项目权限。模型调用 B-101 账单，却回答“A301 应收 0、已收 0、未收 0，已经结清”。实际 **exit=0、status=success、warnings=[]**。
- 边界：工具没有越过主体项目授权，错误仍是“有权限但错目标”。此前 B 基线通过，是因为评测层显式把 lease_id 放进 payload，默认 CLI 没有这一步。
- 修复验收：ask 与 B/领域路径共用可信目标装配；可提供明确目标参数，并在自然语言业务查询时解析/确认目标，不能无声进入纯说明模式。测试必须经过真实 CLI main/装配路径，覆盖换目标、缺省目标、合法纠正和纯说明问题，不能只手工构造带 lease_id 的 AgentRequest。

### Z2 [P1] 失败工具调用进入 accepted 列表，零事实的有目标请求仍成功

- 位置：`backend/app/agents/single/agent.py:156`–`:159`、`:182`。
- 原因：accepts_output 只检查实体，失败 ToolExecution 的 data 为 None/{} 时没有实体冲突，于是也加入 accepted；最低取证判断只看 `not accepted`，没有要求执行成功、事实有效。
- 本次复现：手工明确目标 A-301（mode=targeted、requires_evidence=true），模型调用 billing.statement.read，参数除合法 lease_id 外含未知字段 unexpected。ToolExecutor 正确返回 error（attempts=0），模型随后说“已经核对，没有问题”。最终 **status=success、error=null、facts={}、evidence=0**，输出 tool_calls 明确包含 status=error。
- 影响：即使解决 Z1 并正确传入目标，失败工具仍可能冒充已有取证；这是成功判定错误。
- 修复验收：以成功且属于当前目标的有效业务结果/事实/证据满足最低契约，失败调用只保留审计，不能满足完成条件。覆盖 schema 错误、权限/范围拒绝、超时、全部失败、失败后合法纠正；合法的零条工单/零欠费应继续被接受。

### Z3 [P2] 可信资金结论已生成，默认 CLI 摘要仍只展示原始模型答案

- 位置：`backend/app/agents/single/agent.py:228`–`:229`；`backend/app/cli.py:403`–`:411`；`_investigation_payload()`。
- 原因：Agent 有 authoritative_answer/fund_conclusion/fund_check，调查 report 有 authoritative_amounts；默认摘要没有投影这些字段。ask 的 answer 仍直接取原始模型文本。
- 本次复现：Fake 取到正确 A-301 账单后将三个金额写反。资金校验正确标 mismatch，ask 返回 exit=2、status=partial 并给出警告，这是已有改善；但默认 JSON 的 answer 仍是写反金额，既无 authoritative_answer，也无 fund_check。scripted investigate 默认摘要也没有 authoritative_amounts。
- 边界：本项没有把错误回答标为完全成功，故为 P2 展示/接线问题；`--full` 可以看到完整内部结果，不能代替默认用户路径的清晰展示。
- 修复验收：默认摘要展示可信资金字段与渲染结果；原始模型叙述单独标注，核验状态/未验证/冲突可见。ask 和 investigate 默认/完整输出对照测试，避免仅验证 Agent 内部字段存在。

## 4. 建议下一步与项目进度

这次可以确认 token 发送闸门、B 的显式目标范围、结构化资金结论及指定评分反例有进展。**Q1 可按本轮定义关闭；Q2 仍需完成 Z1/Z2；Q3 原指定反例通过，Z3 可一并收尾。** 不需要重新做 Runtime/Graph/RAG 基础架构。

先集中修正上述 Single/CLI 入口，随后推进已经列明的 PostgreSQL 实机、正式真实模型 heldout/重复测量、人工量表和独立模型配置策略。项目仍在 MVP 集成与最终验收阶段；399 个测试与一条真实模型样例不能替代完整交付验收。

本轮同时发现 docs/README.md 重复登记 022/023，归档时删除重复的旧状态行，保留唯一编号及原归档文件。没有删除历史审查内容，也没有实施 Z1–Z3 的业务修复。
