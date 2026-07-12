"""聚合 API（/merchants）测试：按商户名聚合商品名列表。"""
from fastapi.testclient import TestClient

from app.main import app, _units

client = TestClient(app)


def _get(q=""):
    return client.get("/merchants", params={"q": q}).json()


def test_exact_merchant_returns_all_its_products():
    """搜「永辉」→ 命中 1 家商户，返回其全部 3 个商品名（罗森的同款可乐不得混入）。"""
    d = _get("永辉")
    assert d["count"] == 1
    g = d["merchants"][0]
    assert g["merchant"] == "永辉超市(朝阳店)"
    assert g["product_count"] == 3
    assert {p["name"] for p in g["products"]} == {
        "可口可乐 经典可乐 330ml×6罐",
        "农夫山泉 饮用天然水 550ml×12瓶",
        "元气森林 白桃味苏打气泡水 480ml×6瓶",
    }


def test_partial_keyword_matches_multiple_merchants():
    """模糊词「便利」→ 罗森便利店 + 便利蜂 两家都命中。"""
    d = _get("便利")
    merchants = {g["merchant"] for g in d["merchants"]}
    assert "罗森便利店(建国路店)" in merchants
    assert "便利蜂(中关村店)" in merchants
    assert d["count"] == 2


def test_empty_query_returns_all_merchants_all_products():
    """空关键词 → 全部 16 家商户，商品总数等于全库单元数。"""
    d = _get("")
    assert d["count"] == 16
    total_products = sum(g["product_count"] for g in d["merchants"])
    assert total_products == len(_units) == 116


def test_no_cross_merchant_leakage():
    """每组内的商品必须全部属于该商户（用比价接口回查验证）。"""
    d = _get("罗森")
    assert d["count"] == 1
    g = d["merchants"][0]
    for p in g["products"]:
        cmp = client.get("/compare", params={"unit_id": p["id"]}).json()
        assert cmp["beverage"]["merchant"] == g["merchant"]


def test_products_are_directly_comparable():
    """聚合返回的每个商品 id 都能直接进入比价（界面点击链路）。"""
    d = _get("蜜雪冰城")
    assert d["count"] == 1
    for p in d["merchants"][0]["products"]:
        resp = client.get("/compare", params={"unit_id": p["id"]})
        assert resp.status_code == 200
        assert len(resp.json()["platforms"]) == len(p["platforms"])


def test_unknown_merchant_returns_empty():
    d = _get("不存在的商户名九九九")
    assert d["count"] == 0
    assert d["merchants"] == []


def test_normalization_absorbs_spaces():
    """关键词归一化：「永 辉」也应命中永辉。"""
    d = _get("永 辉")
    assert d["count"] == 1
    assert d["merchants"][0]["merchant"] == "永辉超市(朝阳店)"