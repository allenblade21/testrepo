"""边界点测试。

验证条件：正常返回价格（到手价非负、结构完整）且比价结论无误。
覆盖：优惠门槛边界、免配送线、起送线、数量上下限、负价防护、并列最低价。
"""
from fastapi.testclient import TestClient

from app.models import DeliveryPolicy, Listing, Promotion
from app.pricing import compute_price

DELIV = DeliveryPolicy(platform="测试", base_fee=500, free_over=3900)


def _listing(sale_price, promotions=None):
    return Listing(
        platform="测试", merchant="测试商户", brand="B", name="N", spec="S", type="bottled",
        list_price=sale_price, sale_price=sale_price, promotions=promotions or [],
    )


# ---- 优惠门槛边界（恰好达到 / 差一分）------------------------------------

def test_full_reduction_exact_threshold():
    """满减：小计恰好等于门槛 → 生效（>= 语义）。"""
    promo = Promotion(kind="满减", desc="满15减2", value=200, threshold=1500)
    r = compute_price(_listing(1500, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 200
    assert r.final_price == 1300


def test_full_reduction_one_fen_below_threshold():
    """满减：差一分不达门槛 → 不生效。"""
    promo = Promotion(kind="满减", desc="满15减2", value=200, threshold=1500)
    r = compute_price(_listing(1499, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 0
    assert r.final_price == 1499


def test_coupon_exact_threshold():
    """券：恰好达门槛 → 生效。"""
    promo = Promotion(kind="券", desc="满14减2", value=200, threshold=1400)
    r = compute_price(_listing(1400, [promo]), DELIV, include_delivery=False)
    assert r.discount_total == 200
    assert r.final_price == 1200


# ---- 免配送线 / 起送线边界 ------------------------------------------------

def test_free_delivery_exact_threshold():
    """小计恰好等于免配线 → 免配送。"""
    r = compute_price(_listing(3900), DELIV, include_delivery=True)
    assert r.delivery_fee == 0
    assert r.final_price == 3900


def test_delivery_fee_one_fen_below_threshold():
    """小计差一分 → 照收配送费。"""
    r = compute_price(_listing(3899), DELIV, include_delivery=True)
    assert r.delivery_fee == 500
    assert r.final_price == 4399


def test_min_order_exact_boundary():
    """起送价：恰好等于 → 可下单；差一分 → 拦截。"""
    r_ok = compute_price(_listing(2000), DELIV, include_delivery=False, min_order=2000)
    r_no = compute_price(_listing(1999), DELIV, include_delivery=False, min_order=1999 + 1)
    assert r_ok.orderable is True
    assert r_no.orderable is False


# ---- 负价防护（核心验证条件：正常返回价格）--------------------------------

def test_coupon_never_drives_price_negative():
    """券面额超过应付（如误配 满5减6）→ 到手价封底为 0，不得为负。"""
    promo = Promotion(kind="券", desc="满5减6", value=600, threshold=500)
    r = compute_price(_listing(500, [promo]), DELIV, include_delivery=False)
    assert r.final_price >= 0, f"到手价为负: {r.final_price}"
    assert r.final_price == 0


def test_full_reduction_never_drives_price_negative():
    """满减减免超过应付（如误配 满5减10）→ 到手价封底为 0。"""
    promo = Promotion(kind="满减", desc="满5减10", value=1000, threshold=500)
    r = compute_price(_listing(500, [promo]), DELIV, include_delivery=False)
    assert r.final_price >= 0, f"到手价为负: {r.final_price}"
    assert r.final_price == 0


def test_stacked_discounts_floor_at_zero():
    """补贴清零后，零门槛券不得再把价格打负。"""
    promos = [
        Promotion(kind="补贴", desc="大额补贴", value=5000, threshold=0),
        Promotion(kind="券", desc="无门槛券", value=300, threshold=0),
    ]
    r = compute_price(_listing(1000, promos), DELIV, include_delivery=False)
    assert r.final_price == 0
    assert r.discount_total <= 1000  # 减免合计不得超过小计


def test_breakdown_sums_to_final_price():
    """明细行求和必须等于到手价（对账一致性）。"""
    promos = [
        Promotion(kind="满减", desc="满20减3", value=300, threshold=2000),
        Promotion(kind="券", desc="券减2", value=200, threshold=1000),
    ]
    r = compute_price(_listing(2500, promos), DELIV, quantity=1, include_delivery=True)
    assert sum(l.amount for l in r.lines) == r.final_price


# ---- 数量边界 --------------------------------------------------------------

def test_max_quantity_second_half_price():
    """数量上限 99：第二件半价折 49 对，金额精确。"""
    promo = Promotion(kind="第二件半价", desc="第二件半价")
    r = compute_price(_listing(1450, [promo]), DELIV, quantity=99, include_delivery=False)
    assert r.subtotal == 1450 * 99
    assert r.discount_total == (1450 // 2) * 49
    assert r.final_price == r.subtotal - r.discount_total


# ---- API 边界 --------------------------------------------------------------

def _client():
    from app.main import app
    return TestClient(app)


def _coke_unit_id(client):
    res = client.get("/search", params={"q": "永辉"}).json()["results"]
    return next(r["id"] for r in res if "可乐" in r["name"])


def test_api_qty_bounds():
    """qty=0/100 越界 → 422；qty=1/99 边界值 → 200 且价格非负。"""
    client = _client()
    uid = _coke_unit_id(client)
    assert client.get("/compare", params={"unit_id": uid, "qty": 0}).status_code == 422
    assert client.get("/compare", params={"unit_id": uid, "qty": 100}).status_code == 422
    for qty in (1, 99):
        resp = client.get("/compare", params={"unit_id": uid, "qty": qty})
        assert resp.status_code == 200
        assert all(p["final_price"] >= 0 for p in resp.json()["platforms"])


def test_api_unknown_unit_returns_404():
    client = _client()
    assert client.get("/compare", params={"unit_id": "不存在"}).status_code == 404


def test_api_whitespace_query_returns_all():
    """空白查询 → 归一化为空 → 浏览全库（total=全部单元，分页返回）。"""
    client = _client()
    total = client.get("/health").json()["units"]
    data = client.get("/search", params={"q": "   "}).json()
    assert data["total"] == total
    assert data["count"] <= 20  # 默认页大小


def test_api_tie_cheapest_deterministic_and_savings_correct():
    """并列最低价（永辉可乐×1：阿里=京东=16.90）→ 稳定取其一，节省额按最高价算。"""
    client = _client()
    uid = _coke_unit_id(client)
    d = client.get("/compare", params={"unit_id": uid, "qty": 1}).json()
    finals = {p["platform"]: p["final_price"] for p in d["platforms"]}
    assert finals["阿里闪购"] == finals["京东"] == 1690
    assert d["cheapest"] in ("阿里闪购", "京东")
    assert d["savings_vs_max"] == finals["美团"] - 1690


def test_api_compare_result_ordering():
    """返回按到手价升序、不可下单排最后。"""
    client = _client()
    res = client.get("/search", params={"q": "瑞幸"}).json()["results"]
    d = client.get("/compare", params={"unit_id": res[0]["id"], "qty": 1}).json()
    plats = d["platforms"]
    orderables = [p for p in plats if p["orderable"]]
    assert plats[: len(orderables)] == orderables, "可下单的必须排在前面"
    finals = [p["final_price"] for p in orderables]
    assert finals == sorted(finals), "可下单部分必须按到手价升序"
    assert plats[-1]["orderable"] is False, "瑞幸×1 美团应被起送拦截且排最后"
