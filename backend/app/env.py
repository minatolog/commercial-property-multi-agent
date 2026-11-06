"""最小的 `.env` 加载器（Task 019，无第三方依赖）。

为什么需要它：`.env.example` 一直写着"复制为 .env 即可"，但代码只读 `os.environ`，
所以照做的人会得到一个**静默失效**的配置——密钥填了却没生效，最后表现为
"模型没调用"或"演示主体不对"。这里补上真正的加载逻辑。

三条硬规则：

1. **环境变量优先**：`.env` 只填补"尚未设置"的键，绝不覆盖外部已导出的值；
2. **不回显值**：返回值只含键名，日志/错误里永远不出现密钥内容；
3. **缺文件不报错**：没有 `.env` 是完全正常的运行方式（离线可用）。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["load_env_file", "load_project_env", "parse_env_text"]


def parse_env_text(text: str) -> dict[str, str]:
    """解析 `.env` 文本。

    支持的写法：`KEY=VALUE`、`export KEY=VALUE`、`#` 注释、空行、
    单/双引号包裹的值。不认识的行直接忽略（不抛异常），
    因为 `.env` 是"便利配置"而不是强校验的配置文件。
    """

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(
    path: str | Path, *, override: bool = False, environ: dict[str, str] | None = None
) -> tuple[str, ...]:
    """把 `.env` 里的键写入环境；返回**实际写入的键名**（不含值）。

    `override=False`（默认）时，已存在的环境变量保持原值。
    """

    target = Path(path)
    if not target.is_file():
        return ()
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):  # pragma: no cover - 文件损坏时不影响主流程
        return ()
    env = os.environ if environ is None else environ
    applied: list[str] = []
    for key, value in parse_env_text(text).items():
        if not override and env.get(key):
            continue
        env[key] = value
        applied.append(key)
    return tuple(applied)


def load_project_env(
    *, paths: tuple[Path, ...] | None = None, override: bool = False
) -> tuple[str, ...]:
    """加载项目级 `.env`：先仓库根，再 `backend/`（后者不覆盖前者）。"""

    from .paths import BACKEND_ROOT, REPO_ROOT

    candidates = paths if paths is not None else (REPO_ROOT / ".env", BACKEND_ROOT / ".env")
    applied: list[str] = []
    for candidate in candidates:
        applied.extend(load_env_file(candidate, override=override))
    return tuple(dict.fromkeys(applied))
