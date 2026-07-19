"""团购到手价引擎（G-R1）。

口径（PRD §7 / 设计文档 §6）：

    套餐到手价 = 团购价 − 补贴/神券（封顶于当前应付、不为负）
                 + 包间费/服务费（若该套餐收取且不含在内）
    人均到手价 = 套餐到手价 ÷ 适用人数（未选人数取区间中值）

复用饮品引擎核心不变式：每项减免 ``min(amount, current)``，到手价恒非负——
勿删这个 min()（有测试锁）。团购新增：``extra_fee`` 加项、``人均``。所有金额为分。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import GroupDeal


@dataclass
class DealPriceLine:
    """到手价明细一行。amount 为正=加项，为负=减项（分）。"""

    label: str
    amount: int


@dataclass
class DealPriceResult:
    deal_id: str
    platform: str
    group_price: int          # 团购价
    subsidy: int              # 实际生效补贴（正数）
    extra_fee: int            # 附加费加项
    final_price: int          # 套餐到手价
    people: int               # 计算人均所用人数
    per_capita_price: int     # 人均到手价
    has_menu_detail: bool     # 菜品明细是否可得（缺失需界面标注）
    lines: list[DealPriceLine] = field(default_factory=list)
    note: str = ""


def compute_deal_price(deal: GroupDeal, party_size: int | None = None) -> DealPriceResult:
    """计算某套餐的到手价与人均。

    ``party_size`` 为用户所选人数；未传时取套餐人数区间中值。
    """
    current = deal.group_price_cents
    lines = [DealPriceLine("团购价", deal.group_price_cents)]

    # 补贴/神券：减项，封顶于当前应付，防止打成负数
    subsidy = 0
    if deal.subsidy_cents > 0:
        subsidy = min(deal.subsidy_cents, current)
        current -= subsidy
        lines.append(DealPriceLine("平台补贴/神券", -subsidy))

    # 包间费/服务费：加项（团购价未含）
    extra_fee = deal.usage_rule.extra_fee_cents
    if extra_fee > 0:
        current += extra_fee
        lines.append(DealPriceLine("包间费/服务费", extra_fee))

    final_price = current

    people = party_size if (party_size and party_size > 0) else deal.party_midpoint
    people = max(1, people)
    # 人均取整用「半数进位」的整数运算：round() 是银行家舍入（2487.5→2488 但
    # 2486.5→2486），金额口径必须一致进位——勿改回 round()（有边界测试锁）
    per_capita = (2 * final_price + people) // (2 * people)

    note = "" if deal.has_menu_detail else "未含菜品明细（数据源未授权该字段）"

    return DealPriceResult(
        deal_id=deal.id,
        platform=deal.platform,
        group_price=deal.group_price_cents,
        subsidy=subsidy,
        extra_fee=extra_fee,
        final_price=final_price,
        people=people,
        per_capita_price=per_capita,
        has_menu_detail=deal.has_menu_detail,
        lines=lines,
        note=note,
    )
