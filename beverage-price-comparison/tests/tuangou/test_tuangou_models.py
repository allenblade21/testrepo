"""团购数据模型不变式（G-R1）：金额分存储、明细可得标志、人数中值。"""
from app.tuangou import seed_deals
from app.tuangou.models import GroupDeal, MenuItem, Restaurant, UsageRule


def test_amounts_are_integer_cents():
    """所有金额字段必须是整数「分」（铁律 1）。"""
    for d in seed_deals.DEALS:
        for field_val in (d.list_price_cents, d.group_price_cents, d.subsidy_cents,
                          d.usage_rule.extra_fee_cents):
            assert isinstance(field_val, int), f"{d.id} 金额非整数分"
    for r in seed_deals.RESTAURANTS:
        assert isinstance(r.avg_price_cents, int)


def test_has_menu_detail_flag():
    """有菜品→True；空菜品→False（降级依据）。"""
    hdl = next(d for d in seed_deals.DEALS if d.id == "d_hdl_4p")
    fengmao = next(d for d in seed_deals.DEALS if d.id == "d_fengmao")
    assert hdl.has_menu_detail is True
    assert fengmao.has_menu_detail is False


def test_party_midpoint():
    """未选人数取区间中值。"""
    assert GroupDeal("x", "r", "美团点评", "t", "套餐", (3, 5), 100, 90).party_midpoint == 4
    assert GroupDeal("x", "r", "美团点评", "t", "套餐", (3, 4), 100, 90).party_midpoint == 3
    assert GroupDeal("x", "r", "美团点评", "t", "套餐", (2, 2), 100, 90).party_midpoint == 2


def test_restaurant_name_composition():
    r = Restaurant("r1", "海底捞", "望京店", "火锅", "wangjing", 0.0, 0.0)
    assert r.name == "海底捞(望京店)"


def test_restaurant_id_is_boundary_field():
    """每个套餐都带门店 ID（比价边界）。"""
    for d in seed_deals.DEALS:
        assert d.restaurant_id, "套餐缺少门店边界字段 restaurant_id"
        assert any(r.id == d.restaurant_id for r in seed_deals.RESTAURANTS)
