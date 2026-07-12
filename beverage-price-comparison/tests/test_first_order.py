"""每日首单券测试：引擎逻辑 + API 参数 + 比价结论影响。"""
from fastapi.testclient import TestClient

from app.models import DeliveryPolicy, Listing, Promotion
from app.pricing import compute_price

DELIV = DeliveryPolicy(platform="测试", base_fee=500, free_over=3900)
FO = Promotion(kind="首单券", desc="每日首单减4", value=400, threshold=1000)


def _listing(sale_price, promotions=None):
    return Listing(
        platform="测试", merchant="测试商户", brand="B", name="N", spec="S", type="bottled",
        list_price=sale_price, sale_price=sale_price, promotions=promotions or [],
    )


# ---- 引擎 -----------------------------------------------------------------

def test_first_order_coupon_applied():
    r = compute_price(_listing(1500), DELIV, include_delivery=False, first_order_coupon=FO)
    assert r.discount_total == 400
    assert r.final_price == 1100
    assert any("首单" in l.label for l in r.lines)


def test_first_order_coupon_absent_by_default():
    r = compute_price(_listing(1500), DELIV, include_delivery=False)
    assert r.discount_total == 0
    assert not any("首单" in l.label for l in r.lines)


def test_first_order_coupon_below_threshold_not_applied():
    """门槛边界：应付 999 < 门槛 1000 → 不生效；恰好 1000 → 生效。"""
    r_no = compute_price(_listing(999), DELIV, include_delivery=False, first_order_coupon=FO)
    r_ok = compute_price(_listing(1000), DELIV, include_delivery=False, first_order_coupon=FO)
    assert r_no.discount_total == 0
    assert r_ok.discount_total == 400


def test_first_order_applies_after_store_promos():
    """首单券排在店铺优惠之后：门槛按扣减后的应付判断。"""
    store = Promotion(kind="满减", desc="满10减2", value=200, threshold=1000)
    # 1100 -200(满减) = 900 < 首单券门槛1000 → 首单券不生效
    r = compute_price(_listing(1100, [store]), DELIV, include_delivery=False, first_order_coupon=FO)
    assert r.discount_total == 200
    assert r.final_price == 900


def test_first_order_coupon_capped_never_negative():
    fo = Promotion(kind="首单券", desc="首单减20", value=2000, threshold=0)
    r = compute_price(_listing(500), DELIV, include_delivery=False, first_order_coupon=fo)
    assert r.final_price == 0


# ---- API ------------------------------------------------------------------

def _client():
    from app.main import app
    return TestClient(app)


def _coke(client):
    res = client.get("/search", params={"q": "永辉"}).json()["results"]
    return next(r["id"] for r in res if "可乐" in r["name"])


def test_api_first_order_default_off():
    """不传 first_order → 结果与既有基线一致（S1: 阿里1690）。"""
    c = _client()
    d = c.get("/compare", params={"unit_id": _coke(c), "qty": 1}).json()
    assert d["first_order"] == []
    assert d["cheapest"] == "阿里闪购"
    best = next(p for p in d["platforms"] if p["platform"] == "阿里闪购")
    assert best["final_price"] == 1690


def test_api_first_order_all_platforms_s8():
    """S8：首单券全开×1 → 阿里1290 最优；美团券因门槛1500未达不生效。"""
    c = _client()
    d = c.get("/compare", params={
        "unit_id": _coke(c), "qty": 1, "first_order": "阿里闪购,京东,美团"}).json()
    finals = {p["platform"]: p["final_price"] for p in d["platforms"]}
    assert d["cheapest"] == "阿里闪购" and finals["阿里闪购"] == 1290
    assert finals["京东"] == 1390
    assert finals["美团"] == 1950  # 首单券未达门槛，价格不变
    mt = next(p for p in d["platforms"] if p["platform"] == "美团")
    assert not any("首单" in b["label"] for b in mt["breakdown"])


def test_api_first_order_flips_winner_s9():
    """S9：×2 后美团首单券达门槛生效 → 美团2175 反超为最优。"""
    c = _client()
    d = c.get("/compare", params={
        "unit_id": _coke(c), "qty": 2, "first_order": "阿里闪购,京东,美团"}).json()
    assert d["cheapest"] == "美团"
    finals = {p["platform"]: p["final_price"] for p in d["platforms"]}
    assert finals["美团"] == 2175
    mt = next(p for p in d["platforms"] if p["platform"] == "美团")
    assert any("首单" in b["label"] for b in mt["breakdown"])


def test_api_first_order_single_platform_and_unknown_ignored():
    """只勾单个平台只影响该平台；未知平台名安全忽略。"""
    c = _client()
    d = c.get("/compare", params={
        "unit_id": _coke(c), "qty": 1, "first_order": "京东, 不存在的平台"}).json()
    finals = {p["platform"]: p["final_price"] for p in d["platforms"]}
    assert finals["京东"] == 1390       # 1290-100补贴-300首单+500配送
    assert finals["阿里闪购"] == 1690   # 未勾选，不变
    assert finals["美团"] == 1950


def test_api_two_entry_pages_served():
    """两个界面入口：/ 客户界面，/test 测试控制台。"""
    c = _client()
    home = c.get("/")
    test = c.get("/test")
    assert home.status_code == 200 and "每日首单券" in home.text
    assert test.status_code == 200 and "测试与报表控制台" in test.text
