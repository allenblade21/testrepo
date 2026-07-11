"""数据模型。

金额统一以「分」为单位存储（整数），展示时换算为「元」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---- 平台 ----------------------------------------------------------------

ALIBABA = "阿里闪购"
JD = "京东"
MEITUAN = "美团"

PLATFORMS = [ALIBABA, JD, MEITUAN]


@dataclass(frozen=True)
class DeliveryPolicy:
    """平台配送策略。满 ``free_over`` 分免配送，否则收 ``base_fee`` 分。"""

    platform: str
    base_fee: int
    free_over: int


@dataclass(frozen=True)
class Promotion:
    """一条优惠。

    kind 取值：
      - ``满减``     : 小计满 threshold 减 value
      - ``补贴``     : 平台直接补贴 value（封顶不超过当前应付）
      - ``券``       : 满 threshold 可用，减 value
      - ``第二件半价``: 每两件，其中一件半价
    """

    kind: str
    desc: str
    value: int = 0
    threshold: int = 0


@dataclass
class Listing:
    """某平台上的一个商品条目。"""

    platform: str
    brand: str
    name: str
    spec: str
    type: str  # "bottled"（瓶装标品）| "made"（现制饮品）
    list_price: int
    sale_price: int
    barcode: Optional[str] = None
    promotions: list[Promotion] = field(default_factory=list)


@dataclass
class ComparableUnit:
    """跨平台对齐后的「可比饮品单元」——同一款饮品在各平台的条目集合。"""

    id: str
    name: str
    brand: str
    spec: str
    type: str
    listings: list[Listing] = field(default_factory=list)
