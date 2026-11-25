# 复查 Prompt：Task 038R 返修确认（只看返修改动）

- 编写：2026-11-25，Claude Code（返修调度与复核者）。给：与实施者不同的模型（由 `scripts/dev_loop/dev_review.ps1` 调用）。
- 性质：**只读复查**，只确认 [上一轮复查](../reviews/2026-11-25_task038_langchain_independent_review.md) 提出的问题是否关闭、返修有没有引入新问题。不重做整轮复查。上一轮结论：有条件通过，无 P1。
- **注意上一轮的教训**：工具调用次数有限，**先写结论再扩展**。每完成一项就记下结果；用到约 80% 的调用次数时停止实验，直接输出报告。

## 0. 硬性约束

同上一轮：不调用付费模型接口（只用脚本模型或 `httpx.MockTransport`）、不 `pip install`、不运行 docker、仓库内不改文件、不提交。PG 测试库（`COMMERCIAL_PG_TEST_URL`）实验后**删除自己建的临时角色**、回退到 `alembic downgrade base`；报告里不写连接串。变异实验在仓库外副本（`backend/` + `docs/evaluation/fixtures/`）里做。

## 1. 返修范围

- 返修提交 `525413c`（实施：dev_loop，编码方 DeepSeek、审查方 Claude，第 1 轮通过）；任务单 [DEV_LOOP_TASK038R_LANGCHAIN_REVIEW_FIXES.md](DEV_LOOP_TASK038R_LANGCHAIN_REVIEW_FIXES.md)。差异：`git diff 9db6687 525413c`。
- 之前的 `5d0b18b`（拒绝建角色的测试总是清理）、`1db4eb7` / `32633c7`（dev_review 续写参数）不在复查范围，但你可以确认 `5d0b18b` 确实让测试在断言失败时也清理角色。
- 返修记录：038 归档 §10。

## 2. 自报数字

731 tests OK（设置 PG URL 时 skipped=1；比上一轮 723 多 8 个）；契约 70；`check` exit 0。复核者自报：6 项变异（SDK 重试改 2、客户端可传 `model_provider`、去掉 `tool_lock`、检索不先按范围筛选、超时不可重试、综合节点不传注入客户端）均被新测试抓到。

## 3. 逐条确认（关闭 / 部分关闭 / 未关闭）

| 编号 | 问题 | 请这样验证 |
|---|---|---|
| P2-2 | SDK 重试无测试 | 读 `tests/test_task038r_langchain.py::TestSdkRetryIsDisabled`：是否真的走 `langchain_client.py` 的构造路径、真的数到物理 HTTP 请求；重做 `max_retries=2` 变异 |
| P2-3 | 客户端切换模式无测试 | 读 `test_api.py` 新测试；重做你上一轮的变异（给 `RunRequest` 加 `model_provider` 并写回服务配置） |
| P3-1 | 串行锁无测试 | 重做去掉 `tool_lock` 的变异 |
| P3-2 | 检索先筛选后 top-k 无区分语料 | 读 `test_rag.py` 新测试的语料是否真的让“高分段全在范围外”；重做你上一轮的回退变异 |
| P3-3 | 超时不可重试 | 第一次超时第二次成功 → 成功且记 2 次；预算只够 1 次 → 不重试；检查 Single 与领域 Agent 一致；确认重试不会绕过共享预算或截止时间 |
| P3-8 | 综合节点绕过注入客户端 | 读新测试；确认 `investigation_demo.py` 里没有其它会自建真实客户端的路径 |
| P3-9 | 综合节点死依赖 | `synthesis.py` 现在给内部循环传 `executor=None  # type: ignore`：判断这是否安全（综合节点真的不可能触发工具节点？模型返回 tool_call 时会怎样？），还是应该改成更明确的做法 |
| P2-1 | 运营总览写死状态 | 逐处检查 `static/ops/index.html` / `app.js` 是否还有会被理解为实时状态或真实审批的文案；3D 商场页（`static/mall/`）是否也需要同样标注 |
| P3-10 | 开发日志措辞 | 看改动是否只限 Task 038 条目 |
| P3-4/5/6/7/11 | 接受为已知差异 | 读 038 归档 §10 的理由是否成立 |

## 4. 回归与副作用

复跑全量回归（两种环境）、契约、`check`；返修有没有改变已有测试（只能追加）、有没有改 `tool_loop.py` / `langchain_client.py` / `rag/` 的实现（任务单禁止）。

## 5. 报告

你的最终回复就是报告正文（由调度脚本保存到 `docs/reviews/2026-11-25_task038_repair_review.md`）：开头写每条关闭情况与是否有新问题（P1 / P2 / P3），整体是否改判；写明本轮限制与实验卫生（是否留下 PG 角色 / 数据）。不要声称最终验收通过。
