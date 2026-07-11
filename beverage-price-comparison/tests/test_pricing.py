"""到手价引擎单元测试。"""
from app.models import DeliveryPolicy, Listing, Promotion
from app.pricing import compute_price

DELIV = DeliveryPolicy(platform="测试", base_fee=500, free_over=3900)


def _listing(sale_price, promotions=None):
    return Listing(
        platform="测试", brand="B", name="N", spec="S", type="bottled",
        list_price=sale_price, sale_price=sale_price, promotions=promotions or [],
    )


def test_basic_no_promo_with_delivery():
    r = compute_price(_listing(1000), DELIV, quantity=1, include_delivery=True)
    assert r.subtotal == 1000
    assert r.delivery_fee == 500        # 未满39元，收配送费
    assert r.final_price == 1500


def test_free_delivery_over_threshold():
    r = compute_price(_listing(4000), DELIV, quantity=1, include_delivery=True)
    assert r.delivery_fee == 0          # 满39元免配送
    assert r.final_price == 4000


def test_exclude_delivery():
    r = compute_price(_listing(1000), DELIV, quantity=1, include_delivery=False)
    assert r.delivery_fee == 0
    assert r.final_price == 1000


def test_full_reduction_applies_above_threshold():
    promo = Promotion(kind="满减", desc="满15减2", value=200, threshold=1500)
    r = compute_price(_listing(1600, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 200
    assert r.final_price == 1400


def test_full_reduction_skipped_below_threshold():
    promo = Promotion(kind="满减", desc="满15减2", value=200, threshold=1500)
    r = compute_price(_listing(1400, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 0
    assert r.final_price == 1400


def test_second_half_price():
    promo = Promotion(kind="第二件半价", desc="第二件半价")
    # 单价1000，买2件：一件全价+一件半价 → 折 500
    r = compute_price(_listing(1000, [promo]), DELIV, quantity=2, include_delivery=False)
    assert r.subtotal == 2000
    assert r.discount_total == 500
    assert r.final_price == 1500


def test_subsidy_capped_at_payable():
    promo = Promotion(kind="补贴", desc="平台补贴", value=5000)
    r = compute_price(_listing(1000, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 1000     # 补贴不超过应付
    assert r.final_price == 0


def test_min_order_not_reached():
    r = compute_price(_listing(1000), DELIV, quantity=1, include_delivery=False, min_order=2000)
    assert r.orderable is False
    assert "起送" in r.note


def test_stacked_promotions_order():
    # 满减 + 券 叠加
    promos = [
        Promotion(kind="满减", desc="满20减3", value=300, threshold=2000),
        Promotion(kind="券", desc="券减2", value=200, threshold=1000),
    ]
    r = compute_price(_listing(2500, promos), DELIV, include_delivery=False)
    # 2500 -300(满减) = 2200 -200(券, 满10可用) = 2000
    assert r.discount_total == 500
    assert r.final_price == 2000
