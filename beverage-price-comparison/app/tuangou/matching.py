"""团购套餐可比单元构建 + 同门店约束（复用饮品 ADR-001 三层保障范式）。

**同门店约束（硬性规则）**：可比单元键第一段永远是 ``restaurant_id``；只有同一
门店在不同平台上的**同人数档**套餐才归入同一可比单元。三层保障：
  1. 匹配键：首段=门店 ID（+ 人数档）；
  2. 构建断言：单元内 ``restaurant_id`` 必须唯一，否则抛错；
  3. 接口校验：``/api/tuangou/compare`` 跨门店返回 409（见 routes.py）。

G-R1 单平台，套餐无跨平台条码，人数档一致是强信号；G-R2 起引入菜品语义相似度。
"""
from __future__ import annotations

import hashlib

from .models import ComparableDeal, GroupDeal


def _party_key(party: tuple[int, int]) -> str:
    return f"{party[0]}-{party[1]}"


def deal_unit_key(deal: GroupDeal) -> str:
    """可比单元自然键：``门店 + 人数档``。门店是第一段，保证跨门店不合并。"""
    return f"{deal.restaurant_id}|party:{_party_key(deal.party_size)}"


def deal_unit_id(deal: GroupDeal) -> str:
    """由自然键派生的稳定短 ID（前端回传用；重建不改已有 ID）。"""
    return hashlib.sha1(deal_unit_key(deal).encode("utf-8")).hexdigest()[:10]


def build_comparable_deals(deals: list[GroupDeal]) -> list[ComparableDeal]:
    """把套餐分组为可比单元。组内门店必须唯一（同门店约束第二层）。"""
    groups: dict[str, list[GroupDeal]] = {}
    for deal in deals:
        groups.setdefault(deal_unit_id(deal), []).append(deal)

    units: list[ComparableDeal] = []
    for uid, group in groups.items():
        # 同门店约束自检：分组键含门店，组内门店必然一致；显式断言防回归
        assert len({d.restaurant_id for d in group}) == 1, "可比套餐单元内出现多个门店"
        rep = group[0]
        platforms = {d.platform for d in group}
        confidence = "单平台" if len(platforms) == 1 else "疑似"
        units.append(
            ComparableDeal(
                id=uid,
                restaurant_id=rep.restaurant_id,
                party_size=rep.party_size,
                deals=group,
                match_confidence=confidence,
            )
        )
    # 覆盖平台多者优先，其次按门店、人数档，便于展示
    units.sort(key=lambda u: (-len(u.deals), u.restaurant_id, u.party_size))
    return units
