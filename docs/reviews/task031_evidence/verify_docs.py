"""Task 031 文档静态核验：UTF-8、围栏配对、相对链接存在、归档 9 节与 Prompt 逐字。

只读检查，不修改文档。运行（仓库根）：

    python docs/reviews/task031_evidence/verify_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

CHECKED = [
    "README.md",
    "backend/README.md",
    "docs/README.md",
    "docs/architecture/CURRENT_BASELINE.md",
    "docs/architecture/agent_architecture.md",
    "docs/architecture/agent_development_guide.md",
    "docs/architecture/agent_runtime_contracts.md",
    "docs/architecture/system_design.md",
    "docs/architecture/planner_vocabulary.md",
    "docs/product/PROJECT_DEVELOPMENT_ROADMAP.md",
    "docs/product/mvp_scope_v2.md",
    "docs/evaluation/evaluation_plan.md",
    "docs/demo/demo_script.md",
    "docs/development_logs/development_log.md",
    "docs/issues/issue_log.md",
    "docs/lessons_learned/knowledge_notes.md",
    "docs/checkpoints/git_history.md",
    "docs/reviews/task031_evidence/README.md",
    "docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md",
]

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def check_links(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            problems.append(f"{path.relative_to(ROOT)} -> {target}")
    return problems


def main() -> int:
    problems: list[str] = []
    for relative in CHECKED:
        path = ROOT / relative
        if not path.is_file():
            problems.append(f"missing file: {relative}")
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            problems.append(f"not utf-8: {relative}: {exc}")
            continue
        fences = len(re.findall(r"(?m)^```", text))
        if fences % 2 != 0:
            problems.append(f"unbalanced code fences: {relative} ({fences})")
        problems.extend(check_links(path))

    archive = ROOT / "docs/prompts/06_testing/2026-11-21_031_core_correctness_fixes.md"
    text = archive.read_text(encoding="utf-8")
    for section in range(1, 10):
        if f"## {section}." not in text:
            problems.append(f"archive missing section {section}")
    prompt = (ROOT / "docs/handoffs/DEEPSEEK_TASK031_CORE_FIXES_PROMPT.md").read_text(
        encoding="utf-8"
    )
    for line in prompt.strip().splitlines():
        if line.strip() and line not in text:
            problems.append(f"archive prompt line not verbatim: {line[:60]!r}")
            break

    if problems:
        print("PROBLEMS:")
        for item in problems:
            print(" -", item)
        return 1
    print(f"OK: {len(CHECKED)} files, links/fences/utf-8/sections/prompt-verbatim all pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
