"""团购到手价引擎（G-R1）：补贴封顶不为负、附加费加项、人均口径。"""
from app.tuangou import seed_deals
from app.tuangou.pricing import compute_deal_price


def _deal(did):
    return next(d for d in seed_deals.DEALS if d.id == did)


def test_normal_deal_final_and_per_capita():
    """海底捞 4 人套餐：39800 − 补贴3000 = 36800；未选人数取中值4 → 人均9200。"""
    r = compute_deal_price(_deal("d_hdl_4p"))
    assert r.subsidy == 3000
    assert r.final_price == 36800
    assert r.people == 4
    assert r.per_capita_price == 9200


def test_extra_fee_is_added():
    """西贝包间套餐：29800 + 包间费5000 = 34800；4 人 → 人均8700。"""
    r = compute_deal_price(_deal("d_xibei_room"))
    assert r.extra_fee == 5000
    assert r.final_price == 34800
    assert r.per_capita_price == 8700
    labels = [ln.label for ln in r.lines]
    assert "包间费/服务费" in labels


def test_subsidy_capped_never_negative():
    """海底捞双人套餐：补贴20000 > 团购价16800 → 补贴封顶16800，到手价0，人均0。"""
    r = compute_deal_price(_deal("d_hdl_2p"))
    assert r.subsidy == 16800          # 封顶于团购价
    assert r.final_price == 0          # 恒非负
    assert r.per_capita_price == 0


def test_per_capita_uses_selected_party_size():
    """指定人数覆盖中值：丰茂到手价18900，选4人 → 人均4725。"""
    r = compute_deal_price(_deal("d_fengmao"), party_size=4)
    assert r.final_price == 18900
    assert r.people == 4
    assert r.per_capita_price == 4725


def test_per_capita_midpoint_when_unspecified():
    """丰茂 3-4 人档未选人数 → 取中值3 → 人均6300。"""
    r = compute_deal_price(_deal("d_fengmao"))
    assert r.people == 3
    assert r.per_capita_price == 6300


def test_breakdown_lines_reconcile():
    """明细对账：团购价 + 各行 = 到手价（加减项闭合）。"""
    r = compute_deal_price(_deal("d_xibei_room"))
    # 首行是团购价，其余为加/减项；累加应等于 final_price
    total = r.lines[0].amount + sum(ln.amount for ln in r.lines[1:])
    assert total == r.final_price
