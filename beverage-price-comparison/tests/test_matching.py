"""匹配引擎与接口测试。核心覆盖「同商户」比价约束。"""
from app.matching import build_units, search_units
from app.models import Listing


def _l(platform, merchant, brand, name, spec, barcode=None):
    return Listing(platform=platform, merchant=merchant, brand=brand, name=name,
                   spec=spec, type="bottled", list_price=1000, sale_price=1000,
                   barcode=barcode)


# ---- 商户约束（本次重构核心）--------------------------------------------

def test_same_merchant_same_product_merged_across_platforms():
    """同一商户 + 同一条码，跨三平台 → 归为一个可比单元。"""
    listings = [
        _l("阿里闪购", "永辉超市(朝阳店)", "可口可乐", "经典可乐", "330ml×6罐", "690111"),
        _l("京东", "永辉超市(朝阳店)", "可口可乐", "Coca-Cola 汽水", "330ml×6罐", "690111"),
        _l("美团", "永辉超市(朝阳店)", "可口可乐", "可口可乐", "330ml×6罐", "690111"),
    ]
    units = build_units(listings)
    assert len(units) == 1
    assert len(units[0].listings) == 3
    assert units[0].merchant == "永辉超市(朝阳店)"


def test_same_product_different_merchant_not_merged():
    """同一条码但商户不同 → 必须拆成两个独立单元，互不比价。"""
    listings = [
        _l("阿里闪购", "永辉超市(朝阳店)", "可口可乐", "可乐", "330ml×6罐", "690111"),
        _l("美团", "永辉超市(朝阳店)", "可口可乐", "可乐", "330ml×6罐", "690111"),
        _l("阿里闪购", "罗森便利店(建国路店)", "可口可乐", "可乐", "330ml×6罐", "690111"),
        _l("美团", "罗森便利店(建国路店)", "可口可乐", "可乐", "330ml×6罐", "690111"),
    ]
    units = build_units(listings)
    assert len(units) == 2
    merchants = {u.merchant for u in units}
    assert merchants == {"永辉超市(朝阳店)", "罗森便利店(建国路店)"}


def test_every_unit_is_single_merchant():
    """任何单元内的所有条目商户必须一致（用真实种子数据全量校验）。"""
    from app.main import _units
    for unit in _units:
        merchants = {l.merchant for l in unit.listings}
        assert len(merchants) == 1, f"单元 {unit.name} 跨商户: {merchants}"
        assert unit.merchant in merchants


def test_made_drink_same_merchant_matched_despite_spec_format():
    """现制饮品：同商户、规格写法不同（/、空格）→ 仍归为一个单元。"""
    listings = [
        _l("阿里闪购", "喜茶(国贸店)", "喜茶", "多肉葡萄", "大杯/正常糖/去冰"),
        _l("美团", "喜茶(国贸店)", "喜茶", "多肉葡萄", "大杯 正常糖 去冰"),
    ]
    units = build_units(listings)
    assert len(units) == 1
    assert len(units[0].listings) == 2


def test_made_drink_different_merchant_not_merged():
    """现制饮品：同品牌同款但不同门店 → 两个独立单元。"""
    listings = [
        _l("阿里闪购", "喜茶(国贸店)", "喜茶", "多肉葡萄", "大杯"),
        _l("美团", "喜茶(三里屯店)", "喜茶", "多肉葡萄", "大杯"),
    ]
    units = build_units(listings)
    assert len(units) == 2


# ---- 基础匹配 -----------------------------------------------------------

def test_different_products_not_merged():
    listings = [
        _l("京东", "永辉超市(朝阳店)", "农夫山泉", "天然水", "550ml×12瓶", "690222"),
        _l("京东", "永辉超市(朝阳店)", "元气森林", "白桃气泡水", "480ml×6瓶", "690333"),
    ]
    units = build_units(listings)
    assert len(units) == 2


def test_search_filters_by_keyword_and_merchant():
    listings = [
        _l("京东", "永辉超市(朝阳店)", "可口可乐", "经典可乐", "330ml×6罐", "690111"),
        _l("京东", "罗森便利店(建国路店)", "农夫山泉", "天然水", "550ml×12瓶", "690222"),
    ]
    units = build_units(listings)
    assert len(search_units(units, "可乐")) == 1
    assert len(search_units(units, "罗森")) == 1     # 商户名也可搜
    assert len(search_units(units, "")) == 2


# ---- 接口 ---------------------------------------------------------------

def test_api_search_returns_merchant():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    results = client.get("/search", params={"q": "可乐"}).json()["results"]
    assert len(results) == 2, "永辉与罗森的可乐应是两个独立可比单元"
    assert {r["merchant"] for r in results} == {"永辉超市(朝阳店)", "罗森便利店(建国路店)"}


def test_api_compare_single_merchant_only():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    results = client.get("/search", params={"q": "可乐"}).json()["results"]
    for r in results:
        cmp = client.get("/compare", params={"unit_id": r["id"]}).json()
        merchants = {p["merchant"] for p in cmp["platforms"]}
        assert len(merchants) == 1, "比价结果必须来自同一商户"
        assert cmp["beverage"]["merchant"] in merchants


def test_api_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"

    results = client.get("/search", params={"q": "永辉"}).json()["results"]
    assert results, "应能按商户名搜到永辉的商品"
    unit_id = results[0]["id"]

    cmp = client.get("/compare", params={"unit_id": unit_id, "qty": 1}).json()
    assert cmp["cheapest"] in ("阿里闪购", "京东", "美团")
