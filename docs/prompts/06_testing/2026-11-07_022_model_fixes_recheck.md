# 2026-11-07_022_model_fixes_recheck

## 1. 基本信息

- 日期：2026-11-07（Asia/Shanghai）
- 编号：022
- 模块：06_testing
- 关联任务：021 及其 N1–N6 修复
- 执行者：Codex（用户临时请求复查）
- 审查基线：`main` / `2512a3b`
- 本轮 Commit：`Pending`

## 2. 任务目标和背景

核对 DeepSeek 本次模型路径修复和 scoring-v3.1，复现原问题与修复边界，给出有证据的完成判断。

## 3. 原始用户 Prompt

```text
检查一下 deepseek 又完成了
```

## 4. AI 实际执行的主要步骤

1. 核对 Git 状态、`45af0cb..2512a3b` 差异、路线图、可信范围/最低事实契约/预算/叙述校验实现。
2. 运行现有 345 项 unittest、57 项契约检查和 scripted CLI。
3. 重跑三个离线 heldout 基线，结果仅在内存读取，没有覆盖历史报告。
4. 用 Fake 和内存 fixture 副本独立验证原 N1/N2/N4/N5 的改善，并复现 token 已耗尽后补查、B 基线错误目标、最终答案字段金额互换及错误结清。
5. 归档 Q1–Q3 及其验收标准；本轮不修改业务代码。

## 5. 新增和修改的文件

| 文件 | 变更 |
|---|---|
| docs/reviews/2026-11-07_model_fixes_recheck.md | 新增完整复查证据 |
| 本文件 | 新增 022 Prompt 归档 |
| docs/README.md | 登记 022 |
| docs/product/PROJECT_DEVELOPMENT_ROADMAP.md | 新增当前复查提示 |
| docs/development_logs/development_log.md | 新增日志 |
| docs/issues/issue_log.md | 新增 Q1–Q3 未解决入口 |
| docs/checkpoints/git_history.md | 登记审查基线与未提交状态 |

## 6. 执行结果和验证方式

- unittest：345 tests，21.686 秒，OK（skipped=1）。
- smoke：57 项通过。
- scripted 调查：exit 0，conflicting，无失败，模型/工具调用为 6/4。
- scoring-v3.1 离线 heldout：A 20/30、B 21/30、C 23/30。
- 原模型物理次数限额、领域目标约束、无证据成功及空调筛选均有实际改善。
- 仍复现三项 P1，见 [完整报告](../../reviews/2026-11-07_model_fixes_recheck.md)。

## 7. 遇到的问题及解决方法

修复缺口集中在 token 耗尽后的发送闸门、未接入 TaskScope 的 Single/B 路径，以及只看数字集合的叙述校验。已定位并提供反例，本轮没有实施修复。

## 8. 对应 Git Commit Hash

- 被审查基线：`2512a3b`。
- 本轮文档：`Pending`，未提交或推送。

## 9. 后续待办事项

- [ ] 修 Q1：已耗尽 token 预算阻止后续物理请求。
- [ ] 修 Q2：Single/B 与领域 Agent 共用目标和文档范围约束。
- [ ] 修 Q3：用户资金结论与字段值绑定，并对未验证状态如实计分。
