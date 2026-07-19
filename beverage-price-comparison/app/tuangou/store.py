"""团购数据仓库：把「适配器抽取 → 建索引 → 构建可比单元」封装为可重建快照。

复用饮品 DataStore 范式（ADR-002 / 内存快照）：``DealStore.rebuild()`` 可随时
原子重建。单元 ID 由内容哈希派生（确定性），重建不改已有单元 ID。

数据源由环境变量选择（真实联盟 API 就绪即切，代码零改动）：
  TUANGOU_SOURCE=mock|union     默认 mock
  MEITUAN_UNION_APPKEY/SECRET   联盟密钥（union 必填）
  MEITUAN_UNION_BASE            网关地址（默认官方；测试指向仿真网关）
  MEITUAN_UNION_SID             二级渠道标识（选填）
  TUANGOU_GRID                  取数商圈网格（默认 wangjing）
union 拉取失败时**回退 Mock 并保留服务**（与饮品刷新失败不拖垮服务同策略）。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from .adapters import MockMeituanTuangouAdapter, TuangouAdapter
from .matching import build_comparable_deals
from .models import ComparableDeal, GroupDeal, Restaurant

_log = logging.getLogger("bpc.tuangou")


def _build_adapters() -> tuple[list[TuangouAdapter], str]:
    """按环境变量装配适配器，返回 (适配器列表, 实际生效数据源)。"""
    source = os.environ.get("TUANGOU_SOURCE", "mock").strip().lower()
    if source == "union":
        app_key = os.environ.get("MEITUAN_UNION_APPKEY", "")
        secret = os.environ.get("MEITUAN_UNION_SECRET", "")
        if app_key and secret:
            from .union_adapter import MeituanUnionAdapter
            from .union_client import UNION_BASE_URL, MeituanUnionClient
            client = MeituanUnionClient(
                app_key, secret,
                base_url=os.environ.get("MEITUAN_UNION_BASE", UNION_BASE_URL),
            )
            return [MeituanUnionAdapter(
                client,
                grid_id=os.environ.get("TUANGOU_GRID", "wangjing"),
                sid=os.environ.get("MEITUAN_UNION_SID", ""),
            )], "union"
        _log.warning("event=union_config_missing 未配置密钥，回退 mock")
    return [MockMeituanTuangouAdapter()], "mock"


class DealStore:
    def __init__(self) -> None:
        self.rebuild_count = 0
        self.source = "mock"
        self.rebuild()

    def rebuild(self) -> None:
        """全量重建快照。先在局部完成构建，再原子替换属性。"""
        now = datetime.now(timezone.utc)
        as_of = now.isoformat(timespec="seconds")

        adapters, source = _build_adapters()
        restaurants: list[Restaurant] = []
        deals: list[GroupDeal] = []
        try:
            for a in adapters:
                for d in a.fetch_deals():
                    d.price_as_of = as_of  # 统一戳快照时间（团购时效性强）
                    deals.append(d)
                restaurants.extend(a.fetch_restaurants())
            if source == "union" and not deals:
                raise RuntimeError("联盟返回 0 条商品")
        except Exception:  # noqa: BLE001 — 真实源失败回退 Mock，保留服务
            if source == "union":
                _log.exception("event=union_fetch_failed 回退 mock 数据源")
                source = "mock(union失败回退)"
                restaurants, deals = [], []
                mock = MockMeituanTuangouAdapter()
                for d in mock.fetch_deals():
                    d.price_as_of = as_of
                    deals.append(d)
                restaurants.extend(mock.fetch_restaurants())
            else:
                raise

        units = build_comparable_deals(deals)
        self.source = source

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
