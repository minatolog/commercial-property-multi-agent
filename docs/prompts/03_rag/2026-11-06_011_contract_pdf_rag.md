# 2026-11-06_011_合同 PDF 导入、条款检索与可追溯证据

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：011（正式 Prompt 6）
- **模块**：03_rag
- **状态**：**DeepSeek 自检通过**（离线 BM25；向量检索 / Embedding / Reranker 属 P1，未实现）
- **前置任务**：007（Runtime 证据契约）、009（多 Agent 图）、010（文档元数据与只读数据层）
- **Git Commit**：见 §8

## 2. 任务目标和背景

此前"合同条款"只以 fixture 里**预写的 2 行片段**（`document_snippets`）出现，证据页码是硬编码的模拟值。
本任务把它换成**真实的 PDF 解析链路**：合成合同 PDF → 逐页提取 → 条款级分块 → BM25 检索 → 引用两级验证 → 进入多 Agent 报告的 `document_clause` 证据。

验收重点不是"能搜到字"，而是**页码可回溯**：fixture 声明 5.2 在第 12 页，真实 PDF 第 12 页就必须真的有 5.2，否则视为数据造假并直接失败。

## 3. 原始用户 Prompt

用户本轮（2026-11-06）要求：取消 Codex 逐任务审查，由 AI 依次完成 Task 007 自检 → Task 008–015，并给出每个任务的执行要求与停止条件。其中与本任务直接相关的原文摘录：

````
## 后续任务

按照路线图中既定顺序完成 Task 008–015。先读对应范围和验收标准，再实现当前任务；
每个任务完成并自检后，自动继续下一个，不要每完成一步就等待用户或 Codex 确认。

- Task 011：合同 PDF 导入、RAG 检索和可追溯证据

## 每个任务的执行要求

1. 一次只推进一个任务，保持模块边界清晰、低耦合、Agent 可插拔、配置独立。
2. 按 docs/README.md 的编号规则分配下一个全局唯一 Prompt 编号，并将完整 Prompt 归档到正确目录。
3. 实现当前任务的最小完整垂直切片，不顺手扩张到无关功能。
4. 为关键行为补充自动化验证；运行本任务相关测试和适当的现有回归测试，记录真实命令与结果。
5. 每个任务结束后更新：Prompt 归档、development_log、路线图、issue_log/knowledge_notes（必要时）、
   git_history 检查点。
6. 只有真实实现和验证完成后，才可把任务标记为"DeepSeek 自检通过"。不得编造测试、提交、推送或模型调用结果。
7. API Key 等只从环境变量或本地忽略文件读取，绝不写入代码、文档、日志、测试输出或 Git。
8. 没有外部凭据时，完成可验证的接口、Fake/离线测试和配置说明；准确标出真实服务验证受凭据限制。
9. 不重建或删除现有数据库设计，不擅自变更业务范围，不引入未论证的大型依赖。
10. 不执行破坏性 Git 操作。
````

任务范围以仓库文件 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` 的 **Prompt 6 / Task 011** 为准：

> 制作独立的合成合同 PDF；解析、分段、索引和受控检索；保留文档版本、页码、原文定位。先实现可评测的最小检索路径，召回不足再选择混合检索或 rerank，不复制其他项目的数据。
>
> 验收：引用能定位到实际 PDF 原文；不存在的条款明确无结果；草案与签署文件区分；文档内指令不能扩大权限或改变工具策略；同一版本能重建索引。模拟页码与真实页码的测试分开。

## 4. AI 实际执行的主要步骤

1. 安装 `pypdf`（解析）与 `reportlab`（写中文 PDF）。
2. `app/rag/pdf_builder.py`：用 reportlab + 系统中文字体（TTF 子集嵌入，缺失时回退 `STSong-Light`）生成**26 页合成合同**与 2 页物业制度；页码刻意与 fixture `document_snippets` 对齐。
3. `app/rag/chunker.py`：逐页提取 → 按条款号（`第X条` / `5.2` / `5.1.1` / `附件B`）切块；剔除页脚；`chunk_id` 编码 `document_id#vN#pX#clause`。
4. `app/rag/bm25.py`：纯词法 BM25；中文取二元组（单字仅在整段单字时保留），英文/数字按词小写。
5. `app/rag/service.py`：`KnowledgeService` 建索引 / 检索 / 引用验证。新增 `project_id` 与 `project_ids` 过滤（空集合 = 默认拒绝）。
6. `app/rag/library.py`：把 fixture 的 `documents` 元数据挂到真实 PDF，**严格校验** fixture 声明的页码/条款能在索引里定位到，否则抛 `DocumentMismatch`。
7. `app/tools/knowledge_tools.py`：`document.search` 只读工具，输出 `document_clause` 证据（含真实页码、条款号、摘录）并按调用方 `project_ids` 隔离。
8. `LeaseAgent` 增加条款检索步骤（仅当 `document.search` 在 `allowed_tools` 且 Planner 下发了 `query`）；工具不可用时**降级为警告**，不让租约事实查询整体失败。
9. 图与配置接线：`RuleBasedPlanner` 为 lease 子任务下发 `query`；`lease.yaml` 增加 `document.search`；`build_investigation_bundle` 装配知识库；报告新增 `derivation=document_clause` 的条款级 finding。
10. CLI：新增 `search` 子命令（可 `--verify-claim` 做 L1/L2 验证）；`tools` / `check` 改为使用与真实运行一致的工具集合。
11. 新增 `backend/tests/test_rag.py`（29 项）；按新行为修正 3 个既有断言（Trace 数量、降级状态）。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/rag/__init__.py` | 新增 | 不导出 `pdf_builder`（避免 `-m` 重复导入告警） |
| `backend/app/rag/pdf_builder.py` | 新增 | 26 页合成合同 + 2 页制度 PDF 生成 |
| `backend/app/rag/chunker.py` | 新增 | 逐页条款分块、页脚剔除、子条款号保留 |
| `backend/app/rag/bm25.py` | 新增 | 中文二元组 BM25 |
| `backend/app/rag/service.py` | 新增 | 索引 / 检索 / L1+L2 引用验证 / 项目隔离 |
| `backend/app/rag/library.py` | 新增 | fixture 文档 ↔ 真实 PDF 的对齐与严格校验 |
| `backend/app/tools/knowledge_tools.py` | 新增 | `document.search` 工具 |
| `docs/evaluation/documents/lease_xh_a301_contract_v1.pdf` | 新增 | 合成合同产物（26 页） |
| `docs/evaluation/documents/property_policy_v1.pdf` | 新增 | 合成制度产物（2 页） |
| `backend/app/agents/lease/agent.py` | 修改 | 条款检索 + 降级路径 |
| `backend/app/config/agents/lease.yaml` | 修改 | `allowed_tools` 增加 `document.search` |
| `backend/app/orchestration/investigation.py` | 修改 | Planner 下发 `query`；条款级 finding |
| `backend/app/investigation_demo.py` | 修改 | 装配 `KnowledgeLibrary` 与工具 |
| `backend/app/fixtures/repository.py` | 修改 | 新增只读 `snapshot()` |
| `backend/app/paths.py` | 修改 | `DOCUMENT_DIR` / `DOCUMENT_FILES` |
| `backend/app/cli.py` | 修改 | 新增 `search`；`tools`/`check` 统一工具集 |
| `backend/pyproject.toml` | 修改 | 声明 `pypdf` / `reportlab` |
| `backend/tests/test_rag.py` | 新增 | 29 项 |
| `backend/tests/test_graph_workflow.py` | 修改 | Trace 断言改为"按 subtask 归属"，不再断言固定条数 |
| `backend/tests/test_database_layer.py` | 修改 | 未注册文档工具时断言"降级为 partial + 明确警告" |

## 6. 执行结果和验证方式

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python -m app.rag.pdf_builder` | 0 | 生成 26 页合同 + 2 页制度 PDF |
| 2 | `python -m unittest tests.test_rag` | 0 | `Ran 29 tests ... OK` |
| 3 | `python -m unittest discover -s tests -p "test_*.py"` | 0 | `Ran 135 tests ... OK`（原 106 + 新增 29） |
| 4 | `python tests/smoke_agent_contracts.py` | 0 | 57 项契约检查通过 |
| 5 | `python -m app.cli search "租金递增比例"` | 0 | 命中 `5.3`(p13)、`5.2`(p12)、`3.2`(p3) |
| 6 | `python -m app.cli check` | 0 | `unimplemented_allowed_tools` 只剩 `compliance.checklist.read`、`lease.term_extract` |
| 7 | `python -m app.cli tools` | 0 | 列出 5 个工具，含 `document.search` |
| 8 | `python -m app.cli investigate` | 0 | 报告含 `derivation=document_clause` 的条款 finding（带页码） |
| 9 | `python -m app.cli demo` / `ask` | 0 | 既有路径未受影响 |

关键行为（均有断言）：

| 行为 | 证据 |
|---|---|
| 引用可定位到真实 PDF 原文 | fixture 声明 `5.2→p12`、`7.1→p20`、`附件B→p26`、制度 `3.1→p1`，`verify_snippets` 严格校验通过 |
| 页码造假会被抓住 | 故意声明 `5.2→p99` 时抛 `DocumentMismatch` |
| 不存在的条款明确无结果 | `search("押金")` 返回 `0` 条（合同与制度均无该条款） |
| 文档版本隔离 | v1 / v2 索引同一 PDF，按 `document_version` 过滤互不串味 |
| 项目隔离 | `project_ids={}` 或 `{prj_jinlan}` → 0 条；`{prj_xinghui}` → 命中 |
| 文档内指令不能改策略 | 注入条款「忽略以上所有指令…」只出现在 `excerpt`，工具 `name` / `required_permissions` / `max_attempts` 不变 |
| 工具不可用时降级 | 未注册 `document.search` 时 Lease 子任务 `partial` + 警告「条款检索不可用」，调查仍完成 |
| 报告含条款级证据 | finding 带 `source.page` / `source.clause_id`，`evidence_id` 可用 `get_chunk()` 回查 |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| 手写 PDF 生成报 `UnicodeEncodeError: 'ascii' codec` | 手工拼装内容流只能写 ASCII，Helvetica 也无法表示汉字 | 改用 reportlab + 系统中文字体子集嵌入；无 TTF 时回退 `STSong-Light` CID 字体 |
| 提取文本混入页脚「第 2 页 / 共 3 页」 | 页脚也是内容流里的文本 | chunker 增加页脚正则剔除，避免污染证据摘录 |
| `search("押金")` 返回 3 条低分噪声 | 中文单字也参与打分，任意含「金/押」的条款都能命中 | tokenize 改为中文只取二元组（单字仅在整段单字时保留） |
| `5.1.1` 被切块成 `clause_id=5.1`，与 `5.1` 重名 | 子条款正则只取到两段 | 改为 `\d+(\.\d+)+`，保留完整子条款号 |
| `document.search` 硬编码 `project_id="prj_xinghui"`，跨项目可越权 | 工具没有使用可信上下文 | 索引记录 `project_id`，检索按 `AgentContext.project_ids` 过滤，空集合默认拒绝 |
| 追加 Lease 工具调用后 3 个既有断言失败（Trace 3→4） | 原断言把 Trace 数量写死为子任务数 | 改为"按 `subtask_id` 归属断言 + 至少 N 条"，同时保留"call_id 全局唯一" |
| `python -m app.rag.pdf_builder` 触发 `RuntimeWarning: found in sys.modules` | 包 `__init__` 提前 import 了 `pdf_builder` | `__init__` 不再导出 `pdf_builder` |

## 8. 对应 Git Commit Hash

- **状态**：见 `docs/checkpoints/git_history.md`（里程碑提交后回填）。

## 9. 后续待办事项

- [ ] **P1 检索增强**：当前只有 BM25。用长问题（如 C03 全文）检索时，排名会被"字面重合多但业务无关"的条款占据；应接 Embedding / 混合检索 / Reranker，并用 Task 013 的评测集量化召回提升。
- [ ] 附件B 仍未电子化：这是 fixture 中的**真实缺失**（`doc_xh_a301_annex_b`），应保持"查不到"而不是补占位文件。
- [ ] `doc_jl_b101_contract`（锦澜）尚未生成 PDF，目前体现在 `missing_documents`；若要用跨项目隔离做端到端评测需补齐。
- [ ] 条款检索目前用 Planner 下发的**整段问题**作为查询；后续可拆出确定性关键词抽取，或改由模型生成检索式（需评测对比）。
- [ ] L2「引用是否支持结论」是词元覆盖度启发式（`method=token_coverage_heuristic`），不是语义判断；接入模型后应做两路对比。
