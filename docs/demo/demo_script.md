# 演示脚本（A-301 三个主场景 + 两个失败场景）

所有命令在 `backend/` 目录下执行；数据为**合成数据**，无网络、无真实模型。
每节都给出「预期现象」与「讲解要点」，便于现场演示和复核。

> 上述“无真实模型”仅指本脚本的默认离线命令，不代表项目从未调用真实模型。当前状态见 [当前基线](../architecture/CURRENT_BASELINE.md)；默认 CLI 可信金额投影 Z3 尚未闭合，完整字段需结合 `--full` 查看，本脚本的预期金额不能当作默认输出已经全部接线。

准备：

```bash
conda activate commercial-agent
cd backend
python -m app.cli tools        # 确认 5 个只读工具已注册（含 document.search）
```

---

## 场景 A：确定性路径（不该惊动多 Agent）

```bash
python -m app.cli investigate "A-301 现在还有多少钱没交？" --lease lease_xh_a301_2025
```

预期：

- `route = deterministic`（只选 billing，不扇出）
- `verdict = conflicting`（账单本身存在租金差额，属既有事实）
- 工具调用 1 次，`findings` 给出 `应收 52596.00 / 已收 34560.00 / 未收 18036.00`

讲解要点：

1. 简单问题**不拆任务**；路由是效率指标，不是答案正确性指标。
2. 金额来自 `billing.statement.read` 的 `Decimal` 计算，不是模型生成。

---

## 场景 B：跨系统冲突（扇出 + 不擅自选边）

```bash
python -m app.cli investigate --lease lease_xh_a301_2025
```

预期：

- `route = fanout`，3 个子任务（lease / billing / property）并发
- `verdict = conflicting`，`conflicts[0].amount = 756.00`，附 `evidence_ids`
- `missing_information` 含「合同引用但未电子化的文档: doc_xh_a301_annex_b」
- `requires_human_review = true`

讲解要点：

1. 冲突必须**并列呈现**，不能替用户选一边；
2. 「资料缺失」和「金额冲突」是两件事，报告里分开列（`verdict` vs `completeness`）；
3. 每条 finding 都能回查到证据 ID（`docs/evaluation/fixtures/agent_first_v1.json`）。

---

## 场景 C：人工审批（暂停 → 两级串行 → 只出草案）

```bash
python -m app.cli investigate --with-approval --thread-id demo_thread_01
# 记下输出里的 "request_id": "apr_xxxxxxxx" 与 draft_version

python -m app.cli pending

# 1) 物业管理部门（需 approval.decide + property_manager 角色）
python -m app.cli approve <apr_id> --principal principal_property_manager_xinghui --draft-version 2

# 2) 财务部门（必须换人）
python -m app.cli approve <apr_id> --principal principal_finance_xinghui --draft-version 2
```

预期：

| 步骤 | `approval_status` |
|---|---|
| investigate | `pending_approval`（图被 `interrupt` 暂停） |
| 第一次 approve | `pending_next_stage`（图仍暂停） |
| 第二次 approve | `approved` + `approved_draft`（`status=approved_draft_only`、`executed_side_effects=[]`） |
| 再次 approve | 幂等：返回首次结果 + 「重复恢复」警告，不重放节点 |

讲解要点：

1. checkpoint 存"流程停在哪"，审批台账存"谁在何时批准了什么"，**两份独立存储**；
2. 请求人不能自批、同一人不能签两段、财务不能跳过物业先批；
3. 批准**不等于执行**：本项目没有任何调账/派单副作用；
4. **一条 `thread_id` 只承载一次运行**：再演示一次要换 `demo_thread_02`（或新的 `--control-dir`），
   否则会被 `invalid_context` 明确拒绝——持久化状态里的旧结果不能混进新结论；
5. 审批意见用 `--reason "..."` 提交，会写进台账并在 `pending` 输出里可见。

---

## 场景 D（失败示例 1）：越权访问

```bash
python -m app.cli investigate "B-101 的租期是什么时候？" --lease lease_jl_b101_2025
```

预期：

- 子任务失败，`error_code = project_scope_denied`
- `results` 为空，`completeness = partial`，**不会**返回锦澜中心的任何字段

讲解要点：数据隔离失败必须"报错"，而不是"静默返回空答案"。

---

## 场景 E（失败示例 2）：版本不匹配的审批

```bash
python -m app.cli approve <apr_id> --principal principal_property_manager_xinghui --draft-version 1
```

预期：

- 退出码 **3**
- `{"error": {"code": "invalid_request", "message": "审批版本不匹配：请求为 v2，提交为 v1"}}`
- 图**仍停在审批节点**（不会因为一次失败而丢失进度）

---

## 场景 F：条款证据可回溯

```bash
python -m app.cli search "租金递增比例" --verify-claim "自第二个租赁年度起租金递增百分之五"
```

预期：

- 命中 `doc_xh_a301_contract#v1#p12#5.2`（真实 PDF 第 12 页）
- `citation_check` 给出 L1（`reference_exists=true`）与 L2（`supports_claim`）
- 若把 `--verify-claim` 换成与该条款无关的话，L2 会给出 `unrelated`，`acceptable=false`

讲解要点：页码不是"模拟值"，`tests/test_rag.py` 会逐条比对 fixture 声明页码与真实 PDF。

---

## 场景 G：网页演示

```powershell
python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000/
```

工作台（Task 027）左栏是任务与历史，中央是固定职责图：

1. 直接点「提交调查」→ 提交期间所有节点显示「状态待返回」，返回后按 `report.agent_results` 高亮实际参与的 Agent
   （A-301 复杂问题三个领域都参与；只问欠费时只有账单 Agent 高亮，其余标「本次未调用」）。
2. 点任意节点 → 下方展开该 Agent 的状态、工具调用（`traces`）、冲突与发现；「证据」标签页按合同/账单/工单分组，
   条款证据带页码与条款号；「调用记录」可按 Agent 筛选。
3. 「审批」标签页：草案金额与 `computed_variance` 分栏（草案金额不是差额结论），审批人只从服务端白名单选择，
   依次批准会显示 `approved_draft`（`executed_side_effects` 为空）；驳回会保留意见且不再提供操作按钮。

讲解要点：请求体里带 `principal_id` 会被拒绝——身份由服务端注入；页面不显示虚构的进度百分比或思考过程；
规划/核验/报告节点是「结果回顾」，因为接口一次性返回完整结果。

页面资源（Tabler 1.7.4 CSS/JS、页面样式与脚本）全部来自本仓库 `backend/app/api/static/`，运行期不访问外网。
改动前端后需要重启 uvicorn 才能加载新的 `/static` 挂载。

---

## 一次性自查（演示前 30 秒）

```bash
python tests/smoke_agent_contracts.py                       # 57 项
python -m unittest discover -s tests -p "test_*.py"         # 以当次输出为准；Task 025 为 399 项（跳过 1 项）
python -m app.cli evaluate --split dev --quiet              # 生成本地报告
```
