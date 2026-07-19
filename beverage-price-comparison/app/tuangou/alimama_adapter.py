"""阿里妈妈/淘宝联盟真实数据适配器：淘客物料 → GroupDeal / Restaurant。

平台记为「口碑」（阿里系到店入口，PRD §3.2）。诚实映射边界：
  - ``zk_final_price`` 为「元」字符串 → 分；``reserve_price`` 作划线价；
  - 无菜品明细/使用规则 → 降级；品牌取 ``shop_title``，伪门店平台无关（可与
    其他平台同品牌对齐）；
  - deeplink 优先 ``coupon_share_url``（带券佣金链），次 ``url``；协议相对地址
    （``//`` 开头）补 https。
"""
from __future__ import annotations

import logging

import geo_data

from .adapters import TuangouAdapter
from .cps_common import brand_store_id, build_brand_restaurant, parse_party, yuan_to_cents
from .models import KOUBEI, DEAL_SET, GroupDeal, Restaurant, UsageRule
from .alimama_client import AlimamaClient

_log = logging.getLogger("bpc.alimama")


class AlimamaAdapter(TuangouAdapter):
    platform = KOUBEI

    def __init__(self, client: AlimamaClient, grid_id: str = "wangjing",
                 query: str = "团购 套餐", max_pages: int = 2):
        self._client = client
        self.grid_id = grid_id if grid_id in geo_data.GRIDS else "wangjing"
        self._query = query
        self._max_pages = max(1, max_pages)
        self._restaurants: dict[str, Restaurant] = {}

    def fetch_deals(self) -> list[GroupDeal]:
        deals: list[GroupDeal] = []
        self._restaurants = {}
        for page in range(1, self._max_pages + 1):
            items = self._client.material_search(q=self._query, page_no=page)
            if not items:
                break
            for item in items:
                deal = self._map_item(item)
                if deal is not None:
                    deals.append(deal)
        _log.info("event=alimama_fetch grid=%s deals=%d", self.grid_id, len(deals))
        return deals

    def fetch_restaurants(self) -> list[Restaurant]:
        if not self._restaurants:
            self.fetch_deals()
        return list(self._restaurants.values())

    @staticmethod
    def _abs_url(u: str) -> str:
        return f"https:{u}" if u.startswith("//") else u

    def _map_item(self, item: dict) -> GroupDeal | None:
        item_id = str(item.get("item_id") or "")
        title = item.get("title") or ""
        if not item_id or not title:
            return None

        brand = item.get("shop_title") or "未知品牌"
        rid = brand_store_id(brand)
        if rid not in self._restaurants:
            self._restaurants[rid] = build_brand_restaurant(brand, self.grid_id)

        group_cents = yuan_to_cents(item.get("zk_final_price"))
        list_cents = yuan_to_cents(item.get("reserve_price")) or group_cents
        if group_cents <= 0:
            return None

        link = item.get("coupon_share_url") or item.get("url") or ""
        return GroupDeal(
            id=f"ali_{item_id}",
            restaurant_id=rid,
            platform=self.platform,
            title=title,
            deal_type=DEAL_SET,
            party_size=parse_party(title),
            list_price_cents=list_cents,
            group_price_cents=group_cents,
            subsidy_cents=0,
            menu_items=[],            # 无菜品明细 → 降级
            usage_rule=UsageRule(),
            deeplink=self._abs_url(link),
        )
