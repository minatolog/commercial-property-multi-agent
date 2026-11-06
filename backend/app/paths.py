"""路径解析。

配置文件中的 `prompt_path` 等相对路径统一以 `backend/` 为基准，
避免依赖进程当前工作目录（从仓库根启动与从 backend/ 启动必须表现一致）。
"""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT: Path = Path(__file__).resolve().parents[1]
REPO_ROOT: Path = BACKEND_ROOT.parent
CONFIG_DIR: Path = BACKEND_ROOT / "app" / "config" / "agents"
DEFAULT_FIXTURE_PATH: Path = (
    REPO_ROOT / "docs" / "evaluation" / "fixtures" / "agent_first_v1.json"
)


def resolve_project_path(relative: str | Path) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError(f"只接受相对路径（基准为 backend/），收到: {relative}")
    resolved = (BACKEND_ROOT / candidate).resolve()
    if BACKEND_ROOT.resolve() not in resolved.parents and resolved != BACKEND_ROOT.resolve():
        raise ValueError(f"路径越界: {relative}")
    return resolved
