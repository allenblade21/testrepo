"""CPS 适配器共用工具：金额换算、人数解析、品牌伪门店。

品牌伪门店 ID **平台无关**（``r_brand_<品牌>``）：联盟类数据源普遍只给品牌不给
具体门店，按品牌×商圈聚合成伪门店后，**不同平台的同品牌会对齐进同一可比
单元**（match_confidence=疑似），这是 G-R2 跨平台匹配的第一块地基；真实门店
主数据映射待商家授权补全（PRD P2-2）。
"""
from __future__ import annotations

import re

import geo_data

from .models import Restaurant

_PARTY_RE = re.compile(r"(\d+)\s*[-~至]?\s*(\d+)?\s*人")


def yuan_to_cents(v) -> int:
    """「元」→「分」（铁律 1）。兼容 float/str；异常返回 0。"""
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


def brand_store_id(brand: str) -> str:
    """品牌伪门店 ID（平台无关，保证跨平台同品牌可对齐）。"""
    slug = re.sub(r"[^0-9a-zA-Z一-鿿]+", "", brand)[:24] or "unknown"
    return f"r_brand_{slug}"


def build_brand_restaurant(brand: str, grid_id: str, poi_num: int = 0) -> Restaurant:
    gname, glat, glng = geo_data.GRIDS[grid_id]
    branch = f"品牌级·{gname}附近可用{poi_num}店" if poi_num else f"品牌级·{gname}"
    return Restaurant(
        id=brand_store_id(brand), brand=brand, branch=branch,
        cuisine="到店餐饮", grid_id=grid_id, lat=glat, lng=glng,
    )
