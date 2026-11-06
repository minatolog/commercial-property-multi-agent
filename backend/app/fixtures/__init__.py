"""合成业务数据（fixture）只读访问层。

唯一事实源是 `docs/evaluation/fixtures/agent_first_v1.json`；
本层不复制数据、不写回、不做网络/数据库访问。所有金额用 `Decimal`。
"""

from .repository import FixtureRepository

__all__ = ["FixtureRepository"]
