# Flowise 本地试用

固定版本：Flowise 3.1.4，Node 24 便携运行环境。

从项目根目录启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\flowise\start.ps1
```

打开 http://localhost:3000 ，首次进入按页面提示创建管理员账户。

停止：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\flowise\stop.ps1
```

默认端口被占用时，启动脚本可传 `-Port 3001`。

## 数据与凭证

`.data/` 保存 SQLite 数据库、加密密钥、上传文件和日志；`.runtime/` 保存 Node 与安装缓存。两者与 node_modules 均已加入 Git 忽略。备份流程时保留完整 `.data/`，尤其是加密密钥。

首次体验：进入 Agentflows，新建 Agentflow V2，添加 Start、Agent 和 Direct Reply 节点；在 Agent 内配置模型及凭证，连接节点后保存并测试。可从 Marketplace 导入模板。

这是独立的 Flowise 实例，尚未接入本仓库的 LangGraph 运行时、受控业务工具及审批流程。在 Flowise 内创建流程不会自动调用已有后端。模型凭证通过 Flowise 的 Credentials 配置。

安装依据：https://docs.flowiseai.com/getting-started

## 本机验证

已验证首页 HTTP 200、`/api/v1/ping` 返回 `pong`，监听地址为 `127.0.0.1:3000`。首次管理员和模型凭证尚未设置，尚未执行真实模型流程。

当前上游包有三个节点加载错误：旧版 ReActAgentChat、ReActAgentLLM（LangChain 的 uuid 导出兼容性），以及 AWSBedrock LLM（缺少 smithy 依赖）。启动日志中未发现 Agentflow V2 节点加载错误。日志见 `.data/stdout.log`。

Flowise 启动仍强制创建了用户目录下的空 `.flowise` 目录，实际数据库及密钥路径已配置到本目录的 `.data/`。
