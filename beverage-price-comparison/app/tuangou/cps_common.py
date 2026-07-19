"""CPS 适配器共用工具：金额换算、人数解析、品牌伪门店。

品牌伪门店 ID **平台无关**（``r_brand_<品牌>``）：联盟类数据源普遍只给品牌不给
具体门店，按品牌×商圈聚合成伪门店后，**不同平台的同品牌会对齐进同一可比
单元**（match_confidence=疑似），这是 G-R2 跨平台匹配的第一块地基；真实门店
主数据映射待商家授权补全（PRD P2-2）。
"""
from __future__ import annotations

import math
import re

import geo_data

from .models import Restaurant

_PARTY_RE = re.compile(r"(\d+)\s*[-~至]?\s*(\d+)?\s*人")

PARTY_UNKNOWN = (1, 99)   # 未知人数档；也是合法人数上限（99）


def yuan_to_cents(v) -> int:
    """「元」→「分」（铁律 1）。兼容 float/str；非有限数/异常一律返回 0。

    必须挡住 inf/nan：JSON 可携带 Infinity，``int(round(inf))`` 会抛
    OverflowError 炸掉整个数据源（边界测试覆盖）。
    """
    try:
        f = float(v)
        if not math.isfinite(f):
            return 0
        return int(round(f * 100))
    except (TypeError, ValueError):
        return 0


def cents_to_int(v) -> int:
    """已是「分」口径的字段 → 整数分。兼容 int/float/str；非法/非有限返回 0。"""
    try:
        f = float(v)
        if not math.isfinite(f):
            return 0
        return int(round(f))
    except (TypeError, ValueError):
        return 0


def parse_party(title: str) -> tuple[int, int]:
    """从套餐标题解析人数档：「4 人餐」→(4,4)，「3-4人」→(3,4)。

    解析不到、或解析出无意义档位（0 人 / 超过 99 人）→ (1,99) 未知档，
    避免出现永远匹配不到任何用户人数的「死档」。
    """
    m = _PARTY_RE.search(title or "")
    if not m:
        return PARTY_UNKNOWN
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    lo, hi = min(lo, hi), max(lo, hi)
    if lo < 1 or lo > 99:
        return PARTY_UNKNOWN
    return (lo, min(hi, 99))


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
