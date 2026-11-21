"""把 Task 031 证据目录里的文本统一成 UTF-8（Windows PowerShell `>` 默认写 UTF-16）。

只处理 `docs/reviews/task031_evidence/` 下的文本/JSON 证据文件；不触碰源码、用例或报告。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUFFIXES = {".txt", ".json", ".md"}


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("gbk"), "gbk"


def main() -> int:
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        if path.name == Path(__file__).name:
            continue
        raw = path.read_bytes()
        text, encoding = decode(raw)
        if encoding not in {"utf-8"}:
            path.write_text(text, encoding="utf-8")
            print(f"[converted] {path.relative_to(ROOT)} ({encoding} -> utf-8)")
        else:
            print(f"[utf-8 ok] {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
