"""匹配引擎与接口测试。"""
from app.matching import build_units, search_units
from app.models import Listing


def _l(platform, brand, name, spec, barcode=None):
    return Listing(platform=platform, brand=brand, name=name, spec=spec, type="bottled",
                   list_price=1000, sale_price=1000, barcode=barcode)


def test_bottled_matched_by_barcode_across_platforms():
    listings = [
        _l("阿里闪购", "可口可乐", "经典可乐", "330ml×6罐", "690111"),
        _l("京东", "可口可乐", "Coca-Cola 汽水", "330ml×6罐", "690111"),  # 名称不同但条码同
        _l("美团", "可口可乐", "可口可乐", "330ml×6罐", "690111"),
    ]
    units = build_units(listings)
    assert len(units) == 1                     # 三条归为一个可比单元
    assert len(units[0].listings) == 3


def test_made_matched_by_brand_name_spec():
    listings = [
        _l("阿里闪购", "喜茶", "多肉葡萄", "大杯/正常糖/去冰"),
        _l("美团", "喜茶", "多肉葡萄", "大杯 正常糖 去冰"),  # 空格差异，归一化后一致
    ]
    units = build_units(listings)
    assert len(units) == 1
    assert len(units[0].listings) == 2


def test_different_products_not_merged():
    listings = [
        _l("京东", "农夫山泉", "天然水", "550ml×12瓶", "690222"),
        _l("京东", "元气森林", "白桃气泡水", "480ml×6瓶", "690333"),
    ]
    units = build_units(listings)
    assert len(units) == 2


def test_search_filters_by_keyword():
    listings = [
        _l("京东", "可口可乐", "经典可乐", "330ml×6罐", "690111"),
        _l("京东", "农夫山泉", "天然水", "550ml×12瓶", "690222"),
    ]
    units = build_units(listings)
    assert len(search_units(units, "可乐")) == 1
    assert len(search_units(units, "")) == 2       # 空查询返回全部


def test_api_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"

    results = client.get("/search", params={"q": "可乐"}).json()["results"]
    assert results, "应能搜到可乐"
    unit_id = results[0]["id"]

    cmp = client.get("/compare", params={"unit_id": unit_id, "qty": 1}).json()
    assert cmp["cheapest"] in ("阿里闪购", "京东", "美团")
    assert len(cmp["platforms"]) == 3
