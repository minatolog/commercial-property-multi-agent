# 知识笔记

记录技术原理与选型原因，而不是命令清单。每条笔记应当能回答「为什么这样做」和「什么时候会踩坑」。

---

## 模板

```markdown
## 主题

- **日期**：YYYY-MM-DD
- **关联任务**：NNN
- **关键词**：

### 原理

### 为什么这样选

### 常见坑与规避
```

---

## 一、Conda 环境隔离原理

- **日期**：2026-11-03
- **关联任务**：001
- **关键词**：环境隔离、sys.prefix、硬链接、PATH 优先级

### 原理

Conda 的环境隔离不是"复制一份完整的 Python"，而是三层机制协同：

1. **独立目录 + 独立解释器**：每个环境是 `envs/<name>` 下的独立目录，拥有自己的 `python.exe`、`Lib\site-packages`、`Scripts`。`sys.prefix` 指向该目录，`stdlib` 和第三方包都从 `sys.prefix` 相对定位。
2. **共享包缓存 + 硬链接**：`pkgs/` 目录是全局包缓存。安装时 Conda 优先用**硬链接**把包文件链接到环境目录，因此第二个环境装同一个包几乎不额外占磁盘。删除环境只是删除链接，缓存仍在。
3. **激活 = 改 PATH**：`conda activate` 并不"切换"任何全局状态，它只是把环境的 `bin`/`Scripts` 目录**前置**到当前 shell 进程的 `PATH`，并设置 `CONDA_PREFIX`、`CONDA_DEFAULT_ENV` 环境变量。所以激活是**进程级**的，不同终端窗口互不影响。

理解这一点就能解释为什么 `conda activate` 必须由 shell 集成完成：conda 本身是 Python 程序，无法直接修改父 shell 的环境变量，只能输出一段 shell 脚本交给父 shell 执行（`conda shell.powershell activate <env>`）。

### 为什么这样选

本项目选 Conda 而非 `venv`，核心原因是 **Windows 上的二进制依赖**：

- 后续要引入 BGE Embedding（`sentence-transformers`）、向量检索等依赖，其底层可能牵涉 PyTorch、`faiss`、`hnswlib` 等含编译扩展的包。
- `venv` 只隔离 Python 包，**不隔离非 Python 依赖**（如 OpenMP 运行库、MKL、CUDA 相关 DLL）。多个项目对同一 DLL 版本要求冲突时，`venv` 无能为力。
- Conda 能同时管理 Python 包与 C/C++ 运行时库，并通过 `vc`、`vs2015_runtime` 等包统一 MSVC 运行库版本。

另外，PyPI 上部分包在 Windows 缺少预编译 wheel，`pip install` 会触发本地编译（需要 MSVC Build Tools）。Conda channel 中通常已有编译好的版本，能显著降低环境搭建失败率。

### 常见坑与规避

1. **只改终端、不改解释器**：`conda activate` 只影响终端。VS Code 的编辑器/调试器/测试运行器使用独立的 `python.defaultInterpreterPath`。两者不一致时会出现"终端能 import、编辑器报红线"。规避：显式设置工作区解释器，并以 `Python: Select Interpreter` 的结果为准。
2. **`where python` 命中 Microsoft Store 占位符**：Windows 的 `WindowsApps\python.exe` 是一个 0 字节的应用执行别名，优先级可能高于 Conda。规避：`where python` 必须确认**第一条**是目标环境的 `python.exe`。
3. **`auto_activate_base=True` 的隐性成本**：每次开终端自动进 base，容易在 base 里误装包，导致 base 越来越重、难以复现问题。规避：`conda config --set auto_activate_base false`，手动激活目标环境。
4. **环境放进项目目录**：Conda 环境含大量文件与绝对路径，放进仓库会污染 Git、拖慢索引。规避：环境统一放在 `envs/`，项目里只放代码和依赖声明文件。
5. **环境重命名成本高**：Conda 不直接支持重命名（`conda rename` 在新版本才有且易出问题），且环境内有硬编码路径。规避：创建时就定好名字。

---

## 二、`.gitignore` 的模式匹配语义

- **日期**：2026-11-03
- **关联任务**：001、002
- **关键词**：gitignore、路径段匹配、否定规则、安全默认

### 原理

gitignore 的匹配有两条容易误解的规则：

1. **目录模式按"路径段边界"匹配**。`logs/` 只匹配**名为 `logs` 的目录**，不会匹配 `development_logs/`。因为模式末尾的 `/` 表示"仅匹配目录"，且模式中不含 `/` 前缀时按路径段对齐匹配。同理 `build/` 不会误伤 `mybuild/`。
2. **否定规则 `!` 不能"救回"父目录已被排除的文件**。若某个目录整体被忽略，Git 不会再进入该目录，里面的 `!` 规则全部失效。因此「忽略目录内容、放行个别文件」必须分两步写：

```gitignore
.vscode/*              # 忽略目录内容，但不忽略目录本身
!.vscode/extensions.json   # 放行特定文件
```

若写成 `.vscode/`（带尾斜杠）或 `.vscode`，则目录被整体排除，`!` 规则无效。

### 为什么这样选

`.vscode/` 采用「忽略全部 + 白名单」策略：

- **必须忽略**：`settings.json` 常含解释器绝对路径（如 `D:\anacada\envs\commercial-agent\python.exe`），换机器即失效；还可能含个人终端配置、代码格式化偏好，提交会造成团队冲突。
- **值得共享**：`launch.json`（调试配置）、`tasks.json`（构建任务）、`extensions.json`（推荐扩展）对各开发者通用，提交能显著降低协作成本。

同理，`.env` 必须忽略而 `.env.example` 必须提交 —— 前者含 DeepSeek API Key 与数据库密码，后者是只有键名和说明的模板。

### 常见坑与规避

1. **忽略规则写宽了导致源码丢失**：例如写 `data/` 结果把 `src/data/` 里的代码也排除。规避：规则尽量锚定根目录（`/data/`），且新增规则后用 `git check-ignore -v <path>` 双向验证 —— **既验证该忽略的已忽略，也验证该保留的未被忽略**。
2. **`*.log` 误伤文档**：`issue_log.md` 是 `.md` 不受影响，但若有人建 `debug.log.md` 之外的日志类源码需注意。规避：优先用 `logs/` 目录规则而非全局 `*.log`。
3. **已跟踪文件不受 ignore 影响**：`.gitignore` 只对未跟踪文件生效。若 `.env` 曾被 `git add`，需 `git rm --cached .env` 才真正解除跟踪。规避：项目第一步就建 `.gitignore`，不要等有了提交再补。
4. **验证方式**：`git check-ignore -v <path>` 输出命中的规则与行号，是最可靠的调试手段，比肉眼读规则准确。

---

## 三、Windows 中文环境下的编码与工具链

- **日期**：2026-11-03
- **关联任务**：001
- **关键词**：GBK、cp936、UTF-8、PYTHONIOENCODING、中文路径

### 原理

简体中文 Windows 的系统 ANSI 代码页是 **GBK（cp936）**。Python 在 Windows 上启动时，`stdout` 的默认编码取自控制台代码页，因此在中文系统上默认为 `gbk`。

只要程序要输出的字符在 GBK 中不存在，`print()` 就会抛 `UnicodeEncodeError`。这解释了为什么很多命令行工具在中文 Windows 上"平时没事，一旦输出特殊字符或中文路径就崩"。

`PYTHONIOENCODING=utf-8` 会覆盖这一默认行为，强制 `stdin`/`stdout`/`stderr` 使用 UTF-8，绕过 GBK 的限制。

另外，**路径中含中文 + 多层 shell 嵌套**时，容易出现编码往返损坏：A 层用 UTF-8 编码路径 → B 层按 GBK 解码 → 再编码回字符串，非 ASCII 字符被替换成 `?` 或 `\ufffd`。本任务中 `D:\应用管理\Microsoft VS Code\bin` 在自动化 shell 的 PATH 里就变成了乱码，进而触发了 conda 的 GBK 输出失败。

### 为什么这样选

本项目所有工具链（Python 3.11、Git、Conda）都能良好支持 UTF-8，而项目自身的业务数据（租约、物业、租户名称）**必然包含中文**。因此在数据库层面必须选 UTF-8 编码（PostgreSQL 建库时 `ENCODING 'UTF8'`），而不是依赖系统默认。

在 shell 层面，本次采取「**按需局部修复**」而非「全局改系统编码」的策略，原因：

- 全局把系统代码页改成 65001（UTF-8）会影响其他依赖 GBK 的老程序，属于不可逆的隐性风险。
- 编码问题只出现在特定 shell 嵌套场景，用会话级环境变量即可解决，代价最低。

### 常见坑与规避

1. **不要在日志里只写 `print()` 中文**：脚本化工具中建议显式指定编码，或统一用 `logging` 并配置 UTF-8 handler。
2. **读写文件必须显式 `encoding="utf-8"`**：Python 在 Windows 上 `open()` 默认用 GBK，读写 UTF-8 文件会乱码或报错。
3. **路径尽量避开中文**：工具链（尤其是编译类、打包类）对中文路径支持参差不齐。若无法避免，至少保证 shell 层不重复转码。
4. **排查顺序**：先确认是「程序 bug」还是「编码问题」—— 用同样命令在用户真实终端跑一次对比，若正常则是 shell 层问题。

---

## 四、Python 环境可信度的验证方法

- **日期**：2026-11-03
- **关联任务**：001
- **关键词**：sys.executable、sys.path、pip list、交叉验证

### 原理

「我以为我在正确的环境里」是 Python 项目最常见的问题源头。可靠的验证不是看提示符，而是让解释器**自报身份**：

| 手段 | 能回答的问题 |
|---|---|
| `sys.executable` | 当前运行的到底是哪个 `python.exe` |
| `sys.prefix` vs `sys.base_prefix` | 是否在虚拟环境中（相等即不在） |
| `sys.path` | 包搜索路径，可看出是否混入其他环境或用户级 `site-packages` |
| `python -m pip --version` | pip 属于哪个环境（比直接 `pip` 更可靠） |
| `where python` | 多个同名可执行文件时的优先级顺序 |

`python -m pip` 优于直接 `pip`，因为 `pip` 作为独立可执行文件可能来自 PATH 中优先级更高的其他环境，而 `python -m pip` 强制用**当前解释器**的 pip 模块。

### 为什么这样选

本项目涉及多 Agent、数据库、向量库，依赖复杂且体积大。环境混装导致的故障（如 numpy 版本冲突、PyTorch CPU/GPU 混用）排查成本极高，往往表现为难以理解的运行时错误而非明确报错。

因此把「环境自检」作为每次环境变更后的固定动作，成本几秒，收益是避免数小时的玄学排查。

### 常见坑与规避

1. **只看提示符**：`(base)` 只说明 shell 层激活了什么，不说明编辑器、Jupyter kernel、pytest 用的是哪个解释器。
2. **忽略用户级 `site-packages`**：`%APPDATA%\Python\Python311\site-packages` 会被自动加入 `sys.path`，导致「明明没装却 import 成功」。规避：检查 `sys.path` 中是否出现 `AppData\Roaming\Python`。
3. **`pip install` 提示 already satisfied 但 import 失败**：典型的装到了另一个环境。规避：一律用 `python -m pip install`。
4. **建立基线**：新建环境后立即执行一次「自检三连」并记录到文档：

```powershell
python --version
python -c "import sys; print(sys.executable); print(sys.path)"
python -m pip --version
```

后续任何异常，先复跑这三条对比基线。
