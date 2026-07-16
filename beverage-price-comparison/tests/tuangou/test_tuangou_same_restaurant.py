"""同门店比价约束三层保障（G-R1，复用饮品 ADR-001 范式，边界=restaurant_id）。"""
import pytest
from fastapi import HTTPException

from app.tuangou import seed_deals
from app.tuangou.matching import build_comparable_deals, deal_unit_key
from app.tuangou.models import ComparableDeal
from app.tuangou.routes import compute_deal_comparison


def test_unit_key_first_segment_is_restaurant():
    """第一层：匹配键首段永远是门店 ID。"""
    d = seed_deals.DEALS[0]
    assert deal_unit_key(d).startswith(d.restaurant_id)


def test_build_units_are_single_restaurant():
    """第二层：构建出的每个可比单元门店唯一。"""
    units = build_comparable_deals(seed_deals.DEALS)
    for u in units:
        assert len({d.restaurant_id for d in u.deals}) == 1


def test_same_restaurant_different_party_are_separate_units():
    """同门店不同人数档 → 独立单元（海底捞 3-5 与 2-2 不合并）。"""
    units = build_comparable_deals(seed_deals.DEALS)
    hdl_units = [u for u in units if u.restaurant_id == "r_haidilao_wj"]
    assert len(hdl_units) == 2
    assert {u.party_size for u in hdl_units} == {(3, 5), (2, 2)}


def test_cross_restaurant_unit_rejected_409():
    """第三层：跨门店的可比单元比价 → 409。"""
    d1 = next(d for d in seed_deals.DEALS if d.restaurant_id == "r_haidilao_wj")
    d2 = next(d for d in seed_deals.DEALS if d.restaurant_id == "r_xibei_gm")
    bad = ComparableDeal(id="bad", restaurant_id="mixed", party_size=(4, 4), deals=[d1, d2])
    with pytest.raises(HTTPException) as ei:
        compute_deal_comparison(bad)
    assert ei.value.status_code == 409
