"""商户发现 API（/discover）测试：模糊商户搜索 + 商户上限 20 + 商品分页 100。"""
from fastapi.testclient import TestClient

import geo_data
from app.main import app, _units

client = TestClient(app)


def _get(**params):
    return client.get("/api/discover", params=params).json()


# ---- 商户模糊搜索 -----------------------------------------------------------

def test_fuzzy_merchant_match():
    """「便利」→ 罗森便利店 + 便利蜂。"""
    d = _get(q="便利")
    names = {m["merchant"] for m in d["merchants"]}
    assert "罗森便利店(建国路店)" in names
    assert "便利蜂(中关村店)" in names


def test_empty_query_returns_all_merchants_capped():
    """空查询 → 全部 16 商户（<20 上限，全返回）；商品扁平列表可分页。"""
    d = _get()
    assert d["merchant_total"] == 16
    assert d["merchant_count"] == 16
    assert d["product_total"] == len(_units) == 116


# ---- 商户上限 20 ------------------------------------------------------------

def test_merchant_limit_default_20():
    """默认商户上限为 20；当前库仅 16 家，故全返回但 limit 字段为 20。"""
    d = _get()
    assert d["merchant_limit"] == 20
    assert d["merchant_count"] <= 20


def test_merchant_limit_caps_and_reports_total():
    """人为设小上限 → 只返回上限数量，但 merchant_total 反映真实命中数。"""
    d = _get(merchant_limit=3)
    assert d["merchant_count"] == 3
    assert d["merchant_total"] == 16
    # 商品仅来自被展示的 3 家商户
    shown = {m["merchant"] for m in d["merchants"]}
    assert {p["merchant"] for p in d["products"]} <= shown


# ---- 商品分页 100 -----------------------------------------------------------

def test_product_pagination_default_100():
    """默认每页 100 商品；116 总数 → 首页 100，次页 16，不重不漏。"""
    p1 = _get(product_offset=0)
    assert p1["product_total"] == 116
    assert p1["product_count"] == 100
    p2 = _get(product_offset=100)
    assert p2["product_count"] == 16
    ids1 = {x["id"] for x in p1["products"]}
    ids2 = {x["id"] for x in p2["products"]}
    assert not ids1 & ids2                       # 翻页不重复
    assert len(ids1 | ids2) == 116               # 合并覆盖全部


def test_product_limit_custom():
    d = _get(product_limit=10)
    assert d["product_count"] == 10
    assert d["product_total"] == 116


def test_product_offset_beyond_total_empty():
    d = _get(product_offset=999)
    assert d["product_count"] == 0 and d["products"] == []
    assert d["product_total"] == 116


# ---- 每个商品可直接比价 -----------------------------------------------------

def test_products_carry_merchant_and_are_comparable():
    d = _get(q="蜜雪冰城")
    assert d["merchant_count"] == 1
    for p in d["products"]:
        assert p["merchant"] == "蜜雪冰城(五道口店)"
        resp = client.get("/compare", params={"unit_id": p["id"]})
        assert resp.status_code == 200


# ---- GPS 网格过滤 + 排名 -----------------------------------------------------

def test_grid_filter_and_ranking():
    """带 grid：只返回网格内商户、按排名分降序、商品仅来自这些商户。"""
    d = _get(grid="wangjing")
    assert d["grid"]["grid_id"] == "wangjing"
    wangjing = {m for m, g in geo_data.MERCHANT_GEO.items() if g[2] == "wangjing"}
    got = {m["merchant"] for m in d["merchants"]}
    assert got <= wangjing
    scores = [m["rank"]["score"] for m in d["merchants"]]
    assert scores == sorted(scores, reverse=True)
    assert {p["merchant"] for p in d["products"]} <= wangjing


def test_grid_and_fuzzy_combined():
    """望京网格 + 模糊「瑞幸」→ 命中瑞幸望京店。"""
    d = _get(q="瑞幸", grid="wangjing")
    assert d["merchant_count"] == 1
    assert d["merchants"][0]["merchant"] == "瑞幸咖啡(望京店)"


def test_unknown_grid_400():
    assert client.get("/api/discover", params={"grid": "moon"}).status_code == 400


# ---- 界面入口 ---------------------------------------------------------------

def test_discover_page_served():
    r = client.get("/discover")
    assert r.status_code == 200
    assert "商户发现" in r.text or "discover" in r.text.lower()
