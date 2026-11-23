# 复查 Prompt：Task 033（MCP 工具网关，stdio 第一版）独立复查

- 编写：2026-11-23（Asia/Shanghai），Claude Code（任务拆分、dev_loop 调度与复核者）。
- 给：与实施者**不同**的模型或人（DeepSeek / Codex / 人工）。
- 性质：**只读复查**。不修改源码、测试、配置；需要做实验时，在仓库外的临时目录或仓库外的代码副本里做。

> 实施方式与以往不同：本任务拆成 033A / 033B / 033C 三张任务单，由 `scripts/dev_loop/` 执行——编码方是 DeepSeek（`deepseek-flash`），审查方是 Claude；每张都在第 1 轮通过审查。之后 Claude Code 又做了复核（变异测试、原始 stdio 实测），并**自己补了一个测试**（见 §4.5）。所以编码方、dev_loop 审查方、复核者都不是“独立复查者”。下面的“已知风险点”只是起点，不是复查范围的上限。

---

## 0. 硬性约束

1. **不调用付费模型接口。** 本任务不涉及模型；任何命令都不要带 `--planner-provider deepseek` / `--model-provider deepseek`。
2. **不提交、不推送、不切分支、不 stash、不改工作区里的文件。** 需要改代码做实验（例如删掉一行看测试会不会失败）时，先把 `backend/` 复制到仓库外再改。
3. **不碰 `data/`**，不动 `tools/flowise/` 和 `.gitignore` 的 Flowise 三行。
4. 环境：`D:\anacada\envs\commercial-agent\python.exe`（Python 3.11）。Git Bash 里的 `python` 是占位程序，必须写完整路径；在 `backend/` 下运行，设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。`mcp==2.3.0` 已安装，**不要再 `pip install` 任何东西**。
5. 报告新写的文本文件用 LF。

## 1. 复查对象

- 本次改动**都已提交**，可以直接用 git 看：
  - `483560a` 三张任务单；`083335a` 033A；`4422a74` 033B；`57a0921` 033C。
  - 中间的 `e4bc85e` 只改了 `scripts/dev_loop/`（开发辅助脚本），**不在复查范围**。
  - 复查用的差异：`git diff 483560a 57a0921 -- . ':(exclude)scripts/dev_loop'`（21 个文件，约 3000 行新增）。
- 开始前确认 `git rev-parse HEAD` 为 `57a0921096d1b50d9dc8842676dbf6ac0240d295` 或其后只多了本 Prompt 的提交，且 `git status --porcelain` 除 `.claude/` 外为空。不一致就在报告里写明。
- 前置条件：原 Prompt 要求 Task 031 已通过独立复查（[报告](../reviews/2026-11-21_task031_repair_independent_review.md)，有条件通过，Z2 已处理）。

## 2. 必读材料

| 用途 | 文件 |
|---|---|
| 原始要求 | [`DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md`](DEEPSEEK_TASK033_MCP_GATEWAY_PROMPT.md) |
| 拆分后的任务单（与原 Prompt 冲突时以任务单为准，但**任务单本身也要审**：拆分有没有漏掉原 Prompt 的要求） | [`DEV_LOOP_TASK033A_MCP_CORE.md`](DEV_LOOP_TASK033A_MCP_CORE.md)、[`DEV_LOOP_TASK033B_MCP_SERVER.md`](DEV_LOOP_TASK033B_MCP_SERVER.md)、[`DEV_LOOP_TASK033C_MCP_DOCS.md`](DEV_LOOP_TASK033C_MCP_DOCS.md) |
| 实施记录 | [`prompts/04_agents/2026-11-23_033_mcp_gateway.md`](../prompts/04_agents/2026-11-23_033_mcp_gateway.md) |
| 代码 | `backend/app/mcp_gateway/`（`profiles.py`、`identity.py`、`results.py`、`server.py`）、`backend/app/config/mcp_clients/*.yaml`、`backend/app/cli.py` 的 `mcp-serve`、`backend/tests/test_mcp_gateway.py` |
| 被包装的执行层（未改动，但要读） | `backend/app/tools/executor.py`、`base.py`、`registry.py`、`backend/app/runtime/types.py`（`RESERVED_PAYLOAD_KEYS`、`ToolExecution`、`TrustedContext`）、`budget.py` |
| SDK | `D:/anacada/envs/commercial-agent/Lib/site-packages/mcp/`、`.../mcp_types/`（v2 版本线；low-level `Server`、stdio 传输、内存客户端） |
| 证据 | `docs/reviews/task033_evidence/`（`stdio_probe.py` / `.txt`、`unittest.txt`、`smoke.txt`） |

## 3. 自报数字（全部独立复跑）

| 项 | 自报 |
|---|---|
| 全量回归 | 651 tests OK（skipped=1）；033 之前为 610 |
| `tests/test_mcp_gateway.py` | 41 个测试（033A 29 个单元测试 + 033B 端到端 / stdio 冒烟 + 复核补充 1 个） |
| 契约自检 `tests/smoke_agent_contracts.py` | 70 项 |
| `python -m app.cli check` | exit 0 |
| `stdio_probe.py` | 输出与 `stdio_probe.txt` 一致（只有随机 `call_id` 不同） |

## 4. 复查清单

### 4.1 核心原则：执行器是唯一入口

1. `backend/app/mcp_gateway/` 里有没有任何绕过 `ToolExecutor.execute()` 的路径（直接 `invoke`、直接读 fixture / 仓库、自己做权限判断代替执行器）。
2. 白名单、权限、参数校验、保留键、预算、超时重试、输出校验、项目范围检查，是否**全部**仍由执行器完成；网关新增的检查（保留键预拦截、只读白名单）是否只会更严、不会更松。
3. 执行器、`runtime/types.py` 是否真的没改（`git diff 483560a 57a0921 -- backend/app/tools backend/app/runtime`）。

### 4.2 身份与参数

1. 身份只来自会话（档案 `principal_id` / `DEMO_PRINCIPAL_ID`），任何调用参数都不能影响 `AgentContext`。
2. **保留键只拦截顶层**：网关和执行器都是 `RESERVED_PAYLOAD_KEYS & set(arguments)`。请实测嵌套写法（例如把 `project_ids` 放进某个对象参数里）、大小写变体、别名字段名，确认是被 `input_model` 的 `extra="forbid"` 挡住，还是有漏洞。
3. 网关对保留键返回 `permission_denied` / `status=denied`，而执行器对同一情况返回 `invalid_tool_arguments`。任务单要求 `denied`，这是有意的语义差异——判断它是否合理、是否在文档里说清楚。
4. `DEMO_PRINCIPAL_ID` 可以把主体换成任意 fixture 主体（包括其它项目的审批人）。这是开发模式的设计，但请评估：stdio 第一版下这是否构成可利用的问题，文档里的“不可用于生产”提示是否足够醒目（stderr 提示、README、归档）。

### 4.3 协议与结果

1. 用 SDK v2 的写法是否正确（`Server(on_list_tools=..., on_call_tool=..., lifespan=...)`、`ServerRequestContext.lifespan_context`），有没有混入 v1 写法；对照已安装的 SDK 源码确认。
2. **SDK 自身的校验**：v2 的 `Server` 在调用处理器之前会不会按 `inputSchema` 校验参数、在返回后会不会按 `outputSchema` 校验 `structuredContent`？如果会，保留键 / 失败信封的测试测到的是网关逻辑还是 SDK 的拒绝？失败信封（`data=null`）在 SDK 校验下是否仍然合法？
3. 结果信封：只有执行器判定成功才是 `ok`；未知状态落到 `error`；`structuredContent` 与 JSON 文本同源；`isError` 与 `status` 一致。
4. 金额：全程十进制字符串，`outputSchema` 中声明为 `string`；找一找有没有任何路径会经过 `float`（包括 `json.dumps` 的默认行为、pydantic 的序列化模式）。
5. 证据是否原样带出（文档、版本、页码、条款号）——用 `document.search` 实际调一次看。
6. stdout 是否只有协议消息：除了正常调用，再试 CLI 参数错误、档案错误、运行期异常时 stdout 有没有混入其它输出。

### 4.4 档案、预算与会话

1. 档案的各种错误（缺失、禁用、未注册工具、非只读工具、多余字段、名称不一致）是否都在启动期失败、退出码非零、信息明确。
2. 只读约束（`READ_ONLY_TOOLS`）放在哪里、是否有两处定义需要同步维护；将来注册写工具时会不会被顺手暴露。
3. 预算按连接计算：同一连接内额度是否准确（包括被网关预拦截的调用是否消耗额度——判断哪种更合理）；`GatewayServer._sessions` 会随连接数增长，stdio 下影响多大、HTTP 版本会不会变成问题。
4. 别名：冲突检测是否完整；原名与别名调用结果是否等价。

### 4.5 测试有效性

1. 41 个测试有没有空断言、恒真断言、`skip`、只测了 helper 没测真实路径的情况。
2. 复核者做过的变异测试（自报：033A 4 项、033B 6 项全部被抓到，其中“网关异常当成功”是复核时补测试后才抓到）——请**在仓库外副本里**至少独立重做 3 项，并自己再设计 2 项复核者没做过的变异（例如：身份从参数读取、预算跨连接共享、`structuredContent` 与文本不同源）。
3. `TestMcpGatewayUnexpectedError` 是复核者补的，不在 dev_loop 审查范围内，请单独审一遍。
4. stdio 冒烟测试是否真的启动了子进程、是否在测试结束时可靠关闭（Windows 下残留进程）。

### 4.6 文档与证据

1. `stdio_probe.txt` 是否为真实输出：自己运行 `stdio_probe.py` 对比。
2. 归档、`backend/README.md`、`docs/README.md`、开发日志、问题日志、`CURRENT_BASELINE.md`、路线图对 033 的状态与数字是否一致；有没有写成“已通过”“已验收”。
3. Flowise 的 stdio 连接说明是否可操作（命令、工作目录、档案）。
4. 归档里“下一版 HTTP + OAuth 最大风险”的分析是否成立、有没有遗漏更大的风险。

## 5. 输出

写一份报告：`docs/reviews/2026-11-23_task033_independent_review.md`，参照 [`2026-11-22_task032_independent_review.md`](../reviews/2026-11-22_task032_independent_review.md) 的格式：

1. 头部：复查日期、复查者（模型名）、依据、代码基线（HEAD 与 `git status` 核对结果）、环境、复查方式、是否调用了付费接口。
2. **结论**：`通过` / `有条件通过` / `不通过`，一句话说明理由。任何能让外部调用方越过项目范围、伪造身份、或把失败当成功拿到的路径，都是`不通过`。
3. **独立验证结果表**：验证项、实际运行结果、与 §3 自报数字的对比。
4. 逐项对照 §4，以及你自己发现的问题，按严重程度分级：
   - **P1**：安全边界被突破（越权、身份伪造、失败当成功、金额变浮点）；
   - **P2**：与原 Prompt / 任务单要求不符、测试没有覆盖到所声称的行为；
   - **P3**：文档不一致、可维护性问题、边界说明缺失。

   每个问题给出复现步骤或 `文件:行号`。
5. 通过所需的条件（如果是有条件通过），以及返修建议。不要直接动手修改。

复查结束后，**不要**更新开发日志、`CURRENT_BASELINE` 或路线图，由用户决定是否采纳复查结论。也不要声称“最终验收通过”。
