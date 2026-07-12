"""到手价计算引擎。

到手价 = 售价小计 − 各项优惠（第二件半价/满减/补贴/券）+ 配送费

每项优惠的减免额封顶于当前应付金额，保证到手价恒为非负。
输出结构化明细，供前端透明展示。所有金额单位为「分」。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import DeliveryPolicy, Listing, Promotion


# 优惠参与计算的先后顺序（数字小者先算）
_KIND_ORDER = {"第二件半价": 0, "满减": 1, "补贴": 2, "券": 3}


@dataclass
class PriceLine:
    """到手价明细的一行。amount 为正表示加项，为负表示减项。"""

    label: str
    amount: int


@dataclass
class PriceResult:
    platform: str
    quantity: int
    subtotal: int          # 售价小计
    discount_total: int    # 优惠合计（正数）
    delivery_fee: int      # 实际配送费
    final_price: int       # 到手价
    orderable: bool        # 是否满足起送/可下单
    note: str = ""
    lines: list[PriceLine] = field(default_factory=list)


def _promotion_discount(promo: Promotion, listing: Listing, quantity: int, current: int) -> int:
    """计算单条优惠的减免额（分）。current 为已扣减前序优惠后的应付金额。"""
    if promo.kind == "第二件半价":
        if quantity >= 2:
            pairs = quantity // 2
            return (listing.sale_price // 2) * pairs
        return 0
    if promo.kind == "满减":
        return promo.value if current >= promo.threshold else 0
    if promo.kind == "补贴":
        return min(promo.value, current)
    if promo.kind == "券":
        return promo.value if current >= promo.threshold else 0
    return 0


def compute_price(
    listing: Listing,
    delivery: DeliveryPolicy,
    quantity: int = 1,
    include_delivery: bool = True,
    min_order: int = 0,
) -> PriceResult:
    """计算某平台条目在给定数量下的到手价与明细。

    ``min_order`` 为现制饮品起送价（分）；商品小计未达时标记为不可下单。
    """
    quantity = max(1, quantity)
    subtotal = listing.sale_price * quantity
    lines = [PriceLine("售价小计", subtotal)]

    current = subtotal
    discount_total = 0
    for promo in sorted(listing.promotions, key=lambda p: _KIND_ORDER.get(p.kind, 99)):
        amount = _promotion_discount(promo, listing, quantity, current)
        # 任何减免不得超过当前应付：防止误配的满减/券把到手价打成负数
        amount = min(amount, current)
        if amount > 0:
            current -= amount
            discount_total += amount
            lines.append(PriceLine(promo.desc, -amount))

    delivery_fee = 0
    if include_delivery:
        delivery_fee = 0 if subtotal >= delivery.free_over else delivery.base_fee
        if delivery_fee > 0:
            lines.append(PriceLine("配送费", delivery_fee))
        else:
            lines.append(PriceLine(f"配送费（满{delivery.free_over // 100}元免）", 0))
        current += delivery_fee

    orderable = subtotal >= min_order
    note = "" if orderable else f"未达起送价{min_order // 100}元，不可下单"

    return PriceResult(
        platform=listing.platform,
        quantity=quantity,
        subtotal=subtotal,
        discount_total=discount_total,
        delivery_fee=delivery_fee,
        final_price=current,
        orderable=orderable,
        note=note,
        lines=lines,
    )
