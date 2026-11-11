# 多 Agent 协作工作台：GitHub 模板调研与选型

- 日期：2026-11-10（Asia/Shanghai），Task 027。
- 本地起点：main / 8569cc2，工作区干净。
- 本轮范围：读现有页面/API、查官方 GitHub 仓库与许可、编写 DeepSeek 实施 Prompt。**未实现新 UI，未下载 vendor，未安装依赖，未提交或推送。**
- 用户要求：前端美化，体现多 Agent 合作，基于模板/开源方案复用，由 DeepSeek 实施。

## 1. 结论

**直接采用 Tabler 官方 starter/core 作为 UI 基础，借鉴 Langflow 的节点关系和详情面板。** 保持现有 FastAPI 同源静态页面，无需迁移为 Next.js，也无需替换已有 Agent/Graph 后端。

实现 Prompt：[DEEPSEEK_TASK027_MULTI_AGENT_UI_PROMPT.md](../handoffs/DEEPSEEK_TASK027_MULTI_AGENT_UI_PROMPT.md)。

## 2. 核实的候选

| 候选 | 核实内容 | 本项目用途/限制 |
|---|---|---|
| [tabler/tabler-starter](https://github.com/tabler/tabler-starter) | 官方最小 HTML 起始模板，含页面/卡片/表单结构；MIT | 直接复用基础 HTML；其示例 CDN @latest 要改成本地固定资源 |
| [tabler/tabler](https://github.com/tabler/tabler) | 完整 UI 组件/布局和编译 CSS/JS；MIT；默认分支 dev，不应当稳定资源版本 | 复用布局、卡片、状态徽章、表单、tabs/list 等；只引入必要 core 资源 |
| [langflow-ai/langflow](https://github.com/langflow-ai/langflow) | 节点式可视化工作流平台；MIT；完整独立前后端 | 借鉴节点/连线/详情交互，不能把平台本体当作轻量 HTML 主题安装 |
| [langchain-ai/agent-chat-ui](https://github.com/langchain-ai/agent-chat-ui) | Next.js；对接 LangGraph Server，要求 messages 状态；MIT；GitHub archived=true，页面标注 2026-11-03 归档 | 不作为本轮基础；自定义 FastAPI 不可直接无适配替换为该协议 |

这项选择是结合本仓库技术栈的工程判断，不是声称这些仓库提供了完全匹配商业地产调查的现成页面。通用 UI 复用现成模板，Agent 业务映射需要新增少量适配代码。

## 3. 具体来源与固定版本

- Tabler 当前查得的稳定发布：[core 1.7.4](https://github.com/tabler/tabler/releases/tag/%40tabler/core%401.7.4)，GitHub API published_at=2026-11-08T21:20:00Z，prerelease=false。
- 固定版本 [core/package.json](https://github.com/tabler/tabler/blob/%40tabler/core%401.7.4/core/package.json)：版本 1.7.4，提供 dist 静态资源，license=MIT。源码构建有 Node 要求；本轮建议使用预编译资源，不要求新增 Node 运行服务。
- 固定版本 [DefaultLayout.astro](https://github.com/tabler/tabler/blob/%40tabler/core%401.7.4/shared/layouts/DefaultLayout.astro)：包含 Navbar/Sidebar/PageHeader 等布局组织。仅参考/复用输出结构，不把 Astro 构建链搬入项目。
- [starter index.html](https://github.com/tabler/tabler-starter/blob/main/index.html)：GitHub blob SHA `84baea2d9a90ad96f5275d69cb96ab49d7ff4f67`，已读实际模板；实施时记录真正采用的资源版本和哈希。
- Tabler [许可](https://github.com/tabler/tabler/blob/dev/LICENSE)、starter [许可](https://github.com/tabler/tabler-starter/blob/main/LICENSE)：MIT。捆绑插件各自有许可，不能把 core 的许可概括为所有可选插件许可；本轮不需要图表插件。
- [Langflow README](https://github.com/langflow-ai/langflow)、[画布文档](https://docs.langflow.org/concepts-overview)、[许可](https://github.com/langflow-ai/langflow/blob/main/LICENSE)：核实节点画布、多 Agent 定位和 MIT；不引入该平台。
- [Agent Chat UI README](https://github.com/langchain-ai/agent-chat-ui)、[许可](https://github.com/langchain-ai/agent-chat-ui/blob/main/LICENSE)：核实服务协议、Next.js、归档与 MIT。
- Tabler [预览](https://preview.tabler.io/)、[官方文档](https://docs.tabler.io/) 供实施时查看组件；Codex 本轮未启动候选模板或对其浏览器视觉作验收。

以上为 2026-11-10 的调研快照；实施时核对固定版本可用性，页面运行不依赖 @latest/CDN。一次 GitHub tags ref 查询因连接器 URL 校验失败；已通过固定 tag 的 package.json 和布局文件读取核实版本，不声称解析得到完整 tag commit SHA。

## 4. 现有代码决定的边界

- `backend/app/api/static/index.html` 是约 10KB 的同源单文件页面，已有提交、历史、报告、审批与 Trace。
- `app.py` 当前返回 HTML，但尚未挂载拆分资源的静态目录；实施可补最小 StaticFiles 挂载，不暴露仓库根目录。
- POST /api/runs 等待调查结果后返回；没有逐节点实时事件流。因此采用整体等待状态和返回后的协作结果视图，不用定时动画伪造实时进度。
- 已有 report.agent_results、conflicts、missing_information、failures、budget、approval_request、approved_draft、authoritative_amounts 等；详情还带 traces。以真实字段映射展示，不增加事实。
- Agent/工具计量和“执行已结束”“证据充分”“争议解决”是不同维度，页面需要分开表达。
- 当前缺少完整处置建议生成；UI 本轮呈现缺口，不编造一套最终减免结论。预设草案金额与核算差额分别展示。

## 5. 推荐交付

工作台左侧为任务/历史，中央为规则规划→三个领域→核验→报告→审批的协作图，节点可展开实际证据/工具记录；报告与审批在独立面板清楚展示。组件来自 Tabler，节点视觉参考 Langflow。保留 API/业务边界、状态真实性、本地离线资产、窄屏布局和可访问性。

详尽范围与验收在实施 Prompt，实施尚待 DeepSeek 执行。本轮只核验调研与文档，不把历史 399/57 回归写成当前 UI 验收。

## 6. Codex 本轮文档核验

7 份 Markdown 变更（4 修改、3 新增）；58 个本地链接目标存在；33 个代码围栏块闭合；任务编号 001–027 连续且唯一；原始用户 Prompt 精确保存、九节归档齐全。UTF-8、Git 差异格式与纯文档变更范围检查通过。没有改 backend 源码或冻结评测，未进行模板运行/浏览器视觉验收。
