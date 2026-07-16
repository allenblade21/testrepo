"""团购平台适配器（可插拔，复用主系统适配器范式）。

G-R1 为 ``MockMeituanTuangouAdapter``，读固定种子，但**字段集严格对齐美团联盟
「团单/商品查询」可得字段**：门店/标题/团购价/门市价/人数/deeplink 为主字段；
菜品清单（``menu_items``）与使用规则细项为**可能缺失字段**，缺失时下游降级
（``has_menu_detail=False`` + 界面标注），见 ADR-011 与设计文档 §4。

接真实联盟 API 时只替换本层实现，上层（匹配/算价/路由）零改动。
"""
from __future__ import annotations

import abc

from . import seed_deals
from .models import GroupDeal, MEITUAN_DIANPING, Restaurant


class TuangouAdapter(abc.ABC):
    """团购平台适配器统一接口。"""

    platform: str

    @abc.abstractmethod
    def fetch_restaurants(self) -> list[Restaurant]:
        """拉取门店主数据。"""

    @abc.abstractmethod
    def fetch_deals(self) -> list[GroupDeal]:
        """拉取本平台团购套餐。"""


class MockMeituanTuangouAdapter(TuangouAdapter):
    """美团点评团购 Mock 适配器（G-R1）。

    读固定种子；字段契约对齐联盟可得范围。``price_as_of`` 由调用方（Store）在
    重建时统一戳快照时间，避免脏读。
    """

    platform = MEITUAN_DIANPING

    def fetch_restaurants(self) -> list[Restaurant]:
        return list(seed_deals.RESTAURANTS)

    def fetch_deals(self) -> list[GroupDeal]:
        return [d for d in seed_deals.DEALS if d.platform == self.platform]
