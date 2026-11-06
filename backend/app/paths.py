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

#: 控制面存储（Task 012）。默认放在仓库内的 `data/`，已被 `.gitignore` 排除：
#: checkpoint 与审批台账是运行期状态，不应进入版本库。
DATA_DIR: Path = REPO_ROOT / "data"
CHECKPOINT_DB: Path = DATA_DIR / "checkpoints" / "graph.sqlite"
CONTROL_DB: Path = DATA_DIR / "control" / "approval.sqlite"
SQLITE_DB_PATH: Path = DATA_DIR / "business" / "business.sqlite"

#: 合成文档产物目录（Task 011）。PDF 由 `python -m app.rag.pdf_builder` 生成并纳入仓库，
#: 保证"索引内容"可复现，而不是每次运行时随机生成。
DOCUMENT_DIR: Path = REPO_ROOT / "docs" / "evaluation" / "documents"

#: fixture `documents` 中的 document_id → 实际 PDF 文件。
DOCUMENT_FILES: dict[str, str] = {
    "doc_xh_a301_contract": "lease_xh_a301_contract_v1.pdf",
    "doc_xh_property_policy": "property_policy_v1.pdf",
}


def resolve_project_path(relative: str | Path) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError(f"只接受相对路径（基准为 backend/），收到: {relative}")
    resolved = (BACKEND_ROOT / candidate).resolve()
    if BACKEND_ROOT.resolve() not in resolved.parents and resolved != BACKEND_ROOT.resolve():
        raise ValueError(f"路径越界: {relative}")
    return resolved
