# 2026-11-06_015_最终验收与项目展示材料

## 1. 基本信息

- **日期**：2026-11-06
- **任务编号**：015（正式 Prompt 10）
- **模块**：01_environment（交付与环境复现）
- **状态**：**DeepSeek 自检通过**（本地复现与全量验证通过；未打 Tag、未发布、未部署）
- **前置任务**：007–014
- **Git Commit**：见 §8

## 2. 任务目标和背景

前 14 项把能力做出来了，但对外仍缺一份"别人能照着跑起来"的材料。本任务做交付收尾：

- 根 README（是什么 / 怎么跑 / 架构图 / 演示 / 评测 / 限制）；
- `.env.example`（只有键名，无任何密钥）；
- 演示脚本（三个主场景 + 两个失败场景 + 网页）；
- 清理"只计划却写成已实现"的表述（重点重写 `backend/README.md`）；
- 全量复跑验证，产出可展示的版本候选。

## 3. 原始用户 Prompt

本轮（2026-11-06）用户取消 Codex 逐任务审查，要求连续推进到 Task 015：

````
- Task 015：可靠性收尾、使用文档、演示流程和项目交付材料

## 持续执行与停止条件

在当前运行时和额度允许范围内，持续按 Task 007 自检、Task 008、Task 009……Task 015 的顺序推进，
不要只输出计划就停止。

## Git 与检查点

项目所有者此前已授权在功能或里程碑完成后保存并推送到 GitHub。每次保存前：
- 检查完整 diff、测试结果和敏感信息；
- 提供清楚的 GitHub Desktop Summary 和 Description；
- 记录真实 commit hash 和推送状态。
````

范围以 `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md` 的 **Prompt 10 / Task 015** 为准。
该节明确要求：**不自动提交、打 Tag、发布或部署，需用户另行确认**——
本轮按用户更晚的授权**提交并推送**（属于"里程碑保存"），但**不打 Tag、不发布、不部署**。

## 4. AI 实际执行的主要步骤

1. 新增根 `README.md`：定位、快速开始、Mermaid 架构图、四个演示场景、评测结论、文档地图、质量证据、**已知限制**、版本候选说明。
2. 重写 `backend/README.md`：按当前真实模块（rag/db/orchestration/approval/api/evaluation）整理命令与职责表，旧版把系统写成"只有单 Agent 基线"，属过时表述。
3. 新增 `.env.example`：只列键名与缺省值，明确"未设置时仍可离线运行"。
4. 新增 `docs/demo/demo_script.md`：场景 A/B/C（成功）+ D/E（失败）+ F（证据）+ G（网页），每节含预期现象与讲解要点。
5. 全量复跑：契约自检、192 项单测、`pip install --dry-run -e .`（声明依赖可解析）、CLI 场景 A/D 实测、`evaluate --split heldout` 生成最终报告。
6. 记录检查点；不使用 `git tag` / release / 部署。

## 5. 新增和修改的文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `README.md` | 新增 | 项目主文档（架构图、演示、评测、限制） |
| `.env.example` | 新增 | 环境变量模板（无密钥） |
| `docs/demo/demo_script.md` | 新增 | 演示脚本与失败示例 |
| `backend/README.md` | 重写 | 对齐当前实现，删除过时/夸大表述 |
| `docs/evaluation/reports/*` | 更新 | 保留最终 dev 与 heldout v2 两批 |

## 6. 执行结果和验证方式

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python tests/smoke_agent_contracts.py` | 0 | 57 项通过 |
| 2 | `python -m unittest discover -s tests -p "test_*.py"` | 0 | `Ran 192 tests ... OK` |
| 3 | `python -m pip install --dry-run -e .` | 0 | `Would install commercial-property-multi-agent-0.1.0`（依赖均可解析） |
| 4 | `python -m app.cli investigate "A-301 现在还有多少钱没交？" --lease lease_xh_a301_2025` | 0 | `route=deterministic`、`verdict=conflicting` |
| 5 | `python -m app.cli investigate "B-101 的租期是什么时候？" --lease lease_jl_b101_2025` | 0 | 子任务 `project_scope_denied`，`results=()` |
| 6 | `python -m app.cli evaluate --split heldout` | 0 | A 0.5556 / B 0.5926 / C 0.8519（27 计分题） |
| 7 | `git check-ignore -v .env.example` | 1 | 未被忽略（应随仓库分发）；`.env` 已忽略 |

验收项对照：

| 验收要求 | 证据 |
|---|---|
| 新环境按文档可复现 | README §2 + backend/README §1–2（`conda activate` → `pip install -e .` → 自检命令），依赖 `--dry-run` 已验证可解析 |
| A-301 成功/故障/审批可演示 | `docs/demo/demo_script.md` 场景 A–E 全部实测 |
| 40 题对照有结果文件 | `docs/evaluation/reports/` 下 dev 与 heldout v2 各一套（JSON + 汇总 Markdown） |
| 切换/禁用 Agent 有回归证据 | `test_runtime.py::test_replace_success_swaps_capabilities_atomically`、`test_graph_workflow.py::test_disabled_capability_degrades_explicitly` |
| 未提交敏感数据 | `.env` 忽略；`.env.example` 仅键名；提交前 diff 扫描无密钥 |
| 明确限制与后续工作 | README §8、§9 |

## 7. 遇到的问题及解决方法

| 问题 | 原因 | 解决 |
|---|---|---|
| `backend/README.md` 严重过时 | 它停在 Task 008 之前（只有单 Agent 基线、缺 rag/db/api/eval） | 按当前模块重写；命令逐条实测后再写入 |
| 评测报告越攒越多 | 每次 `evaluate` 都新建时间戳文件 | 保留"最终代码提交对应的那一批"，中间调试批次删除；报告绑定 commit，避免误引 |
| 文档里存在"计划即已实现"的表述风险 | 早期文档写在功能之前 | 逐项对照代码/测试核对；未验证的一律写进 README §8 与 backend/README §5 |

## 8. 对应 Git Commit Hash

- **状态**：见 `docs/checkpoints/git_history.md`（里程碑提交后回填）。
- **未执行**：`git tag`、GitHub Release、任何部署。

## 9. 后续待办事项

- [ ] 接真实 DeepSeek 后按冻结配置重复 3 次测量，产出真实 token/成本报告（当前 token=0、cost=null）。
- [ ] PostgreSQL 实机验证排他约束/RLS/原生 NUMERIC。
- [ ] 混合检索 + rerank，用评测集验证召回（H18–H20 是目前已知短板）。
- [ ] 数据集 v3：补全 5 道无断言题；人工量表实际评分。
- [ ] 若要做产品化演示：替换演示鉴权（会话/OIDC + CSRF），`RunIndex` 迁 PostgreSQL。
