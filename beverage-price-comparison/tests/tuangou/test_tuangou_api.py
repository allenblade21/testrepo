"""团购 API（G-R1）：restaurants / search / compare 正常返回、分页、人数筛选。"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


# ---- restaurants -----------------------------------------------------------

def test_restaurants_list_all():
    c = _client()
    d = c.get("/api/tuangou/restaurants").json()
    assert d["count"] == 3
    # 按评分降序
    ratings = [r["rating"] for r in d["restaurants"]]
    assert ratings == sorted(ratings, reverse=True)


def test_restaurants_filter_by_grid():
    c = _client()
    d = c.get("/api/tuangou/restaurants", params={"grid": "wangjing"}).json()
    assert all(r["grid_id"] == "wangjing" for r in d["restaurants"])
    assert d["grid"]["name"] == "望京商圈"


def test_restaurants_unknown_grid_400():
    c = _client()
    assert c.get("/api/tuangou/restaurants", params={"grid": "nowhere"}).status_code == 400


def test_restaurants_filter_by_cuisine():
    c = _client()
    d = c.get("/api/tuangou/restaurants", params={"cuisine": "火锅"}).json()
    assert d["count"] == 1
    assert d["restaurants"][0]["brand"] == "海底捞"


def test_restaurants_filter_by_party():
    """人数=2 只有海底捞双人套餐覆盖；人数=4 三家都有。"""
    c = _client()
    d2 = c.get("/api/tuangou/restaurants", params={"party": 2}).json()
    assert {r["id"] for r in d2["restaurants"]} == {"r_haidilao_wj"}
    d4 = c.get("/api/tuangou/restaurants", params={"party": 4}).json()
    assert d4["count"] == 3


# ---- search ----------------------------------------------------------------

def test_search_all_units():
    c = _client()
    d = c.get("/api/tuangou/search").json()
    assert d["total"] == 4          # 4 个可比单元
    assert d["count"] == 4


def test_search_by_keyword():
    c = _client()
    d = c.get("/api/tuangou/search", params={"q": "烤串"}).json()
    assert d["total"] == 1
    assert d["results"][0]["restaurant"]["brand"] == "丰茂烤串"


def test_search_party_filter():
    """人数=4 覆盖 3 个单元（3-5 / 4-4 / 3-4），排除双人 2-2。"""
    c = _client()
    d = c.get("/api/tuangou/search", params={"party": 4}).json()
    assert d["total"] == 3


def test_search_pagination():
    c = _client()
    d = c.get("/api/tuangou/search", params={"limit": 2, "offset": 0}).json()
    assert d["count"] == 2 and d["total"] == 4
    d2 = c.get("/api/tuangou/search", params={"limit": 2, "offset": 2}).json()
    assert d2["count"] == 2
    assert {u["id"] for u in d["results"]} & {u["id"] for u in d2["results"]} == set()


def test_search_unit_shape():
    """单元含门店信息、人数档、置信度、平台、套餐列表。"""
    c = _client()
    u = c.get("/api/tuangou/search").json()["results"][0]
    assert {"id", "restaurant", "party_size", "match_confidence", "platforms", "deals"} <= u.keys()
    assert u["match_confidence"] == "单平台"    # G-R1 单平台


# ---- compare ---------------------------------------------------------------

def _unit_id(c, restaurant_id, party):
    res = c.get("/api/tuangou/search").json()["results"]
    return next(u["id"] for u in res
               if u["restaurant"]["id"] == restaurant_id and u["party_size"] == party)


def test_compare_basic():
    c = _client()
    uid = _unit_id(c, "r_haidilao_wj", [3, 5])
    d = c.post("/api/tuangou/compare", json={"unit_id": uid}).json()
    plat = d["platforms"][0]
    assert plat["final_price"] == 36800
    assert plat["per_capita_price"] == 9200
    assert d["cheapest"] == "美团点评"
    assert plat["deeplink"].startswith("https://")


def test_compare_with_party_size():
    c = _client()
    uid = _unit_id(c, "r_fengmao_zgc", [3, 4])
    d = c.post("/api/tuangou/compare", json={"unit_id": uid, "party_size": 4}).json()
    assert d["party_used"] == 4
    assert d["platforms"][0]["per_capita_price"] == 4725


def test_compare_unknown_unit_404():
    c = _client()
    assert c.post("/api/tuangou/compare", json={"unit_id": "nope"}).status_code == 404


def test_compare_missing_unit_id_400():
    c = _client()
    assert c.post("/api/tuangou/compare", json={}).status_code == 400


def test_compare_includes_usage_rule():
    """使用规则透明：比价结果带结构化 usage_rule。"""
    c = _client()
    uid = _unit_id(c, "r_xibei_gm", [4, 4])
    d = c.post("/api/tuangou/compare", json={"unit_id": uid}).json()
    rule = d["platforms"][0]["usage_rule"]
    assert rule["need_reserve"] is True
    assert rule["extra_fee_cents"] == 5000
