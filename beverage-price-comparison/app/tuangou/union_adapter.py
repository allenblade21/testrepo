"""美团联盟真实数据适配器：联盟商品券 → GroupDeal / Restaurant。

只换适配器层，上层（匹配/算价/路由）零改动（ADR-002/011 兑现）。

诚实映射边界（联盟字段为「带货」设计，与设计文档 §4.2 一致）：
  - **无菜品明细** → ``menu_items=[]``，``has_menu_detail=False``，界面标注降级；
  - **到店券无具体门店 ID**（仅品牌 + 可用门店数）→ 门店按「品牌×商圈」聚合为
    伪门店（``r_union_<brand>``），真实门店主数据映射待商家授权补全（PRD P2-2）；
  - **人数档从标题解析**（如「4 人餐」「3-4人」），解析不到记为 (1, 99)=未知档；
  - 价格「元」→「分」（×100 四舍五入，铁律 1）；划线价字段兼容官方拼写
    ``originalPrlice``（真实接口即如此）与 ``originalPrice``。
"""
from __future__ import annotations

import logging
import re

import geo_data

from .adapters import TuangouAdapter
from .models import MEITUAN_DIANPING, DEAL_SET, GroupDeal, Restaurant, UsageRule
from .union_client import LINKTYPE_H5, MeituanUnionClient, UnionAPIError

_log = logging.getLogger("bpc.union")

_PARTY_RE = re.compile(r"(\d+)\s*[-~至]?\s*(\d+)?\s*人")


def _yuan_to_cents(v) -> int:
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return 0


def parse_party(title: str) -> tuple[int, int]:
    """从套餐标题解析人数档：「4 人餐」→(4,4)，「3-4人」→(3,4)，无→(1,99) 未知档。"""
    m = _PARTY_RE.search(title or "")
    if not m:
        return (1, 99)
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return (min(lo, hi), max(lo, hi))


def _brand_store_id(brand: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z一-鿿]+", "", brand)[:24] or "unknown"
    return f"r_union_{slug}"


class MeituanUnionAdapter(TuangouAdapter):
    """真实联盟适配器。``grid_id`` 指定取数商圈（用其中心坐标做经纬度入参）。"""

    platform = MEITUAN_DIANPING

    def __init__(self, client: MeituanUnionClient, grid_id: str = "wangjing",
                 sid: str = "", max_pages: int = 3, fetch_links: bool = True):
        self._client = client
        self.grid_id = grid_id if grid_id in geo_data.GRIDS else "wangjing"
        self._sid = sid
        self._max_pages = max(1, max_pages)
        self._fetch_links = fetch_links
        self._restaurants: dict[str, Restaurant] = {}

    # ---- 取数 --------------------------------------------------------------

    def fetch_deals(self) -> list[GroupDeal]:
        _name, lat, lng = geo_data.GRIDS[self.grid_id]
        deals: list[GroupDeal] = []
        self._restaurants = {}
        page = 1
        while page <= self._max_pages:
            data = self._client.query_coupon(latitude=lat, longitude=lng, page_no=page)
            for item in data.get("data") or []:
                deal = self._map_item(item)
                if deal is not None:
                    deals.append(deal)
            if not data.get("hasNext"):
                break
            page += 1
        _log.info("event=union_fetch grid=%s deals=%d restaurants=%d",
                  self.grid_id, len(deals), len(self._restaurants))
        return deals

    def fetch_restaurants(self) -> list[Restaurant]:
        # 门店由 fetch_deals 过程中按品牌聚合产生；单独调用时先拉一次
        if not self._restaurants:
            self.fetch_deals()
        return list(self._restaurants.values())

    # ---- 映射 --------------------------------------------------------------

    def _map_item(self, item: dict) -> GroupDeal | None:
        detail = item.get("couponPackDetail") or {}
        if not detail.get("saleStatus", True):
            return None  # 不可售不入库
        sku = detail.get("skuViewId") or ""
        title = detail.get("name") or ""
        if not sku or not title:
            return None

        brand = (item.get("brandInfo") or {}).get("brandName") or "未知品牌"
        rid = _brand_store_id(brand)
        if rid not in self._restaurants:
            gname, glat, glng = geo_data.GRIDS[self.grid_id]
            poi_num = (item.get("availablePoiInfo") or {}).get("availablePoiNum", 0)
            self._restaurants[rid] = Restaurant(
                id=rid, brand=brand,
                branch=f"品牌级·{gname}附近可用{poi_num}店" if poi_num else f"品牌级·{gname}",
                cuisine="到店餐饮", grid_id=self.grid_id, lat=glat, lng=glng,
            )

        sell = detail.get("sellPrice")
        # 官方接口划线价字段拼写即为 originalPrlice；两种写法都兼容
        original = detail.get("originalPrlice", detail.get("originalPrice", sell))
        group_cents = _yuan_to_cents(sell)
        list_cents = _yuan_to_cents(original) or group_cents
        if group_cents <= 0:
            return None

        deeplink = ""
        if self._fetch_links:
            try:
                deeplink = self._client.get_referral_link(
                    sku, link_type=LINKTYPE_H5, sid=self._sid)
            except UnionAPIError as e:
                _log.warning("event=union_link_failed sku=%s err=%s", sku, e)

        return GroupDeal(
            id=f"u_{sku}",
            restaurant_id=rid,
            platform=self.platform,
            title=title,
            deal_type=DEAL_SET,
            party_size=parse_party(title),
            list_price_cents=list_cents,
            group_price_cents=group_cents,
            subsidy_cents=0,           # 联盟出参不含补贴口径，不虚构（诚实标注）
            menu_items=[],             # 联盟无菜品明细 → 降级（has_menu_detail=False）
            usage_rule=UsageRule(),    # 结构化使用规则不可得，默认值 + 界面标注
            deeplink=deeplink,
        )
