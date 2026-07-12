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
    results = client.get("/search", params={"q": "可乐", "limit": 100}).json()["results"]
    # 同一条码的 330ml×6罐 可乐在永辉与罗森必须是两个独立可比单元
    assert {"永辉超市(朝阳店)", "罗森便利店(建国路店)"} <= {r["merchant"] for r in results}
    assert all("merchant" in r for r in results)


def test_api_compare_single_merchant_only():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    results = client.get("/search", params={"q": "可乐", "limit": 100}).json()["results"]
    assert results
    for r in results:
        cmp = client.get("/compare", params={"unit_id": r["id"]}).json()
        merchants = {p["merchant"] for p in cmp["platforms"]}
        assert len(merchants) == 1, "比价结果必须来自同一商户"
        assert cmp["beverage"]["merchant"] in merchants


def test_api_search_pagination():
    """分页：limit/offset 生效、total 稳定、翻页不重不漏。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    p1 = client.get("/search", params={"q": "", "limit": 10, "offset": 0}).json()
    p2 = client.get("/search", params={"q": "", "limit": 10, "offset": 10}).json()
    assert p1["total"] == p2["total"] > 20, "全库浏览应远超一页"
    assert p1["count"] == 10 and p2["count"] == 10
    ids1 = {r["id"] for r in p1["results"]}
    ids2 = {r["id"] for r in p2["results"]}
    assert not ids1 & ids2, "翻页结果不得重复"


def test_api_search_relevance_brand_first():
    """相关度：品牌前缀命中排在商户名命中之前。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    results = client.get("/search", params={"q": "星巴克", "limit": 20}).json()["results"]
    assert results, "全库应能搜到星巴克"
    assert all("星巴克" in r["brand"] or "星巴克" in r["merchant"] for r in results)
    assert "星巴克" in results[0]["brand"], "品牌命中应排最前"


def test_api_paging_exhaustion_no_overlap_no_loss():
    """「加载更多」计数依赖的后端契约：带关键词翻页到底，
    不重、不漏、各页 total 恒定、累计数恰好等于 total。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    seen, offset, total = [], 0, None
    while True:
        d = client.get("/search", params={"q": "茶", "limit": 20, "offset": offset}).json()
        if total is None:
            total = d["total"]
        assert d["total"] == total, "翻页过程中 total 必须恒定"
        if d["count"] == 0:
            break
        ids = [r["id"] for r in d["results"]]
        assert not set(ids) & set(seen), "页间出现重复条目"
        seen.extend(ids)
        offset += d["count"]
        assert offset <= total, "累计返回数不得超过 total"
    assert len(seen) == total, f"翻页到底应恰好取回全部：{len(seen)} != {total}"


def test_api_offset_beyond_total_returns_empty():
    """偏移越过总数（前端竞态可能产生的请求）→ 空页 + total 不受影响。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    total = client.get("/search", params={"q": "茶", "limit": 1}).json()["total"]
    d = client.get("/search", params={"q": "茶", "limit": 20, "offset": total + 100}).json()
    assert d["count"] == 0 and d["results"] == []
    assert d["total"] == total


def test_api_search_full_catalog_size():
    """全商户产品库规模：单元数应达到目录级别（>60），覆盖多家商户。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    h = client.get("/health").json()
    assert h["units"] > 60
    assert h["listings"] > 200
    browse = client.get("/search", params={"q": "", "limit": 100}).json()
    merchants = {r["merchant"] for r in browse["results"]}
    assert len(merchants) >= 8, "首页浏览应覆盖多家商户"


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
