# Agent-first Markdown 一致性修正（Task 026）

- 日期：2026-11-09（Asia/Shanghai）。
- 本地起点：main / d6577da，工作区干净；最近提交只归档 Task 025，未发现后续业务修复。
- 依据：用户要求消除 Markdown 前后矛盾，以最新指导架构为准。
- 结果：建立 [当前基线](../architecture/CURRENT_BASELINE.md)，统一当前范围/契约/进度；历史原文与冻结记录保留。

## 1. 修正依据与边界

用户确认的 Agent-first V1.0、ADR-005 继续定义方向；后续用户指令决定协作流程和授权。当前源码证明实现状态，不自动推翻需求。历史 Prompt、报告和日志按当时版本解读，不以新结论改写旧测量。

本轮仅修改 Markdown，包含五份 Agent 执行提示词的范围/证据边界；没有修改 Python、YAML、迁移、业务数据，没有安装、数据库操作、付费模型调用、提交或推送。提示词修正不等于 Z1–Z3 已修复；项目仍为版本候选。

## 2. 具体矛盾与处置

| 原冲突 | 统一后的解释 | 主要文件 |
|---|---|---|
| 目标是完整地产 ERP / Agent-first | Agent 工程核心，地产作验证场景；完整 ERP 暂停 | 当前基线、系统架构、MVP |
| 数据库必须全量按 14 表落地 / P0 最小模型 | 14 表长期参考；当前为 12 表精简映射，PostgreSQL 待验 | 数据库顶部、系统架构、MVP |
| 未引入 FastAPI/Graph/ORM / 实际已有 | 明列实际模块和依赖，去掉早期骨架状态 | 系统架构、Agent 架构 |
| V2 提案是当前 API / 代码仍增量契约 | 不存在正式 contract_version=2.0 切换；按实际类型说明 | Runtime 契约、ADR |
| WorkflowState/map reducer / 实际 InvestigationState | 追加通道、按 run 过滤/subtask 收敛、单 thread 单新任务；保留目标与差距 | Runtime 契约 |
| 模型调用 ID 重放复用 / 物理请求须逐次计量 | 模型每次请求含 request_seq；工具逻辑调用与尝试分开 | Runtime 契约 |
| 模型从不重试 / BaseAgent 配置重试 | 如实描述各层有限尝试和共享预算，不增加独立无限重试 | Runtime 契约 |
| token 上限绝不超 / 响应后才能知道实际消耗 | 阻止已耗尽后的新增请求，记录已发生的超额，不承诺所有在途消耗绝不超限 | Runtime 契约 |
| 同 thread 跨新 run / 当前禁止复用 | 一条 thread 一次新调查，恢复走既有入口 | Runtime 契约、开发指南 |
| 改领域 YAML 即独立换模型 / 实际共享客户端 | 独立 YAML 已有，实际模型工厂读取 single.yaml，共享注入；策略未闭合 | Agent 架构、开发指南、README |
| 直接 invoke 工具示例 / 受控执行器要求 | 业务调用统一走 ToolExecutor/公共循环 | 开发指南 |
| 运行提示词要求续租建议/推导滞纳 / 当前只取事实供人工 | 保留现有能力，明确续租仅汇总事实、金额/逾期仅据工具；失败不算取证、目标不可替换 | 五份 Agent system.md |
| 完整 Service 分层已实现 / 部分聚合在仓库 | 保留目标，明确独立 Business Service 层差距 | 系统架构、开发指南 |
| 从未真实调用 / dev 与单题证据已存在 | 已有真实证据；正式 heldout/重复实验未完成 | README、评测计划、路线图 |
| 只有 8 题/runner 未开始 / 当前已有 40 题三基线 | 8 dev + 32 heldout_v3，30 题自动计分；人工与真实实验待做 | 评测计划、MVP |
| v1 导航指向旧 v2 / 当前 scoring-v3.3 | 仅更新历史导航，冻结评分正文和结果不变 | scoring_v1 |
| PDF 页码仅约定 / 已有实际解析 | 初始 fixture 定位与实际合成 PDF 解析分别描述 | 评测计划、契约 |
| Q1–Q3 全部修复 / 独立审查 Z1–Z3 未闭合 | 保留自检的时间语境；现行文档明确默认入口仍有缺陷 | 当前基线、README、路线图 |
| 所有剩余工作只缺外部条件 | Z1–Z3、配置策略可离线推进；PG/真实实验分别依赖外部条件 | 路线图 |
| 强制 Codex 每步审查 / 用户已取消 | DeepSeek 连续实现/自检，Codex 按需独立审查 | ADR、docs 规范、路线图 |
| 十步规划仅完成一步 / 当前修复任务已到 025 | 原十步主线与后续审查任务分开；剩余建议五个工作包 | 路线图 |
| 238/343/399 都被称“当前测试” | 标明对应历史任务；最新引用为 Task 025 的 399/57，本轮不冒充重跑 | README、演示脚本 |
| checkpoint 历史 Pending / 已提交 d6577da | 新增回填说明，旧记录保留 | Git 检查点 |

## 3. 历史保留方式

六份重整前原文保存在原目录的 `*_legacy_2026-11-09.md`。各文件只增加历史横幅，横幅之后的原文与起点工作区逐字节一致。保留旧 ADR-001～004 的原始理由、V2 迁移提案、原步骤验收和场景协议，不通过删除历史来“消除矛盾”。

两份 handoff 只增加适用说明；14 表设计只调整顶部指导范围，`## 1` 起正文保留。既有任务 Prompt、Review 和 reports 原文不改；日志/问题/检查点仅增加本轮记录与时间语境。运行提示词与历史任务 Prompt 分开：前者同步当前边界，后者逐字保留。

## 4. 本轮验证

本轮实际执行（解释器 `D:\anacada\envs\commercial-agent\python.exe`）：

| 检查 | 结果 |
|---|---|
| unittest discover（backend） | 399 tests，20.191 秒，OK（skipped=1） |
| smoke_agent_contracts.py（backend） | 57 项通过；首次因 Lease 角色标识短语改变失败，保留原角色名称后通过，未改测试 |
| 六份历史原文 | 全部与整理前工作区记录的 SHA-256 相符；与 HEAD 正文文本也相符（Git LF/工作区 CRLF 差异单独处理） |
| Markdown 范围 | 34 份 Markdown：25 份已跟踪文件修改、9 份新文件；无 Python/YAML/迁移/数据变更 |
| 本轮本地链接 | 237 个引用目标存在，零断链 |
| 代码围栏 | 168 个围栏块全部闭合（含六份历史原文） |
| 编号与原始 Prompt | 001–026 唯一且连续；026 原始用户文字精确匹配 |
| UTF-8/中文 | 34 份均可解码、含中文，无替换字符或连续问号损坏 |
| 历史保护 | 旧任务 Prompt/Review/测量/数据未改；两份 handoff 原正文、数据库 §1 起正文、scoring-v1 冻结规则正文保持一致 |
| Git 差异 | git diff --check 通过；HEAD 仍 d6577da，本轮未提交/推送 |

首次 PowerShell 写入管道的 ASCII 编码使新文中文失真，已以 UTF-8 完整重写；静态检查覆盖中文与替换字符。初次归档校验发现四份 Git LF/工作区 CRLF 字节不同，进一步用起点 SHA-256 核对原工作区字节，六份均精确保留。

没有读取/输出 .env，也没有新增真实模型请求。现有 Fake/scripted 回归通过只能证明工程兼容，不能证明新提示词在真实模型上的质量，更不关闭 Z1–Z3。

## 5. 下一步

按 [现行路线图](../product/PROJECT_DEVELOPMENT_ROADMAP.md) 先修复 Z1–Z3，再闭合独立模型配置和数据边界，完成 PostgreSQL、正式评测与人工量表、最终复现。MCP、部署和混合检索是可选后续，不因本轮整理升为 P0。

Git 状态：本轮 Pending；建议 Summary 为 `docs: reconcile Agent-first architecture and project status`。
