# 2026-11-03_004_PostgreSQL 数据库架构设计

## 1. 基本信息

- **日期**：2026-11-03
- **任务编号**：004
- **模块**：02_database
- **用户侧编号**：用户在本条 Prompt 中称其为「Task 003」；因项目内部编号已用至 003（模块化多 Agent 架构约束），本归档顺延为 **004** 以避免编号冲突，原始 Prompt 中的编号保持原样未改
- **关联任务**：002（文档体系，建立本文档骨架）；003（Agent 架构，Service 分层与 `agent_runs` 契约）
- **Git Commit**：`Pending`

## 2. 任务目标和背景

项目前两步（GitHub 仓库、独立 Conda 环境）已完成。本步进入数据库设计。

范围被明确限定为**设计与文档**：不安装 PostgreSQL、不建真实表、不写 SQLAlchemy 模型代码、不提交 Git。

核心约束（来自业务侧）：

- 一个综合体 → 多楼栋 → 多商铺；一个商铺可有多个历史租约；一个租户可租多个商铺。
- 第一版可限制"一合同一商铺"，但**必须保留多商铺租约的扩展空间**。
- 同一商铺的租约生效时间不得冲突。
- 支持免租期、物业费、阶梯租金；一账单含多收费项；一付款可核销多账单。
- 合同文档需版本与来源追溯；Agent 运行需保存任务状态与审计信息。
- 金额必须 `NUMERIC`；区分业务日期与系统时间戳；不得用删除历史合同表达租户变更。
- 各 Agent 不得直接依赖其他 Agent 的内部数据结构，须经 Service / Repository 访问。
- 为项目级数据隔离与权限控制预留扩展。
- 规模基线：约 30 个商铺、25 个租户，但结构需支持后续扩展。

## 3. 原始用户 Prompt

````
# Task 003 — PostgreSQL 数据库架构设计
你现在担任我的 Python 后端架构工程师和数据库设计助手。

项目名称：commercial-property-multi-agent

## 一、项目背景
我们正在开发商业地产租约与物业运营 Multi-Agent 协作系统。

项目的主要业务包括：

- 商业综合体及商铺管理
- 商业租赁合同管理
- 租户管理
- 租金和物业费计算
- 应收账单与实际收款
- 租约到期和欠费风险
- 商铺维修与物业工单
- AI Agent 跨业务分析
未来将使用 LangGraph 实现 Coordinator、Lease Agent、Billing Agent、Property Agent、Risk Agent 等模块。

系统必须具备模块化、可维护性、可扩展性和低耦合特性。

技术方案：

- PostgreSQL：业务数据库
- SQLAlchemy 2.0：ORM
- Alembic：数据库迁移
- FastAPI：后端接口
- Pydantic：数据验证
- LangGraph：Agent 编排

## 二、本次任务
目前已经完成：

1. GitHub 项目仓库创建。
2. 独立 Conda 环境配置。
现在进入第三步：数据库设计。

**本次仅完成数据库结构设计和文档，不要安装 PostgreSQL 或创建真实数据表。**

## 三、设计范围
以以下十三张表为初始方案：

1. projects
2. buildings
3. units
4. tenants
5. leases
6. lease_charge_rules
7. invoices
8. invoice_items
9. payments
10. payment_allocations
11. work_orders
12. documents
13. agent_runs
请先分析这些表是否足以支持 MVP，不要机械照搬。如果发现数据关系不合理、实体缺失或冗余，请说明原因并提出优化建议。

需要重点考虑：

- 一个商业综合体包含多个楼栋。
- 一个楼栋包含多个商铺。
- 一个商铺可能存在多个历史租约。
- 一个租户可以同时租赁多个商铺。
- 第一版可以限制一份合同对应一个商铺，但要保留未来支持多商铺租约的扩展空间。
- 同一商铺的合同生效时间不能出现未经业务允许的冲突。
- 租约可以存在免租期、物业费和阶梯租金。
- 一张账单包含不同收费项目。
- 一笔付款可能核销多张账单。
- 维修工单与具体商铺相关联。
- 合同文档需要支持版本及来源追溯。
- Agent 运行记录需要保存任务状态和必要的审计信息。

## 四、技术设计要求

1. 所有表明确主键、外键和关联关系。
2. 金额采用 PostgreSQL NUMERIC 类型，不使用浮点数。
3. 明确每张表的必要字段、字段类型、Nullable 和默认值。
4. 对必要的字段设置唯一约束、CHECK 约束和索引。
5. 明确合同状态、账单状态和付款状态的含义。
6. 使用规范的时间字段，区分业务日期和系统时间戳。
7. 避免重复存储可以通过可靠查询计算出来的数据。
8. 不能通过删除历史合同来表达租户变更。
9. 数据库设计要便于未来增加招商 Agent、财务 Agent 等模块。
10. 各 Agent 不能直接依赖其他 Agent 的内部数据结构，而应通过业务 Service / Repository 访问数据。
11. 为不同商业项目的数据隔离和权限控制预留扩展设计。
12. 设计应符合关系数据库规范化原则，但避免为了理论上的完美而过度复杂化。

## 五、文档交付
请生成或更新：

`docs/architecture/database_design.md`

该文档必须包含：

1. 数据库业务背景。
2. 核心业务实体说明。
3. 完整 ER 图（使用 Mermaid erDiagram）。
4. 每张数据表的字段设计。
5. 主键、外键、唯一约束和必要索引。
6. 主要业务关系解释。
7. 租金计算及账单核销的数据流。
8. Agent 如何通过 Service 层访问业务数据库。
9. 未来扩展建议。
10. 当前设计存在的限制和待确认问题。
同时更新：

`docs/development_logs/development_log.md`

将本次数据库设计任务的 Prompt 归档到：

`docs/prompts/02_database/`

并遵守我们已经建立的 Prompt 归档、开发日志、经验总结和 Git Checkpoint 规范。

如果相关文档不存在，可以创建；如果已经存在，不要覆盖已有记录。

## 六、特别注意
不要直接开始实现所有数据库模型。

请先完成架构设计文档，说明字段和实体之间的关系。

不要为了让 Agent 看起来更复杂而创建大量无意义的数据表。

本项目第一阶段的数据规模只有约30个商铺、25个租户，但数据库结构需要适合后续扩展。

不要修改此前已经创建的 Conda 环境。

不要提交 Git Commit，先让我审核设计。

## 七、最终汇报
完成后请告诉我：

1. 最终建议采用多少张数据表。
2. 为什么这样拆分。
3. 最重要的业务关系是什么。
4. 哪些字段容易出现设计问题。
5. 如何保证未来 Agent 扩展不需要大规模修改数据库。
6. 生成和修改了哪些文档。
7. 下一步应该执行什么。
最后提供一条建议的 Git Commit Message。

本次任务以数据库设计文档和 ER 图为交付物，不创建真实业务数据库。
````

## 4. AI 实际执行的主要步骤

### 4.1 前置状态检查（只读）

1. `git log` / `git status`：确认上次提交仍为 `7ed2665`，任务 003 的架构骨架尚未提交（工作区有未提交改动）。
2. 读取 `docs/architecture/database_design.md`（4690 字符，骨架状态），确认其中已有「5 条设计原则 + 10 个待建模实体 + 6 项待决策问题」。
3. 检查 `docs/prompts/02_database/` 仅有 `.gitkeep`，无历史归档 → 不存在覆盖风险。

### 4.2 方案评估（不照搬 13 张表）

对 13 张表逐张判断「保留 / 合并 / 删除 / 新增」，结论：

- **无删除、无合并**：`invoice_items`、`payment_allocations`、`lease_charge_rules`、`documents`、`agent_runs` 均有不可替代的独立存在理由。
- **新增 1 张** `lease_units`，解决"多商铺租约"扩展性（若把 `unit_id` 放在 `leases`，未来放开需破坏性迁移 + 全量代码改动）。
- **识别 9 项设计缺口**：排他约束缺失、约束无法引用其他表、明细无规则追溯链、文档缺版本与来源字段、缺隔离键、`agent_runs` 缺调用树字段、软删除与唯一约束冲突、公共区域工单无商铺。

### 4.3 设计文档编写

在既有骨架上**升级而非覆盖**：保留原 5 条设计原则并扩充（2.1~2.8），保留 `## 14. 变更历史` 中的 002 行，新增 004 行。原 6 项待决策问题逐条给出结论并写入对应章节。

新增章节：方案评估（第 3 章）、最终表清单（第 4 章）、实体说明（第 5 章）、14 张表完整字段（第 6 章）、Mermaid ER（第 7 章）、约束与索引汇总（第 8 章）、状态机与业务关系（第 9 章）、出账与核销数据流（第 10 章）、Service 分层（第 11 章）、扩展建议（第 12 章）、限制与待确认（第 13 章）。

### 4.4 关键技术决策

| 决策点 | 选择 | 被否决的方案及原因 |
|---|---|---|
| 多商铺支持 | 新增 `lease_units` + MVP 用 `UNIQUE(lease_id)` 限一铺 | 否决 `leases.unit_id`：未来放开需破坏性迁移 |
| 租期冲突 | `EXCLUDE USING gist` 排他约束 | 否决应用层校验：并发下失效 |
| 排他约束如何排除草稿 | `lease_units.blocks_occupancy` 本地列 + 触发器 | 否决 JOIN `leases.status`：PG 排他约束不支持跨表引用 |
| 阶梯租金 | 物化多条 `effective_from/to` 分段规则 | 否决存递增率：规则中途变更后历史账单无法复现 |
| 账单总额 | 不落库，由 `SUM(invoice_items.amount)` 派生 | 否决存 `amount_total`：双写会不一致 |
| 账单租户 | 不落库，经 `leases.tenant_id` 取 | 租约租户不可变（换租户=新租约），无需快照 |
| 行级金额 | 存储 `invoice_items.amount` | 这是唯一一处"看似冗余"的存储：行级四舍五入后 `quantity × unit_price` 无法还原，属财务凭证性质 |
| 枚举表示 | `TEXT + CHECK` | 否决 PG 原生 `ENUM`：删改值需重建类型，早期状态机变动频繁 |
| 数据隔离 | 叶子表冗余 `project_id` + 复合外键 `(id, project_id)` | 否决纯 JOIN 推导：RLS 策略需 4 层 JOIN，无法高效表达；复合外键让冗余不可能不一致 |
| 文档版本 | 不可变行 + `supersedes_id` 链，无 `updated_at` | 否决原地更新 + 历史表：版本链本身即审计证据 |
| Agent 输出 | `agent_runs.request_payload/output_payload` 用 `jsonb` | 否决为每个 Agent 建结构化列：Agent 演进会导致频繁改表 |
| 软删除唯一约束 | 全部改为部分唯一索引 | 否则删除后编号被永久占用 |

### 4.5 校验

1. 章节结构检查：14 个章节齐全，`### 6.1`~`### 6.14` 共 14 张表全部有字段表。
2. 代码围栏平衡：40 个 ``` 围栏，偶数（闭合）。
3. Mermaid 结构校验：14 个实体块 / 14 个闭合括号；全部属性行符合 `类型 名称 [PK|FK|UK]` 语法。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `docs/architecture/database_design.md` | **修改（大幅扩充）** | 由 4690 字符骨架升级为约 46000 字符完整设计；保留原原则与变更历史，不覆盖既有记录 |
| `docs/prompts/02_database/2026-11-03_004_postgresql_database_design.md` | 新增 | 本归档 |
| `docs/prompts/02_database/.gitkeep` | 删除 | 目录已有实际文件，占位不再需要 |
| `docs/development_logs/development_log.md` | 修改 | 追加任务 004 记录 |
| `docs/checkpoints/git_history.md` | 修改 | 新增阶段 2 待提交记录 + 建议 Commit Message |
| `docs/README.md` | 修改 | 编号登记表补 004 |
| `docs/lessons_learned/knowledge_notes.md` | 修改 | 新增 2 篇数据库建模笔记 |
| `docs/architecture/system_design.md` | 修改 | 待定问题 #9 标记为已决策，引用数据库设计文档 |
| `docs/architecture/agent_development_guide.md` | 修改 | 新增「数据访问规则」章节（Agent 不得直接访问 DB） |

**未创建**：任何 `.sql` 文件、SQLAlchemy 模型、Alembic 迁移、数据库连接配置。
**未修改**：Conda 环境、`backend/app/` 下任何代码。

## 6. 执行结果和验证方式

| 验证项 | 方式 | 结果 |
|---|---|---|
| 文档章节完整 | 提取所有 `^## ` 标题 | 14 个章节，覆盖用户要求的 10 项内容 |
| 14 张表逐表字段设计 | 提取 `^### 6\.\d+` | 6.1~6.14 全部存在，每表含「字段 / 类型 / Nullable / 默认 / 说明」五列 |
| ER 图为 Mermaid erDiagram | 正则提取 mermaid 块 | 存在，14 实体 + 25 条关系 |
| Mermaid 语法结构 | 实体块与闭合括号计数、属性行正则校验 | 14/14 闭合，属性行 0 处非法 |
| 代码围栏闭合 | 统计 `^``` 行数 | 40（偶数） |
| 主键外键唯一约束索引 | 第 8 章汇总 | 17 条唯一约束、2 条排他约束、21 条索引，每条注明所服务的查询 |
| 状态含义 | 第 9 章 | 租约 / 账单 / 收款 / 工单 / Agent 运行 5 组状态机全部定义 |
| 业务日期与系统时间戳区分 | 2.1 + 各表字段类型 | 日期用 `date`，事件用 `timestamptz`，并说明判断标准 |
| 未安装 PostgreSQL / 未建表 | 未执行任何安装或连接命令 | 确认 |
| 未提交 Git | 未执行 `git add` / `commit` | 确认 |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| 任务编号冲突 | 用户称本次为「Task 003」，但项目内部 003 已用于「模块化多 Agent 架构约束」 | 归档文件顺延为 004，并在基本信息中标注用户侧编号；原始 Prompt 中的「Task 003」标题保持原样不改 |
| PostgreSQL 排他约束无法表达"草稿不占位" | `EXCLUDE` 的谓词只能引用本表列，不能 JOIN `leases.status` | 在 `lease_units` 增加 `blocks_occupancy` 本地列，由触发器按租约状态同步；文档中显式声明这是受约束能力限制的受控冗余，并列入已知限制 #1 |
| 软删除使业务编号永久不可重用 | 普通 `UNIQUE` 会把软删除行也算进去 | 全部业务唯一约束改为 `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`，并在 2.4 说明 |
| `project_id` 冗余可能不一致 | 手工维护的冗余字段容易写错 | 用复合外键 `(unit_id, project_id) → units(id, project_id)` 强制一致；父表加 `UNIQUE(id, project_id)` |
| 概览视图若同时 JOIN 明细与核销会翻倍 | 两个一对多关系 JOIN 产生笛卡尔积 | 视图改用两个独立子查询分别聚合后再 LEFT JOIN，并在第 10.3 节点明该陷阱 |
| 验证脚本正则报错 | PowerShell 中 `?` 在正则里被当作量词 | 改用显式 `[PK|FK|UK]` 分组与 `-match` 两次校验，重新验证通过 |

## 8. 对应 Git Commit Hash

- **状态**：`Pending`
- **原因**：用户明确要求「不要提交 Git Commit，先让我审核设计」。同时工作区仍包含任务 003 的未提交改动，本次设计与之同属未提交状态。
- **建议 Commit Message**：见 `docs/checkpoints/git_history.md`。

## 9. 后续待办事项

- [ ] 评审本文档第 13.2 节的 8 项待确认问题
- [ ] 评审通过后提交（可与其他未提交改动分开提交，便于回溯）
- [ ] 安装 PostgreSQL 并创建数据库（`ENCODING 'UTF8'`）
- [ ] 执行 `CREATE EXTENSION btree_gist`
- [ ] 编写 SQLAlchemy 2.0 模型（`app/db/models/`），严格对照第 6 章字段
- [ ] 编写 Alembic 初始迁移，**手动补充** 2 条 `EXCLUDE` 约束、部分唯一索引 `WHERE`、复合外键（见 2.5）
- [ ] 创建 `v_invoice_outstanding` 视图
- [ ] 编写 `set_updated_at()` 与 `lease_units.blocks_occupancy` 同步触发器
- [ ] 建立 Repository / Service 骨架与 DTO（`app/db/repositories/`、`app/services/`、`app/schemas/`）
- [ ] 为 `payment_allocations` 的 4 条跨行不变量编写测试
- [ ] 阶段 3：`document_chunks` 与向量存储方案
