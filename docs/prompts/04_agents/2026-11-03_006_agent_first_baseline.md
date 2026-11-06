# 2026-11-03_006_Agent-first 基线、契约与首批评测样例

## 1. 基本信息

- **日期**：2026-11-03
- **任务编号**：006
- **模块**：04_agents
- **用户侧名称**：Prompt 1（新一轮 Codex → DeepSeek → Codex 协作的第一项任务，不重置全局归档编号）
- **当前状态**：**Prompt 1 / Task 006 已由 Codex 验收通过（2026-11-06）**；进入 Prompt 2 / Task 007
- **Git Commit**：`Pending`
- **最新需求基线**：`docs/handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md`

## 2. 任务目标和背景

用户已确认以 Agent 工程为核心的新方向，并指定协作流程：Codex 编写执行 Prompt，DeepSeek 落地，Codex 读取实际文件及验证结果后审查，再进入下一项。

本任务先确定可编码、可验收的最小范围、接口草案和固定测试数据，不实施 Runtime、数据库或框架集成。历史代码和 14 表数据库设计保留。执行提示词完整保存在第 10 节。

## 3. 原始用户 Prompt

```text
好 那我们的项目正式开始了 告诉我下一步要干什么 我们的工作流程 是codex写提示词 prommpt1 然后deepseek 进行落地执行 然后codex 再进行检查 然后进行下一步
```

## 4. AI 实际执行的主要步骤

### Codex：提示词准备阶段

1. 检查 Git 分支、历史及工作区，读取 docs 编号表、日志和检查点约定。
2. 确认全局编号下一项为 006，新方向基线文件已存在。
3. 编写本归档与第 10 节执行 Prompt，登记编号并记录准备状态。
4. 未执行 DeepSeek 阶段的交付，不将预期产物标为已完成。

### DeepSeek：执行阶段（已完成，待 Codex 审查）

**执行者**：DeepSeek（VS Code Copilot SDK 会话）
**执行时间**：2026-11-03
**执行前仓库状态**：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`；工作区已存在接手前的未提交变更（`backend/` 未跟踪、`docs/` 多处修改/删除），**全部保留，未清理、未覆盖，也不计入本任务产出**。

实际步骤：

1. **只读盘点**：读取 §10 列出的全部文件；核对 `backend/app/agents/base/*`、`factory.py`、`config/*`、`llm/adapter.py`、`tools/base.py`、`orchestration/*`、`tests/smoke_agent_contracts.py` 实际源码（不采信历史汇报）。仓库内无 `AGENTS.md`（已确认不存在）。
2. **源码核对已知问题**：逐条验证 §四 末尾要求的 4 个骨架问题，全部复现，并额外发现 2 项（见 §7）。证据写入 `agent_runtime_contracts.md` §13（K1–K6）。
3. **新建目录**：`docs/decisions/`、`docs/product/`、`docs/evaluation/`、`docs/evaluation/fixtures/`、`docs/evaluation/cases/`。
4. **交付 1**：编写 `ADR-005` 与 `mvp_scope_v2.md`，严格区分"用户已确认 C1–C7"与"本 ADR 建议 S1–S10"，并把每项 P0 完成标准映射为可验证行为。
5. **交付 2**：编写 `agent_runtime_contracts.md`（§1–§13 覆盖 §四 要求的 12 项），并增量更新 `agent_architecture.md`（仅加说明与链接，不复制字段定义）。
6. **交付 3**：编写 `evaluation_plan.md`、`fixtures/agent_first_v1.json`、`cases/smoke_v1.jsonl`（8 行）。
7. **文档同步**：更新 `docs/README.md`（目录索引 + 006 状态）、`system_design.md`（修正与现状矛盾的表述并链接 ADR-005）、开发日志、Git 检查点。
8. **执行校验**（只读、标准库）：JSON/JSONL 解析、8 行与 case_id 唯一、变体与证据 ID 存在性、负例语义、`Decimal` 金额核对、Markdown 相对链接可解析、`git diff --check` 基线对比、`backend/` 前后一致性。

**未执行**：修改 `backend/`、安装依赖、调用模型 API、建库/迁移、删除历史文件、改写 §3 与 §10、提交或推送 Git。

### DeepSeek：Prompt 1-R1 返修阶段（已完成，待 Codex 复验）

**执行者**：DeepSeek（DeepSeek Harness 会话）
**执行时间**：2026-11-06
**执行前仓库状态**：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`；工作区含接手前未提交变更（`backend/` 未跟踪、`docs/` 多处修改/删除），**全部保留**。
**基线记录**：执行前对工作区 93 个文件（排除 `.git`）逐一记录 SHA-256 与字节数，共 1,080,865 字节；`backend/` 与 `database_design.md` 的 hash 在执行后比对，不使用"大小相等"推断内容一致。

实际步骤：

1. 完整阅读 Review 第 7 节 Prompt 1-R1、总路线、本归档，以及被点名的 6 个交付文件。
2. 记录 git 状态、HEAD、远端与全量文件 SHA-256 基线（执行前）。
3. 按 R1–R6 逐项修正 `mvp_scope_v2.md`、`agent_runtime_contracts.md`、`evaluation_plan.md`、`agent_first_v1.json`、`smoke_v1.jsonl`。
4. 用 Python 标准库执行 JSON/JSONL 解析、变体与场景解析、证据 ID 存在性、Decimal 金额复核，以及 §9 的 6 项语义检查。
5. 比对 `backend/`、`database_design.md` 与其余未授权修改文件的内容 hash；更新归档、日志与检查点。

**本轮未执行**：修改 `backend/`、安装依赖、调用模型、建库/迁移、改 `database_design.md`、提交或推送；未开始 Prompt 2 / 任务 007。

### Codex：审查阶段

2026-11-03 首轮完成：独立核对 JSON/JSONL、各 overlay、来源 ID、Decimal 金额、相对文件链接，并重新运行 57 项骨架自检。核心数据验证通过，但超时条件、三基线路由、审批事件、归并/预算、Graph/证据契约及范围记录有冲突，结论为**待修正**。

详细发现、验证边界与完整返修 Prompt：[006 Review](../../reviews/2026-11-03_task006_review.md)。本轮同步新增用户要求的[项目总路线](../../product/PROJECT_DEVELOPMENT_ROADMAP.md)，不代替 DeepSeek 修正文档规格或实施 Runtime。

## 5. 新增和修改的文件

| 文件 | 类型 | 当前实际改动 |
|---|---|---|
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 新增 | 用户原文、执行 Prompt、阶段状态、DeepSeek 执行记录 |
| `docs/README.md` | 修改 | 登记 006；新增 decisions/product/evaluation/handoffs 目录索引与新文档行 |
| `docs/development_logs/development_log.md` | 修改 | 记录提示词准备阶段 + DeepSeek 执行阶段 |
| `docs/checkpoints/git_history.md` | 修改 | 记录 Pending 检查点（准备 + 执行） |
| `docs/decisions/ADR-005-agent-first-refocus.md` | **新增** | 方向决策、用户已确认 vs 建议、取舍、与旧产物关系 |
| `docs/product/mvp_scope_v2.md` | **新增** | P0/P1/暂停、主场景、完成标准映射、数据库策略 |
| `docs/architecture/agent_runtime_contracts.md` | **新增** | 12 项运行时契约 + 已知骨架缺陷 K1–K6 |
| `docs/architecture/agent_architecture.md` | 修改 | 增量说明与链接（不改写原有设计内容） |
| `docs/architecture/system_design.md` | 修改 | 修正与现状矛盾的表述；链接 ADR-005 |
| `docs/evaluation/evaluation_plan.md` | **新增** | 数据协议、变体解析顺序、三基线、指标分项 |
| `docs/evaluation/fixtures/agent_first_v1.json` | **新增** | 合成共享数据 + 变体注册表 + 可信主体 |
| `docs/evaluation/cases/smoke_v1.jsonl` | **新增** | 8 条评测用例 |

**未修改**：`backend/` 下任何文件（前后一致性已校验）、`docs/architecture/database_design.md`（本轮明确不改）、`docs/prompts/001–005` 历史归档原文。
**未创建**：任何 `.py` 实现、`.sql`、依赖清单变更。

### Prompt 1-R1 返修修改的文件（2026-11-06）

| 文件 | 类型 | 本次实际改动（对应 Review 项） |
|---|---|---|
| `docs/evaluation/fixtures/agent_first_v1.json` | 修改 | 新增 `spec_revision`、`scenario_protocol`、审批主体/角色规则/草案版本；`v_tool_timeout_billing` 拆两个场景；`v_approval_flow` 拆六个场景（R1、R3） |
| `docs/evaluation/cases/smoke_v1.jsonl` | 修改 | 8 行全部重写路由口径；C06 双场景；C08 六场景（R1、R2、R3） |
| `docs/evaluation/evaluation_plan.md` | 修改 | 解析优先级、三基线三层分离与评分示例、保留集入 P0、重复测量、6 项语义检查（R1、R2、R6） |
| `docs/architecture/agent_runtime_contracts.md` | 修改 | 增量迁移、Evidence/ToolResult/Computation/状态枚举、State 写入者与归并、穷尽转移表、预算原子性与墙钟、审批状态机、K6→N1（R4、R5、R6） |
| `docs/product/mvp_scope_v2.md` | 修改 | Trace 替代 `agent_runs` 预设、保留集入 P0、审批规则细化、重复测量（R6） |
| `docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md` | 修改 | 追加 R1 执行与验证记录；修正 §8 旧状态（R6） |
| `docs/development_logs/development_log.md` | 修改 | 追加 R1 返修记录 |
| `docs/checkpoints/git_history.md` | 修改 | 追加 R1 返修检查点 |
| `docs/README.md` | 修改 | 006 编号登记状态更新为"返修完成，待复验" |

**仍未修改**：`backend/`、`docs/architecture/database_design.md`、ADR-005、历史 Prompt 原文（§3、§10）、`docs/reviews/`、总路线文件。

### Prompt 1-R2 窄范围修正的文件（2026-11-06）

| 文件 | 本次实际改动（对应 R1-R2 / R3-R4） |
|---|---|
| `docs/evaluation/fixtures/agent_first_v1.json` | `scenario_protocol` 改为可按**实际数组结构**执行的 r2 协议（运行项展开、`scenario_id` 双端匹配、8 类错误码、一致性规则）；`approval_replay` 删除重复事件的 `replayed` 字段并新增 `delivery.duplicates`；`spec_revision` → `2026-11-06-r2` |
| `docs/evaluation/cases/smoke_v1.jsonl` | C06/C08 协议版本 → r2，新增 `scenario_expansion`；`scenario_resolution` 改为按 `scenario_id` 解析；probe `evidence_policy` 与 fixture 统一为 `required_on_success` |
| `docs/evaluation/evaluation_plan.md` | §2.3 重写为运行项展开 / 双端匹配 / 错误行为；§5.1、§5.2 改为"运行项"；§7 解析要求；§9 新增 S7–S9 |
| `docs/architecture/agent_runtime_contracts.md` | §9.2 事件冲突措辞、§12.6 明确"重复投递表达重放、禁止 `replayed` 字段" |
| `docs/README.md` | 006 编号登记状态更新为"Prompt 1-R1/R2 返修完成，待 Codex 复验" |
| 本归档、开发日志、Git 检查点 | 追加 R1-R2 记录 |

### Codex 复验结论（2026-11-06）

**Task 006 / Prompt 1 已验收**。Codex 独立重跑场景选择器检查（62/62）和审批回归（30/30），核对 14 个真实运行项、重放事件逐字段一致、同 ID 异内容冲突；hash 比对确认 R2 仅改动 8 个授权文档，`backend/` 62 个文件及 `database_design.md` 未变。详细证据见 [Task 006 R2 Review](../../reviews/2026-11-06_task006_r2_review.md)。本结论只验收规格与 fixture，不表示 Runtime 或模型行为已经实现。下一步为 Prompt 2 / Task 007。

**仍只改 Markdown 与 `docs/evaluation/` 的 JSON/JSONL**；`backend/`、`database_design.md`、审批角色规则与业务事实均未改。

## 6. 执行结果和验证方式

- 提示词准备前核实：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`；存在接手前未提交变更。
- 本阶段只准备提示词并更新归档；未修改 `backend/`，未安装依赖或创建数据库。
- DeepSeek 执行验证与 Codex 验收结果：见下。

### DeepSeek 执行阶段的真实验证结果

执行前状态：分支 `main`，HEAD `7ed2665bb9201568a8d74a12af37bf0a502378f1`，工作区含接手前未提交变更（全部保留）。

| # | 验证项 | 命令 / 方式 | 结果 |
|---|---|---|---|
| V1 | fixture 可解析 | `json.loads`（Python 3.11 标准库） | ✅ 通过；`dataset_version=agent-first-v1`，`as_of=2026-11-03`，`synthetic=True`；基线实体 44 个 |
| V2 | JSONL 行数与唯一性 | 逐行 `json.loads` | ✅ 非空行 **8**；`case_id` C01–C08 唯一且有序 |
| V3 | 变体引用存在 | 对照 `variant_registry` | ✅ 8/8 case 的 `variant` 均已注册 |
| V4 | 证据 ID 存在 | 应用 overlay 后重建 ID 索引 | ✅ 全部 `required_evidence_ids` 命中（C07 为空集，属预期） |
| V5 | 负例语义 | 负例 ID 若存在则必须越权；否则必须缺失 | ✅ C05 的 `doc_xh_a301_annex_b` 确认不存在；C07 的 3 个 `prj_jinlan` ID 确认存在且越权；required/negative 无交集 |
| V6 | 金额核对（Decimal） | `decimal.Decimal` 逐账单汇总 | ✅ 08/09/10 月合计 `17280.00 / 17280.00 / 18036.00`；有效核销 `17280.00 / 17280.00 / 0.00`；未收合计 **18036.00** |
| V7 | 冲销排除对照 | 若把 `alloc_003` 计入 | ✅ 08 月已收将变为 `22280.00` > 账单额，证明排除逻辑必要且被断言覆盖 |
| V8 | 合同金额自洽 | `120 × 126.0000`、`120 × 132.3000`、`120 × 18` | ✅ `15120.00` / `15876.00` / `2160.00`；超额 `756.00`；递增 `120→126→132.30` 自洽 |
| V9 | 数据变体生效 | `v_oct_rent_corrected` | ✅ 10 月合计变 `17280.00`、未收变 `17280.00`；且基线对象未被就地修改（overlay 为深拷贝） |
| V10 | 冲突变体生效 | `v_annex_conflict` | ✅ 文档 +1、片段 +1 |
| V11 | C03 事实与 fixture 一致 | 交叉比对 | ✅ HVAC 工单 3 条、未结 1 条（`wo_2026_09_25`）、超额 756.00 与 fixture 一致 |
| V12 | C08 审批子变体对齐 | 对照 `sub_variants` | ✅ 3 个子变体（denied/granted/replay）名称与 fixture 完全一致 |
| V13 | 悬空文档引用 | 检查 `leases.referenced_document_ids` | ✅ 唯一悬空项为 `doc_xh_a301_annex_b`；`work_notes` 已记录"尚未电子化" |
| V14 | Markdown 相对链接 | 扫描 `docs/**/*.md` 全部相对链接 | ✅ 21 个文件、55 条相对链接，**新增文档 0 处断链**，原有文档 0 处断链 |
| V15 | `backend/` 未被改动 | 目录枚举与文件大小比对 | ✅ 与本任务开始前一致 |
| V16 | `git diff --check` | 区分本任务与原有问题 | ⚠️ 唯一告警 `docs/architecture/database_design.md:1661: new blank line at EOF` 为**任务 005 遗留**，本轮明确不改该文件，故未处理（见 §7） |

合计程序化断言 **164 项全部通过**（`PASS=164 / FAIL=0`）。

**未执行**：任何模型调用、Runtime 运行、数据库连接。因此**不产出**任务成功率、成本、延迟等指标（见 `evaluation_plan.md` §1）。

### Prompt 1-R1 返修阶段的真实验证结果

执行环境：`D:\anacada\envs\commercial-agent\python.exe -X utf8`（Python 3.11.18，仅标准库；未安装任何工具）。以下均为**规格/参考输入检查**，不是工作流已运行通过。

| # | 验证项 | 命令 / 方式 | 结果 |
|---|---|---|---|
| R-V1 | fixture / JSONL 解析 | `json.loads` 逐行 | ✅ `dataset_version=agent-first-v1`、`spec_revision=2026-11-06-r1`、`as_of=2026-11-03`；JSONL 非空行 **8**，`case_id` 唯一有序 |
| R-V2 | 变体与场景可解析 | 对照 `variant_registry` 与 `scenarios` | ✅ 8/8 case 变体已注册；C06 的 2 个子场景、C08 的 6 个子场景全部命中；`fail_attempts <= tool_max_attempts` |
| R-V3 | 证据 ID（应用 overlay 后） | 重建实体 ID 索引 | ✅ 顶层与场景级 `required_evidence_ids` 全部命中；C07 空集属预期 |
| R-V4 | 负例语义 | 检查 `negative_references` | ✅ `doc_xh_a301_annex_b` 确认不存在；C07 的 3 个 `prj_jinlan` ID 存在但越权；required/negative 无交集 |
| R-V5 | 金额（Decimal） | 逐项 `quantity × unit_price`、逐月汇总、有效付款与未收 | ✅ 明细逐条相等；账单 `17280.00 / 17280.00 / 18036.00`；有效付款 `34560.00`；未收 **18036.00**；超额 **756.00**；更正后未收 `17280.00` |
| R-V6 | 冲销排除对照 | 计入 `alloc_003` | ✅ 8 月已收变 `22280.00`（> 账单额），证明排除必要 |
| R-V7 | S1 失败 C06 不强制证据 | 读取 `main_timeout_exhausted` | ✅ `required_evidence_ids=[]`、`evidence_policy=none`、顶层 required 为空 |
| R-V8 | S2 probe 成功才要求证据 | 读取 `recovery_probe` + 尝试模拟 | ✅ `fail_attempts=1 < tool_max_attempts=2`；模拟结果 `[timeout, ok]`，成功后要求 3 张 invoice；主路径模拟 `[timeout, timeout]` 无数据 |
| R-V9 | S3 同一答案通过 A/B/C | 评测计划 §3.4 假想正确结果 | ✅ Q1–Q7 在三个基线下全部通过，仅 E1–E3 效率不同 |
| R-V10 | S4 审批只认可信授权事件 | 6 个场景逐一跑参考状态机 | ✅ 仅 `approval_granted` / `approval_replay` 达到 `approved`；拒绝/越权/换版/过期均被拒且业务写入为 0 |
| R-V11 | S5 重放不重复计账、顺序无关 | 参考归并/账本算法 | ✅ 正序/逆序到达 map 与 `seen` 完全一致；同 ID 不同内容报 `EVIDENCE_CONFLICT`；重复调用预算增量为 0 |
| R-V12 | S6 verify 组合均有出口 | 3 verdict × 2 补查状态 × 2 草案状态 | ✅ 12 组全部有明确去向；契约 §9.4 恰好 12 行编号转移 |
| R-V13 | Markdown 相对链接 | 扫描 `docs/**/*.md` | ✅ **0 断链** |
| R-V14 | 编码完整性 | UTF-8 解码 + U+FFFD 扫描 | ✅ 0 处替换字符 |
| R-V15 | 文件级一致性 | 执行前后 93 个文件逐文件 SHA-256 | ✅ **0 新增 / 0 删除**；10 个文件内容变化（全部在本任务授权范围）；其余 83 个逐字节不变 |
| R-V16 | `backend/` 与数据库设计 | 逐文件 SHA-256 比对 | ✅ `backend/` 全部一致；`database_design.md` 仍为 `1b7e37350a18ff4c17e7063558a1ab3b4be5beabbd6a94aa4efbe236a5f56db7` |
| R-V17 | `git diff --check` | — | ⚠️ 唯一告警仍是 `docs/architecture/database_design.md:1661: new blank line at EOF`（任务 005 遗留，本轮明确不改该文件） |

程序化检查合计 **PASS=178 / FAIL=0**（脚本为会话内一次性只读校验，不属于仓库交付物）。

**审计边界（R6 修正）**：一致性结论来自**逐文件内容 hash**，不是"目录枚举 + 文件大小"。本轮未运行模型、未建库，因此不宣称任何运行时行为已验证。

### Prompt 1-R2 窄范围修正的真实验证结果

命令：`D:\anacada\envs\commercial-agent\python.exe -X utf8 <verify_r2.py>`（Python 3.11.18，仅标准库；脚本为会话内一次性只读校验，不属于仓库交付物）。

| # | 验证项 | 方式 | 结果 |
|---|---|---|---|
| R2-V1 | JSON / JSONL 解析 | `json.loads` 逐行 | ✅ 8 行、C01–C08 唯一有序；`spec_revision` 与 `scenario_protocol.version` 均为 `2026-11-06-r2` |
| R2-V2 | 运行项展开 | 只读选择器 `expand_run_items` 对真实 JSON 求值 | ✅ 共 **14** 项：C06=2、C08=6、其余 6 个 case 各 1 |
| R2-V3 | C06 选择器解析 | `scenario_id` 双端匹配 | ✅ `main_timeout_exhausted` → `evt_tool_fault_main_001`（fail 2 次）；`recovery_probe` → `evt_tool_fault_probe_001`（fail 1 次）；证据 main=`[]`、probe=3 张发票 |
| R2-V4 | C08 选择器解析 | 6 个场景 | ✅ 6 项事件与 expected 终态/审批状态全部匹配，断言按场景独立选中 |
| R2-V5 | 普通 case 只跑一次 | C01 / C03 | ✅ `scenario_id=null`、事件取 `variant.events`、只用 case 级断言 |
| R2-V6 | 错误注入（10 个反例） | 变异真实数据后重跑选择器 | ✅ `MISSING_SCENARIO_ID`/`DUPLICATE_SCENARIO_ID`/`UNKNOWN_SCENARIO_ID`/`EMPTY_SCENARIOS`/`SCENARIOS_NOT_ARRAY`/`DEFAULT_SCENARIO_MISSING`/`DEFAULT_SCENARIO_UNKNOWN`/`SCENARIO_MISMATCH` 均按码报错 |
| R2-V7 | S8 同 ID 同内容幂等 | 规范化（键排序）哈希比较 | ✅ `evt_apr_fin_grant_003` 投递 2 次、逐字段相同；全 fixture 无 `replayed` 字段；`ignored=1`、唯一事件 3、预算增量 0 |
| R2-V8 | S9 同 ID 异内容冲突 | 合成反例（改 `decision` / `occurred_at`） | ✅ 两种均抛 `EVENT_ID_CONFLICT`，不覆盖、不幂等 |
| R2-V9 | 相关证据解析 | 每个运行项按 overlay 重建 ID 索引 | ✅ 有效证据全部命中；C08 场景回退到 case 级 5 个证据 |
| R2-V10 | Decimal 金额 | 明细 + 汇总 + 变体 | ✅ 未收 `18036.00`、超额 `756.00`、更正后未收 `17280.00` |
| R2-V11 | 相对链接 / 编码 | 扫描 `docs/**/*.md` | ✅ 0 断链；0 处 U+FFFD |
| R2-V12 | 文件级一致性 | 执行前后 94 个文件 SHA-256 | ✅ 8 个文件内容变化（全部授权范围），其余 86 个逐字节不变；`backend/` 与 `database_design.md` 未变 |
| R2-V13 | `git diff --check` | — | ⚠️ 唯一告警仍为 `docs/architecture/database_design.md:1661: new blank line at EOF`（任务 005 遗留，禁止修改该文件） |

程序化检查合计 **PASS=62 / FAIL=0**。这些仍是**规格/参考输入检查**：选择器是只读参考实现，未运行 Runtime、未调用模型。

## 7. 遇到的问题及解决方法

- 全局归档已使用 001–005，故“Prompt 1”对应任务 006，避免重用 001。
- 仓库已有未提交代码与文档，后续执行必须先盘点，不覆盖、清理或认领旧变更。
- 本阶段未遇到阻塞性问题。

### DeepSeek 执行阶段遇到的问题

| 问题 | 处理 |
|---|---|
| **K1 已复现**：`AgentRegistry.register(replace=True)` 先 `unregister` 再写入，中途无回滚 | 记入 `agent_runtime_contracts.md` §13，列任务 007 修复项，本轮不改代码 |
| **K2 已复现**：`BaseAgent.descriptor` 用类属性 `version`/`description`/`capabilities`，而 `AgentConfig` 同名字段从不参与校验，`factory.build_agent` 也不比对 | 同上；影响"改 YAML 即生效"的可配置性主张，优先级提到第二位 |
| **K3 已复现**：`handle()` 的 `asyncio.wait_for(timeout=self._config.timeout_seconds)` 未与剩余 deadline 取小，单次执行可越过上游 deadline | 同上；影响可靠性基线 |
| **K4 已复现**：`summarize_results` 在无 FAILED 时**无条件**返回 `PARTIAL`，`allow_partial` 未参与；有 FAILED 时才受其影响 | 同上；语义不一致会污染评测口径 |
| **K5 新发现**：`TaskStatus.SKIPPED` 完全不参与聚合，全 `SKIPPED` 会被判为 `SUCCESS` | 同上（额外发现，非 §四 要求） |
| **K6 新发现**：数据库设计 v2 的 `UNIQUE(lease_id)` 单商铺限制在代码层无对应表达 | 记录为"接数据库时注意"，本轮不动数据库文档 |
| `git diff --check` 报 `database_design.md:1661: new blank line at EOF` | 判定为**任务 005 遗留**、非本任务引入；本轮明确"不改 database_design.md"，故**未擅改**，在此显式记录以便后续任务清理 |
| 中文字符在 PowerShell 控制台显示为乱码 | 仅为控制台代码页现象，文件本身为 UTF-8；用 `view` 工具与 UTF-8 读取复核，未改动文件编码 |

### Prompt 1-R1 返修阶段遇到的问题

| 问题 | 处理 |
|---|---|
| 会话沙箱以低完整性令牌运行普通进程，工作区子目录无法由 `python` / `pwsh` 直接写入（仅工作区根目录可写） | 文档与 JSONL 一律改用 DSH 文件工具写入；生成 JSONL 的那一条命令申请一次性提权，未扩大其他权限，也未改动 `backend/` |
| 首次写入 `evaluation_plan.md` 时，一个标题字符被写成 3 个 U+FFFD | 立即修正，并在校验脚本中加入全 `docs/**/*.md` 的 U+FFFD 扫描；最终 0 处（R-V14） |
| C08 拒绝场景里 `satisfied_roles` 语义有歧义（拒绝算不算"满足"） | 拆成 `decided_roles` / `satisfied_roles` / `pending_roles` 三个字段，并写入契约 §12.7；fixture 与校验同步 |
| 契约"相反到达顺序"示例最初把不同重放次数当成同一事件集，导致 `seen` 不一致 | 改为同一事件多重集，并单独给出重放示例；校验脚本对正序/逆序/重放分别断言（R-V11） |
| 006 §8 旧状态与新执行记录冲突 | 按 R6 重写 §8，明确 DeepSeek 已执行、R1 已完成、Commit 仍 Pending |

### Prompt 1-R2 遇到的问题

| 问题 | 处理 |
|---|---|
| JSONL 的 `scenarios` 是数组、fixture 的是映射，原协议写成 `case.scenarios[case.scenario_id]` 无法按实际 JSON 求值 | 改为"运行项展开 + 同一 `scenario_id` 双端匹配"，并在计划与 fixture 中定义 8 类错误码 |
| C06 probe 的 `evidence_policy` 写成 `required_after_success`，与 fixture `evidence_requirement.mode=required_on_success` 不一致 | 统一为 `required_on_success`，并加入 `SCENARIO_MISMATCH` 一致性断言 |
| 原重放用例用 `replayed` 字段区分第二次投递，等于改变事件内容哈希 | 删除该字段，两条事件逐字段相同；重复投递由 `delivery.duplicates`（event_id + deliveries）表达 |
| 只读选择器需要能复用又不污染仓库 | 放在会话临时目录运行，仓库内只留协议文本与错误码定义 |

## 8. 对应 Git Commit Hash

- **Commit**：`Pending`（**未提交、未推送**）
- **原因**：任务 006、Prompt 1-R1 与 Prompt 1-R2 的文档/数据交付均已完成，但尚未获得用户提交确认，因此不提交、不推送。
- **此前旧表述已更正（R6）**：本文件第 8 节旧版曾把任务写成"准备完成、尚未执行"，与后续执行记录矛盾；实际是 DeepSeek 已于 2026-11-03 执行、2026-11-06 完成 R1 与 R1-R2 返修，当前真实状态为"返修完成，待 Codex 复验"。
- **当前真实 Git 状态**：分支 `main`，HEAD 仍为 `7ed2665bb9201568a8d74a12af37bf0a502378f1`（这是任务 001/002 的既有提交，**不是** 006 的提交）；工作区包含接手前的未提交变更，以及本任务新增/修改的文件。
- **一致性口径（R6）**：不再用"目录枚举 + 文件大小"推断 `backend/` 未被改动，改为执行前后逐文件 SHA-256 比对（见 §14）；hash 相同才说明内容一致。
- **任务完成后建议 Commit Message**：`docs: establish agent-first MVP scope and evaluation baseline`

## 9. 后续待办事项

- [x] DeepSeek 按第 10 节完成任务 006（执行完成，待审查）。
- [x] Codex 首轮审查实际文件与数据，结论为待修正（不是最终验收通过）。
- [x] DeepSeek 按 Review 第 7 节执行 Prompt 1-R1，修正 R1–R6（**返修完成，待 Codex 复验**）。
- [x] DeepSeek 执行 Prompt 1-R2，修正场景选择协议与审批重放事件内容（**返修完成，待 Codex 复验**）。
- [ ] Codex 复验 R1–R6 与 R1-R2 两项；通过后才进入下一步。
- [ ] 006 通过后，Codex 编写 Prompt 2 / 任务 007：Agent Runtime 与受控 Tool Calling。
- [ ] 任务 007 需一并修复 `agent_runtime_contracts.md` §13 的 K1–K5（K6 已改记为未来数据库映射注意事项 N1）。
- [ ] 清理任务 005 遗留的 `database_design.md` EOF 空行（需在允许修改该文件的任务中进行）。
- [ ] 如需提交，由用户明确确认后执行，并回填真实 hash。

## 10. DeepSeek 执行 Prompt 1（完整原文）

将本节下面代码块中的完整内容交给 DeepSeek 执行。

````text
# Prompt 1 / Task 006 — Agent-first 开发基线、契约与评测样例

你负责在 commercial-property-multi-agent 仓库中落地本任务。协作方式是：Codex 编写 Prompt → DeepSeek 执行 → Codex 审查实际文件和验证结果 → 通过后安排下一项。

本任务不是再写一份泛泛的方向分析，而是交付下一项 Runtime 编码能够直接使用的范围、接口规格和固定样例。完成后停止，不提前执行任务 007。

## 一、先读文件与核实仓库

完整阅读：
- docs/handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md（已获用户确认的最新方向）
- docs/README.md
- docs/architecture/system_design.md
- docs/architecture/agent_architecture.md
- docs/architecture/agent_development_guide.md
- docs/architecture/database_design.md
- docs/prompts/02_database/2026-11-03_005_database_design_review.md
- docs/prompts/04_agents/2026-11-03_006_agent_first_baseline.md
- docs/development_logs/development_log.md
- docs/checkpoints/git_history.md

检查当前实际代码，重点为 agents/base、factory.py、config、llm、tools、orchestration 和现有自检脚本。如有适用的 AGENTS.md，一并遵守。

记录 git status、当前分支、HEAD、未提交变更。不要假定 HEAD 仍为 7ed2665。仓库已有未提交变更，不得清理、覆盖或把历史改动计为本任务产出。

## 二、本轮边界

本轮仅允许新增/修改 Markdown 文档，以及 docs/evaluation/ 下的合成 JSON/JSONL 数据。

不要修改 backend/、安装依赖、调用付费模型 API、下载模型、连接或创建数据库、生成迁移、创建前端、提交或推送 Git。不要删除历史文件，不改写历史 Prompt 原文。

现有数据库设计继续保留为长期参考。完整计费、押金、能耗表计、核销写引擎和 CRUD 后台暂停，不作为本任务依赖。最小数据库表数仍是待实施评审的建议，不要把“10 表”或“14 表”写成用户已确认的硬指标。

## 三、交付 1：正式记录方向与 MVP 范围

新增（如已存在则检查后增量更新，避免重复文档）：
1. docs/decisions/ADR-005-agent-first-refocus.md
2. docs/product/mvp_scope_v2.md

ADR 清楚区分：用户已确认的方向、此次建议的实现细节、延后决策。写明旧方案保留、当前 P0 优先级，以及适用范围冲突时以新基线为准。

MVP 主场景：A-301 投诉近三个月租金不一致，空调多次维修，要求费用减免。系统核对合同、账单、付款和工单，输出事实、证据、冲突、缺失信息与人工处理草案。

P0 至少覆盖：
- Lease、Billing、Property 三类独立能力；现有 Compliance 保留、默认禁用。
- 统一 Runtime、Registry、独立配置、受控 Tool Calling。
- 真实 LangGraph 条件路由、按需并发、合流、有限补查。
- 精简合同 RAG、确定性金额核对、结构化 Evidence。
- 超时、预算、失败反馈、持久 checkpoint、审批暂停与授权恢复。
- Deterministic / Single Agent / Multi-Agent 三基线。
- 固定评测集、Trace、最少命令演示。最终 P0 有 30–50 题，本任务只准备 8 题。

明确 P1 和暂停清单，并用表把每项 P0 完成标准映射到未来可验证的行为。不要把普通 SQL 查询强行拆成多 Agent；不要宣称多 Agent 必然更好。

P0 审批只针对草案：即使审批通过，也不产生真实调账、减免、派单或对外通知。

## 四、交付 2：可直接指导编码的接口和 Graph 规格

新增 docs/architecture/agent_runtime_contracts.md，并增量更新 agent_architecture.md；共享规则用链接引用，不要两处复制大段定义。

本轮只写字段表、类型、约束、输入输出样例和接口签名示意，不实现 Python 模块。

至少明确：
1. AgentRequest / AgentContext / AgentResult 与现有类型的兼容策略。
2. Evidence / Finding / ToolResult / InvestigationPlan / VerificationResult / ApprovalDraft / WorkflowResult。
3. Evidence 区分数据库事实和文档条款：数据记录主键、项目、数据版本、工具调用 ID；文档还需版本、页码和原文。引用存在和引用支持结论是两种不同验证。
4. 金额用 Decimal 语义和带币种的十进制字符串交换；禁止浮点真值。业务日期与带时区的事件时间分开。
5. 项目权限由可信调用上下文提供，不接受模型或用户 payload 自报的权限；tenant_id 不同时代表商业租户与权限隔离主体。
6. Tool Executor 统一做工具白名单、业务权限、参数校验、deadline/预算和结果校验。只允许参数化业务查询，不提供任意 SQL 或任意代码工具。
7. Model Adapter 可注入 Fake 实现和真实 Provider；复用已有 llm 层，不另造重复客户端。
8. Registry 和 Graph Builder 按能力工作；明确新增/禁用/替换 Agent 需要改什么、无需改什么；不做热插拔或插件市场。
9. State 字段、节点输入输出、条件边、并发合流条件、重试/补查上限。结果按 subtask_id 与 attempt 归并，不能仅靠列表追加处理重放；合流必须等待本轮预期子任务终止。
10. 每任务总预算和各层重试的归属，避免 Runtime、模型、工具和 Graph 重试相乘。
11. thread_id、run_id、trace_id、request_id 的区别；持久恢复所需的数据/配置/契约版本。恢复前重新授权，审批绑定草案版本。checkpoint 不承诺外部副作用恰好一次。
12. 审批为独立 Graph 节点，不嵌入通用业务异常兜底逻辑。

列出已知骨架问题作为任务 007 待修项，本轮不改代码：Registry 多能力替换非原子；配置与类描述符不一致；deadline 未限制单次执行；allow_partial=False 未完整覆盖 PARTIAL。核对实际源码后再描述，不把旧汇报当证据。

## 五、交付 3：8 个可机器读取的固定评测样例

新增：
- docs/evaluation/evaluation_plan.md
- docs/evaluation/fixtures/agent_first_v1.json
- docs/evaluation/cases/smoke_v1.jsonl

全部使用合成数据，固定 dataset_version 和 as_of_date=2026-11-03，核心调查期间为 2026 年 8、9、10 月。数据尽量小，但至少覆盖两个项目，以便测试隔离。不要读取真实公司数据。

共享 fixture 提供稳定主键及必要事实：商铺、合同条款、三个月账单明细、付款/分配、工单时间线和文档片段。金额、日期、规则切换和证据引用必须自洽；存在争议的数据要区分“故意设置的业务差异”与“fixture 写错”。

文档片段属于模拟检索语料，必须标明 synthetic；没有真实 PDF 时不得声称已经验证 PDF 页码或实现 RAG，模拟页码仅代表约定的测试来源定位。

8 题分别覆盖：
C01 确定性欠费查询，不要求多 Agent。
C02 单份合同条款检索。
C03 合同、账单、付款、维修工单的完整争议调查。
C04 同主题冲突证据，应标记冲突而非擅自选择结论。
C05 必要合同资料缺失，应列出缺失并停止无依据判断。
C06 工具超时，有限重试后恢复或明确失败/降级。
C07 跨项目/无权限请求，禁止工具返回越权数据。
C08 费用减免草案、审批暂停、拒绝/允许恢复和重复恢复请求的处理要求；仍不写真实账单。

每条 JSONL 至少包含：case_id、dataset_version、as_of_date、用户输入、可信权限上下文、数据变体/故障注入说明、预期关键事实、必需证据 ID、允许的路由/下一步、禁止行为、评分断言。

每条 case 必须可解析地引用共享 fixture；冲突、缺失、超时和审批事件通过明确的 variant/overlay/events 表达，不允许只在自然语言里说“假设数据有变化”。给出变体解析顺序与语义。预期事实只能供评测器使用，不能作为 Agent 的输入或工具结果暴露。

本轮样例是未来 runner 的输入规格，不是已执行的模型评测。没有 Runtime 时不得报告任务成功率、模型费用、恢复成功率或延迟提升。

评测计划明确三基线共用数据、工具、权限和总预算；程序断言与人工/模型评分分开；事实、引用、路由、故障、审批、可插拔性、延迟和全任务成本分项统计。说明开发样例与后续保留测试集的隔离。

## 六、文档同步与执行记录

更新 docs/README.md 的文档索引；任务 006 已登记，不重用编号、不另建同任务 Prompt 归档。后续任务 007 才是 Prompt 2。

system_design.md 如有与实际状态矛盾的概述，增量修正并链接新 ADR，保留历史 ADR。database_design.md 本轮不修改、不修复完整财务引擎。

在本归档的执行阶段追加真实步骤、文件和验证结果；第 3 节用户原文及第 10 节执行 Prompt 不改写。开发日志和 Git 检查点增加 DeepSeek 执行阶段，明确“执行完成、待 Codex 审查”，Commit 保持 Pending。不要把 Codex 的准备记录改成已完成全部任务。Issue 和知识笔记仅在确有新问题或可复用结论时追加。

## 七、验收与完成汇报

实际执行并记录：
- 所有新文档内部相对链接可解析，章节引用正确。
- JSON fixture 可解析；JSONL 恰好 8 行且 case_id 唯一。
- 每个 case 的 fixture 引用、variant 和证据 ID 都存在；应用 overlay 后按用例检查有效/缺失引用的预期。故意无效引用须显式标注为负例，不能冒充正常证据。
- 用 Python 标准库 Decimal 复核账单明细合计、有效付款分配与余额；排除冲销/无效记录，按各数据变体分别核对关键事实。
- 预期答案与允许路由、禁止行为不矛盾。
- git diff --check：区分本任务引入的问题与原有问题，不为通过检查擅改历史文件。
- backend/ 与执行前一致；没有安装依赖、建库、提交或推送。

可使用已存在的项目 Python 和标准库做临时只读校验，不安装校验工具；不要为本次文档任务创建正式测试框架。不要仅用“围栏偶数、章节连续”证明完成。

最终输出：
1. 真实分支、HEAD、执行前后状态及本任务文件清单。
2. 已完成/未完成内容和关键决策；建议与用户已确认事项分开。
3. 8 题摘要、数据版本、验证命令及真实结果。
4. 未解决问题、偏离 Prompt 的地方及原因。
5. 建议 Commit Message，但不执行提交。

完成后停止，等待 Codex Review。不要自行开始任务 007。
````

## 11. 用户追加请求原文（Codex Review 与总路线）

```text
deepseek 完成了 你检查一下 另外 我需要你给我一份文件 告诉我你要怎么完成本本项目的开发 你是怎么理解本项目的 你打算分为多少步完成（假如deepseek每一步都完美完成 我要给deepseek 发送多少次promopt）每一步要做什么 从而让我掌握整个项目的进度
```

## 12. Codex 首轮审查产物与下一步

- 新增 `docs/reviews/2026-11-03_task006_review.md`：验证结果、R1–R6、完整 Prompt 1-R1。
- 新增 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`：项目理解、10 次正式 Prompt、每步验收/依赖/检查点、当前状态。
- 更新编号状态、开发日志、Issue 与 Pending 检查点；未改 `backend/`、fixture 或 DeepSeek 的规格交付。
- 理想从头一次完成：10 次正式 Prompt；当前已识别一次返修，若此后全部通过则实际预计 11 次发送。
- 下一步：DeepSeek 执行 Review 第 7 节 Prompt 1-R1 → Codex 复验 → 通过后才进入 Prompt 2 / 任务 007。
- 原始第 3 节与第 10 节内容保持不变；第 8 节的旧执行状态残留已列入 R6 待修正，不能当作当前状态。

## 13. 路线派生交付：Notability 图文 PDF（2026-11-04）

### 用户原文

```text
这个项目总开发路线和进度表 给我一份图文并茂的PDF 文件 我平时要在notbililty上看的
```

### 实际执行与结果

- Codex 根据 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` 制作 16 页 A4 竖版阅读批注手册。
- 产物：`output/pdf/commercial_property_agent_first_roadmap_notability.pdf`。
- 包含矢量架构图、协作流程、可点击十步导航、每步任务与验收、手写批注区、进度勾选表和完成清单；中文字体嵌入，带目录书签。
- 路线/状态快照截至 2026-11-03；导出日期 2026-11-04。未重新验收 006、未推进 Runtime。
- 使用 ReportLab 制作，Poppler 渲染全部 16 页；检查完整联系表及重点页，pypdf 验证 16 页、16 项书签、文本可提取和关键内容存在。
- 原项目 Conda 环境不变；制作使用 Codex 附带 Python 依赖。没有模型 API 调用、Git 提交或推送。
- 本次是 006 总路线的阅读格式派生交付，不新增正式 DeepSeek Prompt，不改变 10 次正式步骤及返修计数。

## 14. Prompt 1-R1 返修记录（2026-11-06）

**任务口径**：这是 Task 006 的 Prompt 1-R1，**不是** Task 007。按 Review 第 7 节原文执行，只修正 R1–R6。
**最终状态**：**返修完成，待 Codex 复验**（未自行标记为已验收，未开始 Prompt 2）。

### 14.1 R1–R6 逐项修正位置

| 项 | Review 问题 | 修正位置 | 修正内容 |
|---|---|---|---|
| **R1** | C06 无条件要求 3 张 invoice 证据；probe `fail_attempts=1` 与注册事件 `2` 矛盾；解析顺序未定义 | `evaluation_plan.md` §2.3、§5.1；`agent_first_v1.json` `scenario_protocol` + `v_tool_timeout_billing`；`smoke_v1.jsonl` C06 | 主失败路径（连续 2 次超时）与恢复 probe（1 次超时后成功）**分场景定义**；失败路径 `required_evidence_ids=[]`；probe 成功后要求 3 张 invoice；写死解析优先级（case > variant.scenarios > variant.events，事件替换不合并，未知场景校验失败） |
| **R2** | C03/C04/C08 只允许 multi_agent，三基线比较被路由预设 | `evaluation_plan.md` §3、§4；`smoke_v1.jsonl` 8 行 `allowed_routes` / `preferred_route` | 事实/引用/权限/审批为 A/B/C **共通质量断言**；编排约束按 `baseline_mode` 单独判；`route_class` 降为 E1 效率指标；C03/C04/C05/C08 放开三条路由；C04 明确"单 Lease Agent + Verifier 即可"；给出 A/B/C 对同一假想正确结果的评分示例（`evaluation_plan.md` §3.4） |
| **R3** | 无审批角色/approval.decide、无事件 ID、无草案版本、AND/OR 与顺序不明 | `agent_first_v1.json` `principals`、`approval_role_rules`、`approval_drafts`、`v_approval_flow`；`agent_runtime_contracts.md` §12；`smoke_v1.jsonl` C08 | 新增物业/财务审批主体、跨项目审批人、只读主体；`all_of` + 串行 + 两名不同主体 + 禁止自批 + 72h 过期；草案 v1/v2 与 `expires_at`；6 个场景（拒绝/正确版本批准/同版本重放/无权限/换版/过期）均以稳定 `event_id` 定义 |
| **R4** | `budget_used` 简单相加、Evidence 后写覆盖、并发墙钟相加、reserve/consume 缺原子性 | `agent_runtime_contracts.md` §9.1–9.2、§10.1–10.3、§11.1 | State 唯一写入者表；`tool_call_id`/`model_call_id`/`event_id` 稳定 ID；`reserve/settle/release` 原子两阶段；Evidence 按 `content_hash` 幂等合并、不同内容报 `EVIDENCE_CONFLICT`；墙钟用单调时钟，节点耗时不求和；给出正/逆序到达、重复投递、不同内容冲突的具体输入与预期 |
| **R5** | verify 分支不闭合；revise 违反 plan 单一写入；缺资料被送审批；report 后审批状态未定；关键类型只有"关键字段" | `agent_runtime_contracts.md` §3.5–3.9、§9.3–9.4、§11.3、§12 | 12 行穷尽转移表（supported/conflicting/insufficient × 补查上限 × 有无草案）；`revise` 只发 `RevisionRequest` 回 `planner`；`awaiting_human_input` 与 `awaiting_approval` 分离且无草案不得审批；`WorkflowResult.approval` 含状态/拒绝理由；补齐 Evidence 数据版本、ToolResult 证据输出、`Computation`、`WorkflowStatus` 枚举；resume 明确可能重放并给出幂等手段 |
| **R6** | 保留集被放进 P1；`agent_runs` 未决策；"只跑一次"不利测量；K6 不是已复现 bug；006 §8 旧状态；三套兼容生命周期 | `mvp_scope_v2.md` §3、§6；`evaluation_plan.md` §6；`agent_runtime_contracts.md` §1.2、§13；本文件 §8 | 保留集（22–42 题）纳入 P0；指标改由 **Trace** 记录，存储方案单独决定；允许预先固定重复次数并冻结配置、禁止看结果调参；K6 改记为未来数据库映射注意事项 **N1**；更正 §8 旧状态与"大小相等"措辞；兼容策略改为**单一路径增量迁移**并列出必须保留的接口与回归范围 |

### 14.2 未修改的内容

- `backend/` 全部文件、`docs/architecture/database_design.md`、`docs/decisions/ADR-005-agent-first-refocus.md`、`docs/reviews/2026-11-03_task006_review.md`、`docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`。
- 本文件 §3（原始用户 Prompt）与 §10（原始执行 Prompt）**未改一字**。
- 未安装依赖、未调用模型、未建库、未提交、未推送；未开始任务 007。

### 14.3 执行前后一致性（逐文件 SHA-256，不使用文件大小推断）

| 指标 | 数值 |
|---|---|
| 执行前文件数（排除 `.git`） | **93**（1,080,865 字节） |
| 执行后文件数 | **93** |
| 新增 / 删除 | **0 / 0** |
| 内容发生变化 | **10**（全部在本任务授权范围） |
| 逐字节不变 | **83** |
| `backend/` 下全部文件 | ✅ 前后 SHA-256 完全相同 |
| `docs/architecture/database_design.md` | ✅ `1b7e37350a18ff4c17e7063558a1ab3b4be5beabbd6a94aa4efbe236a5f56db7` 未变 |

发生变化的 10 个文件：`docs/evaluation/fixtures/agent_first_v1.json`、`docs/evaluation/cases/smoke_v1.jsonl`、`docs/evaluation/evaluation_plan.md`、`docs/architecture/agent_runtime_contracts.md`、`docs/architecture/agent_architecture.md`、`docs/product/mvp_scope_v2.md`、本文件、`docs/README.md`、`docs/development_logs/development_log.md`、`docs/checkpoints/git_history.md`。

**说明**：执行前的完整 hash 清单保存在会话临时基线文件中（不作为仓库交付物）。因此本记录可复核的是"统计口径 + 关键文件 hash + `backend/`/数据库设计未变"，而不是要求后续任务复现该临时文件。

## 15. Prompt 1-R2 窄范围修正记录（2026-11-06）

**任务口径**：Task 006 的 Prompt 1-R2，**不是** Task 007。依据 [2026-11-06_task006_r1_review.md](../../reviews/2026-11-06_task006_r1_review.md) 第 4 节，只修两项。
**最终状态**：**返修完成，待 Codex 复验**（未自行宣布通过，未把总路线更新为通过，未开始 Prompt 2）。

### 15.1 R1-R2：场景选择协议与 JSONL 结构对齐

| 项 | 修正前 | 修正后 |
|---|---|---|
| 协议写法 | `case.scenarios[case.scenario_id]`（对数组无法求值） | `run_items(case)` 展开；`case.scenarios` 按 `scenario_id` **数组查找**，`variant.scenarios[id]` **映射查找** |
| 运行项 | 未定义 | 有 `scenarios` 的 case 展开为 `len(scenarios)` 个运行项，每个只跑一次；无 `scenarios` 的 case 恰好 1 项 |
| 错误行为 | 仅笼统 `validation_error` | 8 类错误码：`MISSING_SCENARIO_ID` / `DUPLICATE_SCENARIO_ID` / `UNKNOWN_SCENARIO_ID` / `EMPTY_SCENARIOS` / `SCENARIOS_NOT_ARRAY` / `DEFAULT_SCENARIO_MISSING` / `DEFAULT_SCENARIO_UNKNOWN` / `SCENARIO_MISMATCH` |
| 证据要求 | fixture 覆盖 case，未说明未提供时怎么办 | fixture 提供 `evidence_requirement` 则以之为权威；未提供回退 case 级；case 显式写出时必须一致 |
| 一致性 | 无约束 | case 场景与 fixture 场景的 fault / terminal / evidence / assertions 逐项一致，否则 `SCENARIO_MISMATCH` |

已同步四处：[evaluation_plan.md](../../evaluation/evaluation_plan.md) §2.3、fixture `scenario_protocol`、C06/C08 的 JSONL、只读选择器验证脚本。

### 15.2 R3-R4：审批重放事件内容一致

| 项 | 修正前 | 修正后 |
|---|---|---|
| 第二次投递 | 事件对象多一个 `"replayed": true`（改变内容哈希） | 与第一次**逐字段相同**；已删除该字段 |
| 重放表达 | 依赖事件内部标记 | 场景级 `delivery.duplicates = [{event_id, deliveries: 2}]` |
| 幂等/冲突 | 只写 `expected`，未验证内容 | 校验器验证：同 ID 同内容 → 忽略 1 次、唯一事件 3、预算增量 0；同 ID 异内容（改 `decision` 或 `occurred_at`）→ `EVENT_ID_CONFLICT` |

契约 §12.6 同步写明：重放只能用**重复投递**表达，禁止在事件对象中加入 `replayed` 之类会改变内容哈希的字段；`AttemptRecord.replayed` 是运行时归并标记，与事件来源无关。

### 15.3 验证结果

见 §6 "Prompt 1-R2 窄范围修正的真实验证结果"：**PASS=62 / FAIL=0**，覆盖 JSON/JSONL 解析、14 个运行项展开、C06 两路径、C08 六路径、普通 case、10 个错误注入反例、事件内容哈希/幂等/冲突、证据解析、Decimal、相对链接与文件 hash。

**补充回归**：用 R1 的审批状态机参考实现重跑 C08 六个场景，**30/30 通过**（终态、审批状态、角色满足、拒绝码、重放计数均未因删除 `replayed` 而改变）。

### 15.4 执行前后一致性（逐文件 SHA-256）

| 指标 | 数值 |
|---|---|
| 执行前文件数（排除 `.git`） | **94** |
| 执行后文件数 | **94** |
| 新增 / 删除 | **0 / 0** |
| 内容发生变化 | **8**（fixture、JSONL、评测计划、契约、本归档、开发日志、Git 检查点、Docs README） |
| 逐字节不变 | **86** |
| `backend/`（62 个文件） | ✅ 前后 SHA-256 完全相同 |
| `docs/architecture/database_design.md` | ✅ `1b7e37350a18ff4c17e7063558a1ab3b4be5beabbd6a94aa4efbe236a5f56db7` 未变 |

**未修改**：`backend/`、`docs/architecture/database_design.md`、ADR-005、Review 文件、总路线、历史 Prompt 原文（§3、§10）、审批角色规则与业务事实。
**未执行**：安装依赖、调用模型、建库、提交、推送；未开始 Task 007。

### Codex 复验结论（2026-11-06）

**Task 006 / Prompt 1 已验收通过**。Codex 独立重跑场景选择器检查（62/62）和审批回归（30/30），核对 14 个真实运行项、重放事件逐字段一致、同 ID 异内容冲突；hash 比对确认 R2 仅改动 8 个授权文档，`backend/` 62 个文件及 `database_design.md` 未变。详细证据见 [Task 006 R2 Review](../../reviews/2026-11-06_task006_r2_review.md)。本结论只验收规格与 fixture，不表示 Runtime 或模型行为已经实现。下一步为 Prompt 2 / Task 007。

