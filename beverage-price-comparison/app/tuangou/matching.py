"""团购套餐可比单元构建 + 同门店约束（复用饮品 ADR-001 三层保障范式）。

**同门店约束（硬性规则）**：可比单元键第一段永远是 ``restaurant_id``；只有同一
门店在不同平台上的**同人数档**套餐才归入同一可比单元。三层保障：
  1. 匹配键：首段=门店 ID（+ 人数档）；
  2. 构建断言：单元内 ``restaurant_id`` 必须唯一，否则抛错；
  3. 接口校验：``/api/tuangou/compare`` 跨门店返回 409（见 routes.py）。

**G-R2 置信度分级**（多信号，套餐无条码只能语义判定）：
  - 单平台：单元内只有一个平台，无跨平台可比性问题；
  - 精确：跨平台且【标题相似度 ≥ 0.6（归一化字符二元组 Jaccard）
    且 价位带接近（min/max ≥ 0.75）】——两信号都过才算；
  - 疑似：跨平台但任一信号不过——界面必须标注「套餐内容可能有差异」，
    不假装等同（PRD §6.5）。
判定阈值有测试锁（test_tuangou_matching_confidence），调整须同步测试与文档。
"""
from __future__ import annotations

import hashlib
import re

from .models import ComparableDeal, GroupDeal

TITLE_SIM_THRESHOLD = 0.6
PRICE_BAND_THRESHOLD = 0.75


def _party_key(party: tuple[int, int]) -> str:
    return f"{party[0]}-{party[1]}"


def _norm_title(t: str) -> str:
    return re.sub(r"[\s　/／·,，、()（）【】\[\]-]+", "", t or "").lower()


def title_similarity(a: str, b: str) -> float:
    """归一化标题的字符二元组 Jaccard 相似度（0~1）。"""
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ga = {na[i:i + 2] for i in range(len(na) - 1)} or {na}
    gb = {nb[i:i + 2] for i in range(len(nb) - 1)} or {nb}
    return len(ga & gb) / len(ga | gb)


def _classify(group: list[GroupDeal]) -> tuple[str, str]:
    """对一组同门店同人数档的套餐判定置信度，返回 (置信度, 说明)。"""
    if len({d.platform for d in group}) == 1:
        return "单平台", ""
    # 两信号逐对判定：任何一对不过即降为疑似
    min_sim = 1.0
    prices = [d.group_price_cents for d in group if d.group_price_cents > 0]
    band = (min(prices) / max(prices)) if prices else 0.0
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            min_sim = min(min_sim, title_similarity(group[i].title, group[j].title))
    if min_sim >= TITLE_SIM_THRESHOLD and band >= PRICE_BAND_THRESHOLD:
        return "精确", f"标题相似{min_sim:.2f}·价位带{band:.2f}"
    reasons = []
    if min_sim < TITLE_SIM_THRESHOLD:
        reasons.append(f"标题相似度低({min_sim:.2f})")
    if band < PRICE_BAND_THRESHOLD:
        reasons.append(f"价位差异大({band:.2f})")
    return "疑似", "套餐内容可能有差异：" + "、".join(reasons)


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
        confidence, note = _classify(group)
        units.append(
            ComparableDeal(
                id=uid,
                restaurant_id=rep.restaurant_id,
                party_size=rep.party_size,
                deals=group,
                match_confidence=confidence,
                match_note=note,
            )
        )
    # 覆盖平台多者优先，其次按门店、人数档，便于展示
    units.sort(key=lambda u: (-len(u.deals), u.restaurant_id, u.party_size))
    return units
