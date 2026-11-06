"""演示用 Web 适配层（Task 014）。

删除本包不会影响 CLI（`python -m app.cli`）与评测（`app.evaluation`）：
它们都不 import `app.api`。
"""

from __future__ import annotations

from .app import app, create_app

__all__ = ["app", "create_app"]
