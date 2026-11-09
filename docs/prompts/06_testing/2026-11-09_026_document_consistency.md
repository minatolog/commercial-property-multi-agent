# 2026-11-09_026_document_consistency

## 1. 基本信息

- 日期：2026-11-09（Asia/Shanghai）。
- 全局任务编号：026；模块：06_testing（文档一致性检查）。
- 关联任务：006–025；Git 起点：main / d6577da，工作区干净。
- 本轮 Git Commit：Pending；未提交或推送。

## 2. 任务目标和背景

消除 Markdown 中旧业务方向、历史骨架状态与当前实现的冲突。以用户确认的 Agent-first V1.0/ADR-005 为方向依据，最新用户指令决定流程。设计、实现、验证分别描述，保留历史文档、原始 Prompt、冻结测量和现有代码。

## 3. 原始用户 Prompt

```text
刚才发现有的md 文件中出现了前后矛盾 的情况 帮我消除这些矛盾 一切用最新的指导架构
```

## 4. AI 实际执行的主要步骤

1. 检查本地 Git 状态与最近提交、Markdown 文件清单、项目 docs 规范及可见 AGENTS 文件。
2. 完整阅读 Refocus V1.0、ADR-005、MVP 范围和主要现行规范；检索其他 Markdown 的状态/优先级/流程冲突。
3. 对照代码的工厂/配置、Runtime、工具、数据库、实际 Graph 状态、评测与最近 Task 025 报告。
4. 为六份需要重整的长文保存原文归档；新增当前基线入口，重整现行指导并同步相关入口和索引。
5. 首次写入遇到 PowerShell ASCII 管道导致新文中文变问号，切换 UTF-8 重写；原文归档正文保留。
6. 同步五份运行提示词的职责/证据边界；检查链接、围栏、编号、Unicode、Git 差异及冻结/历史文件保护，运行现有回归与契约自检。验证实录见本轮报告。

## 5. 新增和修改的文件

| 分组 | 内容 |
|---|---|
| 当前入口 | docs/architecture/CURRENT_BASELINE.md（新增） |
| 六份现行文档 | system_design、agent_architecture、agent_runtime_contracts、agent_development_guide、evaluation_plan、PROJECT_DEVELOPMENT_ROADMAP |
| 原文归档 | 上述六份同目录的 *_legacy_2026-11-09.md（新增，仅加历史横幅，正文逐字节保留） |
| 适用范围/入口 | 根与 backend README、docs README、MVP 范围、ADR-005、数据库设计顶部、两份 handoff 顶部、scoring_v1 导航、演示脚本 |
| 运行提示词 | Lease/Billing/Property/Single 当前范围与证据边界；Compliance 默认禁用占位说明；不替代 Z1–Z3 代码修复 |
| 记录 | 本 Prompt、本轮 review、开发日志、问题日志、Git 检查点 |

## 6. 执行结果和验证方式

现行文档统一为 Agent-first；规划不冒充实现，历史快照不冒充现状。真实模型已有记录，正式实验仍待做；12 表实际映射与 14 表长期设计分开；独立模型配置和 Service 分层差距明确，Z1–Z3 保持未关闭。

文档静态检查、历史原文/数据保护与 Git 变更范围验证见 [本轮报告](../../reviews/2026-11-09_document_consistency_review.md)。本轮实际回归 399 tests（20.191 秒，skipped=1）、57 项契约通过；没有调用真实模型或 PostgreSQL，不能用 Fake 回归证明新提示词的真实质量。

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| 文档互相否定 | 只叠加新状态，未同步旧正文；历史指令未标范围 | 建当前入口、重整六份现行文档，保留历史并标适用范围 |
| 新文中文变问号 | PowerShell 5.1 的 OutputEncoding 默认 ASCII | 显式 UTF-8 重写、核验 CJK 字符/问号、原文哈希 |
| 首次契约自检失败 | Lease Prompt 的固定角色标识短语改变 | 保留“商业地产租约专员”角色名，重新自检通过，不修改测试 |

## 8. 对应 Git Commit Hash

- Pending：本轮未执行 Git 提交或推送。
- 起点 d6577da；该 hash 不是本轮提交。

## 9. 后续待办事项

- 修复并复验 Z1–Z3；明确独立模型配置与数据层职责。
- 按更新路线完成 PostgreSQL 实机、正式真实实验/人工量表和最终复现。
- 旧 Notability PDF 保持历史快照；未来需要当前阅读版时另行更新。
