"""跨平台匹配引擎。

把三个平台上代表「同一款饮品」的条目对齐成一个可比饮品单元。

**商户约束（硬性规则）**：匹配键始终包含商户。只有同一商户（门店）
在不同平台上的条目才会归入同一可比单元；同款商品由不同商户售卖时，
形成多个独立单元，互不比价。

商户内的商品对齐规则：
  - 瓶装标品：有条码 → 按条码精确匹配
  - 现制饮品：无条码 → 按 品牌 + 品名 + 规格 归一化匹配

真实系统中现制饮品还会引入语义相似度/同义词，此处用归一化字符串近似。
"""
from __future__ import annotations

import hashlib
import re

from .models import ComparableUnit, Listing


def _normalize(text: str) -> str:
    """归一化：去除空格（含全角）与常见分隔符、统一大小写，用于弱匹配。

    这样「大杯/正常糖/去冰」与「大杯 正常糖 去冰」「大杯　标准」等写法可对齐。
    """
    return re.sub(r"[\s　/／·,，、]+", "", text).lower()


def unit_key(listing: Listing) -> str:
    """可比单元的自然键：``商户 + 商品``。

    商户是第一段，保证不同商户的同款商品不会被合并比价；
    第二段有条码用条码，否则用 品牌|品名|规格。
    """
    merchant = _normalize(listing.merchant)
    if listing.barcode:
        return f"{merchant}|barcode:{listing.barcode}"
    return (
        f"{merchant}|made:"
        f"{_normalize(listing.brand)}|{_normalize(listing.name)}|{_normalize(listing.spec)}"
    )


def unit_id(listing: Listing) -> str:
    """由自然键派生的稳定短 ID（前端回传用）。"""
    return hashlib.sha1(unit_key(listing).encode("utf-8")).hexdigest()[:10]


def build_units(listings: list[Listing]) -> list[ComparableUnit]:
    """把条目分组为可比单元。"""
    groups: dict[str, list[Listing]] = {}
    for listing in listings:
        groups.setdefault(unit_id(listing), []).append(listing)

    units: list[ComparableUnit] = []
    for uid, group in groups.items():
        rep = group[0]
        # 商户约束自检：分组键含商户，组内商户必然一致；此处显式断言防回归
        assert len({_normalize(l.merchant) for l in group}) == 1, "可比单元内出现多个商户"
        units.append(
            ComparableUnit(
                id=uid,
                merchant=rep.merchant,
                name=f"{rep.brand} {rep.name} {rep.spec}".strip(),
                brand=rep.brand,
                spec=rep.spec,
                type=rep.type,
                listings=group,
            )
        )
    # 覆盖平台多的排前面，其次按商户、名称，便于展示
    units.sort(key=lambda u: (-len(u.listings), u.merchant, u.name))
    return units


def search_units(units: list[ComparableUnit], query: str) -> list[ComparableUnit]:
    """按关键词召回可比单元（匹配品牌/品名/各平台标题）。"""
    q = _normalize(query)
    if not q:
        return units
    hits = []
    for unit in units:
        haystack = (
            _normalize(unit.name)
            + _normalize(unit.merchant)
            + "".join(_normalize(l.name + l.brand + l.merchant) for l in unit.listings)
        )
        if q in haystack:
            hits.append(unit)
    return hits
