"""数据仓库：把「建库→适配器抽取→归并→匹配」的启动快照封装为可重建对象。

生产化要点：快照不再是模块级冻结全局量——``DataStore.rebuild()`` 可随时
原子重建（手动 /admin/refresh 或定时任务触发），为真实数据源的调度刷新
预留机制。单元 ID 由内容哈希派生（确定性），重建不改变已有商品的 ID。
"""
from __future__ import annotations

from datetime import datetime, timezone

from .adapters.alibaba import AlibabaAdapter
from .adapters.jd import JDAdapter
from .adapters.meituan import MeituanAdapter
from .db import init_db
from .matching import build_units


class DataStore:
    def __init__(self) -> None:
        self.rebuild_count = 0
        self.rebuild()

    def rebuild(self) -> None:
        """全量重建快照。先在局部完成构建，再原子替换属性。"""
        conn = init_db()
        adapters = [AlibabaAdapter(conn), JDAdapter(conn), MeituanAdapter(conn)]
        delivery = {a.platform: a.fetch_delivery() for a in adapters}
        listings = []
        for a in adapters:
            listings.extend(a.fetch_listings())
        units = build_units(listings)

        self.conn = conn
        self.delivery = delivery
        self.listings = listings
        self.units = units
        self.units_by_id = {u.id: u for u in units}
        self.snapshot_at = datetime.now(timezone.utc)
        self.rebuild_count += 1

    @property
    def snapshot_at_iso(self) -> str:
        return self.snapshot_at.isoformat(timespec="seconds")
