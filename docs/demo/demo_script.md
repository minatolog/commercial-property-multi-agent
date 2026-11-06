# 演示脚本（A-301 三个主场景 + 两个失败场景）

所有命令在 `backend/` 目录下执行；数据为**合成数据**，无网络、无真实模型。
每节都给出「预期现象」与「讲解要点」，便于现场演示和复核。

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
python -m app.cli investigate --with-approval --thread-id demo_thread
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
3. 批准**不等于执行**：本项目没有任何调账/派单副作用。

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

```bash
python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000/
```

1. 直接点「提交调查」→ 右侧出现 findings / 冲突 / 缺失 / 工具 Trace；
2. 在「审批」区选择审批人（服务端白名单），点「批准」两次（换人）；
3. 看到 `approved_draft`，且明确写着不产生业务副作用。

讲解要点：请求体里带 `principal_id` 会被 400 拒绝——身份由服务端注入，用户不能自报权限。

---

## 一次性自查（演示前 30 秒）

```bash
python tests/smoke_agent_contracts.py                       # 57 项
python -m unittest discover -s tests -p "test_*.py"         # 192 项
python -m app.cli evaluate --split dev --quiet              # 生成本地报告
```
