"""团购数据仓库：把「适配器抽取 → 建索引 → 构建可比单元」封装为可重建快照。

复用饮品 DataStore 范式（ADR-002 / 内存快照）：``DealStore.rebuild()`` 可随时
原子重建。单元 ID 由内容哈希派生（确定性），重建不改已有单元 ID。
"""
from __future__ import annotations

from datetime import datetime, timezone

from .adapters import MockMeituanTuangouAdapter, TuangouAdapter
from .matching import build_comparable_deals
from .models import ComparableDeal, GroupDeal, Restaurant


class DealStore:
    def __init__(self) -> None:
        self.rebuild_count = 0
        self.rebuild()

    def rebuild(self) -> None:
        """全量重建快照。先在局部完成构建，再原子替换属性。"""
        now = datetime.now(timezone.utc)
        as_of = now.isoformat(timespec="seconds")

        adapters: list[TuangouAdapter] = [MockMeituanTuangouAdapter()]
        restaurants: list[Restaurant] = []
        deals: list[GroupDeal] = []
        for a in adapters:
            restaurants.extend(a.fetch_restaurants())
            for d in a.fetch_deals():
                d.price_as_of = as_of      # 统一戳快照时间（团购时效性强）
                deals.append(d)

        units = build_comparable_deals(deals)

        self.restaurants = restaurants
        self.restaurants_by_id = {r.id: r for r in restaurants}
        self.deals = deals
        self.deals_by_id = {d.id: d for d in deals}
        self.units = units
        self.units_by_id = {u.id: u for u in units}
        self.snapshot_at = now
        self.rebuild_count += 1

    @property
    def snapshot_at_iso(self) -> str:
        return self.snapshot_at.isoformat(timespec="seconds")
