"""到手价引擎单元测试。"""
from app.models import DeliveryPolicy, Listing, Promotion
from app.pricing import compute_price

DELIV = DeliveryPolicy(platform="测试", base_fee=500, free_over=3900)


def _listing(sale_price, promotions=None):
    return Listing(
        platform="测试", merchant="测试商户", brand="B", name="N", spec="S", type="bottled",
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


def test_quantity_unlocks_full_reduction():
    """单件不满门槛、多件满 → 满减按小计判定生效。"""
    promo = Promotion(kind="满减", desc="满15减2", value=200, threshold=1500)
    r1 = compute_price(_listing(1000, [promo]), DELIV, quantity=1, include_delivery=False)
    r2 = compute_price(_listing(1000, [promo]), DELIV, quantity=2, include_delivery=False)
    assert r1.discount_total == 0
    assert r2.discount_total == 200
    assert r2.final_price == 1800


def test_second_half_price_odd_quantity():
    """第二件半价：3件只成一对 → 只折一件的半价。"""
    promo = Promotion(kind="第二件半价", desc="第二件半价")
    r = compute_price(_listing(1000, [promo]), DELIV, quantity=3, include_delivery=False)
    assert r.subtotal == 3000
    assert r.discount_total == 500
    assert r.final_price == 2500


def test_coupon_below_threshold_not_applied():
    promo = Promotion(kind="券", desc="满14减2", value=200, threshold=1400)
    r = compute_price(_listing(1300, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 0
    assert r.final_price == 1300


def test_quantity_unlocks_free_delivery():
    """多件把小计推过免配送线 → 配送费归零。"""
    r1 = compute_price(_listing(2000), DELIV, quantity=1, include_delivery=True)
    r2 = compute_price(_listing(2000), DELIV, quantity=2, include_delivery=True)
    assert r1.delivery_fee == 500
    assert r2.delivery_fee == 0


def test_min_order_reached_by_quantity():
    """单杯未达起送、两杯达到 → 可下单。"""
    r1 = compute_price(_listing(1780), DELIV, quantity=1, include_delivery=False, min_order=2000)
    r2 = compute_price(_listing(1780), DELIV, quantity=2, include_delivery=False, min_order=2000)
    assert r1.orderable is False
    assert r2.orderable is True
