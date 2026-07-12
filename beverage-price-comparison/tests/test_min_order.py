"""起送价专项测试（BUG-002 修复验证）。

背景：起送价在现实中是「商户(门店) × 平台」级属性（各平台商家自设、逐店
不同），此前误建为平台级常量（美团统一 ¥20），导致瑞幸美团门店不足 20 元
被错误拦截——已有证据表明瑞幸美团外卖低于 ¥20 可正常下单。

修复：STORE_MIN_ORDER 以 (商户, 平台) 为键，未配置默认 0。
本文件为该规则的专项用例，防止回归。
"""
from fastapi.testclient import TestClient

import seed_data


def _client():
    from app.main import app
    return TestClient(app)


def _unit(client, q, merchant):
    res = client.get("/search", params={"q": q, "limit": 100}).json()["results"]
    return next(r for r in res if merchant in r["merchant"])


def _platform(cmp_result, name):
    return next(p for p in cmp_result["platforms"] if p["platform"] == name)


# ---- 核心修复：瑞幸美团不足 20 元可下单 ------------------------------------

def test_luckin_meituan_under_20_orderable():
    """瑞幸生椰拿铁×1（美团小计 ¥17.80 < ¥20）→ 必须可下单。"""
    c = _client()
    d = c.get("/compare", params={"unit_id": _unit(c, "瑞幸", "瑞幸")["id"], "qty": 1}).json()
    mt = _platform(d, "美团")
    assert mt["orderable"] is True, "瑞幸美团不足20元被错误拦截（BUG-002 回归）"
    assert mt["note"] == ""
    assert mt["final_price"] == 1780  # 17.80 − 券5(满15) + 配送5 = 17.80


def test_luckin_meituan_becomes_cheapest_after_fix():
    """修复后美团 ¥17.80 应成为瑞幸×1 的最优平台（此前被拦截让位于阿里）。"""
    c = _client()
    d = c.get("/compare", params={"unit_id": _unit(c, "瑞幸", "瑞幸")["id"], "qty": 1}).json()
    assert d["cheapest"] == "美团"
    assert d["savings_vs_max"] == 1990 - 1780


def test_luckin_all_platforms_no_min_order():
    """瑞幸未配置任何起送价 → 三平台任意小额均可下单。"""
    assert not any(m == "瑞幸咖啡(望京店)" for (m, _p) in seed_data.STORE_MIN_ORDER)
    c = _client()
    d = c.get("/compare", params={"unit_id": _unit(c, "瑞幸", "瑞幸")["id"], "qty": 1}).json()
    assert all(p["orderable"] for p in d["platforms"])


# ---- 起送价必须是商户级而非平台级 ------------------------------------------

def test_min_order_is_merchant_level_not_platform_level():
    """同为美团：喜茶(配置¥26)×1 被拦截，瑞幸(未配置)更低小计却可下单——
    证明起送价按商户区分，不存在平台统一门槛。"""
    c = _client()
    xicha = c.get("/compare", params={"unit_id": _unit(c, "多肉葡萄", "喜茶")["id"], "qty": 1}).json()
    luckin = c.get("/compare", params={"unit_id": _unit(c, "瑞幸", "瑞幸")["id"], "qty": 1}).json()
    xicha_mt = _platform(xicha, "美团")
    luckin_mt = _platform(luckin, "美团")
    assert xicha_mt["orderable"] is False and "起送" in xicha_mt["note"]
    assert luckin_mt["orderable"] is True
    assert luckin_mt["subtotal"] < xicha_mt["subtotal"], "更低小计可下单，唯一解释是商户级门槛"


def test_min_order_blocked_store_excluded_from_cheapest():
    """被起送拦截的平台不得参与最优评选：喜茶×1 最优应为阿里闪购。"""
    c = _client()
    d = c.get("/compare", params={"unit_id": _unit(c, "多肉葡萄", "喜茶")["id"], "qty": 1}).json()
    assert d["cheapest"] == "阿里闪购"
    assert _platform(d, "阿里闪购")["final_price"] == 2600


def test_min_order_unblocks_by_quantity():
    """喜茶×2 美团小计 ¥50 ≥ ¥26 → 恢复可下单并因满减+免配成为最优。"""
    c = _client()
    d = c.get("/compare", params={"unit_id": _unit(c, "多肉葡萄", "喜茶")["id"], "qty": 2}).json()
    mt = _platform(d, "美团")
    assert mt["orderable"] is True
    assert d["cheapest"] == "美团"
    assert mt["final_price"] == 4600  # 50.00 − 满25减4 + 免配送(≥39)


def test_unconfigured_stores_default_zero():
    """未配置起送价的门店（含商超类）一律默认 0：永辉美团小额可下单。"""
    c = _client()
    d = c.get("/compare", params={"unit_id": _unit(c, "可乐", "永辉")["id"], "qty": 1}).json()
    assert all(p["orderable"] for p in d["platforms"])