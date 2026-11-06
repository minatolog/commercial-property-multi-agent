# 问题记录

按时间追加，最新记录在最上方。每条记录必须包含现象、错误信息、根因、解决方案与预防措施。

---

## [2026-11-07] 修复复查仍有持久状态、授权与证据边界缺口

- **关联任务**：017；关联 016。
- **严重程度**：高（R1–R4 为 P1；R5–R7 为 P2）。
- **状态**：未解决，本轮仅复查。

### 现象与验证结果

238 项测试通过，额外反例仍复现：旧 thread 的成功结果掩盖新运行的越权失败；旧记录 scope 为空时详情默认放行；创建者全部项目被当成单份报告所属范围；未签署合同草案混入正式依据；工具后空回答仍成功；冲突阻止可恢复子任务补查；相同条号的不同版本引用被混绑。

### 原因分析

持久 State 的追加 reducer 不会因输入空列表而重置；范围缺失/过宽导致授权失效；目录的签署状态未进入检索策略；成功条件与补查条件不完整；证据使用条号子串匹配。

### 解决方案

待实施，具体位置、复现和验收见 [Task 017 复查报告](../reviews/2026-11-07_release_candidate_recheck.md)。

### 如何避免再次出现

回归同时覆盖新库/旧库、单项目/多项目、首次运行/复用线程、签署/草案及相同条款不同版本。以当前授权、当前 run 状态和精确证据身份判定输出；不要用历史成功或存在过工具证据代替当前任务完成。

---

## 模板

```markdown
## [YYYY-MM-DD] 问题标题

- **关联任务**：NNN
- **严重程度**：阻塞 / 高 / 中 / 低
- **状态**：已解决 / 规避中 / 未解决

### 现象

### 错误信息

```
（原始报错，逐字复制）
```

### 原因分析

### 解决方案

### 如何避免再次出现
```

---

## [2026-11-07] 任务 020：真实 provider 首跑暴露的 3 个装配缺陷

- **关联任务**：020
- **严重程度**：高（第 1 项完全阻断真实调用；第 3 项让报告与事实相反）
- **状态**：已解决

### 现象

填入真实 `DEEPSEEK_API_KEY` 后：

1. `investigate --model-provider deepseek` → 三个子任务全部 `model_error`；
2. 修好第 1 项后 → 三个子任务全部 `budget_exhausted`；
3. 全部跑通后 → 报告头部仍写 `模型：offline_deterministic` 与
   "无 DEEPSEEK_API_KEY，三基线均未调用真实模型"，而同页却记录 26 次模型调用、42,217 tokens。

### 错误信息

```text
OpenAIInvalidRequestError: Error code: 400 - Invalid 'tools[0].function.name':
string does not match pattern. Expected a string that matches the pattern '^[a-zA-Z0-9_-]+$'
```

```text
budget: {"max_model_calls": 32, "max_total_tokens": 0, "used_model_calls": 3, ...}
failures: [{"error_code": "budget_exhausted", ...}]
```

### 原因分析

1. **工具名**：内部工具名用 `domain.action`（`lease.lookup`），OpenAI 兼容接口的函数名只允许
   `[a-zA-Z0-9_-]`。离线引擎不校验名字，所以 299 项测试全绿也发现不了。
2. **token 预算**：`Budget(max_total_tokens=0)` 的语义是"一个 token 都不许用"，
   而 CLI 只设了 `max_model_calls`，于是第一次 token 结算就失败。
3. **报告绑定**：`runner.py` 里 `model` 与 `cost_basis` 是硬编码常量，从未与实际客户端关联。

### 解决方案

1. `ToolSpec.name`（暴露名 `lease__lookup`）与 `ToolSpec.tool_name`（内部名）分离；
   `run_tool_loop` 执行前映射回内部名；`ToolSpecBuilder` 对映射冲突显式报错。
2. CLI `investigate --budget-tokens`（默认 20000）；基线模型路径 `max_total_tokens=60000`/题。
   保持 0 = 禁用的语义不变。
3. `_model_binding(model_client)` 按实际 provider 填写；`cost_basis` 区分
   `unavailable_offline_no_pricing` 与 `unavailable_no_pricing`；加 2 条回归测试。

### 如何避免再次出现

1. **真实 provider 的契约要在边界处被测**：至少一条"暴露给模型的名字"的断言
   （本轮已加：`assertNotIn(".", " ".join(exposed))`）。
2. **"0 = 禁用"这类语义要有对照测试**：否则接入新路径时必然踩到。
3. **报告里的"元信息"必须由事实生成**，不能是常量字符串。报告自述与数据矛盾，
   比数据错误更难被发现——因为读者会先信自述。

---

## [2026-11-07] 任务 019：`.env.example` 承诺的 `.env` 支持从未实现

- **关联任务**：019
- **严重程度**：中（配置静默失效，用户会以为"key 填了没用"）
- **状态**：已解决

### 现象

`.env.example` 第一条写着"复制为 .env（.env 已被 .gitignore 忽略）或直接 export"。
用户照做，把 `DEEPSEEK_API_KEY` 填进 `.env`，然后运行 `--model-provider deepseek`：

```text
[error] MissingApiKeyError: 环境变量 DEEPSEEK_API_KEY 未设置
```

### 错误信息

```text
[error] MissingApiKeyError: 环境变量 DEEPSEEK_API_KEY 未设置；API Key 不得写入 YAML 或提交到仓库
```

### 原因分析

代码只读 `os.environ`（`app/llm/adapter.py` 的 `resolve_api_key`），
而项目**没有** `python-dotenv` 依赖，也没有任何自写的 `.env` 加载逻辑。
`.env` 文件被创建后，对程序而言完全不存在。

这类缺陷的典型特征：**模板、文档、忽略规则都齐了，只缺执行的那一行**。
因为不会报错（只是"读不到"），所以比崩溃更难被发现。

### 解决方案

新增 `backend/app/env.py`：

```python
load_project_env()   # 读 REPO_ROOT/.env 与 backend/.env，只补空缺
```

并接入两个真实入口：`app/cli.py::main()` 与 `app/api/app.py` 模块导入。

优先级与安全：

- 已存在的环境变量优先（部署系统注入的值不会被本地文件覆盖）；
- `.env` 空值不覆盖已导出的非空值；
- 加载结果只返回**键名**，日志与错误里不出现值；
- `.env` 保持被 `.gitignore` 忽略（`git check-ignore` 已验证）。

### 如何避免再次出现

1. **模板文件里的每条承诺都要有一条测试**：本例只需一个"填了就能读到"的断言即可拦住。
2. 配置项存在 ≠ 配置路径可用。凡是"文档说可以"，都要有一次端到端验证。
3. 新增启动入口（CLI / uvicorn / worker）时，把配置加载挂在**每个入口**上，
   而不是只挂在"我平时用的那个"。

---

## [2026-11-07] 任务 018：并发子任务的模型调用被预算去重吞掉

- **关联任务**：018
- **严重程度**：中（预算上限失效、`model_calls` 指标不可信；不会产生错误业务结论）
- **状态**：已解决

### 现象

模型驱动的调查工作流有 3 个并发子 Agent，每个 2 轮模型调用（共 6 次），
但 `budget.used_model_calls` 显示 **2**。

### 错误信息

```text
budget: {"max_model_calls": 32, "used_model_calls": 2, "used_tool_calls": 4}
```

### 原因分析

`run_tool_loop` 里预算记账的 ID 是：

```python
model_call_id = f"mc_{context.run_id or 'norun'}_{round_index}"
```

`Budget._reserve` 对 `call_id` 做幂等去重（`if call_id in self._settled or call_id in self._reserved: return`）。
并发子任务共享同一个 `run_id`，第 1 轮三个子任务都用 `mc_run_x_1` → 只记一次账。
于是 6 次真实调用被记成 2 次（只按轮次计数）。

这个缺陷一直存在，但确定性引擎下 `used_model_calls` 恒为 0，从未暴露；
接入模型驱动后立刻显形。它有两个真实后果：

1. `max_model_calls` 上限失效——3 个子任务可以超出限额；
2. 报告里的模型调用数、token 与成本口径全部偏小。

### 解决方案

```python
agent_scope = context.subtask_id or "root"
model_call_id = f"mc_{context.run_id or 'norun'}_{agent_scope}_{round_index}"
```

并加两条回归：

- `test_parallel_subtasks_count_every_model_call`：断言 `used_model_calls == 6`、`used_tool_calls == 3`；
- `test_model_budget_is_enforced_across_subtasks`：`max_model_calls=3` 时实际用量 ≤ 3，且报告必须体现 `partial`。

### 如何避免再次出现

1. **幂等键必须包含全部区分维度**：运行 + 子任务 + 轮次。只带其中两个，就会把并发路径合并成一次。
2. **指标的"恒为 0"是危险信号**：`model_calls` 长期为 0 说明这条路径没被走过，而不是"没花钱"。
3. 新增"并发 × 计量"功能时，先写一条"断言累计次数"的测试，再看业务结果。

---

## [2026-11-07] 任务 018：LLM 引擎让冲突检测静默失效

- **关联任务**：018
- **严重程度**：高（会输出 `supported`，把真实差额吞掉）
- **状态**：已解决

### 现象

同样的 A-301 场景，确定性引擎得到 `verdict=conflicting`（差额 756.00），
换成模型驱动引擎后得到 `verdict=supported`，且报告没有冲突。

### 错误信息

```text
VERDICT supported completeness complete
CONFLICTS []
```

### 原因分析

图的核验读的是 Agent 输出**顶层**的领域字段：

```python
variance = output.get("rent_variance_total")
```

确定性 Agent 把工具输出平铺到顶层（`{**data}`），所以能读到；
而最初的 LLM Agent 只输出 `{"facts": {...}}`，顶层没有 `rent_variance_total`，
核验读不到差额 → 判 `supported`。

这不是"模型答错了"，而是**换引擎顺带换了输出契约**，下游规则静默失效。

### 解决方案

新增 `_domain_view(capability, tool_outputs, evidence)`：把工具输出映射成与确定性 Agent
**同构**的领域视图（`lease` 子对象、`rules`、`clauses`、`rent_variance_total` 等），
LLM 的 `answer`/`facts`/`usage` 作为附加字段并存。

### 如何避免再次出现

1. 新增一种引擎/适配器时，先写"同一输入在两种引擎下产生同一判定"的对照测试。
2. 下游若依赖某个字段，该字段必须由**契约**保证存在，而不是"恰好某个实现会填"。
3. 让"少字段"变成可见失败：本轮用 `test_llm_engine_produces_same_report_shape` 固定住。

---

## [2026-11-07] 任务 017 修复：持久线索、范围授权与证据适用性的 7 项缺陷

- **关联任务**：017（复查 R1–R7）
- **严重程度**：高（R1–R4 可导致旧数据/他人数据或草案进入当前结论）
- **状态**：已修复并有回归测试；真实模型与 PostgreSQL 验证仍未完成

| 编号 | 根因（真正的机制） | 修法 |
|---|---|---|
| R1 | LangGraph 的 `results`/`failures` 是追加通道；`investigate` 传入空列表**清不掉** checkpoint 里的旧结果，而核验把"同 ID 有成功结果"当作已解决 | `investigate()` 拒绝复用已有 thread（主体/租约/run 任一不符即报错）；结果打 `run_id`，所有统计按当前 run 过滤 |
| R2 | 迁移只加列不回填；`get()` 对 `None/[]` **跳过**范围校验，而 `list()` 会过滤——"列表看不到"被误当成"详情安全" | 空范围默认拒绝；服务层回填，失败即隔离 |
| R3 | 记录直接把服务主体的**全部授权**写成 `project_ids` | 拆成数据范围（按租约解析）与授权范围（审计） |
| R4 | `DocumentMeta` 有 `document_status`，但装配、索引、检索、引用都不用它；`documents` 字典按 `document_id` 单键还会**覆盖**版本 | 状态贯穿索引与检索，默认只 `signed`；元数据改 `(document_id, version)` 复合键 |
| R5 | 空回答检查要求 `not executions and not evidence`，调过工具就放行 | 空最终文本一律 `MODEL_ERROR` |
| R6 | 补查闸门是 `verdict == insufficient`，而账单差额会把 verdict 提到 `conflicting` | 只看未解决的可重试子任务 |
| R7 | 证据用 `clause_id in evidence_id` 子串匹配，忽略文档与版本 | 按 `chunk_id` 精确绑定 |

### 如何避免再次出现

1. **追加型状态 + 可复用标识 = 越权通道**。凡是"按 ID 累积"的状态，都要同时校验"这条 ID 属于本次运行"。
2. **默认放行只写一次就会长期存在**：`if scope not in (None, [])` 这类守卫，请把 `None` 也当拒绝。
3. **范围字段要问清语义**：是"谁被授权"还是"数据属于谁"？两个问题必须两个字段。
4. **文档的"存在"与"生效"是两件事**：状态字段一旦进了元数据，就必须在每个消费点被执行，否则它只是注释。
5. **过程指标不能替代结果判定**：有工具证据 ≠ 有答案。
6. **恢复能力不要挂在别人的结论上**：用"我这边还有没有可重试的失败"决定要不要补查。

---

## [2026-11-07] 版本候选复查：旧数据、跨项目范围与草案仍可进入结论

- **关联任务**：017
- **严重程度**：高
- **状态**：R1–R7 已修复（见上一条）；真实模型/PG 验证未完成

### 现象

238 项测试通过，额外反例仍复现：复用持久 `thread_id` 后越权主体拿到他人成功结果；旧库记录无范围标签却可跨项目读取；多项目创建者产出的单项目报告被其他项目主体读走；未签署草案被当作正式条款；先调工具再空回答被标成功；有账单冲突时可恢复失败不再补查；证据按条款号串行混入其他版本。

### 错误信息

```text
（无异常；上述均为"错误地成功"的行为，表现为 status=supported / 200 / final_answer）
```

### 原因分析

见上一条逐项根因。共同点是：**守卫存在但边界条件被放过**（空范围、空回答、追加状态、状态字段未消费）。

### 解决方案

见上一条修法；260→261 项测试通过，新增 20 项针对性回归。

### 如何避免再次出现

审查时优先构造"旧数据 + 新请求"、"多授权 + 单数据"、"状态字段存在但没人读"这三类组合，它们最容易在"测试全绿"时静默失效。

---

## [2026-11-06] 任务 016 修复：12 项缺陷的根因与修法

- **关联任务**：016（第一批 F1/F2/F7/F8；第二批 F3/F4/F5/F6/S1–S4 + 审批意见未持久化）
- **严重程度**：高
- **状态**：已修复并有回归测试；第三批真实服务验证未完成

修复逐项先复现、再改代码，回归用例放在对应 `backend/tests/test_*.py` 中。

| 编号 | 根因（真正的机制） | 修法 |
|---|---|---|
| F1 | 期望事实用"这个金额是否在答案文本里出现过"判定，事实键与字段完全脱钩 | 键必须与基线 `facts[key]` **同名字段**比较；金额走 `Decimal` 到分；新增 `BASELINE_FACT_VOCABULARY` 明确"基线会产出哪些键" |
| F2 | 评分器对 `denied` 无条件扣分，而三条基线对"拒绝"给出的 status 不一致 | 用例显式声明 `expected_outcome`（`ok`/`denied`/`failed`）；`derive_status()` 让三基线共用一套结局推导 |
| F3 | 知识库装配直接依赖 `FixtureRepository.snapshot`，SQLite 仓库没有该方法 | 抽出 `DocumentCatalog` 契约（`app/rag/catalog.py`），fixture 与 DB 各自提供适配器，由装配层注入 |
| F4 | `conflicts`/`missing` 用 `operator.add` 追加，每轮重算的结果与历史残留叠加；`verify` 把已解决的历史失败仍算在完整度里 | 每轮重算字段改覆盖语义；新增 `retry_subtasks` 只重跑未解决子任务；报告分离 `failures`（未解决）与 `resolved_failures`（历史） |
| F5 | 审批节点把**临时生成**的请求对象返回给调用方，与台账里持久化的那条不是同一份 | 钩子改为返回台账权威 `ApprovalRequest`；`interrupt` 恢复后用 `approval_reader` 回读台账并覆盖结果 |
| F6 | LangChain 把参数解析失败的调用放进 `invalid_tool_calls`，运行循环只看 `tool_calls`，于是"什么都没做"被当成终答 | 收集 `invalid_tool_calls`、缺名调用与 args 解析失败；`finish_reason in {length,max_tokens}` 或空输出无证据时统一 `MODEL_ERROR` |
| F7 | 条款检索只按租户/项目过滤，没有限定"这份合同自己的文档版本" | 文档按 `document_ids` 限定；工具输出 `document_scope` 证据字段，让越界可被发现 |
| F8 | 运行索引只存 `principal_id`，不存项目归属，查询时无所有权概念 | 索引记录 `project_ids`，`get`/`list` 按所有权过滤，跨项目按"不存在"处理（404） |
| S1 | 终态校验在版本/权限校验之前，且未处理"同一人重复提交同一结论" | 校验顺序重排为：身份/权限/范围 → 版本 → 自批 → 已记录决定（同人同结论=幂等） → 终态 → 过期 → 重复审批人 → 阶段顺序 |
| S2 | 只读承诺只写在文档里，装配期没有任何强制 | 装配仓库的 Session 上执行 `PRAGMA query_only=1`，写操作抛 `OperationalError` |
| S3 | 路由直接从 `dict` 取值并 `int()`/`bool()` 强转 | Pydantic 请求模型（`extra="forbid"`、严格类型、预算边界）+ 统一 422 响应 |
| S4 | 公开 `run_id` 由服务层生成，`bundle` 内部又生成一个，图上存的是后者 | `build_investigation_bundle(run_id=, trace_id=)` 注入统一身份，提交与恢复都用同一个值 |
| 附 | API 收到 `reason` 但没传给 `Investigator`/台账，CLI 也没转发 | `Investigator.resume(..., reason=)` 一路落库，CLI 与 API 均转发 |

### 如何避免再次出现

1. **评分断言必须绑定字段名**，禁止"数字出现在文本里"这类判定；规则变更必须升版并保留旧报告。
2. 每条"装配路径"都要有一个**从真实入口跑通**的测试（CLI 后端切换、SQLite + RAG），不能只测模块内部。
3. 图状态里"每轮重算"的字段用覆盖语义，"跨轮累积"的字段才用 `operator.add`，并在字段注释里写明是哪种。
4. 审计类数据（审批结论）只认台账，流程状态只认 checkpoint，二者不得互相冒充。
5. `passed is None` 与 `passed is False` 是两种结论：前者是"判定不了"，后者是"判错了"。报告必须区分。

---

## [2026-11-06] 版本候选独立审查：评分、集成、恢复与隔离存在缺陷

- **关联任务**：016，涉及 008–014。
- **严重程度**：高。
- **状态**：F1–F8、S1–S4 已修复（见上一条修复记录）；第三批真实服务验证未完成。

### 现象

192 项测试全部通过，额外反例仍复现：金额互换获满分、正确拒绝被错误扣分、SQLite 调查入口崩溃、成功补查仍判缺失、审批恢复返回不存在的请求 ID、非法模型调用被当成功、引用其他租约合同和跨主体读取运行记录。

### 错误信息

```text
AttributeError: 'DatabaseRepository' object has no attribute 'snapshot'
```

### 原因分析

字段判分使用全局字符串搜索；不同基线状态映射不一致；知识库依赖 fixture 全量快照；图将历史失败与当前状态混用；审批节点重放时未复用持久请求；缺少模型非法调用处理和合同/运行记录的目标范围检查。

### 解决方案

已按 [Task 016 审查报告](../reviews/2026-11-06_release_candidate_review.md) 分两批修复，逐项根因见上一条记录。全量 238 项 unittest 与 57 项契约检查通过；SQLite 入口退出码 0；审批意见可落库回读；评分升 `scoring-v2` 并重新生成保留集报告（A 20/30、B 21/30、C 23/30）。

### 如何避免再次出现

补充公开 CLI/服务真实装配路径测试；用错误金额交换、一次失败后恢复、不同主体/租约等反例验证结果语义；检查报告与权威台账的身份和状态一致性。评分规则修正后升版并保留旧报告。

---

## [2026-11-06] 手写 PDF 无法写入/取回中文，导致合同证据不可用

- **关联任务**：011
- **严重程度**：高（阻塞 Task 011 的证据链路）
- **状态**：已解决

### 现象

生成合成合同 PDF 时直接抛异常；即便绕过，`pypdf` 也取不回中文条款。

### 错误信息

```
UnicodeEncodeError: 'ascii' codec can't encode characters in position ...
```

### 原因分析

手写 PDF 的内容流以 ASCII 编码写入 `(文本) Tj`；中文超出 ASCII 范围。
更深一层：标准 PDF 字体（Helvetica）不含汉字字形，且没有 `ToUnicode` CMap，
所以"写进去"和"取得回"是两件独立的事，改编码字符集并不能解决字形问题。

### 解决方案

改用 reportlab：探测系统中文字体（`simhei.ttf` 等）做子集嵌入并自动生成 `ToUnicode`；
无 TTF 环境回退 CID 字体 `STSong-Light`。同时把 PDF 扩到 26 页，
让 fixture 声明的页码（5.2→p12、7.1→p20、附件B→p26）与真实页码一致，
并由 `verify_snippets()` 在索引时强制校验。

### 如何避免再次出现

- 涉及"证据/可追溯"的格式，**先写一个提取往返测试**（生成 → 解析 → 断言原文一致），再谈业务逻辑。
- 任何"页码/行号/条款号"字段都必须由真实解析结果产生，不允许手工填写模拟值。
- 在 `docs/prompts/03_rag/2026-11-06_011_contract_pdf_rag.md` §7 记录该限制与字体回退策略。

---

## [2026-11-06] 保留集 v1 的期望租期为 "None 至 None"（生成脚本取值错误）

- **关联任务**：013
- **严重程度**：中（数据集缺陷；会让正确实现被判为错误）
- **状态**：已解决（发布 v2 数据集，v1 存档不再使用）

### 现象

保留集 v1 中 H09 / H10（租期事实）的期望值为 `lease_period=None 至 None`，
基线实际给出 `2025-01-01 至 2027-12-31` 却被判失败。

### 错误信息

```
期望 lease_period=None 至 None，实际 facts=2025-01-01 至 2027-12-31
```

### 原因分析

生成脚本写的是 `lease = repository.lease_facts(...)`，但该方法返回的是
`{"lease": {...}, "unit": {...}, "rules": [...], ...}`，真正的租约字段在 `facts["lease"]` 内。
于是在外层 dict 上取 `start_date` 得到 `None`，期望值被写坏。

### 解决方案

修正为 `lease = facts.get("lease", {})`，重新生成 **`heldout_v2.jsonl`** 并更新装载器指向 v2。
`heldout_v1.jsonl` 保留在仓库中作为历史存档，报告里也能看到它对应的实验结果；不就地修改 v1。

### 如何避免再次出现

- 生成脚本必须先在**少量样例**上打印期望值人工过目，再批量产出；
- 测试里加一条守卫：期望值中不允许出现 `"None"`（`test_no_placeholder_expectations`）；
- 只要数据集已参与过实验，就**发新版本**而不是就地修改，否则实验间的对比失去意义。

---

## [2026-11-06] 恢复图时从 START 重跑，报 KeyError 'question'

- **关联任务**：012
- **严重程度**：高（恢复功能完全不可用，但**不会**报错提示标识错误）
- **状态**：已解决

### 现象

审批暂停后执行恢复，图的 `plan` 节点重新执行并抛异常；`aget_state` 显示 `next=()`，看起来"流程已结束"。

### 错误信息

```
File "app/orchestration/investigation.py", line 327, in plan_node
    ...
KeyError: 'question'
```

### 原因分析

`Investigator.investigate()` 调用底层 `_ainvoke(payload)` 时**没有传 `thread_id`**，
于是 checkpoint 写到了默认名 `thread_unknown`；而调用方按自己的 `thread_id` 去恢复，
读不到中断点，LangGraph 视为"新线程"，从 START 开始跑，`state["question"]` 自然不存在。

关键陷阱：写错标识**不会**抛错，只会静默地变成一次全新执行。

### 解决方案

`_ainvoke(payload, thread_id=effective_thread)`，并补一条"三个独立 control_plane 依次执行"的用例，
确保跨连接恢复真的被验证到。

### 如何避免再次出现

- 任何持久化/恢复功能，必须写**跨连接或跨进程**用例；单进程内跑通不构成证据。
- 恢复入口要显式校验：读不到中断点时应当报"线程不存在/无待恢复任务"，而不是从 START 重跑。
  本项目通过 `aget_state().next` 判定，非空才认为有暂停点。

---

## [2026-11-06] 中文单字 BM25 召回产生假证据

- **关联任务**：011
- **严重程度**：中（会导致"有依据"的错误结论）
- **状态**：已解决

### 现象

`search("押金")` 在完全没有押金条款的合同上返回 3 条结果，分数 1.2~1.6。

### 错误信息

无异常；属于**静默的正确性缺陷**。

### 原因分析

分词把中文拆成单字 + 二元组，单字匹配面过宽：任意含「金」「押」的条款都能得正分，
而 BM25 会返回所有 `score > 0` 的文档，于是无关条款被当作证据。

### 解决方案

中文只取二元组（整段只有一个字时保留单字）。`search("押金")` 现在返回 0 条。
配套测试 `test_no_evidence_returns_empty_not_fabricated` 固定该行为。

### 如何避免再次出现

- 检索类功能必须包含"**应当查不到**"的反向用例，而不只有"能查到"的正向用例。
- 对"没有任何结果"要显式设计成合法返回（`result_count=0`），不要用低分噪声填充 top_k。

---

## [2026-11-06] 环境未安装 pytest，与“新增 pytest 覆盖”要求冲突

- **关联任务**：007 / Prompt 2
- **严重程度**：中（影响验证方式，不影响交付内容）
- **状态**：规避中（测试用 `unittest` 编写与执行，pytest 可原生收集）

### 现象

Task 007 要求“新增 pytest 自动化覆盖”，但当前 Conda 环境 `commercial-agent` 没有 pytest；同一 Prompt 又明确禁止安装依赖。

### 错误信息

```
D:\anacada\envs\commercial-agent\python.exe: No module named pytest
```

### 原因分析

环境由任务 001 建立，只含 pip / setuptools / wheel / packaging，后续任务未引入测试框架；本任务不允许 `pip install` 或修改环境。

### 解决方案

`backend/tests/test_runtime.py` 使用标准库 `unittest.TestCase` 编写，文件/类/方法命名符合 `test_*.py`、`Test*`、`test_*`，可被 pytest 直接收集；本轮实际执行命令为 `python -m unittest discover -s tests -v`（47 个测试通过）。未安装任何依赖。

### 如何避免再次出现

需要 pytest 的任务应在 Prompt 中显式允许安装测试依赖，或由项目所有者预先装好；提交前按 Task 007 归档 §11 的命令复跑两种运行方式（unittest 现在可跑，pytest 待环境具备）。

---

## [2026-11-03] Task 006 规格与评测场景存在冲突

- **关联任务**：006 / Prompt 1
- **严重程度**：高（阻塞 006 验收，不是运行中系统故障）
- **状态**：已解决（Prompt 1-R1/R2 返修后，Task 006 于 2026-11-06 复验通过）

### 现象与证据

核心 fixture 金额与引用通过，但 C06 失败路径要求取得超时工具证据；三基线使用只允许 multi_agent 的共同路由断言；C08 无具备审批权限的可信事件主体；State 预算简单相加与幂等声明冲突；Graph 缺分支且审批/信息补充混用；P0 保留集与 P1 清单不一致。

完整定位、影响与验证见 [Codex 006 Review](../reviews/2026-11-03_task006_review.md)。无 Runtime 执行错误堆栈，本次为规格审查发现。

### 原因分析

文件可解析、ID 存在和金额正确不足以证明场景在故障、并发、审批及不同基线下可满足。原验证未覆盖这些语义组合。

### 解决方案

DeepSeek 按同任务 Prompt 1-R1 修正 R1–R6，Codex 复验后再进入 007。不在 Review 中悄悄实现 Runtime 或重写整个数据集。

### 如何避免再次出现

同时校验数据结构和语义条件；区分场景真值与运行时实际可获得证据；分离共同质量评分与基线编排指标；审批注入主体、版本、时刻和权限；并发归并使用稳定事件标识。

---

## [2026-11-03] conda activate 报 GBK UnicodeEncodeError

- **关联任务**：001
- **严重程度**：中（仅在特定 shell 环境触发）
- **状态**：已解决

### 现象

在自动化 shell 中加载 Conda PowerShell hook 后执行 `conda activate commercial-agent`，激活失败，且 `conda` 自身打印错误报告后崩溃。

### 错误信息

```
Traceback (most recent call last):
  File "D:\anacada\Lib\site-packages\conda\exception_handler.py", line 30, in __call__
    return func(*args, **kwargs)
  File "D:\anacada\Lib\site-packages\conda\cli\main.py", line 96, in main_sourced
    print(result, end="")
UnicodeEncodeError: 'gbk' codec can't encode character '\u04e6' in position 785: illegal multibyte sequence

`$ D:\anacada\Scripts\conda-script.py shell.powershell activate commercial-agent`
```

### 原因分析

`conda activate` 的实质是让 conda 在**子进程**里生成一段 shell 脚本（`conda shell.powershell activate <env>`），再交给当前 shell 执行。该子进程的 Python `stdout` 使用系统默认编码（简体中文 Windows 为 **GBK / cp936**）。

问题在于：该执行环境的进程 `PATH` 中，含中文字符的路径 `D:\应用管理\Microsoft VS Code\bin` 被以错误编码写回，变成 `D:\\u04e6\ufffd\ufffd\ufffd\...` 之类乱码。这段乱码最终出现在 conda 要打印的内容里，而其中的 `\u04e6`（`Ӧ`）在 GBK 中无法表示 → `print()` 抛 `UnicodeEncodeError` → 脚本生成失败 → 激活中断。

关键结论：**这不是 Conda 的 bug，也不是用户 PATH 本身的问题**（注册表中的用户 PATH 中 `D:\应用管理\...` 完全正常）。是中间 shell 层的编码往返损坏了 PATH，才触发 GBK 编码失败。

### 解决方案

临时（单次会话）：

```powershell
$env:PYTHONIOENCODING = "utf-8"
conda activate commercial-agent
```

`PYTHONIOENCODING` 会强制 conda 子进程用 UTF-8 输出，绕开 GBK 限制，验证后激活成功。

### 如何避免再次出现

1. 遇到 Windows 上中文路径 + Conda + 非 UTF-8 代码页的组合时，优先怀疑编码，而非环境损坏。
2. 判断是否为环境自身问题：对比「用户真实交互终端」与「自动化/第三方 shell」。本例中用户终端正常显示 `(base)`，即可判定为 shell 层问题。
3. 可考虑将 Windows 控制台代码页切到 UTF-8（`chcp 65001`）或设置 `PYTHONIOENCODING=utf-8`，但**不要**为此擅自修改系统级编码设置，避免影响其他依赖 GBK 的程序。

---

## [2026-11-03] PowerShell 禁止运行 Conda hook 脚本

- **关联任务**：001
- **严重程度**：高（阻塞 `conda activate`）
- **状态**：已解决

### 现象

在 VS Code 的 PowerShell 终端执行 `conda activate commercial-agent`，报错；加载 hook 文件 `D:\anacada\shell\condabin\conda-hook.ps1` 同样失败。

### 错误信息

```
& : 无法加载文件 D:\anacada\shell\condabin\conda-hook.ps1，因为在此系统上禁止运行脚本。
有关详细信息，请参阅 https:/go.microsoft.com/fwlink/?LinkID=135170 中的 about_Execution_Policies。
    + CategoryInfo          : SecurityError: (:) [], PSSecurityException
    + FullyQualifiedErrorId : UnauthorizedAccess
```

### 原因分析

`Get-ExecutionPolicy -List` 显示所有作用域（MachinePolicy / UserPolicy / Process / CurrentUser / LocalMachine）均为 `Undefined`。Windows 客户端系统在未显式配置时，默认生效策略为 **`Restricted`**，禁止执行任何 `.ps1` 脚本文件。

Conda 的 shell 集成依赖 `conda-hook.ps1` / profile 中的脚本执行，因此被拦截。

### 解决方案

临时（仅当前进程，不改持久配置）：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

长期（用户已采用）：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
& "D:\anacada\Scripts\conda.exe" init powershell
```

`RemoteSigned` 允许执行本地编写的脚本，但从网络下载的脚本需签名，安全性与可用性平衡较好。**未使用 `Unrestricted` 或 `Bypass` 作为持久设置。**

撤销：`& "D:\anacada\Scripts\conda.exe" init --reverse powershell`

### 如何避免再次出现

1. 新机器搭环境时，先跑 `Get-ExecutionPolicy -List` 一次性确认，不要等到 `conda activate` 失败才排查。
2. 优先用 `-Scope CurrentUser` 而非 `LocalMachine`，避免影响其他系统用户。
3. 永久方案优先 `RemoteSigned`，不要为了省事设成 `Bypass`。

---

## [2026-11-03] conda init 写在 profile.ps1 而非 Microsoft.PowerShell_profile.ps1

- **关联任务**：001
- **严重程度**：低（仅影响排查思路）
- **状态**：已解决

### 现象

用户终端已显示 `(base)` 前缀，说明 Conda hook 已生效；但用工具检查 `C:\Users\lgwlo\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1` 显示文件不存在，且新开的非交互 shell 中 `where conda` 依然找不到。

### 错误信息

无报错，属于「行为与预期不符」。

### 原因分析

PowerShell 有多个 profile 路径，加载优先级不同：

- `Microsoft.PowerShell_profile.ps1`（CurrentUser**CurrentHost**）
- `profile.ps1`（CurrentUser**AllHosts**）

`conda init powershell` 写入的是 **`profile.ps1`（AllHosts）**。两者在交互式 PowerShell 中都会加载，所以用户终端正常；但工具使用的非交互 shell 通常带 `-NoProfile`，不加载任何 profile，因此看不到 `conda` 命令。

### 解决方案

无需修复。排查时按以下顺序确认：

```powershell
$PROFILE.AllUsersAllHosts
$PROFILE.CurrentUserAllHosts    # ← conda 写这里
$PROFILE.CurrentUserCurrentHost
```

确认 `CurrentUserAllHosts` 文件存在且包含 `#region conda initialize` 即可判定初始化成功。

### 如何避免再次出现

1. 判断 Conda 是否初始化成功，**以交互式终端里能否 `conda activate` 为准**，不要以非交互脚本里 `where conda` 的结果为准。
2. 需要脚本中调用 conda 时，显式写全路径 `D:\anacada\Scripts\conda.exe run -n <env> python ...`，不要依赖 profile。

---

## [2026-11-03] conda create 显示异常但实际创建成功

- **关联任务**：001
- **严重程度**：低
- **状态**：已解决

### 现象

执行 `conda create -n commercial-agent python=3.11 pip -y`，PowerShell 报 `NativeCommandError` 且退出码为 1，看起来像失败，但环境实际已创建完成。

### 错误信息

```
conda.exe : 
所在位置 行:2 字符: 1
+ & "D:\anacada\Scripts\conda.exe" create -n commercial-agent python=3.11 pip -y
    + CategoryInfo          : NotSpecified: (:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError

==> WARNING: A newer version of conda exists. <==
    current version: 26.1.1
    latest version: 26.9.4
```

### 原因分析

conda 把「有新版本可用」的提示写到了 **stderr**。PowerShell 在 `$ErrorActionPreference` 默认行为下，会把原生命令的 stderr 输出包装成 `NativeCommandError` 记录，并使 `$?` 为 `$false`。这是 PowerShell 对原生命令 stderr 的已知处理方式，不代表命令真的失败。

### 解决方案

不依赖退出码判断，改用可验证的事实复核：

```powershell
conda env list
D:\anacada\envs\commercial-agent\python.exe --version
```

确认环境存在、解释器可运行，即判定成功。

### 如何避免再次出现

1. 判断原生命令是否成功，优先看**副作用是否达成**，而非 stderr 是否为空。
2. 在脚本里可加 `2>&1` 或使用 `$LASTEXITCODE` 判断真实退出码：

```powershell
& "D:\anacada\Scripts\conda.exe" create -n foo python=3.11 -y 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "conda create failed" }
```

3. 长期可执行 `conda update -n base -c defaults conda` 消除版本提示噪音（本次未执行，避免改动 base 环境）。
