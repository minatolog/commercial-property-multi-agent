# 问题记录

按时间追加，最新记录在最上方。每条记录必须包含现象、错误信息、根因、解决方案与预防措施。

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
