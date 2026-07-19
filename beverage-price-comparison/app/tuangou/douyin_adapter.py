"""抖音生活服务真实数据适配器：线上商品 → GroupDeal / Restaurant。

诚实映射边界：
  - 金额单位已是**分**（``actual_amount``/``origin_amount``），勿再 ×100；
  - 无结构化菜品明细 → 降级（``has_menu_detail=False``）；
  - 品牌取 ``account_name``/``brand_name``，门店按品牌×商圈聚合（与其他 CPS
    源共用平台无关伪门店 ID → 跨平台同品牌可对齐，G-R2 地基）；
  - deeplink 取商品 H5/小程序链接字段（有则带上，无则空——不虚构）。
"""
from __future__ import annotations

import logging

import geo_data

from .adapters import TuangouAdapter
from .cps_common import brand_store_id, build_brand_restaurant, cents_to_int, parse_party
from .models import DOUYIN, DEAL_SET, GroupDeal, Restaurant, UsageRule
from .douyin_client import DouyinLifeClient

_log = logging.getLogger("bpc.douyin")


class DouyinLifeAdapter(TuangouAdapter):
    platform = DOUYIN

    def __init__(self, client: DouyinLifeClient, grid_id: str = "wangjing",
                 max_pages: int = 3):
        self._client = client
        self.grid_id = grid_id if grid_id in geo_data.GRIDS else "wangjing"
        self._max_pages = max(1, max_pages)
        self._restaurants: dict[str, Restaurant] = {}

    def fetch_deals(self) -> list[GroupDeal]:
        deals: list[GroupDeal] = []
        self._restaurants = {}
        cursor, pages = 0, 0
        while pages < self._max_pages:
            data = self._client.product_online_get(cursor=cursor)
            for item in data.get("products") or []:
                deal = self._map_item(item)
                if deal is not None:
                    deals.append(deal)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor", 0)
            pages += 1
        _log.info("event=douyin_fetch grid=%s deals=%d", self.grid_id, len(deals))
        return deals

    def fetch_restaurants(self) -> list[Restaurant]:
        if not self._restaurants:
            self.fetch_deals()
        return list(self._restaurants.values())

    def _map_item(self, item: dict) -> GroupDeal | None:
        product = item.get("product") or {}
        sku = item.get("sku") or {}
        pid = str(product.get("product_id") or "")
        title = product.get("product_name") or ""
        if not pid or not title:
            return None
        if product.get("status", 1) not in (1, "online", "ONLINE"):
            return None  # 非在线不入库

        brand = (product.get("account_name") or product.get("brand_name") or "未知品牌")
        rid = brand_store_id(brand)
        if rid not in self._restaurants:
            self._restaurants[rid] = build_brand_restaurant(brand, self.grid_id)

        # 抖音金额单位已是分；字段可能来的是字符串/浮点，防御解析（非法→0→丢弃）
        group_cents = cents_to_int(sku.get("actual_amount"))
        list_cents = cents_to_int(sku.get("origin_amount")) or group_cents
        if group_cents <= 0:
            return None

        return GroupDeal(
            id=f"dy_{pid}",
            restaurant_id=rid,
            platform=self.platform,
            title=title,
            deal_type=DEAL_SET,
            party_size=parse_party(title),
            list_price_cents=list_cents,
            group_price_cents=group_cents,
            subsidy_cents=0,          # 补贴/神券口径不在本接口，不虚构
            menu_items=[],            # 无结构化菜品明细 → 降级
            usage_rule=UsageRule(),
            deeplink=product.get("h5_url") or product.get("detail_url") or "",
        )
