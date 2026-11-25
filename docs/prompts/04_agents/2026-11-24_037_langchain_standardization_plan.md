# 2026-11-24_037_langchain_standardization_plan

## 1. 基本信息

- 日期：2026-11-24；任务 037，模块 04_agents；关联 036。
- 阶段：标准组件迁移方向与实施拆分，未实施。
- 起点：main / 77410ca，保留现有未提交成果；本轮 Pending，无提交/推送。

## 2. 任务目标和背景

用户引用“自研控制逻辑较多、LangChain 使用范围较窄”，要求采用高层实现以提高复用性和工程师接手能力。区分通用循环与领域治理，形成可执行迁移建议，不直接重写或删除原实现。

## 3. 原始用户 Prompt

```text
我觉得我们应该采用这个 不然 我们这个系统没有复用性 别的工程师 也很难理解 和修改
```

引用上下文：上一条回答“我们没有采用 LangChain 的整套高层 Agent／RAG 实现，而是自己写了不少控制逻辑，因此它的使用范围确实比较窄”。用户要求针对该选择调整方向。

## 4. AI 实际执行的主要步骤

1. 核对当前 Runtime、Agent 工厂、ToolExecutor、知识服务、现行契约及 Git 状态。
2. 核对官方 Agents/create_agent、middleware、Tools/ToolRuntime、Retrieval 文档；检索 BaseRetriever 参考链接失败，不据此声称该参考页已读。
3. 通过本地包元数据确认仅有 core/openai/graph，未安装 langchain 高层包；没有导入配置或读取密钥。
4. 编写 ADR-007，提出标准循环/工具/检索接口与现有治理集成，分四个可验收步骤；同步当前方向入口、索引、日志和检查点。

## 5. 新增和修改的文件

- 新增本文件、docs/decisions/ADR-007-langchain-standard-components.md。
- 更新 docs/README.md、当前基线、开发日志、Git 检查点。
- 未修改源码、测试、依赖、数据库、历史报告或冻结测量。

## 6. 执行结果和验证方式

- [ADR-007 迁移建议](../../decisions/ADR-007-langchain-standard-components.md)：用户方向已明确，具体实现尚未验证。
- 本机包元数据：langchain-core 1.7.6、langchain-openai 1.7.4、langgraph 1.2.20；langchain / langchain-community 未安装。
- 文档静态核验结束时追加；本轮没有重新运行业务回归，不沿用 719 tests 当迁移证据。
- 最终核验通过：UTF-8、新文档围栏、ADR/归档新增链接、原始 Prompt、9 节归档、编号 001–037；git diff --check 通过，HEAD 保持 77410ca。

## 7. 遇到的问题及解决方法

标准 Agent 可能改变工具并发、重试与停止语义；检索默认分块可能破坏页码/条款契约。ADR 要求受控试点、共享预算、同一执行边界、显式 metadata 与旧结果对照，避免简单换包造成退化。

## 8. 对应 Git Commit Hash

`d81e33d`（归档写作时为 Pending，之后与 Task 038 一同提交）；基线 77410ca。本轮不安装依赖、不运行 dev_loop、不调用付费模型。

## 9. 后续待办事项

依次推进标准领域试点、所有模型入口与 Graph 集成、标准检索接口、Web 接线和旧循环收尾。实施需另记真实结果；保留现有业务规则、历史实现与评测证据。
