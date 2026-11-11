# 给 DeepSeek 的实施 Prompt：Task 027 多 Agent 协作工作台

请在当前 `D:\commercial-property-multi-agent` 仓库直接完成本任务。目标是美化现有前端，让用户一眼看懂“谁负责什么、查到了什么、在哪里发生冲突、现在等谁审批”。

**必须基于已经核实的开源模板/组件改造，不从零设计一套 UI，也不更换现有 Agent 后端。完成实现、自检和项目文档归档后汇报。** 本任务已获用户授权，不需要再停在泛化方案阶段。本轮不自动提交、推送、发布或部署。

## 1. 先核对当前仓库

完整阅读以下文件，检查 AGENTS.md、Git 状态、未提交变更，保留他人的工作：

- `docs/architecture/CURRENT_BASELINE.md`
- `docs/handoffs/PROJECT_REFOCUS_AGENT_FIRST_V1.0.md`
- `docs/decisions/ADR-005-agent-first-refocus.md`
- `docs/architecture/system_design.md`
- `docs/architecture/agent_runtime_contracts.md`
- `docs/architecture/agent_development_guide.md`
- `docs/product/PROJECT_DEVELOPMENT_ROADMAP.md`
- `docs/README.md`
- `docs/reviews/2026-11-10_multi_agent_ui_template_review.md`
- `backend/app/api/static/index.html`
- `backend/app/api/app.py`、`backend/app/api/service.py`
- `backend/app/orchestration/investigation.py`
- `backend/tests/test_api.py`

Codex 调研时起点为 `main / 8569cc2`，工作区干净。这是调研快照，实施时以实际 Git 为准。Task 027 是本项的全局编号，已经登记；沿用并追加实施记录，不再为同一次实施重复占号，不改写原始用户 Prompt。

当前是 FastAPI 同源 HTML/CSS/JavaScript 页面，不是 React 工程。现有 `/api/runs` 提交采用请求返回完整调查结果的方式；没有可直接拿来用的逐节点 SSE/WebSocket。当前网页默认规则演示，不能标成“DeepSeek 正在实时推理”。

## 2. 已选定的开源基础：直接复用 Tabler，借鉴 Langflow

### 2.1 主模板：Tabler 官方 starter 与 core

- 仓库：https://github.com/tabler/tabler-starter
- 起始 HTML：https://github.com/tabler/tabler-starter/blob/main/index.html
- 主组件库：https://github.com/tabler/tabler
- 预览：https://preview.tabler.io/
- 文档：https://docs.tabler.io/
- 已核实许可：MIT；starter 与 core 都应保留适用版权/许可。
- Codex 核实的稳定 core 版本：`@tabler/core@1.7.4`，发布记录：
  https://github.com/tabler/tabler/releases/tag/%40tabler/core%401.7.4
- 固定版本布局参考：
  https://github.com/tabler/tabler/blob/%40tabler/core%401.7.4/shared/layouts/DefaultLayout.astro

**实际复用要求：**

1. 复用官方 starter 的 page / page-wrapper / page-header / page-body / container / row-cards 等布局和 core 的 card、badge、button、form、list、tabs/accordion 等真实组件样式。根据本项目裁剪，而不是照着截图手写一个“类似 Tabler”的全新主题。
2. 使用 **core 1.7.4 的预编译静态 CSS/必要 JS**，保存到本仓库 `backend/app/api/static/vendor/tabler/`。实施时验证下载内容、版本和 MIME，记录原始 URL、许可、实际版本和 SHA-256；若固定版本确实不可取得，先排查并记录明确替代版本，不能悄悄使用 latest/dev。
3. starter 当前示例使用 CDN 的 `@latest`；本项目必须替换为固定版本的本地资源。可以在准备阶段下载，页面运行阶段不依赖 CDN、Google Fonts、远程图片或 Node 服务。
4. 不复制整个 Tabler 的构建仓库、示例图片、Astro 工程或所有插件。不引入 ApexCharts 等本任务用不到的第三方插件。core 源码构建要求不等于使用其编译资源就必须升级本项目 Node。
5. 复制必要上游许可到 vendor，并建立 `backend/app/api/static/THIRD_PARTY_NOTICES.md`，列出真正复用了哪些布局/资源、来源/版本、许可证和本项目修改。其他图标/代码如另有许可，逐项记录，不笼统声称全都是 MIT。

### 2.2 协作表现参考：Langflow 的节点画布

- 仓库：https://github.com/langflow-ai/langflow
- 官方画布说明：https://docs.langflow.org/concepts-overview
- 已核实许可：MIT；它本身是完整的 Agent/工作流平台。

只借鉴“任务节点、端口、连线、领域颜色、节点详情面板”的视觉组织。**不安装 Langflow，不迁移其后端，不复制完整 React 前端，不做拖拽工作流编辑器。** 本项目已有自己的 LangGraph，画面表现它的现有分工即可。

画布采用少量本项目代码组织业务节点和 SVG/CSS 连线；通用工作台、卡片、表单、列表必须来自现成 Tabler。允许新增这部分业务展示代码，不把“不从零开始”误解为必须找到完全相同业务的成品。

### 2.3 不采用的候选

`https://github.com/langchain-ai/agent-chat-ui` 是 Next.js/聊天界面，要求 LangGraph Server 的协议与 messages 状态；本项目是自定义 FastAPI。Codex 在 2026-11-10 核实其已于 2026-11-03 归档。可以看工具展开/侧栏的交互，但本任务不把它作为新依赖，也不为套模板重建服务协议。

## 3. 产品与视觉目标

页面名称：**商业地产 · Agent 协作工作台**。

整体像清晰、专业的调查工作台：浅灰页面底色、白色卡片、深色文字，蓝/青色作为主要操作色，紫色少量用于知识检索。边框轻、间距统一、层级清楚。使用现有模板字号和组件节奏，中文系统字体即可。

Agent 领域可用蓝/青/紫辅助区分；成功/警告/失败必须另有明确文字和图标，不能仅凭颜色辨别。默认采用一种经过认真打磨的浅色主题，不把开发时间花在主题商城、复杂切换或大面积霓虹效果上。

不是只给旧表单换颜色。首屏必须能看到调查任务和 Agent 协作关系，技术细节折叠到合适位置，不让 JSON 占满页面。

## 4. 页面布局与交互

### 4.1 顶部

- 项目名称、简短业务说明。
- 当前任务/租约、运行状态。
- “规则演示 / 合成数据”标识，与当前后端事实一致。若未来返回真实模式元数据再据实更新；本任务不新增模型切换控件或启用付费调用。
- 刷新/新建调查的真实操作；不显示没有实现的设置、导出或管理入口。

### 4.2 左栏：任务与历史

- 使用模板表单组件保留问题输入、租约 ID、是否启用人工审批。
- 提交按钮给出清楚的 loading/disabled 状态，防止重复点击创建两次运行。
- 最近运行使用模板列表/状态徽章，支持本地搜索或筛选、选中态、空态和刷新。以现有接口参数为准，不向 API 发送不存在的筛选协议。
- 可以提供少量快捷问题，但标签明确为“示例问题”，不伪造运行记录和历史任务。

### 4.3 中央：Agent 协作视图（本次重点）

用节点与有方向的连线表达：

```text
任务规划
   ├─ 合同 Agent：租约、条款、版本与来源
   ├─ 账单 Agent：账单、付款、欠费及差异
   └─ 物业 Agent：维修记录、未关闭工单
                  ↓ 合并结果
             证据核验 → 调查报告 → 人工审批
```

这是一张固定职责图，实际选中/参与节点由返回结果决定，不是可编辑的通用编排器。简单账单查询只高亮账单路径，其他领域标“本次未调用”；不能所有任务永远亮三个 Agent。

每个领域卡片展示：角色名、一句话职责、当前可核实状态、相关工具/记录数。点击卡片在详情区域展示该 Agent 的实际结果、证据与工具调用；能看出合同、账单、物业如何汇到同一任务。

**状态真实性：**

- 请求未完成时，只显示总体“调查执行中，等待结果”，各节点显示“状态待返回”。不使用 setTimeout 把三个 Agent 依次变成“正在思考/完成”，不造进度百分比、聊天、思考链、逐节点耗时或 token。
- 接口返回后，按 report.agent_results / report.failures / traces 等真实字段展示成功、部分完成、失败、未参与。部分完成和 conflicting 必须保留，不能全绿。
- 总状态 completed 只说明执行结束，不能译为“争议解决”；awaiting_approval 是待审批，不能显示为结案。
- 规划/核验/报告节点缺少独立可观测事件时，把连线标为流程结构说明或结果回顾，不冒充逐节点实时日志。
- 如做“执行记录回放”，必须明确标“结果回放”；只用实际工具记录，不虚构顺序、并发时刻或耗时。当前 Trace 无开始时间，列表顺序不能冒充准确因果时间线。

### 4.4 Agent 详情与底部报告区

在可响应布局下设置详情侧栏或抽屉，以及报告 tabs/折叠面板：

1. **调查摘要**：保留已核实事实、冲突、缺失资料和当前待处理状态。只有后端已有的建议才作为“处置建议”展示；不存在时明确“暂未生成处置建议”，本轮不在浏览器编造经营/减免决定。
2. **证据**：按合同/账单/工单分组，展示实际已有的引用 ID、文档/版本/页码/摘录。只有真实可访问的文件/接口才做链接，否则提供复制 ID，不能做空 PDF 按钮。
3. **调用记录**：可按 Agent/工具筛选，展示 tool、attempt、status、duration_ms；不把工具耗时合计标成任务总耗时，也不把不同工具事件伪装成 Agent 对话。
4. **审批**：保留双角色串行批准/驳回、版本、有效期和意见，清楚标明“批准草案不执行真实调账”。已有后端 reason 字段可用于输入审批意见。
5. **原始数据**：JSON 放在可折叠开发详情，保留复制功能，不作为首屏主要内容。

金额只能来自现有可信结构化字段/后端内容，不在前端从自然语言猜出新的“可信金额”，不进行减免后余额等业务运算。

若 authoritative_amounts 有数据，展示其 rendered/结论及检查状态；为空时展示已有账单 finding 或“暂无结构化金额”，不能把它填成零。账单差额 computed_variance 与审批草案 amount 分栏标明，700 元预设草案不是 756 元差异的计算结论；展示来源，不暗示 AI 自主推导了减免金额。

## 5. API 与前后端边界

沿用现有接口，不换成 LangGraph Server 或模板自己的 API：

| 接口 | 用途 |
|---|---|
| GET /api/meta | 可信主体与审批白名单 |
| POST /api/runs | question、lease_id、with_approval，必要时现有 max_tool_calls |
| GET /api/runs | 最近运行 |
| GET /api/runs/{run_id} | report、traces 及运行详情 |
| GET /api/runs/{run_id}/traces | 工具记录 |
| POST /api/runs/{run_id}/approvals | decision、draft_version、reason；X-Actor-Id 按当前服务端白名单 |

实施前再次核对真实返回。特别注意：

- 列表/详情层与 report 层状态不一定同路径；approval_request.status 与阶段记录优先按实际对象展示，不能只读 report.approval_status 导致审批卡失真。
- run.traces 使用 tool 字段，不是假设 tool_name；report.agent_results 的 capability/subtask_id 可用于关联，不凭卡片位置猜。
- 支持字段缺失、空数组、旧记录、unknown 状态；缺失值显示“未提供/待核实”，不能默认成功或 0。
- 前端不能发送自报 permissions/principal_id；不能暴露 .env 或真实 API Key。
- 所有用户问题、证据和错误文本安全渲染，优先 DOM textContent 或统一转义，不能直接拼未转义 innerHTML。
- 捕获网络错误、非 JSON、4xx/5xx，显示可理解错误和服务端提供的 trace_id；服务没启动时提示正确访问方式，保留已输入内容。
- 不并发误刷新不同 run 的详情；快速切换任务时使用请求序号或 AbortController 防止旧响应覆盖新选中任务，事件绑定不能累积。

本任务以 UI 与适配为主。允许 `app/api/app.py` 增加受限的 StaticFiles 挂载以提供本地 CSS/JS/vendor，必要时补充不改变权限与业务语义的只读展示元数据。**不改 Agent、工具、预算、审批规则、数据库或评分逻辑，不重建数据，不把 Z1–Z3 顺手伪装成已解决。**

如果缺少真实实时接口，采用上述等待/结果回顾方案完成本轮，不为动画效果扩成 SSE 或重写任务生命周期。

## 6. 前端文件组织与低耦合

保持现有 FastAPI 单入口启动。不要另建必须同时运行的 Next.js/React/Vite 服务，也不为了样式引入大型构建链。

按职责适度拆分，建议：

```text
backend/app/api/static/
  index.html
  css/workbench.css
  js/api.js                  # fetch / 错误处理
  js/view-model.js           # 只读展示映射 / 状态中文化
  js/app.js                  # UI 事件和协调
  js/components/             # 按需拆 Agent 视图、报告与审批，不追求文件数量
  vendor/tabler/             # 固定版本的预编译资源及许可证
  THIRD_PARTY_NOTICES.md
```

可使用浏览器 ES modules；静态挂载只指向现有 static 目录，不把仓库根目录或 docs/data/.env 暴露成静态站点。模板资产本地化，避免运行时网络依赖。

保留旧页面的可追溯性由现有 Git 历史承担，不把旧代码大段复制进开发日志。不得删除其他模块或覆盖不相关未提交变更。

## 7. 验收要求

### 7.1 视觉与使用

- 1440×900 和 1280×800：首屏可见任务输入、协作视图、当前结果概况；卡片/连线不遮挡。
- 390 像素宽：改为纵向步骤/卡片，正文无横向溢出；JSON/长 ID 独立滚动或换行。
- 中文可读、键盘可操作、有 focus/label，状态有文字；prefers-reduced-motion 下减少动画。
- 新建/选择/刷新任务、查看节点、切换报告、查看证据/调用记录、审批/驳回都真实可用，无纯装饰假按钮。
- 无数据、提交中、部分结果、失败、待审批、批准草案各有清楚画面；服务断开能显示有意义的错误。
- 本地静态资产正常加载，不依赖外网 CSS/字体/图标；已有 Python 命令即可启动。

### 7.2 功能与回归

1. 用独立测试控制面/临时数据验证，不修改用户旧任务或自动批准用户现有草案。
2. 实测 A-301 复杂调查：三领域结果、冲突/缺失、Trace 对上返回内容。
3. 实测简单账单查询：只突出实际参与能力，其他领域为未调用。
4. 实测审批两阶段：物业→财务，批准后为草案，副作用仍为空；驳回、意见、异常状态展示正确。
5. 验证无权限/失败返回不会被画成成功、陈旧响应不覆盖当前任务，刷新能重读既有运行。
6. 浏览器 DevTools 检查无应用脚本错误、无缺失必要资产，确认 asset 的 HTTP 状态与 MIME 正确。使用现有浏览器/测试能力，不单为截图安装一套新框架。
7. 对新增静态路由/确有逻辑的展示映射补必要测试，不写仅断言某个 CSS 字符串存在的镜像测试。改了 API 静态装配则运行 API 测试及现有全量回归/契约自检，记录实际输出，不照抄此前 399/57。

在 backend 下的既有命令：

```powershell
python -m unittest discover -s tests -p "test_api.py"
python -m unittest discover -s tests -p "test_*.py"
python tests/smoke_agent_contracts.py
python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000
```

先检查端口/进程，不结束来源不明的已有服务。必要时在临时端口验收，交付时说明实际演示地址。截图必须来自运行后的真实浏览器，至少保留桌面协作总览、节点详情/调用记录、审批状态、窄屏四类；如果工具无法截图，明确说明未做视觉验收，不能拿示意图冒充。

## 8. 文档与最终交付

1. 在 `docs/prompts/05_frontend/2026-11-10_027_multi_agent_ui_refresh.md` 中追加 DeepSeek 实施记录，保留 Codex 调研和原始 Prompt。
2. 新增/更新本任务的实施与视觉自检报告，记录来源模板、具体复用组件、资产版本/哈希、布局偏差、真实 API 映射、测试/截图路径、未完成项。
3. 更新 docs 索引、开发日志、Git 检查点、演示脚本和当前进度；未实施的功能不写已完成。
4. 不改写冻结评测、旧 Prompt 或旧测量，不把 UI 美化算作模型质量提升，也不自动关闭 Z1–Z3、处置建议生成或 PostgreSQL 等其他任务。
5. 汇报时给出：改了哪些文件、如何套用模板、如何启动、哪些画面实测、剩余限制，以及建议的 GitHub Desktop Summary/Description。本轮不提交或推送。

请完成这个范围内的实现和验证，不只输出设计建议，不扩成完整地产后台或通用工作流平台。
